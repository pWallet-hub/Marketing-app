import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import oidc
from app.config import Settings
from app.hub import AccessDecision
from app.main import create_app

CLIENT_ID = "marketing"
SUB = "sub-employee-1"


class MemoryUsers:
    def __init__(self):
        self.rows = {}

    def record_sign_in(self, sub, email, name):
        self.rows[sub] = {"keycloak_sub": sub, "email": email, "name": name}

    def get(self, sub):
        return self.rows.get(sub)


@pytest.fixture
def settings():
    return Settings(
        database_url="postgresql://unused",
        session_secret="x" * 40,
        https_only=False,
        keycloak_public_url="https://sso.example.org",
        keycloak_internal_url="http://keycloak:8080",
        keycloak_realm="afs",
        oidc_client_id=CLIENT_ID,
        oidc_client_secret="secret",
        public_base_url="https://marketing-api.example.org",
        frontend_origin="https://marketing.example.org",
        command_center_url="http://backend:8000",
        service_token="token",
    )


@pytest.fixture
def signing():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key


class Harness:
    """Holds the fake identity provider state a test can change."""

    def __init__(self, settings, signing):
        self.settings = settings
        self.signing = signing
        self.decision = AccessDecision(allowed=True, external_role="admin", reason="assigned")
        self.access_calls = []
        self.users = MemoryUsers()

    def access_check(self, settings, subject):
        self.access_calls.append(subject)
        return self.decision

    def id_token(self, nonce, audience=CLIENT_ID, subject=SUB, expires_in=300):
        now = int(time.time())
        return jwt.encode(
            {
                "iss": self.settings.issuer,
                "aud": audience,
                "sub": subject,
                "nonce": nonce,
                "iat": now,
                "exp": now + expires_in,
                "email": "employee@afs.example.org",
                "name": "Employee One",
            },
            self.signing,
            algorithm="RS256",
        )


@pytest.fixture
def harness(settings, signing):
    return Harness(settings, signing)


@pytest.fixture
def client(settings, harness, monkeypatch):
    app = create_app(settings=settings, access_check=harness.access_check, users=harness.users)
    public_key = harness.signing.public_key()
    app.state.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key))
    return TestClient(app)


def start_login(client):
    response = client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    return parse_qs(urlparse(response.headers["location"]).query)


def fake_token_endpoint(monkeypatch, harness, nonce_source, status=200):
    seen = {}

    def post(url, data=None, timeout=None):
        seen["data"] = data
        if status != 200:
            return httpx.Response(status, json={"error": "invalid_grant"})
        return httpx.Response(200, json={"id_token": harness.id_token(nonce_source["nonce"])})

    monkeypatch.setattr(oidc.httpx, "post", post)
    return seen


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_login_uses_pkce_state_and_nonce(client):
    params = start_login(client)
    assert params["code_challenge_method"] == ["S256"]
    assert params["client_id"] == [CLIENT_ID]
    assert params["state"][0] and params["nonce"][0]
    assert params["redirect_uri"] == ["https://marketing-api.example.org/api/auth/callback"]


def test_me_requires_sign_in(client):
    assert client.get("/api/me").status_code == 401


def test_full_sign_in_then_me(client, harness, monkeypatch):
    params = start_login(client)
    seen = fake_token_endpoint(monkeypatch, harness, {"nonce": params["nonce"][0]})

    response = client.get(
        "/api/auth/callback",
        params={"code": "abc", "state": params["state"][0]},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://marketing.example.org/"
    # The code verifier is sent, which is what makes PKCE meaningful.
    assert seen["data"]["code_verifier"]

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json() == {"sub": SUB, "email": "employee@afs.example.org", "name": "Employee One", "role": "admin"}
    assert harness.access_calls[-1] == SUB


def test_callback_rejects_wrong_state(client, harness, monkeypatch):
    params = start_login(client)
    fake_token_endpoint(monkeypatch, harness, {"nonce": params["nonce"][0]})
    response = client.get("/api/auth/callback", params={"code": "abc", "state": "forged"})
    assert response.status_code == 400


def test_callback_rejects_nonce_mismatch(client, harness, monkeypatch):
    params = start_login(client)
    fake_token_endpoint(monkeypatch, harness, {"nonce": "some-other-nonce"})
    response = client.get("/api/auth/callback", params={"code": "abc", "state": params["state"][0]})
    assert response.status_code == 400


def test_callback_rejects_wrong_audience(client, harness, monkeypatch):
    params = start_login(client)

    def post(url, data=None, timeout=None):
        return httpx.Response(200, json={"id_token": harness.id_token(params["nonce"][0], audience="biocap")})

    monkeypatch.setattr(oidc.httpx, "post", post)
    response = client.get("/api/auth/callback", params={"code": "abc", "state": params["state"][0]})
    assert response.status_code == 400


def test_callback_rejects_expired_token(client, harness, monkeypatch):
    params = start_login(client)

    def post(url, data=None, timeout=None):
        return httpx.Response(200, json={"id_token": harness.id_token(params["nonce"][0], expires_in=-60)})

    monkeypatch.setattr(oidc.httpx, "post", post)
    response = client.get("/api/auth/callback", params={"code": "abc", "state": params["state"][0]})
    assert response.status_code == 400


def test_unassigned_employee_is_refused_at_sign_in(client, harness, monkeypatch):
    harness.decision = AccessDecision(allowed=False, external_role=None, reason="not assigned")
    params = start_login(client)
    fake_token_endpoint(monkeypatch, harness, {"nonce": params["nonce"][0]})
    response = client.get("/api/auth/callback", params={"code": "abc", "state": params["state"][0]})
    assert response.status_code == 403
    assert harness.users.rows == {}


def test_revoked_access_ends_an_existing_session(client, harness, monkeypatch):
    params = start_login(client)
    fake_token_endpoint(monkeypatch, harness, {"nonce": params["nonce"][0]})
    client.get("/api/auth/callback", params={"code": "abc", "state": params["state"][0]})
    assert client.get("/api/me").status_code == 200

    harness.decision = AccessDecision(allowed=False, external_role=None, reason="not assigned")
    assert client.get("/api/me").status_code == 401


def test_unreachable_command_center_fails_closed(client, harness, monkeypatch):
    params = start_login(client)
    fake_token_endpoint(monkeypatch, harness, {"nonce": params["nonce"][0]})
    client.get("/api/auth/callback", params={"code": "abc", "state": params["state"][0]})

    def down(settings, subject):
        raise httpx.ConnectError("hub is down")

    client.app.state.access_check = down
    assert client.get("/api/me").status_code == 503


def test_role_without_permission_is_forbidden(settings, harness, monkeypatch):
    from fastapi import Depends
    from app.deps import require_role

    app = create_app(settings=settings, access_check=harness.access_check, users=harness.users)
    app.state.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=harness.signing.public_key()))

    @app.get("/api/admin-only")
    def admin_only(user=Depends(require_role("admin"))):
        return {"ok": True}

    harness.decision = AccessDecision(allowed=True, external_role="member", reason="assigned")
    client = TestClient(app)
    params = start_login(client)
    fake_token_endpoint(monkeypatch, harness, {"nonce": params["nonce"][0]})
    client.get("/api/auth/callback", params={"code": "abc", "state": params["state"][0]})
    assert client.get("/api/admin-only").status_code == 403
