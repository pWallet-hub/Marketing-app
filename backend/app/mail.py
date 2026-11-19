"""Sending email through Resend, and the signed links that go into each email.

Links are signed, not stored, so an unsubscribe link keeps working without a database lookup. Form links are random
tokens with only their hash stored, because they open a page that holds personal data.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from itsdangerous import BadSignature, URLSafeSerializer

FORM_LINK_DAYS = 30


class MailError(Exception):
    pass


def _serializer(settings, salt):
    return URLSafeSerializer(settings.session_secret, salt=salt)


def unsubscribe_token(settings, contact_id, purpose):
    return _serializer(settings, "unsubscribe").dumps({"c": contact_id, "p": purpose})


def read_unsubscribe_token(settings, token):
    try:
        data = _serializer(settings, "unsubscribe").loads(token)
    except BadSignature:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("c"), int) or data.get("p") not in ("marketing", "information_request"):
        return None
    return data


def unsubscribe_url(settings, contact_id, purpose):
    return f"{settings.frontend_origin.rstrip('/')}/unsubscribe/{unsubscribe_token(settings, contact_id, purpose)}"


def one_click_unsubscribe_url(settings, contact_id, purpose):
    """The List-Unsubscribe address. Mail clients POST to it directly (RFC 8058), so it is an API route, not a page."""
    token = unsubscribe_token(settings, contact_id, purpose)
    return f"{settings.frontend_origin.rstrip('/')}/api/public/unsubscribe/{token}"


def new_form_token():
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest()


def form_expiry():
    return datetime.now(timezone.utc) + timedelta(days=FORM_LINK_DAYS)


def form_url(settings, token):
    return f"{settings.frontend_origin.rstrip('/')}/forms/{token}"


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def send_email(settings, *, to, subject, html, text, unsubscribe, one_click=None, reply_to=None, idempotency_key):
    """Send one message through Resend. Returns Resend's message id. Raises MailError on failure.

    `unsubscribe` is the page linked in the footer; `one_click` is the address mail clients POST to. Without
    `one_click` (test sends) no List-Unsubscribe header is sent.
    """
    if not settings.mail_configured:
        raise MailError("mail is not configured")
    body = {
        "from": f"{settings.resend_from_name} <{settings.resend_from}>",
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }
    if reply_to:
        body["reply_to"] = reply_to
    if one_click:
        # Lets mail clients show their own one-click unsubscribe button (RFC 8058).
        body["headers"] = {
            "List-Unsubscribe": f"<{one_click}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
    try:
        response = httpx.post(
            f"{settings.resend_api_base.rstrip('/')}/emails",
            json=body,
            headers={"Authorization": f"Bearer {settings.resend_api_key}", "Idempotency-Key": idempotency_key},
            timeout=15,
        )
    except httpx.HTTPError as error:
        raise MailError(f"could not reach Resend: {error.__class__.__name__}") from error
    if response.status_code not in (200, 201):
        raise MailError(f"Resend answered HTTP {response.status_code}")
    message_id = response.json().get("id")
    if not message_id:
        raise MailError("Resend did not return a message id")
    return message_id


def verify_svix_signature(secret, headers, body, now=None, tolerance_seconds=300):
    """Check a Resend webhook (it uses Svix signing). Raises ValueError when the request is not genuine."""
    if not secret:
        raise ValueError("webhook secret is not configured")
    message_id = headers.get("svix-id")
    timestamp = headers.get("svix-timestamp")
    signature_header = headers.get("svix-signature")
    if not (message_id and timestamp and signature_header):
        raise ValueError("missing signature headers")
    try:
        sent_at = int(timestamp)
    except ValueError as error:
        raise ValueError("bad timestamp") from error
    current = int(now if now is not None else datetime.now(timezone.utc).timestamp())
    if abs(current - sent_at) > tolerance_seconds:
        raise ValueError("timestamp outside tolerance")
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{message_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    for part in signature_header.split():
        version, _, signature = part.partition(",")
        if version == "v1" and hmac.compare_digest(signature, expected):
            return
    raise ValueError("signature does not match")
