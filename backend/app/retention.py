"""Deletes old personal data on a schedule. Run by the worker.

- Expired form links are always removed 30 days after they expire: they no longer open anything.
- Send records and form submissions are removed only when a retention period is set (SEND_LOG_RETENTION_DAYS,
  FORM_SUBMISSION_RETENTION_DAYS). 0, the default, keeps them until the period is decided (DESIGN.md, open item 4).
  Queued sends are never removed. The audit log is kept.
"""

import logging

from .db import connect

log = logging.getLogger("marketing.retention")
EXPIRED_FORM_LINK_DAYS = 30


def apply_retention(settings):
    """Delete what is past its retention period. Returns the number of rows removed per table."""
    removed = {}
    with connect(settings.database_url) as conn:
        removed["form_tokens"] = conn.execute(
            "DELETE FROM form_tokens WHERE expires_at < now() - make_interval(days => %s)", (EXPIRED_FORM_LINK_DAYS,)
        ).rowcount
        if settings.form_submission_retention_days > 0:
            removed["form_submissions"] = conn.execute(
                "DELETE FROM form_submissions WHERE created_at < now() - make_interval(days => %s)",
                (settings.form_submission_retention_days,),
            ).rowcount
        if settings.send_log_retention_days > 0:
            removed["sends"] = conn.execute(
                "DELETE FROM sends WHERE status <> 'queued' AND created_at < now() - make_interval(days => %s)",
                (settings.send_log_retention_days,),
            ).rowcount
    if any(removed.values()):
        log.info("retention removed %s", removed)
    return removed
