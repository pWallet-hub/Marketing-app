import base64
import os
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect, migrate
from app.deps import current_user
from app.hub import AccessDecision
from app.main import create_app

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
WEBHOOK_KEY = b"webhook-test-key-0123456789abcdef"
WEBHOOK_SECRET = "whsec_" + base64.b64encode(WEBHOOK_KEY).decode()

requires_db = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not set")


def make_settings(database_url=DATABASE_URL, **overrides):
    values = dict(
        database_url=database_url,
        session_secret="x" * 40,
        https_only=False,
        keycloak_public_url="https://sso.example.org",
        keycloak_internal_url="http://keycloak:8080",
        keycloak_realm="afs",
        oidc_client_id="marketing",
        oidc_client_secret="secret",
        public_base_url="https://marketing.example.org",
        frontend_origin="https://marketing.example.org",
        command_center_url="http://backend:8000",
        service_token="token",
        resend_api_key="re_test",
        resend_from="news@example.org",
        resend_webhook_secret=WEBHOOK_SECRET,
        send_interval_seconds=0,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(scope="session")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def settings():
    return make_settings()


@pytest.fixture
def db(settings):
    """A migrated database, emptied before each test."""
    if not DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    migrate(settings.database_url)
    with connect(settings.database_url) as conn:
        conn.execute(
            "TRUNCATE contacts, lists, templates, campaigns, sends, consents, suppressions, list_members,"
            " form_tokens, form_submissions, audit_log RESTART IDENTITY CASCADE"
        )
    return settings


def build_client(settings, role="admin", signing_key=None):
    """A client signed in as a person with `role`. Access is checked against a stub, not Command Center."""
    decision = AccessDecision(allowed=True, external_role=role, reason="assigned")
    app = create_app(settings=settings, access_check=lambda s, sub: decision)
    user = {"sub": f"sub-{role}", "email": f"{role}@afs.example.org", "name": role, "role": role}
    app.dependency_overrides[current_user] = lambda: user
    if signing_key is not None:
        app.state.jwks = SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=signing_key.public_key())
        )
    return TestClient(app)


@pytest.fixture
def admin(db):
    return build_client(db, "admin")


@pytest.fixture
def member(db):
    return build_client(db, "member")
