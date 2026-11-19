"""Campaigns: drafts, editing, test sends, sending now or on a schedule, reports, and the dashboard."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..common import audit, page_params, valid_email
from ..db import connect
from ..deps import require_role
from ..mail import MailError, send_email
from ..queue import PURPOSE_LABELS, campaign_recipients, eligibility, start_campaign
from ..render import html_to_text, render

router = APIRouter(prefix="/api", tags=["campaigns"])
ALL_ROLES = require_role("admin", "member")
ADMIN = require_role("admin")
EDITABLE = ("draft", "scheduled")
SAMPLE = {"name": "Example Person", "organisation": "Example Media", "email": "person@example.org"}


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    template_id: int
    list_id: int
    purpose: Literal["marketing", "information_request"]
    reply_to: str = Field(default="", max_length=254)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    template_id: int | None = None
    list_id: int | None = None
    purpose: Literal["marketing", "information_request"] | None = None
    reply_to: str | None = Field(default=None, max_length=254)


class TestSendIn(BaseModel):
    email: str = Field(default="", max_length=254)
    emails: list[str] = Field(default_factory=list, max_length=5)


class ScheduleIn(BaseModel):
    send_at: datetime


def _campaign(conn, campaign_id, lock=False):
    row = conn.execute(
        "SELECT * FROM campaigns WHERE id = %s" + (" FOR UPDATE" if lock else ""), (campaign_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return row


def _check_refs(conn, template_id=None, list_id=None):
    if template_id is not None and conn.execute("SELECT 1 FROM templates WHERE id = %s", (template_id,)).fetchone() is None:
        raise HTTPException(status_code=422, detail="Template not found")
    if list_id is not None and conn.execute("SELECT 1 FROM lists WHERE id = %s", (list_id,)).fetchone() is None:
        raise HTTPException(status_code=422, detail="List not found")


def _check_reply_to(value):
    if value and not valid_email(value.strip()):
        raise HTTPException(status_code=422, detail="Enter a valid reply-to address, or leave it empty")


def _rate(part, whole):
    return round(100 * part / whole, 1) if whole else 0.0


def _stats(conn, campaign_id):
    """Counts and rates in the usual terms: rates are of emails delivered (or sent, before delivery is reported)."""
    row = conn.execute(
        "SELECT count(*) FILTER (WHERE status <> 'skipped') AS recipients,"
        " count(*) FILTER (WHERE status = 'skipped') AS skipped,"
        " count(*) FILTER (WHERE status = 'queued') AS queued,"
        " count(*) FILTER (WHERE sent_at IS NOT NULL) AS sent,"
        " count(*) FILTER (WHERE delivered_at IS NOT NULL OR status = 'delivered') AS delivered,"
        " count(*) FILTER (WHERE status = 'bounced') AS bounced,"
        " count(*) FILTER (WHERE status = 'complained') AS complained,"
        " count(*) FILTER (WHERE status = 'failed') AS failed,"
        " count(*) FILTER (WHERE opened_at IS NOT NULL) AS opened,"
        " count(*) FILTER (WHERE clicked_at IS NOT NULL) AS clicked"
        " FROM sends WHERE campaign_id = %s",
        (campaign_id,),
    ).fetchone()
    unsubscribed = conn.execute(
        "SELECT count(*) AS n FROM audit_log WHERE action = 'consent.unsubscribed' AND target IN"
        " (SELECT 'contact:' || contact_id FROM sends WHERE campaign_id = %s AND sent_at IS NOT NULL)"
        " AND at >= (SELECT sent_at FROM campaigns WHERE id = %s)",
        (campaign_id, campaign_id),
    ).fetchone()["n"]
    stats = dict(row)
    base = stats["delivered"] or stats["sent"]
    stats.update(
        unsubscribed=unsubscribed,
        open_rate=_rate(stats["opened"], base),
        click_rate=_rate(stats["clicked"], base),
        bounce_rate=_rate(stats["bounced"], stats["sent"]),
        unsubscribe_rate=_rate(unsubscribed, base),
    )
    return stats


@router.get("/campaigns")
def list_campaigns(request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        return conn.execute(
            "SELECT c.*, t.name AS template, t.subject, l.name AS list_name,"
            " (SELECT count(*) FROM list_members m WHERE m.list_id = c.list_id) AS list_size,"
            " s.recipients, s.delivered, s.opened, s.clicked"
            " FROM campaigns c JOIN templates t ON t.id = c.template_id"
            " LEFT JOIN lists l ON l.id = c.list_id"
            " LEFT JOIN LATERAL (SELECT count(*) FILTER (WHERE status <> 'skipped') AS recipients,"
            "   count(*) FILTER (WHERE delivered_at IS NOT NULL OR status = 'delivered') AS delivered,"
            "   count(*) FILTER (WHERE opened_at IS NOT NULL) AS opened,"
            "   count(*) FILTER (WHERE clicked_at IS NOT NULL) AS clicked"
            "   FROM sends WHERE campaign_id = c.id) s ON true"
            " ORDER BY coalesce(c.sent_at, c.scheduled_for, c.created_at) DESC LIMIT 500"
        ).fetchall()


@router.post("/campaigns", status_code=201)
def create_campaign(body: CampaignIn, request: Request, user=Depends(ALL_ROLES)):
    _check_reply_to(body.reply_to)
    with connect(request.app.state.settings.database_url) as conn:
        _check_refs(conn, body.template_id, body.list_id)
        row = conn.execute(
            "INSERT INTO campaigns (name, template_id, list_id, purpose, reply_to, created_by)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
            (body.name.strip(), body.template_id, body.list_id, body.purpose, body.reply_to.strip(), user["email"] or ""),
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
        template = conn.execute(
            "SELECT id, name, subject, preheader FROM templates WHERE id = %s", (campaign["template_id"],)
        ).fetchone()
        list_row = (
            conn.execute(
                "SELECT l.id, l.name, count(m.contact_id) AS members FROM lists l"
                " LEFT JOIN list_members m ON m.list_id = l.id WHERE l.id = %s GROUP BY l.id",
                (campaign["list_id"],),
            ).fetchone()
            if campaign["list_id"]
            else None
        )
        stats = _stats(conn, campaign_id)
    return {
        **campaign,
        "counts": {row["status"]: row["n"] for row in counts},
        "recent": recent,
        "template": template,
        "list": list_row,
        "stats": stats,
    }


@router.patch("/campaigns/{campaign_id}")
def update_campaign(campaign_id: int, body: CampaignUpdate, request: Request, user=Depends(ALL_ROLES)):
    fields = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if not fields:
        raise HTTPException(status_code=422, detail="Nothing to change")
    if "reply_to" in fields:
        fields["reply_to"] = fields["reply_to"].strip()
        _check_reply_to(fields["reply_to"])
    if "name" in fields:
        fields["name"] = fields["name"].strip()
    with connect(request.app.state.settings.database_url) as conn:
        campaign = _campaign(conn, campaign_id, lock=True)
        if campaign["status"] not in EDITABLE or campaign["list_id"] is None:
            raise HTTPException(status_code=409, detail="Only draft or scheduled campaigns can be changed")
        _check_refs(conn, fields.get("template_id"), fields.get("list_id"))
        assignments = ", ".join(f"{key} = %s" for key in fields)
        row = conn.execute(
            f"UPDATE campaigns SET {assignments}, updated_at = now() WHERE id = %s RETURNING *",
            list(fields.values()) + [campaign_id],
        ).fetchone()
        audit(conn, user, "campaign.updated", f"campaign:{campaign_id}", {"fields": sorted(fields)})
    return row


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        campaign = _campaign(conn, campaign_id, lock=True)
        if campaign["status"] not in EDITABLE:
            raise HTTPException(status_code=409, detail="A campaign that has been sent is kept for its report")
        conn.execute("DELETE FROM campaigns WHERE id = %s", (campaign_id,))
        audit(conn, user, "campaign.deleted", f"campaign:{campaign_id}", {"name": campaign["name"]})
    return {"ok": True}


@router.post("/campaigns/{campaign_id}/duplicate", status_code=201)
def duplicate_campaign(campaign_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        campaign = _campaign(conn, campaign_id)
        if campaign["list_id"] is None:
            raise HTTPException(status_code=409, detail="Invites to one contact cannot be copied")
        row = conn.execute(
            "INSERT INTO campaigns (name, template_id, list_id, purpose, reply_to, created_by)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
            (
                f"{campaign['name']} (copy)"[:160],
                campaign["template_id"],
                campaign["list_id"],
                campaign["purpose"],
                campaign["reply_to"],
                user["email"] or "",
            ),
        ).fetchone()
        audit(conn, user, "campaign.created", f"campaign:{row['id']}", {"copied_from": campaign_id})
    return row


def _preview_values(settings, purpose):
    values = dict(SAMPLE, unsubscribe_url="#unsubscribe", form_url="#form")
    footer = (
        f'<div style="margin-top:12px">You are receiving this because you agreed to receive {PURPOSE_LABELS[purpose]}.'
        '<br><a href="#unsubscribe" style="color:#6b7280">Unsubscribe</a></div>'
    )
    return values, footer


@router.get("/campaigns/{campaign_id}/preview")
def preview_campaign(campaign_id: int, request: Request, user=Depends(ALL_ROLES)):
    """The email as recipients will see it, with sample values."""
    settings = request.app.state.settings
    with connect(settings.database_url) as conn:
        campaign = _campaign(conn, campaign_id)
        template = conn.execute("SELECT * FROM templates WHERE id = %s", (campaign["template_id"],)).fetchone()
        eligible = skipped = 0
        if campaign["status"] in EDITABLE:
            for contact in campaign_recipients(conn, campaign):
                if eligibility(conn, contact, campaign["purpose"]):
                    skipped += 1
                else:
                    eligible += 1
    values, footer = _preview_values(settings, campaign["purpose"])
    body = render(template["body_html"], values)
    return {
        "from": f"{settings.resend_from_name} <{settings.resend_from or 'not configured'}>",
        "subject": render(template["subject"], values, html=False),
        "preheader": render(template["preheader"], values, html=False),
        "html": settings.layout(body, preheader=render(template["preheader"], values, html=False), footer_html=footer),
        "eligible": eligible,
        "will_skip": skipped,
    }


@router.post("/campaigns/{campaign_id}/test")
def test_send(campaign_id: int, body: TestSendIn, request: Request, user=Depends(ADMIN)):
    """Send the campaign to up to five addresses you choose, so you can check it before sending to everyone."""
    settings = request.app.state.settings
    addresses = [a.strip() for a in ([body.email] if body.email else []) + body.emails if a.strip()]
    addresses = list(dict.fromkeys(addresses))[:5]
    if not addresses or not all(valid_email(a) for a in addresses):
        raise HTTPException(status_code=422, detail="Enter one to five valid email addresses")
    if not settings.mail_configured:
        raise HTTPException(status_code=503, detail="Mail is not configured")
    with connect(settings.database_url) as conn:
        campaign = _campaign(conn, campaign_id)
        template = conn.execute("SELECT * FROM templates WHERE id = %s", (campaign["template_id"],)).fetchone()
        audit(conn, user, "campaign.test_sent", f"campaign:{campaign_id}", {"to": addresses})
    values, footer = _preview_values(settings, campaign["purpose"])
    footer += '<div style="margin-top:8px">Test send: the unsubscribe link does not work in tests.</div>'
    body_html = render(template["body_html"], values)
    message_ids = []
    for address in addresses:
        try:
            message_ids.append(
                send_email(
                    settings,
                    to=address,
                    subject="[Test] " + render(template["subject"], values, html=False),
                    html=settings.layout(body_html, preheader=render(template["preheader"], values, html=False), footer_html=footer),
                    text=html_to_text(body_html),
                    unsubscribe="#test-unsubscribe",
                    reply_to=campaign["reply_to"] or None,
                    idempotency_key=f"test-{uuid.uuid4()}",
                )
            )
        except MailError as error:
            raise HTTPException(status_code=502, detail=f"{address}: {error}")
    return {"ok": True, "sent_to": addresses, "message_ids": message_ids}


@router.post("/campaigns/{campaign_id}/send")
def send_campaign(campaign_id: int, request: Request, user=Depends(ADMIN)):
    """Start sending now. Recipients are fixed now; the worker sends them. Drafts and scheduled campaigns can be sent."""
    settings = request.app.state.settings
    if not settings.mail_configured:
        raise HTTPException(status_code=503, detail="Mail is not configured")
    with connect(settings.database_url) as conn:
        campaign = _campaign(conn, campaign_id, lock=True)
        if campaign["status"] not in EDITABLE:
            raise HTTPException(status_code=409, detail="This campaign has already been sent")
        if not campaign_recipients(conn, campaign):
            raise HTTPException(status_code=422, detail="The list has no contacts")
        queued, skipped = start_campaign(conn, campaign)
        audit(conn, user, "campaign.sent", f"campaign:{campaign_id}", {"queued": queued, "skipped": skipped})
    return {"queued": queued, "skipped": skipped}


@router.post("/campaigns/{campaign_id}/schedule")
def schedule_campaign(campaign_id: int, body: ScheduleIn, request: Request, user=Depends(ADMIN)):
    send_at = body.send_at if body.send_at.tzinfo else body.send_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if send_at < now + timedelta(minutes=2):
        raise HTTPException(status_code=422, detail="Choose a time at least two minutes from now")
    if send_at > now + timedelta(days=365):
        raise HTTPException(status_code=422, detail="Choose a time within the next year")
    with connect(request.app.state.settings.database_url) as conn:
        campaign = _campaign(conn, campaign_id, lock=True)
        if campaign["status"] not in EDITABLE or campaign["list_id"] is None:
            raise HTTPException(status_code=409, detail="Only drafts can be scheduled")
        if not campaign_recipients(conn, campaign):
            raise HTTPException(status_code=422, detail="The list has no contacts")
        row = conn.execute(
            "UPDATE campaigns SET status = 'scheduled', scheduled_for = %s, updated_at = now() WHERE id = %s RETURNING *",
            (send_at, campaign_id),
        ).fetchone()
        audit(conn, user, "campaign.scheduled", f"campaign:{campaign_id}", {"send_at": send_at.isoformat()})
    return row


@router.post("/campaigns/{campaign_id}/unschedule")
def unschedule_campaign(campaign_id: int, request: Request, user=Depends(ADMIN)):
    with connect(request.app.state.settings.database_url) as conn:
        campaign = _campaign(conn, campaign_id, lock=True)
        if campaign["status"] != "scheduled":
            raise HTTPException(status_code=409, detail="This campaign is not scheduled")
        row = conn.execute(
            "UPDATE campaigns SET status = 'draft', scheduled_for = NULL, updated_at = now() WHERE id = %s RETURNING *",
            (campaign_id,),
        ).fetchone()
        audit(conn, user, "campaign.unscheduled", f"campaign:{campaign_id}")
    return row


@router.get("/campaigns/{campaign_id}/report")
def campaign_report(
    campaign_id: int,
    request: Request,
    filter: Literal["all", "opened", "clicked", "not_opened", "bounced", "failed", "skipped", "queued"] = "all",
    q: str = "",
    limit: int = 50,
    offset: int = 0,
    user=Depends(ALL_ROLES),
):
    limit, offset = page_params(limit, offset)
    conditions = {
        "all": "true",
        "opened": "s.opened_at IS NOT NULL",
        "clicked": "s.clicked_at IS NOT NULL",
        "not_opened": "s.opened_at IS NULL AND s.sent_at IS NOT NULL",
        "bounced": "s.status IN ('bounced', 'complained')",
        "failed": "s.status = 'failed'",
        "skipped": "s.status = 'skipped'",
        "queued": "s.status = 'queued'",
    }
    where = f"s.campaign_id = %s AND {conditions[filter]}"
    params = [campaign_id]
    if q:
        where += " AND (s.email ILIKE %s OR c.name ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    with connect(request.app.state.settings.database_url) as conn:
        _campaign(conn, campaign_id)
        total = conn.execute(
            f"SELECT count(*) AS n FROM sends s JOIN contacts c ON c.id = s.contact_id WHERE {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            "SELECT s.id, s.contact_id, c.name, s.email, s.status, s.skip_reason, s.error, s.sent_at, s.delivered_at,"
            " s.opened_at, s.clicked_at, s.open_count, s.click_count"
            f" FROM sends s JOIN contacts c ON c.id = s.contact_id WHERE {where}"
            " ORDER BY s.id LIMIT %s OFFSET %s",
            params + [limit, offset],
        ).fetchall()
        links = conn.execute(
            "SELECT e.link, count(*) AS clicks, count(DISTINCT e.send_id) AS people FROM send_events e"
            " JOIN sends s ON s.id = e.send_id WHERE s.campaign_id = %s AND e.type = 'clicked' AND e.link IS NOT NULL"
            " GROUP BY e.link ORDER BY clicks DESC LIMIT 20",
            (campaign_id,),
        ).fetchall()
        timeline = conn.execute(
            "SELECT date_trunc('hour', e.at) AS hour, count(*) FILTER (WHERE e.type = 'opened') AS opens,"
            " count(*) FILTER (WHERE e.type = 'clicked') AS clicks FROM send_events e"
            " JOIN sends s ON s.id = e.send_id WHERE s.campaign_id = %s AND e.at < (SELECT coalesce(sent_at, now()) FROM campaigns WHERE id = %s) + interval '7 days'"
            " GROUP BY 1 ORDER BY 1",
            (campaign_id, campaign_id),
        ).fetchall()
        stats = _stats(conn, campaign_id)
    return {"stats": stats, "links": links, "timeline": timeline, "total": total, "items": rows, "limit": limit, "offset": offset}


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
        engagement = conn.execute(
            "SELECT count(*) FILTER (WHERE sent_at IS NOT NULL) AS sent,"
            " count(*) FILTER (WHERE delivered_at IS NOT NULL OR status = 'delivered') AS delivered,"
            " count(*) FILTER (WHERE opened_at IS NOT NULL) AS opened,"
            " count(*) FILTER (WHERE clicked_at IS NOT NULL) AS clicked,"
            " count(*) FILTER (WHERE status IN ('bounced', 'complained')) AS bounced"
            " FROM sends WHERE sent_at > now() - interval '30 days'"
        ).fetchone()
        daily = conn.execute(
            "SELECT d::date AS day,"
            " (SELECT count(*) FROM sends s WHERE s.sent_at::date = d::date) AS sent,"
            " (SELECT count(*) FROM sends s WHERE s.opened_at::date = d::date) AS opened"
            " FROM generate_series(current_date - 29, current_date, interval '1 day') d ORDER BY 1"
        ).fetchall()
        consent = conn.execute(
            "SELECT purpose, count(*) AS n FROM consents WHERE withdrawn_at IS NULL GROUP BY purpose"
        ).fetchall()
        growth = conn.execute(
            "SELECT count(*) FILTER (WHERE created_at > now() - interval '30 days') AS new_30d FROM contacts"
        ).fetchone()["new_30d"]
        queued = conn.execute("SELECT count(*) AS n FROM sends WHERE status = 'queued'").fetchone()["n"]
        suppressed = conn.execute("SELECT count(DISTINCT lower(email)) AS n FROM suppressions").fetchone()["n"]
        upcoming = conn.execute(
            "SELECT id, name, scheduled_for FROM campaigns WHERE status = 'scheduled' ORDER BY scheduled_for LIMIT 5"
        ).fetchall()
        recent = conn.execute(
            "SELECT id FROM campaigns WHERE status IN ('sending', 'done') ORDER BY sent_at DESC NULLS LAST LIMIT 5"
        ).fetchall()
        recent_campaigns = []
        for row in recent:
            campaign = conn.execute("SELECT id, name, status, sent_at FROM campaigns WHERE id = %s", (row["id"],)).fetchone()
            recent_campaigns.append({**campaign, "stats": _stats(conn, row["id"])})
    base = engagement["delivered"] or engagement["sent"]
    return {
        "contacts_by_type": {r["type"]: r["n"] for r in by_type},
        "media_by_status": {r["status"]: r["n"] for r in media},
        "campaigns_by_status": {r["status"]: r["n"] for r in campaigns},
        "sends_last_30_days": {r["status"]: r["n"] for r in sends},
        "engagement_30_days": {
            **engagement,
            "open_rate": _rate(engagement["opened"], base),
            "click_rate": _rate(engagement["clicked"], base),
            "bounce_rate": _rate(engagement["bounced"], engagement["sent"]),
        },
        "daily": daily,
        "consent": {r["purpose"]: r["n"] for r in consent},
        "new_contacts_30_days": growth,
        "queued": queued,
        "suppressed_addresses": suppressed,
        "upcoming": upcoming,
        "recent_campaigns": recent_campaigns,
    }
