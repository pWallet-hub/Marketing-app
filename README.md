# AFS Marketing Mailer

An independent application in the AFS collection. It sends marketing email to media contacts and partners, and information requests to AFS staff and partners. Email is sent through Resend. People sign in with AFS SSO, and Command Center decides who may use the app and with which role.

Design: [DESIGN.md](DESIGN.md). Deployment with Command Center: [deployment.md](../AFS-access_hub/docs/integrations/deployment.md).

## What it does

- **Contacts**: add by hand or import a CSV (admins). Types: media, partner, staff.
- **Consent and suppression**: consent is recorded per purpose (marketing, information requests) with its source. Unsubscribes and bounces stop mail. Withdrawn consent is kept on record.
- **Lists and templates**: placeholders `{{name}}`, `{{organisation}}`, `{{email}}`, `{{unsubscribe_url}}`, `{{form_url}}`. Unknown placeholders are refused. Values are escaped in HTML.
- **Campaigns**: draft, test send (admin), send (admin). Recipients are fixed when a campaign is sent. Only people with the right consent who are not suppressed receive it. Skipped recipients are recorded with the reason.
- **Worker**: sends the queue through Resend with `Idempotency-Key` and `List-Unsubscribe` headers. Retries a failed send up to three times.
- **Webhooks**: Resend's delivered, bounced, complained and failed events, checked with Svix signatures. A bounce or complaint stops all mail to that address.
- **Unsubscribe page**: signed links, no sign-in needed.
- **Information forms**: one-time links (30 days, only a hash stored). A submission updates the contact and is forwarded to the target system when one is configured.
- **Media invite**: creates the person's blog account when Biocap is configured, then sends the invite. Requires marketing consent.
- **Audit log**: every change is recorded with the signed-in person.

## Layout

| Path | What |
| --- | --- |
| `backend/` | FastAPI API (`app/`), SQL migrations, tests, Dockerfile |
| `backend/app/worker.py` | The mail worker. Runs as its own container. |
| `frontend/` | React app (Vite), served by nginx, which proxies `/api` to the backend |
| `tools/` | Stand-ins for Resend and the Command Center access check, for local checks only |
| `docker-compose.yml` | Local stack: Postgres, API, worker, web app |

## Run locally

Local values are in `backend/.env.local`. They are for this machine only. Real deployments use Coolify variables, as `backend/.env.example` shows.

```bash
docker compose up -d --build
```

- Web app: http://127.0.0.1:8200
- API health: http://127.0.0.1:8200/api/health

Sign-in cannot complete locally: Keycloak and Command Center are not part of this stack.

## Run the tests

The database tests need a separate database, so they never touch the local data:

```bash
docker compose exec db psql -U marketing -d marketing -c "CREATE DATABASE marketing_test"
docker run --rm --network marketing-mailer_default \
  -e TEST_DATABASE_URL=postgresql://marketing:marketing-local@db:5432/marketing_test \
  -v "$PWD/backend/tests":/app/tests:ro marketing-mailer-backend \
  python -m pytest -q tests
```

Without `TEST_DATABASE_URL`, the database tests are skipped and the rest still run.

## Register and deploy with AFS

See `docs/integrations/deployment.md` in the AFS hub. In short:

1. Add `marketing` to the hub's Keycloak clients (`keycloak/bootstrap.py`) and seed its application and roles.
2. Set `MARKETING_OIDC_CLIENT_SECRET`, `MARKETING_REDIRECT_URI`, `MARKETING_ORIGIN` and `AFS_SERVICE_TOKEN_MARKETING` in the hub's environment.
3. In Coolify, deploy this app as two services (API and web app) on one domain, plus the worker. The API handles `/api`, and the web app handles everything else.
4. Set the environment from `backend/.env.example`, including the Resend key and sending domain, the Resend webhook secret, and the Biocap and form-target settings when they are ready.

## Not done yet

These need a decision or another team's work before the app is used with real people:

- **Real sign-in**: not tested against Keycloak or Command Center.
- **Real email**: not sent to a real inbox. Needs the Resend key, a verified sending subdomain, and the webhook registered in Resend.
- **Biocap blog accounts**: Biocap has no endpoint that accepts this app's token. Until it does, invites go out without an account and are marked `not_configured`.
- **Media joining through the hub**: linking a contact to their account when they join in Command Center is not built. It needs an event from the hub.
- **Form forwarding**: the target system is not chosen. Submissions are stored until it is.
- **Deleting a contact** (for data-protection requests): not built.
- **Retention**: no automatic deletion of old send logs or form submissions.
- **Rate limits** on the public unsubscribe and form endpoints.
- **Browser testing** of the screens while signed in.
