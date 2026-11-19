"""Delivery events from Resend (delivered, opened, clicked, bounced, complained, failed).

Requests must carry a valid Svix signature, so only Resend can change a send's status. A bounce or complaint stops all
mail to that address, because continuing would harm the sending domain's reputation.
"""

import json

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Jsonb

from ..db import connect
from ..mail import verify_svix_signature

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/resend")
async def resend_event(request: Request):
    settings = request.app.state.settings
    if not settings.resend_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook is not configured")
    body = await request.body()
    try:
        verify_svix_signature(settings.resend_webhook_secret, dict(request.headers), body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    try:
        event = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid body")

    kind = event.get("type", "")
    data = event.get("data") or {}
    message_id = data.get("email_id")
    if not message_id:
        return {"ok": True, "ignored": True}

    with connect(settings.database_url) as conn:
        send = conn.execute("SELECT * FROM sends WHERE resend_message_id = %s", (message_id,)).fetchone()
        if send is None:
            return {"ok": True, "ignored": True}
        if kind == "email.delivered":
            # An open can arrive before the delivery report; neither moves a bounced send back.
            conn.execute(
                "UPDATE sends SET status = CASE WHEN status = 'sent' THEN 'delivered' ELSE status END,"
                " delivered_at = coalesce(delivered_at, now()) WHERE id = %s",
                (send["id"],),
            )
            _event(conn, send, "delivered")
            return {"ok": True}
        elif kind == "email.opened":
            conn.execute(
                "UPDATE sends SET opened_at = coalesce(opened_at, now()), open_count = open_count + 1 WHERE id = %s",
                (send["id"],),
            )
            _event(conn, send, "opened")
            return {"ok": True}
        elif kind == "email.clicked":
            link = str((data.get("click") or {}).get("link") or "")[:2000] or None
            # A click proves the email was opened, even when images (the open pixel) were blocked.
            conn.execute(
                "UPDATE sends SET clicked_at = coalesce(clicked_at, now()), click_count = click_count + 1,"
                " opened_at = coalesce(opened_at, now()), open_count = greatest(open_count, 1) WHERE id = %s",
                (send["id"],),
            )
            _event(conn, send, "clicked", link)
            return {"ok": True}
        elif kind == "email.bounced":
            conn.execute("UPDATE sends SET status = 'bounced', error = 'bounced' WHERE id = %s", (send["id"],))
            _event(conn, send, "bounced")
            _stop_mail(conn, send, "bounced", "bounced")
        elif kind == "email.complained":
            conn.execute("UPDATE sends SET status = 'complained', error = 'complaint' WHERE id = %s", (send["id"],))
            _stop_mail(conn, send, "complained", "complaint")
        elif kind == "email.failed":
            conn.execute("UPDATE sends SET status = 'failed', error = 'Resend reported failure' WHERE id = %s", (send["id"],))
        conn.execute(
            "INSERT INTO audit_log (actor_sub, actor_email, action, target, detail) VALUES ('resend', '', %s, %s, %s)",
            (f"mail.{kind}", f"send:{send['id']}", Jsonb({"message_id": message_id})),
        )
    return {"ok": True}


def _event(conn, send, kind, link=None):
    conn.execute("INSERT INTO send_events (send_id, type, link) VALUES (%s, %s, %s)", (send["id"], kind, link))


def _stop_mail(conn, send, status, reason):
    conn.execute("UPDATE contacts SET status = %s, updated_at = now() WHERE id = %s", (status, send["contact_id"]))
    conn.execute(
        "INSERT INTO suppressions (email, purpose, reason) VALUES (lower(%s), 'all', %s)"
        " ON CONFLICT (email, purpose) DO NOTHING",
        (send["email"], reason),
    )
