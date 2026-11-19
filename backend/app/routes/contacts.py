"""Contacts, consent, CSV import, and media invites."""

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from ..biocap import BlogAccountError, create_blog_account
from ..common import CONTACT_TYPES, PURPOSES, audit, page_params, valid_email
from ..db import connect
from ..deps import current_user, require_role
from ..queue import eligibility, enqueue

router = APIRouter(prefix="/api/contacts", tags=["contacts"])
ALL_ROLES = require_role("admin", "member")
ADMIN = require_role("admin")
MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 5000


class ContactIn(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(default="", max_length=200)
    organisation: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=50)
    type: Literal["media", "partner", "staff"]
    notes: str = Field(default="", max_length=2000)
    marketing_consent_source: str = Field(default="", max_length=300)
    information_consent_source: str = Field(default="", max_length=300)


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    organisation: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)
    type: Literal["media", "partner", "staff"] | None = None


class ConsentIn(BaseModel):
    purpose: Literal["marketing", "information_request"]
    source: str = Field(min_length=3, max_length=300)


class WithdrawIn(BaseModel):
    purpose: Literal["marketing", "information_request"]


class EraseIn(BaseModel):
    # Keep the address on the do-not-contact list so an old import cannot add the person back with consent.
    suppress: bool = True


class ImportIn(BaseModel):
    csv: str = Field(min_length=1)
    type: Literal["media", "partner", "staff"]
    purpose: Literal["marketing", "information_request"] | None = None
    source: str = Field(default="", max_length=300)


def _contact(conn, contact_id):
    row = conn.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return row


def _grant_consent(conn, contact_id, purpose, source):
    """Record consent unless the address is suppressed for that purpose. Returns True when consent was recorded."""
    row = conn.execute(
        "SELECT email FROM contacts WHERE id = %s", (contact_id,)
    ).fetchone()
    suppressed = conn.execute(
        "SELECT 1 FROM suppressions WHERE lower(email) = lower(%s) AND purpose IN (%s, 'all')", (row["email"], purpose)
    ).fetchone()
    if suppressed:
        return False
    conn.execute(
        "INSERT INTO consents (contact_id, purpose, source) VALUES (%s, %s, %s)"
        " ON CONFLICT (contact_id, purpose) WHERE withdrawn_at IS NULL DO NOTHING",
        (contact_id, purpose, source),
    )
    return True


@router.get("")
def list_contacts(
    request: Request,
    q: str = "",
    type: str = "",
    status: str = "",
    consent: str = "",
    list_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    user=Depends(ALL_ROLES),
):
    limit, offset = page_params(limit, offset)
    clauses, params = _filters(q, type, status, consent, list_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect(request.app.state.settings.database_url) as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM contacts {where}", params).fetchone()["n"]
        rows = conn.execute(
            f"SELECT contacts.*, {CONSENT_COLUMNS} FROM contacts {where}"
            " ORDER BY lower(name), id LIMIT %s OFFSET %s",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "items": rows, "limit": limit, "offset": offset}


CONSENT_COLUMNS = (
    "EXISTS (SELECT 1 FROM consents k WHERE k.contact_id = contacts.id AND k.purpose = 'marketing'"
    " AND k.withdrawn_at IS NULL) AS marketing_consent,"
    " EXISTS (SELECT 1 FROM consents k WHERE k.contact_id = contacts.id AND k.purpose = 'information_request'"
    " AND k.withdrawn_at IS NULL) AS information_consent"
)


def _filters(q, type, status, consent, list_id):
    clauses, params = [], []
    if q:
        clauses.append("(email ILIKE %s OR name ILIKE %s OR organisation ILIKE %s)")
        params += [f"%{q}%"] * 3
    if type in CONTACT_TYPES:
        clauses.append("type = %s")
        params.append(type)
    if status:
        clauses.append("status = %s")
        params.append(status)
    if consent in PURPOSES:
        clauses.append(
            "EXISTS (SELECT 1 FROM consents k WHERE k.contact_id = contacts.id AND k.purpose = %s AND k.withdrawn_at IS NULL)"
        )
        params.append(consent)
    if list_id:
        clauses.append("EXISTS (SELECT 1 FROM list_members m WHERE m.contact_id = contacts.id AND m.list_id = %s)")
        params.append(list_id)
    return clauses, params


@router.get("/export")
def export_contacts(
    request: Request, q: str = "", type: str = "", status: str = "", consent: str = "", list_id: int | None = None,
    user=Depends(ADMIN),
):
    """Download the contacts that match the filters as CSV (the same columns the import reads, plus status and consent)."""
    clauses, params = _filters(q, type, status, consent, list_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect(request.app.state.settings.database_url) as conn:
        rows = conn.execute(
            f"SELECT contacts.*, {CONSENT_COLUMNS} FROM contacts {where} ORDER BY lower(name), id", params
        ).fetchall()
        audit(conn, user, "contacts.exported", "", {"count": len(rows)})
    out = io.StringIO()
    columns = ["email", "name", "organisation", "phone", "type", "status", "marketing_consent", "information_consent", "notes", "created_at"]
    writer = csv.writer(out)
    writer.writerow(columns)
    for row in rows:
        # A leading = + - @ would run as a formula when the file is opened in a spreadsheet.
        writer.writerow([_cell(row[column]) for column in columns])
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="afs-contacts.csv"'},
    )


def _cell(value):
    text = "" if value is None else ("yes" if value is True else "no" if value is False else str(value))
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.post("", status_code=201)
def create_contact(body: ContactIn, request: Request, user=Depends(ALL_ROLES)):
    email = body.email.strip()
    if not valid_email(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    with connect(request.app.state.settings.database_url) as conn:
        exists = conn.execute("SELECT id FROM contacts WHERE lower(email) = lower(%s)", (email,)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="A contact with this email already exists")
        row = conn.execute(
            "INSERT INTO contacts (email, name, organisation, phone, type, notes, created_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (email, body.name, body.organisation, body.phone, body.type, body.notes, user["email"] or ""),
        ).fetchone()
        for purpose, source in (
            ("marketing", body.marketing_consent_source.strip()),
            ("information_request", body.information_consent_source.strip()),
        ):
            if source:
                _grant_consent(conn, row["id"], purpose, source)
        audit(conn, user, "contact.created", f"contact:{row['id']}", {"type": body.type})
    return row


@router.get("/{contact_id}")
def get_contact(contact_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        contact = _contact(conn, contact_id)
        consents = conn.execute(
            "SELECT purpose, source, given_at, withdrawn_at FROM consents WHERE contact_id = %s ORDER BY given_at DESC",
            (contact_id,),
        ).fetchall()
        lists = conn.execute(
            "SELECT l.id, l.name FROM list_members m JOIN lists l ON l.id = m.list_id WHERE m.contact_id = %s ORDER BY l.name",
            (contact_id,),
        ).fetchall()
        sends = conn.execute(
            "SELECT s.id, s.campaign_id, c.name AS campaign, s.status, s.skip_reason, s.sent_at, s.opened_at, s.clicked_at"
            " FROM sends s JOIN campaigns c ON c.id = s.campaign_id WHERE s.contact_id = %s ORDER BY s.id DESC LIMIT 50",
            (contact_id,),
        ).fetchall()
        suppressions = conn.execute(
            "SELECT purpose, reason, created_at FROM suppressions WHERE lower(email) = lower(%s)", (contact["email"],)
        ).fetchall()
        activity = conn.execute(
            "SELECT e.type, e.link, e.at, s.campaign_id, c.name AS campaign FROM send_events e"
            " JOIN sends s ON s.id = e.send_id JOIN campaigns c ON c.id = s.campaign_id"
            " WHERE s.contact_id = %s ORDER BY e.at DESC LIMIT 50",
            (contact_id,),
        ).fetchall()
    return {
        **contact,
        "consents": consents,
        "lists": lists,
        "sends": sends,
        "suppressions": suppressions,
        "activity": activity,
    }


@router.patch("/{contact_id}")
def update_contact(contact_id: int, body: ContactUpdate, request: Request, user=Depends(ALL_ROLES)):
    fields = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if not fields:
        raise HTTPException(status_code=422, detail="Nothing to change")
    assignments = ", ".join(f"{key} = %s" for key in fields)
    with connect(request.app.state.settings.database_url) as conn:
        _contact(conn, contact_id)
        row = conn.execute(
            f"UPDATE contacts SET {assignments}, updated_at = now() WHERE id = %s RETURNING *",
            list(fields.values()) + [contact_id],
        ).fetchone()
        audit(conn, user, "contact.updated", f"contact:{contact_id}", {"fields": sorted(fields)})
    return row


@router.post("/{contact_id}/consent", status_code=201)
def grant_consent(contact_id: int, body: ConsentIn, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        _contact(conn, contact_id)
        recorded = _grant_consent(conn, contact_id, body.purpose, body.source.strip())
        if not recorded:
            raise HTTPException(status_code=409, detail="This address has unsubscribed from this purpose")
        audit(conn, user, "consent.granted", f"contact:{contact_id}", {"purpose": body.purpose, "source": body.source})
    return {"ok": True}


@router.post("/{contact_id}/consent/withdraw")
def withdraw_consent(contact_id: int, body: WithdrawIn, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        _contact(conn, contact_id)
        conn.execute(
            "UPDATE consents SET withdrawn_at = now() WHERE contact_id = %s AND purpose = %s AND withdrawn_at IS NULL",
            (contact_id, body.purpose),
        )
        audit(conn, user, "consent.withdrawn", f"contact:{contact_id}", {"purpose": body.purpose})
    return {"ok": True}


@router.post("/{contact_id}/erase")
def erase_contact(contact_id: int, body: EraseIn, request: Request, user=Depends(ADMIN)):
    """Delete a contact and everything held about them (data-protection request).

    Removes the contact, their consents, list memberships, send records, form links and form submissions, and their
    one-person invite campaigns. With `suppress` (the default) only the address is kept, on the suppression list, so
    they are never mailed again. The audit log keeps the action against the contact's number, not their details.
    A Biocap blog account, if one was created, is not removed here; the response returns its id so it can be.
    """
    with connect(request.app.state.settings.database_url) as conn:
        contact = _contact(conn, contact_id)
        if body.suppress:
            conn.execute(
                "INSERT INTO suppressions (email, purpose, reason) VALUES (lower(%s), 'all', 'erased')"
                " ON CONFLICT (email, purpose) DO NOTHING",
                (contact["email"],),
            )
        else:
            conn.execute("DELETE FROM suppressions WHERE lower(email) = lower(%s)", (contact["email"],))
        conn.execute("DELETE FROM campaigns WHERE single_contact_id = %s", (contact_id,))
        conn.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
        audit(
            conn,
            user,
            "contact.erased",
            f"contact:{contact_id}",
            {"type": contact["type"], "suppressed": body.suppress, "blog_account": bool(contact["blog_account_id"])},
        )
    return {"ok": True, "blog_account_id": contact["blog_account_id"]}


@router.post("/import")
def import_contacts(body: ImportIn, request: Request, user=Depends(ADMIN)):
    """Import contacts from CSV text. Needs an `email` column; `name`, `organisation`, `phone`, `notes` are optional.

    If a purpose is given, consent for it is recorded with `source` for every imported contact, so the source must be
    stated: where the people agreed to be contacted.
    """
    if len(body.csv.encode()) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 2 MB")
    if body.purpose and not body.source.strip():
        raise HTTPException(status_code=422, detail="Say where these people agreed to be contacted (source)")
    reader = csv.DictReader(io.StringIO(body.csv))
    if not reader.fieldnames or "email" not in [name.strip().lower() for name in reader.fieldnames]:
        raise HTTPException(status_code=422, detail="The file needs a header row with an email column")
    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]

    created = updated = consent_recorded = consent_skipped = 0
    errors = []
    rows = list(reader)
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(status_code=413, detail=f"Import at most {MAX_IMPORT_ROWS} rows at a time")
    with connect(request.app.state.settings.database_url) as conn:
        for number, raw in enumerate(rows, start=2):
            row = {key: (value or "").strip() for key, value in raw.items() if key}
            email = row.get("email", "")
            if not valid_email(email):
                errors.append({"line": number, "error": "invalid email", "email": email[:254]})
                continue
            result = conn.execute(
                "INSERT INTO contacts (email, name, organisation, phone, notes, type, created_by)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (lower(email)) DO UPDATE SET"
                " name = CASE WHEN EXCLUDED.name <> '' THEN EXCLUDED.name ELSE contacts.name END,"
                " organisation = CASE WHEN EXCLUDED.organisation <> '' THEN EXCLUDED.organisation ELSE contacts.organisation END,"
                " phone = CASE WHEN EXCLUDED.phone <> '' THEN EXCLUDED.phone ELSE contacts.phone END,"
                " notes = CASE WHEN EXCLUDED.notes <> '' THEN EXCLUDED.notes ELSE contacts.notes END,"
                " updated_at = now()"
                " RETURNING id, (xmax = 0) AS inserted",
                (
                    email,
                    row.get("name", ""),
                    row.get("organisation", ""),
                    row.get("phone", ""),
                    row.get("notes", ""),
                    body.type,
                    user["email"] or "",
                ),
            ).fetchone()
            if result["inserted"]:
                created += 1
            else:
                updated += 1
            if body.purpose:
                if _grant_consent(conn, result["id"], body.purpose, body.source.strip()):
                    consent_recorded += 1
                else:
                    consent_skipped += 1
        audit(
            conn,
            user,
            "contacts.imported",
            "",
            {"type": body.type, "created": created, "updated": updated, "errors": len(errors), "purpose": body.purpose},
        )
    return {
        "created": created,
        "updated": updated,
        "consent_recorded": consent_recorded,
        "consent_skipped_suppressed": consent_skipped,
        "errors": errors[:200],
    }


@router.post("/{contact_id}/invite", status_code=201)
def invite_media_contact(contact_id: int, request: Request, template_id: int, user=Depends(ADMIN)):
    """Invite a media contact to join AFS: create their blog account (if configured), then send the invite."""
    settings = request.app.state.settings
    with connect(settings.database_url) as conn:
        contact = _contact(conn, contact_id)
        if contact["type"] != "media":
            raise HTTPException(status_code=422, detail="Only media contacts receive the invite")
        if contact["status"] in ("joined", "unsubscribed", "bounced", "complained"):
            raise HTTPException(status_code=409, detail=f"Cannot invite a contact who is {contact['status']}")
        template = conn.execute("SELECT id FROM templates WHERE id = %s", (template_id,)).fetchone()
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")

        reason = eligibility(conn, contact, "marketing")
        if reason:
            raise HTTPException(status_code=409, detail=f"The invite cannot be sent: {reason}")

        account = {"status": "not_configured"}
        if contact["blog_account_id"] is None:
            try:
                account = create_blog_account(settings, contact["email"], contact["name"])
            except BlogAccountError as error:
                raise HTTPException(status_code=502, detail=f"Blog account could not be created: {error}")
            if account.get("id"):
                conn.execute("UPDATE contacts SET blog_account_id = %s WHERE id = %s", (str(account["id"]), contact_id))

        campaign = conn.execute(
            "INSERT INTO campaigns (name, template_id, single_contact_id, purpose, created_by)"
            " VALUES (%s, %s, %s, 'marketing', %s) RETURNING id",
            (f"Invite: {contact['name'] or contact['email']}", template_id, contact_id, user["email"] or ""),
        ).fetchone()
        queued, skipped = enqueue(conn, campaign["id"], "marketing", [contact])
        if queued:
            conn.execute("UPDATE contacts SET status = 'invited', updated_at = now() WHERE id = %s", (contact_id,))
            conn.execute("UPDATE campaigns SET status = 'sending', sent_at = now() WHERE id = %s", (campaign["id"],))
        audit(
            conn,
            user,
            "media.invited",
            f"contact:{contact_id}",
            {"campaign": campaign["id"], "queued": queued, "skipped": skipped, "blog_account": account["status"]},
        )
    return {"campaign_id": campaign["id"], "queued": queued, "skipped": skipped, "blog_account": account["status"]}
