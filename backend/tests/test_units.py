import base64
import hashlib
import hmac
import json

import pytest

from app.mail import read_unsubscribe_token, unsubscribe_token, verify_svix_signature
from app.render import html_to_text, render, unknown_placeholders
from tests.conftest import WEBHOOK_KEY, WEBHOOK_SECRET, make_settings


def svix_headers(body, message_id="msg_1", timestamp=1_700_000_000, key=WEBHOOK_KEY):
    signed = f"{message_id}.{timestamp}.".encode() + body
    signature = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {"svix-id": message_id, "svix-timestamp": str(timestamp), "svix-signature": f"v1,{signature}"}


def test_valid_webhook_signature_is_accepted():
    body = json.dumps({"type": "email.delivered"}).encode()
    verify_svix_signature(WEBHOOK_SECRET, svix_headers(body), body, now=1_700_000_010)


def test_webhook_with_tampered_body_is_refused():
    body = b'{"type":"email.delivered"}'
    headers = svix_headers(body)
    with pytest.raises(ValueError):
        verify_svix_signature(WEBHOOK_SECRET, headers, b'{"type":"email.bounced"}', now=1_700_000_010)


def test_webhook_signed_with_another_key_is_refused():
    body = b"{}"
    with pytest.raises(ValueError):
        verify_svix_signature(WEBHOOK_SECRET, svix_headers(body, key=b"other-key-0123456789"), body, now=1_700_000_010)


def test_old_webhook_timestamp_is_refused():
    body = b"{}"
    with pytest.raises(ValueError):
        verify_svix_signature(WEBHOOK_SECRET, svix_headers(body), body, now=1_700_001_000)


def test_webhook_without_secret_is_refused():
    with pytest.raises(ValueError):
        verify_svix_signature("", svix_headers(b"{}"), b"{}", now=1_700_000_010)


def test_unsubscribe_token_round_trips_and_rejects_tampering():
    settings = make_settings()
    token = unsubscribe_token(settings, 42, "marketing")
    assert read_unsubscribe_token(settings, token) == {"c": 42, "p": "marketing"}
    assert read_unsubscribe_token(settings, token + "x") is None
    other = make_settings(session_secret="y" * 40)
    assert read_unsubscribe_token(other, token) is None


def test_unsubscribe_token_rejects_unknown_purpose():
    settings = make_settings()
    token = unsubscribe_token(settings, 42, "all")
    assert read_unsubscribe_token(settings, token) is None


def test_render_escapes_values_in_html_but_not_in_subject():
    html = render("<p>Hi {{name}}</p>", {"name": "<script>x</script>"})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert render("Hi {{name}}", {"name": "A & B"}, html=False) == "Hi A & B"


def test_unknown_placeholders_are_reported():
    assert unknown_placeholders("{{name}} {{password}} {{ secret }}") == ["password", "secret"]


def test_html_to_text_keeps_line_breaks():
    assert html_to_text("<p>One</p><p>Two</p>") == "One\n\nTwo"


def test_rate_limiter_allows_up_to_the_limit_per_window():
    from app.ratelimit import RateLimiter

    now = [0.0]
    limiter = RateLimiter(limit=2, window=60, clock=lambda: now[0])
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")
    now[0] = 61
    assert limiter.allow("a")


def test_client_address_ignores_entries_the_client_wrote():
    from types import SimpleNamespace

    from app.ratelimit import client_address

    request = SimpleNamespace(
        headers={"x-forwarded-for": "6.6.6.6, 203.0.113.9, 10.0.0.2"}, client=SimpleNamespace(host="10.0.0.3")
    )
    assert client_address(request, 2) == "203.0.113.9"
    assert client_address(request, 1) == "10.0.0.2"
    assert client_address(SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.3")), 2) == "10.0.0.3"


GOOD_PRODUCTION = {
    "ENVIRONMENT": "production",
    "SESSION_SECRET": "q9Zr4t8LmW2xVb6nP0sKd3HfJ7yGc1Ua9Zr4t8LmW2x",
    "OIDC_CLIENT_SECRET": "Lw8aTq2NpE6vXc0RsD4mKb9HyJ3uFg7z",
    "AFS_SERVICE_TOKEN_MARKETING": "T4hR9mQw2ZxKc8LpB6vNd1SgY3eJf7Ua",
    "DATABASE_URL": "postgresql://marketing:Vb6nP0sKd3HfJ7yGc1@db:5432/marketing",
    "PUBLIC_BASE_URL": "https://marketing.afs-rwanda.org",
    "FRONTEND_ORIGIN": "https://marketing.afs-rwanda.org",
    "KEYCLOAK_PUBLIC_URL": "https://sso.afs-rwanda.org",
    "SESSION_HTTPS_ONLY": "true",
}


def test_production_checks():
    from app.production import production_problems

    assert production_problems({"ENVIRONMENT": "development"}) == []
    assert production_problems(GOOD_PRODUCTION) == []
    bad = production_problems(
        {**GOOD_PRODUCTION, "OIDC_CLIENT_SECRET": "", "PUBLIC_BASE_URL": "http://m.org", "RESEND_API_KEY": "re_x",
         "DATABASE_URL": "postgresql://marketing:change-me@db/marketing"}
    )
    joined = " ".join(bad)
    for name in ("OIDC_CLIENT_SECRET", "PUBLIC_BASE_URL", "RESEND_WEBHOOK_SECRET", "POSTGRES_PASSWORD"):
        assert name in joined
