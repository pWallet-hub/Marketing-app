# AFS Marketing Mailer

An independent application in the AFS collection. It sends marketing email to media contacts and partners, and information requests to AFS staff and partners. Email is sent through Resend. People sign in with AFS SSO, and Command Center decides who may use the app and with which role.

Design: [DESIGN.md](DESIGN.md). Deployment with Command Center: [deployment.md](../AFS-access_hub/docs/integrations/deployment.md).

## What it does

The app follows the usual shape of an email-marketing tool: a dashboard, campaigns with reports, contacts and lists,
templates with a visual editor, a do-not-contact list, and an activity log. Everything below is in the web app.

- **Dashboard**: sends, open, click and bounce rates over 30 days, a daily chart, audience and consent totals, recent and scheduled campaigns.
- **Campaigns**: create a draft (list, template, type, reply-to), see a live desktop and mobile preview and a ready-to-send checklist, send tests to up to five addresses, then send now or schedule for later (admins). Drafts can be edited, duplicated and deleted. Sent campaigns show a report: delivered, opened, clicked, bounced and unsubscribed, top links, and every recipient with a filter (opened, clicked, not opened, bounced, skipped).
- **Templates**: start from a design (newsletter, announcement, event, media invite, information request, plain letter), edit in a visual editor (headings, lists, links, buttons, images, dividers, personal fields) or as HTML, with a live preview. Every email is wrapped in the AFS layout: header, preview text, footer with postal address and unsubscribe link. Set the branding with `ORG_NAME`, `ORG_ADDRESS`, `ORG_WEBSITE` and `BRAND_COLOR`.
- **Lists**: create, rename and delete. Add contacts one by one, or everyone who matches a filter (type, consent, search). Each list shows how many people can receive each type of email.
- **Do not contact**: every unsubscribe, bounce, complaint and deletion, searchable. Admins can block an address by hand, and lift a manual block or a bounce. Unsubscribes and complaints cannot be lifted.
- **Activity log** (admins): every change, who made it and when.
- **Open and click tracking** comes from Resend's webhook (`email.opened`, `email.clicked`). Turn tracking on for the sending domain in Resend.

- **Contacts**: add by hand or import a CSV (admins), edit, filter by type, consent, status and list, export to CSV (admins). Each contact shows their emails, opens and clicks. Types: media, partner, staff.
- **Consent and suppression**: consent is recorded per purpose (marketing, information requests) with its source. Unsubscribes and bounces stop mail. Withdrawn consent is kept on record.
- **Lists and templates**: placeholders `{{name}}`, `{{organisation}}`, `{{email}}`, `{{unsubscribe_url}}`, `{{form_url}}`. Unknown placeholders are refused. Values are escaped in HTML.
- **Campaigns**: draft, test send (admin), send (admin). Recipients are fixed when a campaign is sent. Only people with the right consent who are not suppressed receive it. Skipped recipients are recorded with the reason.
- **Worker**: sends the queue through Resend with `Idempotency-Key` and `List-Unsubscribe` headers. Retries a failed send up to three times.
- **Webhooks**: Resend's delivered, bounced, complained and failed events, checked with Svix signatures. A bounce or complaint stops all mail to that address.
- **Unsubscribe page**: signed links, no sign-in needed.
- **Information forms**: one-time links (30 days, only a hash stored). A submission updates the contact and is forwarded to the target system when one is configured.
- **Media invite**: creates the person's blog account when Biocap is configured, then sends the invite. Requires marketing consent.
- **Audit log**: every change is recorded with the signed-in person.
- **Deleting a contact** (admins, for data-protection requests): removes the contact and everything held about them. By default the address stays on the do-not-contact list so an old import cannot add them back.
- **Rate limits** on the public unsubscribe and form pages (`PUBLIC_RATE_LIMIT` per minute per client; `TRUSTED_PROXY_HOPS` must match the proxies in front, 2 on Coolify).
- **Retention**: the worker removes expired form links, and send records and form submissions older than `SEND_LOG_RETENTION_DAYS` / `FORM_SUBMISSION_RETENTION_DAYS` once those are set (0 keeps them).

## Layout

| Path | What |
| --- | --- |
| `backend/` | FastAPI API (`app/`), SQL migrations, tests, Dockerfile |
| `backend/app/worker.py` | The mail worker. Runs as its own container. |
| `frontend/` | React app (Vite), served by nginx, which proxies `/api` to the backend |
| `tools/` | Stand-ins for Resend and the Command Center access check, for local checks only |
| `docker-compose.yml` | The one stack, for production (Coolify) and local: Postgres, API, worker, daily backup, web app |
| `.env.example` | Every variable, with the local-only block at the end |

## Run locally

There is one compose file. Its defaults are the production ones; a local `.env` (gitignored) switches it to local use.

1. Start the local AFS Command Center first (its Keycloak, backend and network are used for sign-in).
2. Copy `.env.example` to `.env`, fill in the secrets (the same client secret and service token as Command Center's
   `MARKETING_*` values) and uncomment the "Local only" block at the end.
3. Run:

```bash
docker compose up -d --build
```

- Web app: http://127.0.0.1:8200 (sign in with AFS SSO)
- API health: http://127.0.0.1:8200/api/health
- Emails "sent" locally: http://127.0.0.1:8025/log (the fake Resend, started by `COMPOSE_PROFILES=local`; nothing is delivered)

## Run the tests

The database tests need a separate database, so they never touch the local data:

```bash
docker compose exec db psql -U marketing -d marketing -c "CREATE DATABASE marketing_test"
docker run --rm --network marketing-app_default \
  -e TEST_DATABASE_URL=postgresql://marketing:marketing-local@db:5432/marketing_test \
  -v "$PWD/backend/tests":/app/tests:ro marketing-app-backend \
  python -m pytest -q tests
```

Without `TEST_DATABASE_URL`, the database tests are skipped and the rest still run.

## Register and deploy with AFS

See `docs/integrations/deployment.md` in the AFS hub. In short:

1. Add `marketing` to the hub's Keycloak clients (`keycloak/bootstrap.py`) and seed its application and roles.
2. Set `MARKETING_OIDC_CLIENT_SECRET`, `MARKETING_REDIRECT_URI`, `MARKETING_ORIGIN` and `AFS_SERVICE_TOKEN_MARKETING` in the hub's environment.
3. In Coolify, deploy this app as two services (API and web app) on one domain, plus the worker. The API handles `/api`, and the web app handles everything else.
4. Set the environment from `.env.example` (not its local-only block), including the Resend key and sending domain, the Resend webhook secret, and the Biocap and form-target settings when they are ready.

## Production

- `docker-compose.yml` defaults to `ENVIRONMENT=production`. The API and the worker then refuse to start with placeholder or short secrets, a weak database password, plain-HTTP addresses, or Resend configured without its webhook secret. The deploy log lists every problem.
- Emails carry a one-click `List-Unsubscribe` header (RFC 8058) that points to `/api/public/unsubscribe/<token>`. Gmail and Yahoo require this for bulk mail.
- Unsubscribe links are signed with `SESSION_SECRET`. Changing it signs everyone out and breaks the unsubscribe links in emails already sent, so keep it stable.
- The `backup` service writes a `pg_dump` every day to the `backups` volume and keeps 14 days. Copy that volume off the server as well; the restore command is in the compose file.
- The Resend webhook is `https://<app>/api/webhooks/resend` (events: delivered, bounced, complained, failed).
- The API runs as one process. The rate limiter keeps its counts in memory, so keep it to one replica.

## Not done yet

These need a decision or another team's work before the app is used with real people:

- **Real sign-in**: not tested against Keycloak or Command Center.
- **Real email**: not sent to a real inbox. Needs the Resend key, a verified sending subdomain, and the webhook registered in Resend.
- **Biocap blog accounts**: Biocap has no endpoint that accepts this app's token. Until it does, invites go out without an account and are marked `not_configured`.
- **Media joining through the hub**: linking a contact to their account when they join in Command Center is not built. It needs an event from the hub.
- **Form forwarding**: the target system is not chosen. Submissions are stored until it is.
- **Retention period**: the deletion is built, but the number of days is not decided. Until it is set, send records and form submissions are kept.
- **Biocap blog accounts on deletion**: deleting a contact does not remove their Biocap account; the app shows its id so it can be removed in Biocap.
- **Browser testing** of the screens while signed in.
