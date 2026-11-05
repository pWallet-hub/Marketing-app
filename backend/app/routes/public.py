"""Pages that recipients use without signing in: unsubscribe, and the information form.

Each link carries a signed token (unsubscribe) or a random token whose hash is stored (form). Failed lookups return
the same message whatever the reason, so the endpoints do not reveal which addresses exist.
"""

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from psycopg.types.json import Jsonb

from ..db import connect
from ..mail import hash_token, read_unsubscribe_token

router = APIRouter(prefix="/api/public", tags=["public"])
INVALID = "This link is no longer valid."
FIELDS = ["name", "organisation", "position", "phone", "procurement_contact", "notes"]


class UnsubscribeIn(BaseModel):
    token: str = Field(min_length=10, max_length=500)


class FormIn(BaseModel):
    name: str = Field(default="", max_length=200)
    organisation: str = Field(default="", max_length=200)
    position: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=50)
    procurement_contact: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=2000)


@router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeIn, request: Request):
    settings = request.app.state.settings
    data = read_unsubscribe_token(settings, body.token)
    if data is None:
        raise HTTPException(status_code=400, detail=INVALID)
    purpose = data["p"]
    with connect(settings.database_url) as conn:
        contact = conn.execute("SELECT * FROM contacts WHERE id = %s", (data["c"],)).fetchone()
        if contact is None:
            raise HTTPException(status_code=400, detail=INVALID)
        conn.execute(
            "UPDATE consents SET withdrawn_at = now() WHERE contact_id = %s AND purpose = %s AND withdrawn_at IS NULL",
            (contact["id"], purpose),
        )
        conn.execute(
            "INSERT INTO suppressions (email, purpose, reason) VALUES (lower(%s), %s, 'unsubscribed')"
            " ON CONFLICT (email, purpose) DO NOTHING",
            (contact["email"], purpose),
        )
        if purpose == "marketing":
            conn.execute("UPDATE contacts SET status = 'unsubscribed', updated_at = now() WHERE id = %s", (contact["id"],))
        conn.execute(
            "INSERT INTO audit_log (actor_sub, actor_email, action, target, detail)"
            " VALUES ('public', '', 'consent.unsubscribed', %s, %s)",
            (f"contact:{contact['id']}", Jsonb({"purpose": purpose})),
        )
    return {"ok": True, "purpose": purpose}


def _valid_form_token(conn, token):
    row = conn.execute(
        "SELECT ft.id, ft.contact_id, ft.expires_at, ft.used_at, c.name, c.organisation, c.type, c.email"
        " FROM form_tokens ft JOIN contacts c ON c.id = ft.contact_id WHERE ft.token_hash = %s",
        (hash_token(token),),
    ).fetchone()
    if row is None or row["used_at"] is not None or row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=404, detail=INVALID)
    return row


@router.get("/forms/{token}")
def get_form(token: str, request: Request):
    with connect(request.app.state.settings.database_url) as conn:
        row = _valid_form_token(conn, token)
    return {"name": row["name"], "organisation": row["organisation"], "type": row["type"], "fields": FIELDS}


@router.post("/forms/{token}")
def submit_form(token: str, body: FormIn, request: Request):
    settings = request.app.state.settings
    payload = body.model_dump()
    with connect(settings.database_url) as conn:
        row = _valid_form_token(conn, token)
        used = conn.execute(
            "UPDATE form_tokens SET used_at = now() WHERE id = %s AND used_at IS NULL RETURNING id", (row["id"],)
        ).fetchone()
        if used is None:
            raise HTTPException(status_code=409, detail="This form has already been submitted.")
        contact_id = row["contact_id"]
        conn.execute(
            "UPDATE contacts SET name = CASE WHEN %s <> '' THEN %s ELSE name END,"
            " organisation = CASE WHEN %s <> '' THEN %s ELSE organisation END,"
            " phone = CASE WHEN %s <> '' THEN %s ELSE phone END, updated_at = now() WHERE id = %s",
            (payload["name"], payload["name"], payload["organisation"], payload["organisation"],
             payload["phone"], payload["phone"], contact_id),
        )
        submission = conn.execute(
            "INSERT INTO form_submissions (contact_id, payload) VALUES (%s, %s) RETURNING id",
            (contact_id, Jsonb(payload)),
        ).fetchone()
        contact_email, contact_type = row["email"], row["type"]

    status = _forward(settings, submission["id"], contact_email, contact_type, payload)
    return {"ok": True, "forwarded": status == "forwarded"}


def _forward(settings, submission_id, email, contact_type, payload):
    """Send the submission to the target system when one is configured. A failure is recorded, not hidden."""
    if not settings.form_target_url:
        status = "stored"
    else:
        try:
            response = httpx.post(
                settings.form_target_url,
                json={"email": email, "type": contact_type, "submitted": payload},
                headers={"Authorization": f"Bearer {settings.form_target_token}"},
                timeout=10,
            )
            status = "forwarded" if response.status_code < 300 else f"failed: HTTP {response.status_code}"
        except httpx.HTTPError as error:
            status = f"failed: {error.__class__.__name__}"
    with connect(settings.database_url) as conn:
        conn.execute("UPDATE form_submissions SET forward_status = %s WHERE id = %s", (status, submission_id))
    return status
