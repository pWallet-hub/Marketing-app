"""The suppression list (do-not-contact), the activity log, and the app's sending settings."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..common import audit, page_params, valid_email
from ..db import connect
from ..deps import require_role

router = APIRouter(prefix="/api", tags=["admin"])
ALL_ROLES = require_role("admin", "member")
ADMIN = require_role("admin")
# An unsubscribe, a complaint or an erasure is the person's own choice, so it cannot be undone here. A bounce or a
# manual block can: the address may have been fixed.
REMOVABLE_REASONS = ("manual", "bounced")


class SuppressionIn(BaseModel):
    email: str = Field(max_length=254)
    purpose: Literal["marketing", "information_request", "all"] = "all"


@router.get("/suppressions")
def list_suppressions(
    request: Request, q: str = "", reason: str = "", limit: int = 50, offset: int = 0, user=Depends(ALL_ROLES)
):
    limit, offset = page_params(limit, offset)
    clauses, params = ["true"], []
    if q:
        clauses.append("s.email ILIKE %s")
        params.append(f"%{q}%")
    if reason:
        clauses.append("s.reason = %s")
        params.append(reason)
    where = " AND ".join(clauses)
    with connect(request.app.state.settings.database_url) as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM suppressions s WHERE {where}", params).fetchone()["n"]
        rows = conn.execute(
            "SELECT s.*, c.id AS contact_id, c.name AS contact_name FROM suppressions s"
            " LEFT JOIN contacts c ON lower(c.email) = lower(s.email)"
            f" WHERE {where} ORDER BY s.created_at DESC LIMIT %s OFFSET %s",
            params + [limit, offset],
        ).fetchall()
        reasons = conn.execute("SELECT reason, count(*) AS n FROM suppressions GROUP BY reason").fetchall()
    for row in rows:
        row["removable"] = row["reason"] in REMOVABLE_REASONS
    return {"total": total, "items": rows, "limit": limit, "offset": offset, "reasons": {r["reason"]: r["n"] for r in reasons}}


@router.post("/suppressions", status_code=201)
def add_suppression(body: SuppressionIn, request: Request, user=Depends(ADMIN)):
    email = body.email.strip().lower()
    if not valid_email(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    with connect(request.app.state.settings.database_url) as conn:
        row = conn.execute(
            "INSERT INTO suppressions (email, purpose, reason) VALUES (%s, %s, 'manual')"
            " ON CONFLICT (email, purpose) DO NOTHING RETURNING *",
            (email, body.purpose),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=409, detail="This address is already blocked for that purpose")
        audit(conn, user, "suppression.added", f"suppression:{row['id']}", {"purpose": body.purpose})
    return row


@router.delete("/suppressions/{suppression_id}")
def remove_suppression(suppression_id: int, request: Request, user=Depends(ADMIN)):
    with connect(request.app.state.settings.database_url) as conn:
        row = conn.execute("SELECT * FROM suppressions WHERE id = %s", (suppression_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Not found")
        if row["reason"] not in REMOVABLE_REASONS:
            raise HTTPException(
                status_code=409,
                detail=f"This address is blocked because of: {row['reason']}. Only the person can reverse that.",
            )
        conn.execute("DELETE FROM suppressions WHERE id = %s", (suppression_id,))
        if row["reason"] == "bounced":
            conn.execute(
                "UPDATE contacts SET status = 'new', updated_at = now() WHERE lower(email) = lower(%s) AND status = 'bounced'",
                (row["email"],),
            )
        audit(conn, user, "suppression.removed", f"suppression:{suppression_id}", {"reason": row["reason"]})
    return {"ok": True}


@router.get("/audit")
def audit_log(request: Request, action: str = "", limit: int = 50, offset: int = 0, user=Depends(ADMIN)):
    limit, offset = page_params(limit, offset)
    where, params = ("WHERE action LIKE %s", [f"{action}%"]) if action else ("", [])
    with connect(request.app.state.settings.database_url) as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM audit_log {where}", params).fetchone()["n"]
        rows = conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY at DESC, id DESC LIMIT %s OFFSET %s", params + [limit, offset]
        ).fetchall()
    return {"total": total, "items": rows, "limit": limit, "offset": offset}


@router.get("/settings")
def sending_settings(request: Request, user=Depends(ALL_ROLES)):
    """What the app sends with. Values are set in the deployment; nothing secret is returned."""
    s = request.app.state.settings
    return {
        "org_name": s.org_name,
        "org_address": s.org_address,
        "org_website": s.org_website,
        "brand_color": s.brand_color,
        "from": f"{s.resend_from_name} <{s.resend_from}>" if s.resend_from else "",
        "mail_configured": s.mail_configured,
        "webhook_configured": bool(s.resend_webhook_secret),
        "blog_accounts_configured": bool(s.biocap_account_url),
        "form_forwarding_configured": bool(s.form_target_url),
        "public_base_url": s.public_base_url,
    }
