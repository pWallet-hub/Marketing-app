"""Background worker: drains the send queue. Run as its own container: python -m app.worker"""

import logging
import time

from .config import Settings
from .db import migrate
from .queue import process_once

IDLE_SECONDS = 15


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    migrate(settings.database_url)
    log = logging.getLogger("marketing.worker")
    if not settings.mail_configured:
        log.warning("RESEND_API_KEY or RESEND_FROM is not set: campaigns will wait in the queue")
    while True:
        try:
            handled = process_once(settings)
        except Exception:  # keep the worker alive; the error is logged with its traceback
            log.exception("queue pass failed")
            handled = 0
        if handled == 0:
            time.sleep(IDLE_SECONDS)


if __name__ == "__main__":
    main()
