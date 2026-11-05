"""Creates a default AFS blog account (Biocap) for a media contact.

Biocap has no service-token endpoint for this yet (see docs/integrations/biocap.md). Until BIOCAP_ACCOUNT_URL and
BIOCAP_ACCOUNT_TOKEN are set, this returns status 'not_configured' and the invite goes out without an account.
"""

import httpx


class BlogAccountError(Exception):
    pass


def create_blog_account(settings, email, name):
    if not (settings.biocap_account_url and settings.biocap_account_token):
        return {"status": "not_configured"}
    try:
        response = httpx.post(
            settings.biocap_account_url,
            json={"email": email, "name": name, "role": "media_correspondent"},
            headers={"Authorization": f"Bearer {settings.biocap_account_token}"},
            timeout=10,
        )
    except httpx.HTTPError as error:
        raise BlogAccountError(f"could not reach Biocap ({error.__class__.__name__})") from error
    if response.status_code in (200, 201):
        body = response.json() if response.content else {}
        return {"status": "created", "id": body.get("id") or body.get("_id")}
    if response.status_code == 409:
        return {"status": "exists"}
    raise BlogAccountError(f"Biocap answered HTTP {response.status_code}")
