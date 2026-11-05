"""Sign-in with AFS SSO (Keycloak). Authorization code flow with PKCE, a state and nonce check, and a verified ID token."""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from .hub import check_access

router = APIRouter()

SIGN_IN_FAILED = "Sign-in was cancelled or could not be verified. Please try again."


def pkce_pair():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def verify_id_token(settings, jwks, token, nonce):
    """Raise jwt.PyJWTError unless the ID token is signed by the realm, for this client, unexpired, and for this sign-in."""
    key = jwks.get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=settings.oidc_client_id,
        issuer=settings.issuer,
        options={"require": ["exp", "iss", "sub", "aud"]},
    )
    if not nonce or claims.get("nonce") != nonce:
        raise jwt.InvalidTokenError("nonce does not match")
    return claims


@router.get("/login")
def login(request: Request):
    settings = request.app.state.settings
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair()
    request.session["oidc_state"] = state
    request.session["oidc_nonce"] = nonce
    request.session["oidc_verifier"] = verifier
    query = urlencode(
        {
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return RedirectResponse(f"{settings.issuer}/protocol/openid-connect/auth?{query}")


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    settings = request.app.state.settings
    expected_state = request.session.pop("oidc_state", None)
    nonce = request.session.pop("oidc_nonce", None)
    verifier = request.session.pop("oidc_verifier", None)
    if error or not code or not expected_state or not verifier or not secrets.compare_digest(state or "", expected_state):
        raise HTTPException(status_code=400, detail=SIGN_IN_FAILED)

    try:
        token_response = httpx.post(
            f"{settings.internal_realm_url}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.redirect_uri,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
                "code_verifier": verifier,
            },
            timeout=10,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach the identity provider. Please try again.")
    if token_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Could not complete sign-in with the identity provider.")

    try:
        claims = verify_id_token(settings, request.app.state.jwks, token_response.json()["id_token"], nonce)
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=400, detail=SIGN_IN_FAILED)

    sub = claims["sub"]
    try:
        decision = request.app.state.access_check(settings, sub)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Access could not be checked. Please try again later.")
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this application. Contact an access administrator.",
        )

    request.app.state.users.record_sign_in(sub, claims.get("email"), claims.get("name"))
    # A fresh session on every sign-in prevents session fixation.
    request.session.clear()
    request.session["sub"] = sub
    return RedirectResponse(f"{settings.frontend_origin.rstrip('/')}/")


@router.get("/logout")
def logout(request: Request):
    settings = request.app.state.settings
    request.session.clear()
    query = urlencode(
        {"client_id": settings.oidc_client_id, "post_logout_redirect_uri": f"{settings.frontend_origin.rstrip('/')}/"}
    )
    return RedirectResponse(f"{settings.issuer}/protocol/openid-connect/logout?{query}")
