-- Standard email-marketing features: preheaders, reply-to, scheduling, and open/click tracking.

-- The short line mail clients show after the subject.
ALTER TABLE templates ADD COLUMN preheader text NOT NULL DEFAULT '';

-- Campaigns can be scheduled, and carry an optional reply-to address.
ALTER TABLE campaigns ADD COLUMN reply_to text NOT NULL DEFAULT '';
ALTER TABLE campaigns ADD COLUMN scheduled_for timestamptz;
ALTER TABLE campaigns ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE campaigns DROP CONSTRAINT campaigns_status_check;
ALTER TABLE campaigns ADD CONSTRAINT campaigns_status_check CHECK (status IN ('draft', 'scheduled', 'sending', 'done'));
ALTER TABLE campaigns ADD CONSTRAINT campaigns_scheduled_has_time CHECK (status <> 'scheduled' OR scheduled_for IS NOT NULL);
CREATE INDEX campaigns_due ON campaigns (scheduled_for) WHERE status = 'scheduled';

-- Engagement per recipient. Resend reports opens and clicks when tracking is on for the sending domain.
ALTER TABLE sends ADD COLUMN delivered_at timestamptz;
ALTER TABLE sends ADD COLUMN opened_at timestamptz;
ALTER TABLE sends ADD COLUMN clicked_at timestamptz;
ALTER TABLE sends ADD COLUMN open_count int NOT NULL DEFAULT 0;
ALTER TABLE sends ADD COLUMN click_count int NOT NULL DEFAULT 0;

-- Every delivery event, for reports (link clicks) and the contact's activity.
CREATE TABLE send_events (
    id      bigserial PRIMARY KEY,
    send_id bigint NOT NULL REFERENCES sends(id) ON DELETE CASCADE,
    type    text NOT NULL,
    link    text,
    at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX send_events_send ON send_events (send_id);

-- The activity log is read newest first.
CREATE INDEX audit_log_at ON audit_log (at DESC);
