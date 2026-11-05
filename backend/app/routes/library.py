"""Lists of contacts and email templates."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..common import audit
from ..db import connect
from ..deps import require_role
from ..render import TemplateError, render, unknown_placeholders

router = APIRouter(prefix="/api", tags=["library"])
ALL_ROLES = require_role("admin", "member")


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class MembersIn(BaseModel):
    contact_ids: list[int] = Field(min_length=1, max_length=5000)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=200)
    body_html: str = Field(min_length=1, max_length=100_000)


class PreviewIn(BaseModel):
    contact_id: int | None = None


def _check_template(body):
    bad = unknown_placeholders(body.subject) + unknown_placeholders(body.body_html)
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
        return conn.execute("SELECT * FROM templates ORDER BY name").fetchall()


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn, request: Request, user=Depends(ALL_ROLES)):
    _check_template(body)
    with connect(request.app.state.settings.database_url) as conn:
        if conn.execute("SELECT 1 FROM templates WHERE lower(name) = lower(%s)", (body.name,)).fetchone():
            raise HTTPException(status_code=409, detail="A template with this name already exists")
        row = conn.execute(
            "INSERT INTO templates (name, subject, body_html, created_by) VALUES (%s, %s, %s, %s) RETURNING *",
            (body.name.strip(), body.subject, body.body_html, user["email"] or ""),
        ).fetchone()
        audit(conn, user, "template.created", f"template:{row['id']}")
    return row


@router.put("/templates/{template_id}")
def update_template(template_id: int, body: TemplateIn, request: Request, user=Depends(ALL_ROLES)):
    _check_template(body)
    with connect(request.app.state.settings.database_url) as conn:
        row = conn.execute(
            "UPDATE templates SET name = %s, subject = %s, body_html = %s, updated_at = now() WHERE id = %s RETURNING *",
            (body.name.strip(), body.subject, body.body_html, template_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Template not found")
        audit(conn, user, "template.updated", f"template:{template_id}")
    return row


@router.post("/templates/{template_id}/preview")
def preview_template(template_id: int, body: PreviewIn, request: Request, user=Depends(ALL_ROLES)):
    with connect(request.app.state.settings.database_url) as conn:
        template = conn.execute("SELECT * FROM templates WHERE id = %s", (template_id,)).fetchone()
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        values = {"name": "Example Person", "organisation": "Example Media", "email": "person@example.org",
                  "unsubscribe_url": "#unsubscribe", "form_url": "#form"}
        if body.contact_id:
            contact = conn.execute("SELECT * FROM contacts WHERE id = %s", (body.contact_id,)).fetchone()
            if contact is None:
                raise HTTPException(status_code=404, detail="Contact not found")
            values.update(name=contact["name"], organisation=contact["organisation"], email=contact["email"])
    return {"subject": render(template["subject"], values, html=False), "html": render(template["body_html"], values)}
