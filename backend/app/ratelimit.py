"""A small per-client rate limit for the pages recipients use without signing in (unsubscribe, information form).

The API runs as one process, so an in-memory sliding window is enough. The client address comes from
X-Forwarded-For: each proxy in front of the API appends the address it saw, so the client is the entry
TRUSTED_PROXY_HOPS from the end (1 locally, where nginx is the only proxy; 2 behind Coolify's Traefik and nginx).
Entries further left are written by the client and are not trusted.
"""

import threading
import time
from collections import deque

from fastapi import HTTPException, Request

WINDOW_SECONDS = 60
MAX_TRACKED_CLIENTS = 10_000


class RateLimiter:
    def __init__(self, limit, window=WINDOW_SECONDS, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, key):
        """Record a request from `key`. Returns False when it is over the limit for the current window."""
        if self.limit <= 0:
            return True
        now = self.clock()
        cutoff = now - self.window
        with self._lock:
            if len(self._hits) > MAX_TRACKED_CLIENTS:
                self._forget_idle(cutoff)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def _forget_idle(self, cutoff):
        for key in [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]


def client_address(request, hops):
    forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
    if forwarded:
        return forwarded[-hops] if len(forwarded) >= hops else forwarded[0]
    return request.client.host if request.client else "unknown"


def limit_public(request: Request):
    """Dependency for the public routes."""
    settings = request.app.state.settings
    if not request.app.state.public_limiter.allow(client_address(request, settings.trusted_proxy_hops)):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a minute and try again.",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )
