"""Helpers shared by the route modules: validation, paging, audit logging, and the database handle."""

import re

from psycopg.types.json import Jsonb

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTACT_TYPES = ("media", "partner", "staff")
PURPOSES = ("marketing", "information_request")


def valid_email(value):
    return isinstance(value, str) and len(value) <= 254 and bool(EMAIL_PATTERN.match(value))


def page_params(limit, offset):
    return min(max(limit, 1), 200), max(offset, 0)


def audit(conn, user, action, target="", detail=None):
    conn.execute(
        "INSERT INTO audit_log (actor_sub, actor_email, action, target, detail) VALUES (%s, %s, %s, %s, %s)",
        (user["sub"], user.get("email") or "", action, target, Jsonb(detail or {})),
    )


def database_url(request):
    return request.app.state.settings.database_url
