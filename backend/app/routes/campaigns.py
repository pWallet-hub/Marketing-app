"""Campaigns, test sends, and the dashboard."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..common import audit, valid_email
from ..db import connect
from ..deps import require_role
from ..mail import MailError, send_email
from ..queue import enqueue
from ..render import render

router = APIRouter(prefix="/api", tags=["campaigns"])
ALL_ROLES = require_role("admin", "member")
ADMIN = require_role("admin")


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    template_id: int
    list_id: int
    purpose: Literal["marketing", "information_request"]


class TestSendIn(BaseModel):
    email: str = Field(max_length=254)


def _campaign(conn, campaign_id):
    row = conn.execute("SELECT * FROM campaigns WHERE id = %s", (campaign_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return row


@router.get("/campaigns")
def list_campaigns(request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        return conn.execute(
            "SELECT c.*, t.name AS template, l.name AS list_name,"
            " (SELECT count(*) FROM sends s WHERE s.campaign_id = c.id) AS recipients"
            " FROM campaigns c JOIN templates t ON t.id = c.template_id"
            " LEFT JOIN lists l ON l.id = c.list_id ORDER BY c.created_at DESC LIMIT 200"
        ).fetchall()


@router.post("/campaigns", status_code=201)
def create_campaign(body: CampaignIn, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        if conn.execute("SELECT 1 FROM templates WHERE id = %s", (body.template_id,)).fetchone() is None:
            raise HTTPException(status_code=422, detail="Template not found")
        if conn.execute("SELECT 1 FROM lists WHERE id = %s", (body.list_id,)).fetchone() is None:
            raise HTTPException(status_code=422, detail="List not found")
        row = conn.execute(
            "INSERT INTO campaigns (name, template_id, list_id, purpose, created_by)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (body.name.strip(), body.template_id, body.list_id, body.purpose, user["email"] or ""),
        ).fetchone()
        audit(conn, user, "campaign.created", f"campaign:{row['id']}", {"purpose": body.purpose})
    return row


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        campaign = _campaign(conn, campaign_id)
        counts = conn.execute(
            "SELECT status, count(*) AS n FROM sends WHERE campaign_id = %s GROUP BY status", (campaign_id,)
        ).fetchall()
        recent = conn.execute(
            "SELECT s.id, s.email, s.status, s.skip_reason, s.error, s.sent_at FROM sends s"
            " WHERE s.campaign_id = %s ORDER BY s.id DESC LIMIT 100",
            (campaign_id,),
        ).fetchall()
    return {**campaign, "counts": {row["status"]: row["n"] for row in counts}, "recent": recent}


@router.post("/campaigns/{campaign_id}/test")
def test_send(campaign_id: int, body: TestSendIn, request: Request, user=Depends(ADMIN)):
    """Send the campaign once to an address you choose, so you can check it before sending to everyone."""
    settings = request.app.state.settings
    if not valid_email(body.email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    if not settings.mail_configured:
        raise HTTPException(status_code=503, detail="Mail is not configured")
    with connect(settings.database_url) as conn:
        campaign = _campaign(conn, campaign_id)
        template = conn.execute("SELECT * FROM templates WHERE id = %s", (campaign["template_id"],)).fetchone()
        audit(conn, user, "campaign.test_sent", f"campaign:{campaign_id}", {"to": body.email})
    values = {"name": "Test Recipient", "organisation": "Test", "email": body.email,
              "unsubscribe_url": "#test-unsubscribe", "form_url": "#test-form"}
    html = render(template["body_html"], values) + '<p style="font-size:12px;color:#666">Test send: no unsubscribe link.</p>'
    try:
        message_id = send_email(
            settings,
            to=body.email,
            subject="[Test] " + render(template["subject"], values, html=False),
            html=html,
            text="Test send from AFS Marketing Mailer.",
            unsubscribe="#test-unsubscribe",
            idempotency_key=f"test-{uuid.uuid4()}",
        )
    except MailError as error:
        raise HTTPException(status_code=502, detail=str(error))
    return {"ok": True, "message_id": message_id}


@router.post("/campaigns/{campaign_id}/send")
def send_campaign(campaign_id: int, request: Request, user=Depends(ADMIN)):
    """Start sending. Recipients are fixed now; the worker sends them. Only drafts can be sent."""
    settings = request.app.state.settings
    if not settings.mail_configured:
        raise HTTPException(status_code=503, detail="Mail is not configured")
    with connect(settings.database_url) as conn:
        campaign = conn.execute("SELECT * FROM campaigns WHERE id = %s FOR UPDATE", (campaign_id,)).fetchone()
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if campaign["status"] != "draft":
            raise HTTPException(status_code=409, detail="This campaign has already been sent")
        contacts = conn.execute(
            "SELECT c.* FROM list_members m JOIN contacts c ON c.id = m.contact_id WHERE m.list_id = %s ORDER BY c.id",
            (campaign["list_id"],),
        ).fetchall()
        if not contacts:
            raise HTTPException(status_code=422, detail="The list has no contacts")
        queued, skipped = enqueue(conn, campaign_id, campaign["purpose"], contacts)
        conn.execute("UPDATE campaigns SET status = 'sending', sent_at = now() WHERE id = %s", (campaign_id,))
        audit(conn, user, "campaign.sent", f"campaign:{campaign_id}", {"queued": queued, "skipped": skipped})
    return {"queued": queued, "skipped": skipped}


@router.get("/dashboard")
def dashboard(request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        by_type = conn.execute("SELECT type, count(*) AS n FROM contacts GROUP BY type").fetchall()
        media = conn.execute(
            "SELECT status, count(*) AS n FROM contacts WHERE type = 'media' GROUP BY status"
        ).fetchall()
        campaigns = conn.execute("SELECT status, count(*) AS n FROM campaigns GROUP BY status").fetchall()
        sends = conn.execute(
            "SELECT status, count(*) AS n FROM sends WHERE created_at > now() - interval '30 days' GROUP BY status"
        ).fetchall()
        queued = conn.execute("SELECT count(*) AS n FROM sends WHERE status = 'queued'").fetchone()["n"]
        suppressed = conn.execute("SELECT count(DISTINCT lower(email)) AS n FROM suppressions").fetchone()["n"]
    return {
        "contacts_by_type": {r["type"]: r["n"] for r in by_type},
        "media_by_status": {r["status"]: r["n"] for r in media},
        "campaigns_by_status": {r["status"]: r["n"] for r in campaigns},
        "sends_last_30_days": {r["status"]: r["n"] for r in sends},
        "queued": queued,
        "suppressed_addresses": suppressed,
    }
