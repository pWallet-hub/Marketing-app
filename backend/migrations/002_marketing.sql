-- Contacts: media personnel, partner blogs, and AFS staff who receive outreach.
CREATE TABLE contacts (
    id              bigserial PRIMARY KEY,
    email           text NOT NULL,
    name            text NOT NULL DEFAULT '',
    organisation    text NOT NULL DEFAULT '',
    phone           text NOT NULL DEFAULT '',
    type            text NOT NULL CHECK (type IN ('media', 'partner', 'staff')),
    status          text NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new', 'invited', 'joined', 'unsubscribed', 'bounced', 'complained')),
    keycloak_sub    text UNIQUE,
    blog_account_id text,
    notes           text NOT NULL DEFAULT '',
    created_by      text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX contacts_email_lower ON contacts (lower(email));

-- Consent is recorded per purpose, with where it came from. Withdrawn consent is kept for the record.
CREATE TABLE consents (
    id           bigserial PRIMARY KEY,
    contact_id   bigint NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    purpose      text NOT NULL CHECK (purpose IN ('marketing', 'information_request')),
    source       text NOT NULL,
    given_at     timestamptz NOT NULL DEFAULT now(),
    withdrawn_at timestamptz
);
CREATE UNIQUE INDEX consents_one_active ON consents (contact_id, purpose) WHERE withdrawn_at IS NULL;

-- Addresses that must not receive a purpose (or any mail, when purpose is 'all').
CREATE TABLE suppressions (
    id         bigserial PRIMARY KEY,
    email      text NOT NULL,
    purpose    text NOT NULL CHECK (purpose IN ('marketing', 'information_request', 'all')),
    reason     text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (email, purpose)
);

CREATE TABLE lists (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    description text NOT NULL DEFAULT '',
    created_by  text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE list_members (
    list_id    bigint NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    contact_id bigint NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    added_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (list_id, contact_id)
);

CREATE TABLE templates (
    id         bigserial PRIMARY KEY,
    name       text NOT NULL UNIQUE,
    subject    text NOT NULL,
    body_html  text NOT NULL,
    created_by text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE campaigns (
    id         bigserial PRIMARY KEY,
    name       text NOT NULL,
    template_id bigint NOT NULL REFERENCES templates(id),
    -- A campaign goes to a list, or to one contact (used for media invites). Exactly one is set.
    list_id           bigint REFERENCES lists(id),
    single_contact_id bigint REFERENCES contacts(id),
    CHECK ((list_id IS NULL) <> (single_contact_id IS NULL)),
    purpose    text NOT NULL CHECK (purpose IN ('marketing', 'information_request')),
    status     text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'sending', 'done')),
    created_by text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at    timestamptz
);

-- One row per recipient per campaign. A row is created when a campaign is sent, so the recipient list is fixed then.
CREATE TABLE sends (
    id                bigserial PRIMARY KEY,
    campaign_id       bigint NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    contact_id        bigint NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    email             text NOT NULL,
    status            text NOT NULL CHECK (status IN ('queued', 'sent', 'delivered', 'bounced', 'complained', 'failed', 'skipped')),
    skip_reason       text,
    resend_message_id text UNIQUE,
    attempts          int NOT NULL DEFAULT 0,
    error             text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    sent_at           timestamptz,
    UNIQUE (campaign_id, contact_id)
);
CREATE INDEX sends_queue ON sends (status, id) WHERE status = 'queued';

-- Form links for information requests. Only a hash of the token is stored.
CREATE TABLE form_tokens (
    id         bigserial PRIMARY KEY,
    token_hash text NOT NULL UNIQUE,
    contact_id bigint NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    send_id    bigint REFERENCES sends(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    used_at    timestamptz
);

CREATE TABLE form_submissions (
    id               bigserial PRIMARY KEY,
    contact_id       bigint NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    payload          jsonb NOT NULL,
    forward_status   text NOT NULL DEFAULT 'stored',
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
    id          bigserial PRIMARY KEY,
    actor_sub   text NOT NULL DEFAULT '',
    actor_email text NOT NULL DEFAULT '',
    action      text NOT NULL,
    target      text NOT NULL DEFAULT '',
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb,
    at          timestamptz NOT NULL DEFAULT now()
);
