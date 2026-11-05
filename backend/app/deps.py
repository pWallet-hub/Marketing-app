"""Request dependencies: the signed-in person, and role checks.

The session holds only the Keycloak subject. On every request the access check runs again against Command Center,
so a revoked assignment stops working on the next request.
"""

import httpx
from fastapi import Depends, HTTPException, Request


def current_user(request: Request):
    sub = request.session.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Not signed in")
    settings = request.app.state.settings
    try:
        decision = request.app.state.access_check(settings, sub)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Access could not be checked. Please try again later.")
    if not decision.allowed:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Your access has ended. Please sign in again.")
    profile = request.app.state.users.get(sub)
    if profile is None:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    return {
        "sub": sub,
        "email": profile["email"],
        "name": profile["name"],
        "role": decision.external_role,
    }


def require_role(*allowed_roles):
    def dependency(user=Depends(current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        return user

    return dependency
