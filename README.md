# AFS Marketing Mailer

An independent application in the AFS collection. It sends marketing email to media contacts and partners, and to AFS employees. Email is sent through Resend.

Design: [DESIGN.md](DESIGN.md).

## Current state

- Backend skeleton: AFS SSO sign-in (authorization code with PKCE, verified ID token, nonce and state checks), an access check against AFS Command Center on every request, and a role dependency.
- Not built yet: contacts, consent, templates, campaigns, Resend sending, the Biocap blog-account step, and the frontend.

## Run the tests

The tests need no Keycloak or database:

```bash
docker run --rm -v "$PWD/backend":/app -w /app python:3.12-slim \
  sh -c "pip install -q -r requirements.txt && python -m pytest -q"
```

## Register with AFS (before it can sign anyone in)

These steps happen in the AFS hub repository and Command Center. This app does not change the hub.

1. Add `("marketing", "Marketing Mailer", "MARKETING")` to `APPLICATIONS` in `keycloak/bootstrap.py`, and seed the `marketing` application and its roles (`admin`, `member`) in a migration, as the other applications do.
2. Set `MARKETING_OIDC_CLIENT_SECRET`, `MARKETING_REDIRECT_URI` (this backend's `/api/auth/callback`), `MARKETING_ORIGIN` (the frontend), and `AFS_SERVICE_TOKEN_MARKETING` in the hub's `.env`.
3. Re-run `keycloak-init` so the `marketing` client is created.
4. In Command Center, set the application's launch URL, assign employees, then enable it.
