"""PostgreSQL connection and migrations. Migrations are plain SQL files in migrations/, applied in name order once."""

import pathlib
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "migrations"


@contextmanager
def connect(database_url):
    # The connection commits when the block ends cleanly and rolls back on an error.
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        yield conn


MIGRATION_LOCK_KEY = 827_001  # arbitrary, fixed: the API and the worker both migrate at startup


def migrate(database_url):
    with connect(database_url) as conn:
        # Only one process migrates at a time. The lock is held for this connection and released when it closes.
        conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
