-- People who have signed in to this app. Access itself is decided by AFS Command Center on every request;
-- this table only holds the profile shown in the app, keyed by the Keycloak subject.
CREATE TABLE app_users (
    id              bigserial PRIMARY KEY,
    keycloak_sub    text NOT NULL UNIQUE,
    email           text,
    name            text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_sign_in_at timestamptz NOT NULL DEFAULT now()
);
