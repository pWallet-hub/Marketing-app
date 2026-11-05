"""Runtime settings, read from the environment. A missing required value stops the app at startup."""

import os
from dataclasses import dataclass


def _required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_secret: str
    https_only: bool
    keycloak_public_url: str  # browser-facing; Keycloak writes it into token issuers
    keycloak_internal_url: str  # server-to-server, on the Docker network
    keycloak_realm: str
    oidc_client_id: str
    oidc_client_secret: str
    public_base_url: str  # this backend's public address
    frontend_origin: str  # where users land after sign-in
    command_center_url: str  # internal address of the AFS hub backend
    service_token: str  # AFS_SERVICE_TOKEN_MARKETING, shared with the hub

    @property
    def issuer(self):
        return f"{self.keycloak_public_url.rstrip('/')}/realms/{self.keycloak_realm}"

    @property
    def internal_realm_url(self):
        return f"{self.keycloak_internal_url.rstrip('/')}/realms/{self.keycloak_realm}"

    @property
    def redirect_uri(self):
        return f"{self.public_base_url.rstrip('/')}/api/auth/callback"

    @classmethod
    def from_env(cls):
        secret = _required("SESSION_SECRET")
        if len(secret) < 32:
            raise RuntimeError("SESSION_SECRET must be at least 32 characters")
        return cls(
            database_url=_required("DATABASE_URL"),
            session_secret=secret,
            https_only=os.environ.get("SESSION_HTTPS_ONLY", "true").lower() == "true",
            keycloak_public_url=_required("KEYCLOAK_PUBLIC_URL"),
            keycloak_internal_url=_required("KEYCLOAK_INTERNAL_URL"),
            keycloak_realm=_required("KEYCLOAK_REALM"),
            oidc_client_id=_required("OIDC_CLIENT_ID"),
            oidc_client_secret=_required("OIDC_CLIENT_SECRET"),
            public_base_url=_required("PUBLIC_BASE_URL"),
            frontend_origin=_required("FRONTEND_ORIGIN"),
            command_center_url=_required("COMMAND_CENTER_URL"),
            service_token=_required("AFS_SERVICE_TOKEN_MARKETING"),
        )
