from contextlib import asynccontextmanager

import jwt
from fastapi import APIRouter, FastAPI, Depends
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings
from .db import migrate
from .deps import current_user
from .hub import check_access
from .oidc import router as oidc_router
from .users import PostgresUserStore

SESSION_LIFETIME_SECONDS = 8 * 60 * 60

api = APIRouter(prefix="/api")


@api.get("/health")
def health():
    return {"status": "ok"}


@api.get("/me")
def me(user=Depends(current_user)):
    return user


def create_app(settings=None, access_check=None, users=None):
    """Build the app. Tests pass their own access check and user store; production uses the defaults."""
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        migrate(settings.database_url)
        yield

    app = FastAPI(
        title="AFS Marketing Mailer",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.access_check = access_check or check_access
    app.state.users = users or PostgresUserStore(settings.database_url)
    app.state.jwks = jwt.PyJWKClient(f"{settings.internal_realm_url}/protocol/openid-connect/certs")
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="marketing_session",
        max_age=SESSION_LIFETIME_SECONDS,
        https_only=settings.https_only,
        same_site="lax",
    )
    app.include_router(oidc_router, prefix="/api/auth")
    app.include_router(api)
    return app
