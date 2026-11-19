"""Who gets an email, and the sending queue that the worker drains.

A campaign copies its recipients into `sends` when it is sent. Each recipient is either queued or skipped, with the
reason. The worker picks queued rows, sends them one at a time, and records the result.
"""

import logging
import time

from .db import connect
from .mail import (
    MailError,
    form_expiry,
    form_url,
    new_form_token,
    one_click_unsubscribe_url,
    send_email,
    unsubscribe_url,
)
from .render import html_to_text, render

log = logging.getLogger("marketing.queue")
MAX_ATTEMPTS = 3

PURPOSE_LABELS = {
    "marketing": "AFS news and marketing from AFS",
    "information_request": "information requests from AFS",
}


def eligibility(conn, contact, purpose):
    """Return None when the contact may receive this purpose, or the reason they may not."""
    if contact["status"] in ("unsubscribed", "bounced", "complained"):
        return f"contact is {contact['status']}"
    suppressed = conn.execute(
        "SELECT 1 FROM suppressions WHERE lower(email) = lower(%s) AND purpose IN (%s, 'all')",
        (contact["email"], purpose),
    ).fetchone()
    if suppressed:
        return "suppressed"
    consent = conn.execute(
        "SELECT 1 FROM consents WHERE contact_id = %s AND purpose = %s AND withdrawn_at IS NULL",
        (contact["id"], purpose),
    ).fetchone()
    if consent is None:
        return f"no consent for {purpose}"
    return None


def enqueue(conn, campaign_id, purpose, contacts):
    """Create one send row per contact. Returns (queued, skipped) counts. Repeated calls do not duplicate rows."""
    queued = skipped = 0
    for contact in contacts:
        reason = eligibility(conn, contact, purpose)
        row = conn.execute(
            "INSERT INTO sends (campaign_id, contact_id, email, status, skip_reason)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (campaign_id, contact_id) DO NOTHING RETURNING id",
            (campaign_id, contact["id"], contact["email"], "skipped" if reason else "queued", reason),
        ).fetchone()
        if row is None:
            continue
        if reason:
            skipped += 1
        else:
            queued += 1
    return queued, skipped


def _footer(unsubscribe, purpose):
    label = PURPOSE_LABELS[purpose]
    html = (
        '<hr style="border:none;border-top:1px solid #ddd;margin:24px 0 12px">'
        f'<p style="font-size:12px;color:#666">You are receiving this because you agreed to receive {label}. '
        f'<a href="{unsubscribe}">Unsubscribe</a>.</p>'
    )
    text = f"\n\nYou are receiving this because you agreed to receive {label}.\nUnsubscribe: {unsubscribe}"
    return html, text


def process_once(settings, batch_size=20):
    """Send up to `batch_size` queued messages. Returns how many were handled. Does nothing without mail configured."""
    if not settings.mail_configured:
        return 0
    handled = 0
    with connect(settings.database_url) as conn:
        rows = conn.execute(
            "SELECT s.id, s.email, s.attempts, c.id AS contact_id, c.name, c.organisation, c.type,"
            " camp.id AS campaign_id, camp.purpose, t.subject, t.body_html"
            " FROM sends s"
            " JOIN contacts c ON c.id = s.contact_id"
            " JOIN campaigns camp ON camp.id = s.campaign_id"
            " JOIN templates t ON t.id = camp.template_id"
            " WHERE s.status = 'queued' ORDER BY s.id LIMIT %s FOR UPDATE OF s SKIP LOCKED",
            (batch_size,),
        ).fetchall()
        for index, row in enumerate(rows):
            if index:
                time.sleep(settings.send_interval_seconds)
            handled += 1
            unsub = unsubscribe_url(settings, row["contact_id"], row["purpose"])
            values = {
                "name": row["name"],
                "organisation": row["organisation"],
                "email": row["email"],
                "unsubscribe_url": unsub,
            }
            if row["purpose"] == "information_request":
                token, token_hash = new_form_token()
                conn.execute(
                    "INSERT INTO form_tokens (token_hash, contact_id, send_id, expires_at) VALUES (%s, %s, %s, %s)",
                    (token_hash, row["contact_id"], row["id"], form_expiry()),
                )
                values["form_url"] = form_url(settings, token)

            footer_html, footer_text = _footer(unsub, row["purpose"])
            body = render(row["body_html"], values, html=True)
            html = body + footer_html
            text = html_to_text(body) + footer_text
            subject = render(row["subject"], values, html=False)
            attempts = row["attempts"] + 1
            try:
                message_id = send_email(
                    settings,
                    to=row["email"],
                    subject=subject,
                    html=html,
                    text=text,
                    unsubscribe=unsub,
                    one_click=one_click_unsubscribe_url(settings, row["contact_id"], row["purpose"]),
                    idempotency_key=f"send-{row['id']}",
                )
                conn.execute(
                    "UPDATE sends SET status = 'sent', resend_message_id = %s, attempts = %s, error = NULL,"
                    " sent_at = now() WHERE id = %s",
                    (message_id, attempts, row["id"]),
                )
            except MailError as error:
                status = "failed" if attempts >= MAX_ATTEMPTS else "queued"
                log.warning("send %s failed (attempt %s): %s", row["id"], attempts, error)
                conn.execute(
                    "UPDATE sends SET status = %s, attempts = %s, error = %s WHERE id = %s",
                    (status, attempts, str(error)[:500], row["id"]),
                )
        # A campaign is done once nothing is left queued for it.
        conn.execute(
            "UPDATE campaigns SET status = 'done' WHERE status = 'sending' AND NOT EXISTS"
            " (SELECT 1 FROM sends WHERE sends.campaign_id = campaigns.id AND sends.status = 'queued')"
        )
    return handled
