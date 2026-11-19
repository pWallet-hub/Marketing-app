"""Startup checks for production. With ENVIRONMENT=production the API and the worker refuse to start with placeholder
or short secrets, plain-HTTP public addresses, or cookies that may travel without HTTPS. Development is unchanged."""

import os
from urllib.parse import urlparse

MIN_SECRET_LENGTH = 24
PLACEHOLDER_MARKERS = ("change-me", "replace-with", "example", "local-only", "password")
SECRETS = ("SESSION_SECRET", "OIDC_CLIENT_SECRET", "AFS_SERVICE_TOKEN_MARKETING")
HTTPS_ADDRESSES = ("PUBLIC_BASE_URL", "FRONTEND_ORIGIN", "KEYCLOAK_PUBLIC_URL")


def production_problems(env=os.environ):
    if env.get("ENVIRONMENT", "development") != "production":
        return []
    problems = []
    for name in SECRETS:
        value = env.get(name, "")
        if len(value) < MIN_SECRET_LENGTH or any(marker in value.lower() for marker in PLACEHOLDER_MARKERS):
            problems.append(f"{name} must be a random value of at least {MIN_SECRET_LENGTH} characters, not a placeholder")
    password = urlparse(env.get("DATABASE_URL", "")).password or ""
    if len(password) < 16 or any(marker in password.lower() for marker in PLACEHOLDER_MARKERS):
        problems.append("POSTGRES_PASSWORD must be a random value of at least 16 characters")
    for name in HTTPS_ADDRESSES:
        if not env.get(name, "").startswith("https://"):
            problems.append(f"{name} must be an https:// address in production")
    if env.get("SESSION_HTTPS_ONLY", "true").lower() != "true":
        problems.append("SESSION_HTTPS_ONLY must be true in production")
    # Mail without a webhook secret would send, but bounces and complaints would never stop further mail.
    if env.get("RESEND_API_KEY") and not env.get("RESEND_WEBHOOK_SECRET", "").startswith("whsec_"):
        problems.append("RESEND_WEBHOOK_SECRET (whsec_...) is required once RESEND_API_KEY is set")
    return problems


def assert_production_ready(env=os.environ):
    problems = production_problems(env)
    if problems:
        raise RuntimeError("Refusing to start in production:\n- " + "\n- ".join(problems))
