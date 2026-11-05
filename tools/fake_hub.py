"""A stand-in for AFS Command Center's access check, for local testing only.

GET /api/internal/access answers from a fixed table of people. It refuses any request without the marketing service token.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = "local-only"
PEOPLE = {"sub-admin": "admin", "sub-member": "member"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/api/internal/access":
            return self._reply(404, {"detail": "not found"})
        if self.headers.get("X-Service-Token") != TOKEN:
            return self._reply(401, {"detail": "Invalid service token"})
        query = parse_qs(url.query)
        role = PEOPLE.get((query.get("subject") or [""])[0])
        if query.get("application") != ["marketing"] or role is None:
            return self._reply(200, {"allowed": False, "external_role": None, "reason": "not assigned"})
        return self._reply(200, {"allowed": True, "external_role": role, "reason": "assigned"})

    def _reply(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        sys.stderr.write("fake-hub: " + (args[0] % args[1:]) + "\n")


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
