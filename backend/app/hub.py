"""Asks AFS Command Center whether an employee may use this application, and with which role.

Every request to this app goes through here, so removing an assignment in Command Center takes effect on the
next request, not when the session expires. If Command Center cannot be reached, access is refused.
"""

from dataclasses import dataclass

import httpx

APPLICATION_SLUG = "marketing"


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    external_role: str | None
    reason: str


def check_access(settings, subject):
    response = httpx.get(
        f"{settings.command_center_url.rstrip('/')}/api/internal/access",
        params={"application": APPLICATION_SLUG, "subject": subject},
        headers={"X-Service-Token": settings.service_token},
        timeout=5,
    )
    response.raise_for_status()
    body = response.json()
    # An assignment without a role is refused, as the integration rules require.
    allowed = bool(body.get("allowed")) and bool(body.get("external_role"))
    return AccessDecision(allowed=allowed, external_role=body.get("external_role"), reason=body.get("reason", ""))
