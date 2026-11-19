"""Lists of contacts and email templates."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..common import audit
from ..db import connect
from ..deps import require_role
from ..render import render, unknown_placeholders
from .starters import STARTERS

router = APIRouter(prefix="/api", tags=["library"])
ALL_ROLES = require_role("admin", "member")


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class ListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class FilterIn(BaseModel):
    q: str = Field(default="", max_length=200)
    type: Literal["", "media", "partner", "staff"] = ""
    status: str = Field(default="", max_length=20)
    consent: Literal["", "marketing", "information_request"] = ""


class MembersIn(BaseModel):
    contact_ids: list[int] = Field(min_length=1, max_length=5000)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    body_html: str = Field(min_length=1, max_length=100_000)
    preheader: str = Field(default="", max_length=200)


class DraftPreviewIn(BaseModel):
    subject: str = Field(default="", max_length=200)
    body_html: str = Field(default="", max_length=100_000)
    preheader: str = Field(default="", max_length=200)


class PreviewIn(BaseModel):
    contact_id: int | None = None


def _check_template(body):
    bad = unknown_placeholders(body.subject) + unknown_placeholders(body.body_html) + unknown_placeholders(body.preheader)
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown placeholders: {', '.join(sorted(set(bad)))}")


@router.get("/lists")
def list_lists(request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        return conn.execute(
            "SELECT l.*, count(m.contact_id) AS members FROM lists l"
            " LEFT JOIN list_members m ON m.list_id = l.id GROUP BY l.id ORDER BY l.name"
        ).fetchall()


@router.post("/lists", status_code=201)
def create_list(body: ListIn, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        if conn.execute("SELECT 1 FROM lists WHERE lower(name) = lower(%s)", (body.name,)).fetchone():
            raise HTTPException(status_code=409, detail="A list with this name already exists")
        row = conn.execute(
            "INSERT INTO lists (name, description, created_by) VALUES (%s, %s, %s) RETURNING *",
            (body.name.strip(), body.description, user["email"] or ""),
        ).fetchone()
        audit(conn, user, "list.created", f"list:{row['id']}")
    return row


@router.patch("/lists/{list_id}")
def update_list(list_id: int, body: ListUpdate, request: Request, user=Depends(ALL_ROLES)):
    fields = {key: value.strip() for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if not fields:
        raise HTTPException(status_code=422, detail="Nothing to change")
    with connect(request.app.state.settings.database_url) as conn:
        if "name" in fields and conn.execute(
            "SELECT 1 FROM lists WHERE lower(name) = lower(%s) AND id <> %s", (fields["name"], list_id)
        ).fetchone():
            raise HTTPException(status_code=409, detail="A list with this name already exists")
        assignments = ", ".join(f"{key} = %s" for key in fields)
        row = conn.execute(
            f"UPDATE lists SET {assignments} WHERE id = %s RETURNING *", list(fields.values()) + [list_id]
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="List not found")
        audit(conn, user, "list.updated", f"list:{list_id}", {"fields": sorted(fields)})
    return row


@router.delete("/lists/{list_id}")
def delete_list(list_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        used = conn.execute("SELECT count(*) AS n FROM campaigns WHERE list_id = %s", (list_id,)).fetchone()["n"]
        if used:
            raise HTTPException(
                status_code=409, detail=f"This list is used by {used} campaign(s), so it is kept for their reports"
            )
        row = conn.execute("DELETE FROM lists WHERE id = %s RETURNING name", (list_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="List not found")
        audit(conn, user, "list.deleted", f"list:{list_id}", {"name": row["name"]})
    return {"ok": True}


@router.get("/lists/{list_id}")
def get_list(list_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        row = conn.execute(
            "SELECT l.*, count(m.contact_id) AS members,"
            " count(m.contact_id) FILTER (WHERE EXISTS (SELECT 1 FROM consents c WHERE c.contact_id = m.contact_id"
            "   AND c.purpose = 'marketing' AND c.withdrawn_at IS NULL)) AS with_marketing_consent,"
            " count(m.contact_id) FILTER (WHERE EXISTS (SELECT 1 FROM consents c WHERE c.contact_id = m.contact_id"
            "   AND c.purpose = 'information_request' AND c.withdrawn_at IS NULL)) AS with_information_consent"
            " FROM lists l LEFT JOIN list_members m ON m.list_id = l.id WHERE l.id = %s GROUP BY l.id",
            (list_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="List not found")
    return row


@router.post("/lists/{list_id}/members/by-filter", status_code=201)
def add_members_by_filter(list_id: int, body: FilterIn, request: Request, user=Depends(ALL_ROLES)):
    """Add every contact that matches a search (a saved segment, in other tools' terms)."""
    clauses, params = ["true"], []
    if body.q:
        clauses.append("(email ILIKE %s OR name ILIKE %s OR organisation ILIKE %s)")
        params += [f"%{body.q}%"] * 3
    if body.type:
        clauses.append("type = %s")
        params.append(body.type)
    if body.status:
        clauses.append("status = %s")
        params.append(body.status)
    if body.consent:
        clauses.append(
            "EXISTS (SELECT 1 FROM consents k WHERE k.contact_id = contacts.id AND k.purpose = %s AND k.withdrawn_at IS NULL)"
        )
        params.append(body.consent)
    with connect(request.app.state.settings.database_url) as conn:
        if conn.execute("SELECT 1 FROM lists WHERE id = %s", (list_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="List not found")
        added = conn.execute(
            "INSERT INTO list_members (list_id, contact_id)"
            f" SELECT %s, id FROM contacts WHERE {' AND '.join(clauses)} ON CONFLICT DO NOTHING",
            [list_id] + params,
        ).rowcount
        audit(conn, user, "list.members_added", f"list:{list_id}", {"count": added, "by_filter": body.model_dump()})
    return {"added": added}


@router.post("/lists/{list_id}/members", status_code=201)
def add_members(list_id: int, body: MembersIn, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        if conn.execute("SELECT 1 FROM lists WHERE id = %s", (list_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="List not found")
        found = conn.execute(
            "SELECT id FROM contacts WHERE id = ANY(%s)", (body.contact_ids,)
        ).fetchall()
        for row in found:
            conn.execute(
                "INSERT INTO list_members (list_id, contact_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (list_id, row["id"]),
            )
        audit(conn, user, "list.members_added", f"list:{list_id}", {"count": len(found)})
    return {"added": len(found), "not_found": len(set(body.contact_ids)) - len(found)}


@router.delete("/lists/{list_id}/members/{contact_id}")
def remove_member(list_id: int, contact_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        conn.execute("DELETE FROM list_members WHERE list_id = %s AND contact_id = %s", (list_id, contact_id))
        audit(conn, user, "list.member_removed", f"list:{list_id}", {"contact_id": contact_id})
    return {"ok": True}


@router.get("/lists/{list_id}/members")
def list_members(list_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        return conn.execute(
            "SELECT c.id, c.email, c.name, c.organisation, c.type, c.status FROM list_members m"
            " JOIN contacts c ON c.id = m.contact_id WHERE m.list_id = %s ORDER BY lower(c.name), c.id",
            (list_id,),
        ).fetchall()


@router.get("/templates")
def list_templates(request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        return conn.execute(
            "SELECT t.*, (SELECT count(*) FROM campaigns c WHERE c.template_id = t.id) AS used_by"
            " FROM templates t ORDER BY t.updated_at DESC"
        ).fetchall()


@router.get("/templates/starters")
def template_starters(user=Depends(ALL_ROLES)):
    """Ready-made designs to start a template from."""
    return STARTERS


@router.get("/templates/{template_id}")
def get_template(template_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        row = conn.execute("SELECT * FROM templates WHERE id = %s", (template_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return row


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn, request: Request, user=Depends(ALL_ROLES)):
    _check_template(body)
    with connect(request.app.state.settings.database_url) as conn:
        if conn.execute("SELECT 1 FROM templates WHERE lower(name) = lower(%s)", (body.name,)).fetchone():
            raise HTTPException(status_code=409, detail="A template with this name already exists")
        row = conn.execute(
            "INSERT INTO templates (name, subject, body_html, preheader, created_by) VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (body.name.strip(), body.subject, body.body_html, body.preheader, user["email"] or ""),
        ).fetchone()
        audit(conn, user, "template.created", f"template:{row['id']}")
    return row


@router.put("/templates/{template_id}")
def update_template(template_id: int, body: TemplateIn, request: Request, user=Depends(ALL_ROLES)):
    _check_template(body)
    with connect(request.app.state.settings.database_url) as conn:
        if conn.execute(
            "SELECT 1 FROM templates WHERE lower(name) = lower(%s) AND id <> %s", (body.name.strip(), template_id)
        ).fetchone():
            raise HTTPException(status_code=409, detail="A template with this name already exists")
        row = conn.execute(
            "UPDATE templates SET name = %s, subject = %s, body_html = %s, preheader = %s, updated_at = now()"
            " WHERE id = %s RETURNING *",
            (body.name.strip(), body.subject, body.body_html, body.preheader, template_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Template not found")
        audit(conn, user, "template.updated", f"template:{template_id}")
    return row


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        used = conn.execute("SELECT count(*) AS n FROM campaigns WHERE template_id = %s", (template_id,)).fetchone()["n"]
        if used:
            raise HTTPException(status_code=409, detail=f"This template is used by {used} campaign(s), so it is kept")
        row = conn.execute("DELETE FROM templates WHERE id = %s RETURNING name", (template_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Template not found")
        audit(conn, user, "template.deleted", f"template:{template_id}", {"name": row["name"]})
    return {"ok": True}


@router.post("/templates/{template_id}/duplicate", status_code=201)
def duplicate_template(template_id: int, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        template = conn.execute("SELECT * FROM templates WHERE id = %s", (template_id,)).fetchone()
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        name = f"{template['name']} (copy)"
        number = 2
        while conn.execute("SELECT 1 FROM templates WHERE lower(name) = lower(%s)", (name,)).fetchone():
            name = f"{template['name']} (copy {number})"
            number += 1
        row = conn.execute(
            "INSERT INTO templates (name, subject, body_html, preheader, created_by) VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (name[:120], template["subject"], template["body_html"], template["preheader"], user["email"] or ""),
        ).fetchone()
        audit(conn, user, "template.created", f"template:{row['id']}", {"copied_from": template_id})
    return row


def _sample_values(conn, contact_id):
    values = {"name": "Example Person", "organisation": "Example Media", "email": "person@example.org",
              "unsubscribe_url": "#unsubscribe", "form_url": "#form"}
    if contact_id:
        contact = conn.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,)).fetchone()
        if contact is None:
            raise HTTPException(status_code=404, detail="Contact not found")
        values.update(name=contact["name"], organisation=contact["organisation"], email=contact["email"])
    return values


SAMPLE_FOOTER = (
    '<div style="margin-top:12px">You are receiving this because you agreed to receive AFS news and marketing from AFS.'
    '<br><a href="#unsubscribe" style="color:#6b7280">Unsubscribe</a></div>'
)


def _rendered(settings, subject, body_html, preheader, values):
    pre = render(preheader, values, html=False)
    return {
        "subject": render(subject, values, html=False),
        "preheader": pre,
        "html": settings.layout(render(body_html, values), preheader=pre, footer_html=SAMPLE_FOOTER),
        "unknown_placeholders": sorted(set(unknown_placeholders(subject + body_html + preheader))),
    }


@router.post("/templates/preview")
def preview_draft(body: DraftPreviewIn, request: Request, user=Depends(ALL_ROLES)):
    """Render unsaved editor content in the full email layout, for the live preview."""
    settings = request.app.state.settings
    with connect(settings.database_url) as conn:
        values = _sample_values(conn, None)
    return _rendered(settings, body.subject, body.body_html, body.preheader, values)


@router.post("/templates/{template_id}/preview")
def preview_template(template_id: int, body: PreviewIn, request: Request, user=Depends(ALL_ROLES)):
    settings = request.app.state.settings
    with connect(settings.database_url) as conn:
        template = conn.execute("SELECT * FROM templates WHERE id = %s", (template_id,)).fetchone()
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        values = _sample_values(conn, body.contact_id)
    return _rendered(settings, template["subject"], template["body_html"], template["preheader"], values)
