# Marketing Mailer — design

Status: draft for review. Independent application in the AFS collection. It has its own code, database and deployment. Command Center registers it only for SSO and access checks.

## Decisions (confirmed)

1. Two audiences are handled by this app: external contacts (media personnel, partner blogs such as Biocap) and AFS employees (procurement, orders, missions, information collection).
2. Media contacts get a default AFS blog account, created through the Biocap backend with the `media_correspondent` role, following [docs/integrations/biocap.md](../AFS-access_hub/docs/integrations/biocap.md).
3. AFS employees use the app. They sign in through AFS SSO.
4. Email is sent with Resend.
5. The app is independent. It is not part of the AFS-access_hub code.

## Architecture

The API and the web app share one public address. The web app proxies `/api` to the API, so one sign-in cookie covers both and the redirect URI is `https://<app>/api/auth/callback`.

| Part | Choice |
| --- | --- |
| Backend | Python FastAPI, PostgreSQL (same stack family as the hub's backend; confirm before coding) |
| Frontend | React, served by nginx |
| Sign-in | Keycloak client `marketing`, PKCE, owned by the backend (same pattern as Biocap) |
| Access | `GET /api/internal/access?application=marketing&subject=<sub>` with `X-Service-Token`, as in the hub |
| Email | Resend HTTP API, from a marketing subdomain that is separate from the hub's transactional sender |
| Blog accounts | Biocap backend admin-users API, called with its own service token |
| Background sends | A worker process reads queued sends, so a campaign does not block a request |

Registration in the hub (Command Center, `docs/integrations/README.md`):
- Application slug `marketing`, launch URL = the marketing frontend.
- Env prefix `MARKETING_`, Keycloak client `marketing`, service token `AFS_SERVICE_TOKEN_MARKETING`.
- Roles to seed: `admin` (manage everything, send campaigns) and `member` (view and draft). Assignments come from Command Center.

## Users and roles

- **App users** are AFS employees. Roles come from Command Center on every sign-in, as in the integration rules.
- **Contacts** are recipients. They are not app users. They have a type: `media`, `partner`, or `staff`.

## Data model

- `contacts`: id, name, email, organisation, type (`media` | `partner` | `staff`), status (`invited` | `joined` | `unsubscribed` | `bounced`), keycloak_sub (nullable, set only after a verified-email link), blog_account_id (nullable), created_by, created_at.
- `consents`: contact_id, purpose, source, given_at, withdrawn_at. Marketing and information-collection consent are recorded separately.
- `suppressions`: email (unique), reason. Checked before every send.
- `lists`, `list_members`: named audiences built from contacts.
- `templates`: name, subject, body (with variables), owner.
- `campaigns`: template_id, list_id, status (`draft` | `scheduled` | `sending` | `done`), scheduled_for, created_by.
- `sends`: campaign_id, contact_id, status, resend_message_id, error, sent_at. Also holds a per-recipient token for forms and unsubscribe.
- `audit_log`: actor, action, target, detail, at.

## Flows

### Media contact (invite and join)

1. An admin adds a media contact (or imports a list). Status: `invited`.
2. The app creates a blog account through the Biocap backend (`media_correspondent`) and stores `blog_account_id`.
3. The invite email tells them they already have a blog account and invites them to join the hub.
4. They sign up through Keycloak. The link to the contact is made only when Keycloak reports a verified email and the contact has no `keycloak_sub`, as the integration rules require.
5. After joining, they get access to the app directory through the hub's own grants. Status: `joined`.

### Partner and staff outreach (information collection)

1. A campaign sends each recipient a personal link to a form (their details, procurement, orders, missions).
2. Submitted data is sent to the target system. It is not kept in the marketing app beyond the send record.
3. Staff records are kept in Command Center's Employees section as the source of truth. This app sends only what is needed to update them.

### Sending

- A campaign is previewed and sent to a test address first.
- Suppressions and unsubscribes are checked for every recipient.
- Each send is logged with Resend's message id. Bounces and complaints update contact status.
- Every send includes an unsubscribe link (one-click, per recipient token).

## Consent and data protection

- Record consent per purpose, with its source and date.
- Staff information collection and marketing use different consent records.
- Rwanda's personal data protection law applies. Review the consent wording and the retention period with whoever handles compliance before launch.

## Open items (to confirm before coding)

1. The Biocap account API. The Biocap guide (Step 0) has security prerequisites: the hardcoded database URI, the JWT algorithm, and the unguarded routes. The account-creation endpoint must be added and tested after those fixes. Confirm which Biocap endpoint creates users, and whether it accepts a service token.
2. The backend language and database. The hub uses FastAPI and PostgreSQL. Confirm that this app should match.
3. The marketing subdomain for Resend.
4. Retention period for contacts and send logs.

## Build order

1. Backend skeleton, database, and the Keycloak SSO flow with the access check.
2. Contacts, consents, suppressions, and the import.
3. Templates and a test send through Resend.
4. Campaigns with the worker, unsubscribe, and bounce handling.
5. Media invite flow, including the Biocap account call.
6. Staff and partner form flow.
7. Register in Command Center, enable after tests pass.
