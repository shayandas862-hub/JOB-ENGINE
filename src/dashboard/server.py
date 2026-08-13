"""Serve the Today page — stdlib HTTP, local only, token-gated.

127.0.0.1 bind (pinned by test) + a required DASHBOARD_TOKEN from the
environment: no token configured means no access at all, and the comparison
is constant-time. Tabs and pages arrive as query params, normalised before
loading; every internal link the page renders carries the token back. A
database failure renders one calm line — the daily loop is a separate
process and is never affected by this page. Threaded serving so one slow
request can never wedge the page behind it. Runs by command
(scripts/run_dashboard.py); Phase 8's container carries it unchanged.
"""
from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from dashboard.page import TAB_KEYS, render_page
from dashboard.queries import PAGE_SIZE, fetch_health, fetch_owner_mirror, \
    fetch_scorecard, fetch_sponsors, fetch_today

BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8377
TOKEN_ENV = "DASHBOARD_TOKEN"

_DENIED = ("<!doctype html><meta charset='utf-8'><title>403</title>"
           "<p style='font: 14px system-ui; padding: 2rem; color:#444'>"
           "Missing or wrong token. Open the page as "
           "http://127.0.0.1:8377/?token=&lt;your DASHBOARD_TOKEN&gt;.</p>")
_DOWN = ("<!doctype html><meta charset='utf-8'><title>engine unreachable</title>"
         "<p style='font: 14px system-ui; padding: 2rem; color:#444'>"
         "The engine's database is unreachable right now. The daily loop "
         "runs separately and is not affected. Try again in a minute.</p>")


def check_token(supplied: str | None, expected: str) -> bool:
    """Constant-time token check; an unconfigured token admits nobody."""
    if not expected or not supplied:
        return False
    return hmac.compare_digest(supplied, expected)


def _normalise(tab, page) -> tuple[str, int]:
    """Unknown tabs become 'ready'; pages clamp to a positive integer."""
    tab = tab if tab in TAB_KEYS else "ready"
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    return tab, page


def _load_views(tab: str, page: int, industry: str, town: str):
    """(today, scorecard, health, sponsors, mirror) — five, since Phase 9.5.

    The mirror rides on every tab rather than living in one, because it is not
    a lane of the queue: it is who the queue is being built for, and it belongs
    beside the honesty panel on whichever page the founder happens to open.
    """
    from db.connection import get_conn
    offset = (page - 1) * PAGE_SIZE
    with get_conn() as conn, conn.cursor() as cur:
        scorecard = fetch_scorecard(cur)
        mirror = fetch_owner_mirror(cur)
        if tab == "companies":
            return [], scorecard, fetch_health(cur, limit=PAGE_SIZE,
                                               offset=offset), [], mirror
        if tab == "sponsors":
            return [], scorecard, [], fetch_sponsors(
                cur, industry, town, limit=PAGE_SIZE, offset=offset), mirror
        if tab == "tray":
            return fetch_today(cur, tray_only=True, limit=PAGE_SIZE,
                               offset=offset), scorecard, [], [], mirror
        return fetch_today(cur, bucket=tab, limit=PAGE_SIZE,
                           offset=offset), scorecard, [], [], mirror


def respond(supplied_token: str | None, expected_token: str, *,
            tab: str = "ready", page=1, industry: str = "", town: str = "",
            loader=_load_views) -> tuple[int, str]:
    """(status, html) for one page request — the testable core of serving."""
    if not check_token(supplied_token, expected_token):
        return 403, _DENIED
    tab, page = _normalise(tab, page)
    industry = (industry or "").strip()[:120]
    town = (town or "").strip()[:120]
    try:
        today, scorecard, health, sponsors, mirror = loader(
            tab, page, industry, town)
    except Exception:
        return 500, _DOWN     # one calm line; never a traceback, never a secret
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return 200, render_page(today, scorecard, health, sponsors, mirror=mirror,
                            generated_at=stamp, tab=tab, page=page,
                            industry=industry, town=town,
                            qs=f"/?token={expected_token}&")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):     # noqa: N802 (stdlib naming)
        query = parse_qs(urlparse(self.path).query)
        supplied = (query.get("token") or [None])[0] \
            or (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip() \
            or None
        tab = (query.get("tab") or ["ready"])[0]
        page = (query.get("page") or ["1"])[0]
        industry = (query.get("industry") or [""])[0]
        town = (query.get("town") or [""])[0]
        status, body = respond(supplied, os.environ.get(TOKEN_ENV, ""),
                               tab=tab, page=page, industry=industry,
                               town=town)
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):   # tokens ride in query strings —
        pass                             # never write request lines to a log

    def address_string(self):            # skip reverse-DNS on every request
        return self.client_address[0]


def serve(port: int = DEFAULT_PORT) -> None:
    """Blocking local server. Refuses to start without a token configured."""
    if not os.environ.get(TOKEN_ENV):
        raise SystemExit(
            f"{TOKEN_ENV} is not set — add it to .env; the dashboard refuses "
            "to serve without a token.")
    httpd = ThreadingHTTPServer((BIND_HOST, port), _Handler)
    print(f"Today page: http://{BIND_HOST}:{port}/?token=<{TOKEN_ENV}>")
    httpd.serve_forever()
