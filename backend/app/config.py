"""Runtime settings, read from the environment. A missing required value stops the app at startup.

Optional values switch features on. Without RESEND_API_KEY nothing is sent, and campaigns wait in the queue.
"""

import os
from dataclasses import dataclass


def _required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def _optional(name, default=""):
    return os.environ.get(name, default).strip()


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
    public_base_url: str  # this app's public address (frontend and API share it)
    frontend_origin: str  # same as public_base_url in the standard deployment
    command_center_url: str  # internal address of the AFS hub backend
    service_token: str  # AFS_SERVICE_TOKEN_MARKETING, shared with the hub
    # Mail (Resend)
    resend_api_key: str = ""
    resend_from: str = ""
    resend_from_name: str = "AFS"
    resend_webhook_secret: str = ""
    resend_api_base: str = "https://api.resend.com"
    send_interval_seconds: float = 0.6  # Resend allows 2 requests a second by default
    # Blog accounts (Biocap). Empty means the step is not configured and invites skip it.
    biocap_account_url: str = ""
    biocap_account_token: str = ""
    # Where submitted information forms are forwarded. Empty means they are stored here only.
    form_target_url: str = ""
    form_target_token: str = ""

    @property
    def issuer(self):
        return f"{self.keycloak_public_url.rstrip('/')}/realms/{self.keycloak_realm}"

    @property
    def internal_realm_url(self):
        return f"{self.keycloak_internal_url.rstrip('/')}/realms/{self.keycloak_realm}"

    @property
    def redirect_uri(self):
        return f"{self.public_base_url.rstrip('/')}/api/auth/callback"

    @property
    def mail_configured(self):
        return bool(self.resend_api_key and self.resend_from)

    @classmethod
    def from_env(cls):
        secret = _required("SESSION_SECRET")
        if len(secret) < 32:
            raise RuntimeError("SESSION_SECRET must be at least 32 characters")
        return cls(
            database_url=_required("DATABASE_URL"),
            session_secret=secret,
            https_only=_optional("SESSION_HTTPS_ONLY", "true").lower() == "true",
            keycloak_public_url=_required("KEYCLOAK_PUBLIC_URL"),
            keycloak_internal_url=_required("KEYCLOAK_INTERNAL_URL"),
            keycloak_realm=_required("KEYCLOAK_REALM"),
            oidc_client_id=_required("OIDC_CLIENT_ID"),
            oidc_client_secret=_required("OIDC_CLIENT_SECRET"),
            public_base_url=_required("PUBLIC_BASE_URL"),
            frontend_origin=_required("FRONTEND_ORIGIN"),
            command_center_url=_required("COMMAND_CENTER_URL"),
            service_token=_required("AFS_SERVICE_TOKEN_MARKETING"),
            resend_api_key=_optional("RESEND_API_KEY"),
            resend_from=_optional("RESEND_FROM"),
            resend_from_name=_optional("RESEND_FROM_NAME", "AFS"),
            resend_webhook_secret=_optional("RESEND_WEBHOOK_SECRET"),
            resend_api_base=_optional("RESEND_API_BASE", "https://api.resend.com"),
            send_interval_seconds=float(_optional("SEND_INTERVAL_SECONDS", "0.6")),
            biocap_account_url=_optional("BIOCAP_ACCOUNT_URL"),
            biocap_account_token=_optional("BIOCAP_ACCOUNT_TOKEN"),
            form_target_url=_optional("FORM_TARGET_URL"),
            form_target_token=_optional("FORM_TARGET_TOKEN"),
        )
