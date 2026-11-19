"""Scheduling, editing, tracking, reports, lists, templates, suppressions, export and the activity log."""

import json
import time
from datetime import datetime, timedelta, timezone

from app.db import connect
from app.queue import process_once, start_due_campaigns
from tests.conftest import build_client, make_settings, requires_db
from tests.test_marketing import add_to_list, fake_resend, grant, make_contact, make_list, make_template  # noqa: F401
from tests.test_units import svix_headers

pytestmark = requires_db


def draft(client, **extra):
    template = extra.pop("template", None) or make_template(client, name=f"T{time.time_ns()}")
    group = extra.pop("group", None) or make_list(client, name=f"L{time.time_ns()}")
    body = {"name": "Spring", "template_id": template["id"], "list_id": group["id"], "purpose": "marketing", **extra}
    response = client.post("/api/campaigns", json=body)
    assert response.status_code == 201, response.text
    return response.json(), template, group


def sent_campaign(client, email="reader@example.org"):
    contact = make_contact(client, email, name="Reader")
    grant(client, contact["id"])
    campaign, template, group = draft(client)
    add_to_list(client, group["id"], [contact["id"]])
    assert client.post(f"/api/campaigns/{campaign['id']}/send").status_code == 200
    process_once(client.app.state.settings)
    return campaign, contact


def webhook(client, kind, message_id, **data):
    body = json.dumps({"type": kind, "data": {"email_id": message_id, **data}}).encode()
    response = client.post("/api/webhooks/resend", content=body, headers=svix_headers(body, timestamp=int(time.time())))
    assert response.status_code == 200, response.text


def test_emails_use_the_branded_layout_with_preheader_and_reply_to(admin, fake_resend):
    template = admin.post(
        "/api/templates",
        json={"name": "Branded", "subject": "Hi {{name}}", "body_html": "<p>Body</p>", "preheader": "Peek {{name}}"},
    ).json()
    contact = make_contact(admin, "brand@example.org", name="Bea")
    grant(admin, contact["id"])
    group = make_list(admin, "Brand list")
    add_to_list(admin, group["id"], [contact["id"]])
    campaign = admin.post(
        "/api/campaigns",
        json={"name": "B", "template_id": template["id"], "list_id": group["id"], "purpose": "marketing", "reply_to": "press@afs.example.org"},
    ).json()
    admin.post(f"/api/campaigns/{campaign['id']}/send")
    process_once(admin.app.state.settings)
    message = fake_resend.sent[0]
    assert "Alliance for Science Rwanda" in message["html"] and "Peek Bea" in message["html"]
    assert "Unsubscribe" in message["html"] and message["reply_to"] == "press@afs.example.org"


def test_invalid_reply_to_is_refused(admin):
    template = make_template(admin)
    group = make_list(admin)
    response = admin.post(
        "/api/campaigns",
        json={"name": "X", "template_id": template["id"], "list_id": group["id"], "purpose": "marketing", "reply_to": "nope"},
    )
    assert response.status_code == 422


def test_drafts_can_be_edited_duplicated_and_deleted_but_sent_ones_cannot(admin, fake_resend):
    campaign, _, _ = draft(admin)
    assert admin.patch(f"/api/campaigns/{campaign['id']}", json={"name": "Renamed"}).json()["name"] == "Renamed"
    copy = admin.post(f"/api/campaigns/{campaign['id']}/duplicate").json()
    assert copy["name"] == "Renamed (copy)" and copy["status"] == "draft"
    assert admin.delete(f"/api/campaigns/{copy['id']}").status_code == 200

    sent, _ = sent_campaign(admin)
    assert admin.patch(f"/api/campaigns/{sent['id']}", json={"name": "Late"}).status_code == 409
    assert admin.delete(f"/api/campaigns/{sent['id']}").status_code == 409


def test_scheduled_campaign_starts_when_due_and_can_be_unscheduled(admin, fake_resend):
    contact = make_contact(admin, "later@example.org")
    grant(admin, contact["id"])
    campaign, _, group = draft(admin)
    add_to_list(admin, group["id"], [contact["id"]])

    too_soon = datetime.now(timezone.utc) + timedelta(seconds=30)
    assert admin.post(f"/api/campaigns/{campaign['id']}/schedule", json={"send_at": too_soon.isoformat()}).status_code == 422
    send_at = datetime.now(timezone.utc) + timedelta(hours=1)
    scheduled = admin.post(f"/api/campaigns/{campaign['id']}/schedule", json={"send_at": send_at.isoformat()}).json()
    assert scheduled["status"] == "scheduled"

    settings = admin.app.state.settings
    assert start_due_campaigns(settings) == 0
    assert admin.post(f"/api/campaigns/{campaign['id']}/unschedule").json()["status"] == "draft"
    admin.post(f"/api/campaigns/{campaign['id']}/schedule", json={"send_at": send_at.isoformat()})
    with connect(settings.database_url) as conn:
        conn.execute("UPDATE campaigns SET scheduled_for = now() - interval '1 minute' WHERE id = %s", (campaign["id"],))
    assert start_due_campaigns(settings) == 1
    process_once(settings)
    assert admin.get(f"/api/campaigns/{campaign['id']}").json()["status"] == "done"
    assert fake_resend.sent[0]["to"] == "later@example.org"


def test_members_cannot_send_or_schedule(admin, member):
    campaign, _, _ = draft(admin)
    later = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert member.post(f"/api/campaigns/{campaign['id']}/schedule", json={"send_at": later}).status_code == 403
    assert member.post(f"/api/campaigns/{campaign['id']}/send").status_code == 403


def test_opens_and_clicks_feed_the_report(admin, fake_resend):
    campaign, contact = sent_campaign(admin)
    with connect(admin.app.state.settings.database_url) as conn:
        message_id = conn.execute("SELECT resend_message_id FROM sends WHERE campaign_id = %s", (campaign["id"],)).fetchone()[
            "resend_message_id"
        ]
    webhook(admin, "email.delivered", message_id)
    webhook(admin, "email.opened", message_id)
    webhook(admin, "email.opened", message_id)
    webhook(admin, "email.clicked", message_id, click={"link": "https://afs.example.org/story"})

    report = admin.get(f"/api/campaigns/{campaign['id']}/report").json()
    stats = report["stats"]
    assert (stats["delivered"], stats["opened"], stats["clicked"]) == (1, 1, 1)
    assert stats["open_rate"] == 100.0 and stats["click_rate"] == 100.0
    assert report["links"][0]["link"] == "https://afs.example.org/story"
    assert report["items"][0]["open_count"] == 2
    assert admin.get(f"/api/campaigns/{campaign['id']}/report?filter=not_opened").json()["total"] == 0
    activity = admin.get(f"/api/contacts/{contact['id']}").json()["activity"]
    assert {a["type"] for a in activity} == {"delivered", "opened", "clicked"}
    assert admin.get("/api/dashboard").json()["engagement_30_days"]["opened"] == 1


def test_campaign_preview_counts_who_will_receive_it(admin):
    yes = make_contact(admin, "yes@example.org")
    grant(admin, yes["id"])
    no = make_contact(admin, "no@example.org")
    campaign, _, group = draft(admin)
    add_to_list(admin, group["id"], [yes["id"], no["id"]])
    preview = admin.get(f"/api/campaigns/{campaign['id']}/preview").json()
    assert (preview["eligible"], preview["will_skip"]) == (1, 1)
    assert "<!doctype html>" in preview["html"]


def test_test_send_goes_to_several_addresses(admin, fake_resend, monkeypatch):
    from app.routes import campaigns as campaigns_module

    monkeypatch.setattr(campaigns_module, "send_email", fake_resend)
    campaign, _, _ = draft(admin)
    response = admin.post(f"/api/campaigns/{campaign['id']}/test", json={"emails": ["a@example.org", "b@example.org"]})
    assert response.status_code == 200
    assert [m["to"] for m in fake_resend.sent] == ["a@example.org", "b@example.org"]
    assert all(m["subject"].startswith("[Test]") for m in fake_resend.sent)


def test_lists_can_be_renamed_filled_by_filter_and_deleted_when_unused(admin):
    for n in range(3):
        contact = make_contact(admin, f"m{n}@example.org", type="media")
        if n < 2:
            grant(admin, contact["id"])
    make_contact(admin, "p@example.org", type="partner")
    group = make_list(admin, "Media")
    assert admin.patch(f"/api/lists/{group['id']}", json={"name": "Media desk"}).json()["name"] == "Media desk"
    added = admin.post(f"/api/lists/{group['id']}/members/by-filter", json={"type": "media", "consent": "marketing"}).json()
    assert added["added"] == 2
    assert admin.get(f"/api/lists/{group['id']}").json()["with_marketing_consent"] == 2
    assert admin.get(f"/api/contacts?list_id={group['id']}").json()["total"] == 2
    assert admin.delete(f"/api/lists/{group['id']}").status_code == 200

    used, _, used_list = draft(admin)
    assert admin.delete(f"/api/lists/{used_list['id']}").status_code == 409


def test_templates_have_starters_live_preview_duplicate_and_delete(admin):
    starters = admin.get("/api/templates/starters").json()
    assert {s["key"] for s in starters} >= {"newsletter", "announcement", "information_request"}
    preview = admin.post("/api/templates/preview", json={"subject": "Hi {{name}}", "body_html": "<p>{{bogus}}</p>"}).json()
    assert preview["subject"] == "Hi Example Person" and preview["unknown_placeholders"] == ["bogus"]

    template = make_template(admin, name="Original")
    copy = admin.post(f"/api/templates/{template['id']}/duplicate").json()
    assert copy["name"] == "Original (copy)"
    assert admin.delete(f"/api/templates/{copy['id']}").status_code == 200
    draft(admin, template=template)
    assert admin.delete(f"/api/templates/{template['id']}").status_code == 409


def test_suppression_list_protects_unsubscribes(admin):
    added = admin.post("/api/suppressions", json={"email": "Block@Example.org"}).json()
    assert added["email"] == "block@example.org" and added["reason"] == "manual"
    assert admin.post("/api/suppressions", json={"email": "block@example.org"}).status_code == 409
    with connect(admin.app.state.settings.database_url) as conn:
        unsub = conn.execute(
            "INSERT INTO suppressions (email, purpose, reason) VALUES ('gone@example.org', 'marketing', 'unsubscribed') RETURNING id"
        ).fetchone()["id"]
    listing = admin.get("/api/suppressions").json()
    assert listing["total"] == 2 and listing["reasons"] == {"manual": 1, "unsubscribed": 1}
    assert admin.delete(f"/api/suppressions/{unsub}").status_code == 409
    assert admin.delete(f"/api/suppressions/{added['id']}").status_code == 200


def test_members_cannot_change_suppressions_or_read_the_activity_log(admin, member):
    assert member.post("/api/suppressions", json={"email": "x@example.org"}).status_code == 403
    assert member.get("/api/audit").status_code == 403
    assert member.get("/api/contacts/export").status_code == 403


def test_export_is_csv_and_neutralises_formulas(admin):
    make_contact(admin, "csv@example.org", name="=HYPERLINK(1)", organisation="AFS")
    response = admin.get("/api/contacts/export")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("email,name") and "'=HYPERLINK(1)" in lines[1]


def test_activity_log_lists_changes_newest_first(admin):
    make_list(admin, "Logged")
    log = admin.get("/api/audit").json()
    assert log["items"][0]["action"] == "list.created"
    assert admin.get("/api/audit?action=list.").json()["total"] >= 1


def test_settings_show_branding_without_secrets(admin):
    settings = admin.get("/api/settings").json()
    assert settings["org_name"] == "Alliance for Science Rwanda" and settings["mail_configured"] is True
    assert not any("re_test" in str(v) for v in settings.values())
