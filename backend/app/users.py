"""Profile records for people who have signed in. Kept behind a small interface so tests can replace it."""

from .db import connect


class PostgresUserStore:
    def __init__(self, database_url):
        self.database_url = database_url

    def record_sign_in(self, sub, email, name):
        with connect(self.database_url) as conn:
            conn.execute(
                "INSERT INTO app_users (keycloak_sub, email, name) VALUES (%s, %s, %s)"
                " ON CONFLICT (keycloak_sub) DO UPDATE SET email = EXCLUDED.email, name = EXCLUDED.name,"
                " last_sign_in_at = now()",
                (sub, email, name),
            )

    def get(self, sub):
        with connect(self.database_url) as conn:
            return conn.execute(
                "SELECT keycloak_sub, email, name FROM app_users WHERE keycloak_sub = %s", (sub,)
            ).fetchone()
