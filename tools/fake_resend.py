"""A stand-in for Resend's HTTP API, for local end-to-end checks only. It accepts POST /emails, records each request,
and returns an id. GET /log returns what it has received. It does not deliver anything.
"""

import json
import sys
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path != "/emails":
            return self._reply(404, {"message": "not found"})
        if not self.headers.get("Authorization", "").startswith("Bearer "):
            return self._reply(401, {"message": "missing key"})
        LOG.append({"headers": dict(self.headers), "body": body})
        return self._reply(200, {"id": str(uuid.uuid4())})

    def do_GET(self):
        if self.path == "/log":
            return self._reply(200, LOG)
        return self._reply(404, {"message": "not found"})

    def _reply(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        sys.stderr.write("fake-resend: " + (args[0] % args[1:]) + "\n")


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8025), Handler).serve_forever()
