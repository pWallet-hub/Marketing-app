import json
import re
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import queue as queue_module
from app.db import connect
from app.mail import MailError, unsubscribe_token
from app.queue import process_once
from tests.conftest import WEBHOOK_KEY, build_client, make_settings, requires_db
from tests.test_units import svix_headers

pytestmark = requires_db


def make_contact(client, email, type="partner", **extra):
    body = {"email": email, "name": extra.pop("name", "Contact"), "type": type, **extra}
    response = client.post("/api/contacts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def make_template(client, name="Newsletter", subject="Hello {{name}}", html="<p>Hi {{name}}</p>"):
    response = client.post("/api/templates", json={"name": name, "subject": subject, "body_html": html})
    assert response.status_code == 201, response.text
    return response.json()


def make_list(client, name="Partners"):
    response = client.post("/api/lists", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def add_to_list(client, list_id, contact_ids):
    response = client.post(f"/api/lists/{list_id}/members", json={"contact_ids": contact_ids})
    assert response.status_code == 201, response.text


def grant(client, contact_id, purpose="marketing", source="Signed up at the 2026 media day"):
    response = client.post(f"/api/contacts/{contact_id}/consent", json={"purpose": purpose, "source": source})
    assert response.status_code == 201, response.text


class FakeResend:
    """Stands in for Resend. Records each message and can be told to fail for an address."""

    def __init__(self, fail_for=()):
        self.sent = []
        self.fail_for = set(fail_for)

    def __call__(self, settings, **kwargs):
        if kwargs["to"] in self.fail_for:
            raise MailError("Resend answered HTTP 500")
        self.sent.append(kwargs)
        return f"re_{uuid.uuid4().hex}"


@pytest.fixture
def fake_resend(monkeypatch):
    fake = FakeResend()
    monkeypatch.setattr(queue_module, "send_email", fake)
    return fake


def test_contact_is_not_created_twice(admin):
    make_contact(admin, "Ana@Example.org")
    response = admin.post("/api/contacts", json={"email": "ana@example.org", "type": "partner"})
    assert response.status_code == 409


def test_invalid_email_is_refused(admin):
    response = admin.post("/api/contacts", json={"email": "not-an-email", "type": "partner"})
    assert response.status_code == 422


def test_campaign_sends_only_to_consenting_contacts(admin, fake_resend):
    settings = admin.app.state.settings
    yes = make_contact(admin, "yes@example.org")
    no = make_contact(admin, "no@example.org")
    suppressed = make_contact(admin, "gone@example.org")
    grant(admin, yes["id"])
    grant(admin, suppressed["id"])
    with connect(settings.database_url) as conn:
        conn.execute("INSERT INTO suppressions (email, purpose, reason) VALUES ('gone@example.org', 'all', 'test')")
    template = make_template(admin)
    lst = make_list(admin)
    add_to_list(admin, lst["id"], [yes["id"], no["id"], suppressed["id"]])
    campaign = admin.post(
        "/api/campaigns", json={"name": "Spring", "template_id": template["id"], "list_id": lst["id"], "purpose": "marketing"}
    ).json()

    result = admin.post(f"/api/campaigns/{campaign['id']}/send").json()
    assert result == {"queued": 1, "skipped": 2}

    detail = admin.get(f"/api/campaigns/{campaign['id']}").json()
    reasons = {row["email"]: row["skip_reason"] for row in detail["recent"] if row["status"] == "skipped"}
    assert reasons == {"no@example.org": "no consent for marketing", "gone@example.org": "suppressed"}


def test_sent_campaign_cannot_be_sent_again(admin, fake_resend):
    contact = make_contact(admin, "once@example.org")
    grant(admin, contact["id"])
    template = make_template(admin)
    lst = make_list(admin)
    add_to_list(admin, lst["id"], [contact["id"]])
    campaign = admin.post(
        "/api/campaigns", json={"name": "Once", "template_id": template["id"], "list_id": lst["id"], "purpose": "marketing"}
    ).json()
    assert admin.post(f"/api/campaigns/{campaign['id']}/send").status_code == 200
    assert admin.post(f"/api/campaigns/{campaign['id']}/send").status_code == 409


def test_worker_sends_with_unsubscribe_headers_and_completes_campaign(admin, fake_resend):
    settings = admin.app.state.settings
    contact = make_contact(admin, "send@example.org", name="Sam")
    grant(admin, contact["id"])
    template = make_template(admin, html="<p>Hi {{name}}</p>")
    lst = make_list(admin)
    add_to_list(admin, lst["id"], [contact["id"]])
    campaign = admin.post(
        "/api/campaigns", json={"name": "Go", "template_id": template["id"], "list_id": lst["id"], "purpose": "marketing"}
    ).json()
    admin.post(f"/api/campaigns/{campaign['id']}/send")

    assert process_once(settings) == 1
    message = fake_resend.sent[0]
    assert message["to"] == "send@example.org"
    assert message["subject"] == "Hello Sam"
    assert "Unsubscribe" in message["html"]
    assert message["unsubscribe"].startswith("https://marketing.example.org/unsubscribe/")
    assert message["one_click"].startswith("https://marketing.example.org/api/public/unsubscribe/")
    detail = admin.get(f"/api/campaigns/{campaign['id']}").json()
    assert detail["status"] == "done"
    assert detail["counts"] == {"sent": 1}


def test_failed_send_is_retried_then_marked_failed(admin, monkeypatch):
    settings = admin.app.state.settings
    failing = FakeResend(fail_for=["broken@example.org"])
    monkeypatch.setattr(queue_module, "send_email", failing)
    contact = make_contact(admin, "broken@example.org")
    grant(admin, contact["id"])
    template = make_template(admin)
    lst = make_list(admin)
    add_to_list(admin, lst["id"], [contact["id"]])
    campaign = admin.post(
        "/api/campaigns", json={"name": "Retry", "template_id": template["id"], "list_id": lst["id"], "purpose": "marketing"}
    ).json()
    admin.post(f"/api/campaigns/{campaign['id']}/send")
    for _ in range(3):
        process_once(settings)
    detail = admin.get(f"/api/campaigns/{campaign['id']}").json()
    assert detail["counts"] == {"failed": 1}
    assert detail["status"] == "done"


def test_worker_does_nothing_without_mail_configured(db, fake_resend):
    settings = make_settings(resend_api_key="")
    assert process_once(settings) == 0
    assert fake_resend.sent == []


def test_unsubscribe_stops_marketing_mail(admin, fake_resend):
    settings = admin.app.state.settings
    contact = make_contact(admin, "leave@example.org")
    grant(admin, contact["id"])
    token = unsubscribe_token(settings, contact["id"], "marketing")
    client = TestClient(admin.app)  # public route: no sign-in needed
    assert client.post("/api/public/unsubscribe", json={"token": token}).status_code == 200

    detail = admin.get(f"/api/contacts/{contact['id']}").json()
    assert detail["status"] == "unsubscribed"
    assert detail["consents"][0]["withdrawn_at"] is not None
    assert detail["suppressions"][0]["purpose"] == "marketing"


def test_bad_unsubscribe_token_is_refused(admin):
    client = TestClient(admin.app)
    assert client.post("/api/public/unsubscribe", json={"token": "tampered-token-value"}).status_code == 400


def test_webhook_bounce_stops_all_mail(admin, fake_resend):
    settings = admin.app.state.settings
    contact = make_contact(admin, "bounce@example.org")
    grant(admin, contact["id"])
    template = make_template(admin)
    lst = make_list(admin)
    add_to_list(admin, lst["id"], [contact["id"]])
    campaign = admin.post(
        "/api/campaigns", json={"name": "B", "template_id": template["id"], "list_id": lst["id"], "purpose": "marketing"}
    ).json()
    admin.post(f"/api/campaigns/{campaign['id']}/send")
    process_once(settings)
    with connect(settings.database_url) as conn:
        resend_id = conn.execute("SELECT resend_message_id FROM sends WHERE campaign_id = %s", (campaign["id"],)).fetchone()["resend_message_id"]

    body = json.dumps({"type": "email.bounced", "data": {"email_id": resend_id}}).encode()
    client = TestClient(admin.app)
    response = client.post("/api/webhooks/resend", content=body, headers=svix_headers(body, timestamp=int(time.time())))
    assert response.status_code == 200, response.text

    detail = admin.get(f"/api/contacts/{contact['id']}").json()
    assert detail["status"] == "bounced"
    assert any(s["purpose"] == "all" for s in detail["suppressions"])


def test_webhook_with_bad_signature_is_refused(admin):
    body = b'{"type":"email.bounced","data":{"email_id":"x"}}'
    client = TestClient(admin.app)
    response = client.post("/api/webhooks/resend", content=body, headers={"svix-id": "m", "svix-timestamp": "1", "svix-signature": "v1,AAAA"})
    assert response.status_code == 400


def test_information_campaign_gives_a_one_time_form_link(admin, fake_resend):
    settings = admin.app.state.settings
    contact = make_contact(admin, "form@example.org", type="staff", name="Ruth")
    grant(admin, contact["id"], purpose="information_request", source="Staff directory update, Nov 2026")
    template = make_template(admin, name="Info", subject="Update your details", html="<p>Fill in: {{form_url}}</p>")
    lst = make_list(admin, "Staff")
    add_to_list(admin, lst["id"], [contact["id"]])
    campaign = admin.post(
        "/api/campaigns", json={"name": "Info", "template_id": template["id"], "list_id": lst["id"], "purpose": "information_request"}
    ).json()
    admin.post(f"/api/campaigns/{campaign['id']}/send")
    process_once(settings)

    match = re.search(r"/forms/([A-Za-z0-9_-]+)", fake_resend.sent[0]["html"])
    assert match
    token = match.group(1)
    client = TestClient(admin.app)
    assert client.get(f"/api/public/forms/{token}").json()["name"] == "Ruth"

    submit = client.post(f"/api/public/forms/{token}", json={"name": "Ruth N.", "position": "Procurement officer"})
    assert submit.status_code == 200
    assert submit.json()["forwarded"] is False  # no target configured: stored only
    assert client.post(f"/api/public/forms/{token}", json={"name": "again"}).status_code == 404
    assert admin.get(f"/api/contacts/{contact['id']}").json()["name"] == "Ruth N."


def test_form_link_with_unknown_token_is_not_found(admin):
    assert TestClient(admin.app).get("/api/public/forms/not-a-real-token").status_code == 404


def test_member_cannot_send_or_import(member):
    lst = make_list(member)
    template = make_template(member)
    campaign = member.post(
        "/api/campaigns", json={"name": "M", "template_id": template["id"], "list_id": lst["id"], "purpose": "marketing"}
    ).json()
    assert member.post(f"/api/campaigns/{campaign['id']}/send").status_code == 403
    assert member.post("/api/contacts/import", json={"csv": "email\na@b.org", "type": "partner"}).status_code == 403
    assert member.post(f"/api/campaigns/{campaign['id']}/test", json={"email": "x@y.org"}).status_code == 403


def test_import_creates_contacts_and_records_consent(admin):
    csv_text = "email,name,organisation\na@media.org,Ana,Media One\nbad-address,Bob,Nowhere\nb@media.org,Ben,\n"
    result = admin.post(
        "/api/contacts/import",
        json={"csv": csv_text, "type": "media", "purpose": "marketing", "source": "Media day sign-in sheet"},
    ).json()
    assert result["created"] == 2
    assert result["consent_recorded"] == 2
    assert result["errors"][0]["line"] == 3
    assert admin.get("/api/contacts?type=media").json()["total"] == 2


def test_import_respects_suppression(admin):
    settings = admin.app.state.settings
    with connect(settings.database_url) as conn:
        conn.execute("INSERT INTO suppressions (email, purpose, reason) VALUES ('blocked@media.org', 'marketing', 'test')")
    result = admin.post(
        "/api/contacts/import",
        json={"csv": "email\nblocked@media.org", "type": "media", "purpose": "marketing", "source": "Sign-up form"},
    ).json()
    assert result["consent_recorded"] == 0
    assert result["consent_skipped_suppressed"] == 1


def test_import_needs_a_source_when_consent_is_given(admin):
    response = admin.post("/api/contacts/import", json={"csv": "email\na@b.org", "type": "media", "purpose": "marketing"})
    assert response.status_code == 422


def test_media_invite_needs_marketing_consent(admin):
    contact = make_contact(admin, "invitee@media.org", type="media", name="Invitee")
    template = make_template(admin)
    response = admin.post(f"/api/contacts/{contact['id']}/invite?template_id={template['id']}")
    assert response.status_code == 409


def test_media_invite_sends_and_marks_invited(admin, fake_resend):
    settings = admin.app.state.settings
    contact = make_contact(admin, "invitee@media.org", type="media", name="Invitee")
    grant(admin, contact["id"])
    template = make_template(admin, name="Invite", subject="Join AFS", html="<p>Welcome {{name}}</p>")
    result = admin.post(f"/api/contacts/{contact['id']}/invite?template_id={template['id']}").json()
    assert result["queued"] == 1
    assert result["blog_account"] == "not_configured"
    assert admin.get(f"/api/contacts/{contact['id']}").json()["status"] == "invited"
    process_once(settings)
    assert fake_resend.sent[0]["subject"] == "Join AFS"


def test_dashboard_counts(admin):
    make_contact(admin, "a@x.org", type="media")
    make_contact(admin, "b@x.org", type="partner")
    data = admin.get("/api/dashboard").json()
    assert data["contacts_by_type"] == {"media": 1, "partner": 1}


def test_audit_log_records_changes(admin):
    settings = admin.app.state.settings
    make_contact(admin, "audited@x.org")
    with connect(settings.database_url) as conn:
        row = conn.execute("SELECT action, actor_email FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    assert row["action"] == "contact.created"
    assert row["actor_email"] == "admin@afs.example.org"


def test_template_with_unknown_placeholder_is_refused(admin):
    response = admin.post("/api/templates", json={"name": "Bad", "subject": "Hi", "body_html": "{{password}}"})
    assert response.status_code == 422


def test_public_pages_are_rate_limited(db):
    client = build_client(make_settings(public_rate_limit=3), "admin")
    codes = [client.post("/api/public/unsubscribe", json={"token": "tampered-token-value"}).status_code for _ in range(4)]
    assert codes == [400, 400, 400, 429]


def test_erasing_a_contact_removes_their_records_and_keeps_them_suppressed(admin, fake_resend):
    contact = make_contact(admin, "erase-me@example.org", type="media")
    grant(admin, contact["id"])
    group = make_list(admin)
    add_to_list(admin, group["id"], [contact["id"]])
    template = make_template(admin)
    assert admin.post(f"/api/contacts/{contact['id']}/invite?template_id={template['id']}").status_code == 201

    response = admin.post(f"/api/contacts/{contact['id']}/erase", json={})
    assert response.status_code == 200, response.text
    assert admin.get(f"/api/contacts/{contact['id']}").status_code == 404
    with connect(admin.app.state.settings.database_url) as conn:
        for table, column in (("consents", "contact_id"), ("list_members", "contact_id"), ("sends", "contact_id")):
            assert conn.execute(f"SELECT count(*) AS n FROM {table} WHERE {column} = %s", (contact["id"],)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM campaigns WHERE single_contact_id = %s", (contact["id"],)).fetchone()["n"] == 0
        audit = conn.execute("SELECT detail::text AS d FROM audit_log WHERE action = 'contact.erased'").fetchone()
        assert "erase-me" not in audit["d"]

    again = make_contact(admin, "erase-me@example.org")
    response = admin.post(f"/api/contacts/{again['id']}/consent", json={"purpose": "marketing", "source": "Old CSV"})
    assert response.status_code == 409


def test_erasing_without_suppression_forgets_the_address(admin):
    contact = make_contact(admin, "forget-me@example.org")
    assert admin.post(f"/api/contacts/{contact['id']}/erase", json={"suppress": False}).status_code == 200
    again = make_contact(admin, "forget-me@example.org")
    grant(admin, again["id"])


def test_members_cannot_erase_contacts(admin, member):
    contact = make_contact(admin, "kept@example.org")
    assert member.post(f"/api/contacts/{contact['id']}/erase", json={}).status_code == 403


def test_retention_removes_old_records_only_when_a_period_is_set(admin, fake_resend):
    from app.retention import apply_retention

    contact = make_contact(admin, "old@example.org")
    grant(admin, contact["id"])
    group = make_list(admin)
    add_to_list(admin, group["id"], [contact["id"]])
    template = make_template(admin)
    campaign = admin.post(
        "/api/campaigns", json={"name": "Old", "template_id": template["id"], "list_id": group["id"], "purpose": "marketing"}
    ).json()
    admin.post(f"/api/campaigns/{campaign['id']}/send")
    process_once(admin.app.state.settings)
    with connect(admin.app.state.settings.database_url) as conn:
        conn.execute("UPDATE sends SET created_at = now() - interval '400 days'")
        conn.execute("INSERT INTO form_submissions (contact_id, payload, created_at) VALUES (%s, '{}', now() - interval '400 days')", (contact["id"],))

    kept = apply_retention(admin.app.state.settings)
    assert "sends" not in kept and "form_submissions" not in kept

    removed = apply_retention(make_settings(send_log_retention_days=365, form_submission_retention_days=365))
    assert removed["sends"] == 1 and removed["form_submissions"] == 1


def test_one_click_unsubscribe_from_a_mail_client(admin):
    settings = admin.app.state.settings
    contact = make_contact(admin, "oneclick@example.org")
    grant(admin, contact["id"])
    client = build_client(make_settings(public_rate_limit=1), "admin")
    token = unsubscribe_token(settings, contact["id"], "marketing")
    for _ in range(3):  # never rate-limited, and repeating it is harmless
        response = client.post(
            f"/api/public/unsubscribe/{token}",
            content="List-Unsubscribe=One-Click",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
    assert admin.get(f"/api/contacts/{contact['id']}").json()["status"] == "unsubscribed"
    assert client.post("/api/public/unsubscribe/not-a-real-token-value").status_code == 400
