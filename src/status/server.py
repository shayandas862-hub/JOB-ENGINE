"""Serve the public status page — stdlib HTTP, no auth, Cloud Run shaped.

The deliberate opposite of the dashboard on two counts, and both are pinned by
test. It binds 0.0.0.0 rather than 127.0.0.1, because inside a container the
process must accept traffic from the platform. And it asks for no token at all,
because the whole point is that a stranger can confirm the machine is alive.

What makes that safe is NOT this file — it is migration 0043. The views carry
only machine-health aggregates, so there is nothing here to protect. Every
request renders the same page for everybody; no input reaches a query.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from status.page import render_status
from status.queries import fetch_stages, fetch_status

BIND_HOST = "0.0.0.0"        # container: accept the platform's traffic
DEFAULT_PORT = 8080          # Cloud Run's convention; it injects PORT anyway

_DOWN = ("<!doctype html><meta charset='utf-8'><title>status unavailable</title>"
         "<p style='font:15px system-ui;padding:2rem;color:#444'>"
         "Status is temporarily unavailable. The nightly pipeline runs "
         "separately and is not affected by this page.</p>")


def _load():
    from db.connection import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        return fetch_status(cur), fetch_stages(cur)


def respond(loader=_load) -> tuple[int, str]:
    """(status, html) for one request — the testable core of serving.

    No token, no query parameters, no per-caller behaviour: one page for
    everyone. A database failure renders one calm line, never a traceback —
    a stack trace here would be published to the whole internet.
    """
    try:
        row, stages = loader()
    except Exception:
        return 503, _DOWN
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return 200, render_status(row, stages, generated_at=stamp)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):     # noqa: N802 (stdlib naming)
        if self.path.rstrip("/") not in ("", "/status", "/healthz"):
            self.send_error(404, "Not Found")
            return
        if self.path.rstrip("/") == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        status, body = respond()
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        # A minute of caching absorbs a burst without ever going stale enough
        # to mislead: the pipeline runs once a day.
        self.send_header("Cache-Control", "public, max-age=60")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)

    def address_string(self):            # skip reverse-DNS on every request
        return self.client_address[0]


def serve(port: int | None = None) -> None:
    """Blocking public server. Needs no secret — that is the design."""
    port = port or int(os.environ.get("PORT", DEFAULT_PORT))
    httpd = ThreadingHTTPServer((BIND_HOST, port), _Handler)
    print(f"status page: http://{BIND_HOST}:{port}/", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
