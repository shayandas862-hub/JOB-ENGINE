"""Tests for the hosted MCP transport — token gate + rate limits (Phase 8.3).

The skin gains transport CONFIG, never logic: one bearer token from the
environment guards every HTTP request (constant-time compare, no token = the
server refuses to start — the dashboard's rule), rate limits ride as FastMCP
middleware, stdio stays the default and carries no auth. No network is
touched anywhere in these tests.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from mcp_server.transport import (BearerVerifier, DEFAULT_PORT, TOKEN_ENV,
                                  http_settings)

# A real profile id. profiles.profile_id is a uuid column, so psycopg loads
# it as a uuid.UUID object — faking it as a str is what hid a 500 on the
# hosted door for a whole commit.
OWNER_1 = "11111111-1111-4111-a111-111111111111"


# --- the token gate ----------------------------------------------------------

def _verify(verifier, token):
    return asyncio.run(verifier.verify_token(token))


def test_bearer_verifier_accepts_only_the_exact_bootstrap_token(monkeypatch):
    # Phase 9 task 1 changed this contract deliberately: the verifier now
    # resolves a key to its OWNER instead of stamping everyone "founder", so
    # the identity assertion moved to tests/test_mcp_identity.py. What stays
    # pinned here is the bootstrap token's own gate — exact match, no
    # trimming, nothing else admitted.
    from mcp_server import transport
    from tests.conftest import FakeCursor, fake_conn
    monkeypatch.setattr(transport, "get_conn",
                        lambda: fake_conn(FakeCursor(rows=[])))
    monkeypatch.setattr(transport, "owner_for_key", lambda cur, key: None)
    monkeypatch.setattr(transport, "default_profile_id",
                        lambda cur: uuid.UUID(OWNER_1))

    verifier = BearerVerifier("s3cret")
    granted = _verify(verifier, "s3cret")
    assert granted is not None and granted.client_id == OWNER_1
    assert _verify(verifier, "wrong") is None
    assert _verify(verifier, "") is None
    assert _verify(verifier, "s3cret ") is None      # no trimming games


def test_bearer_verifier_with_no_expected_token_admits_nobody(monkeypatch):
    from mcp_server import transport
    from tests.conftest import FakeCursor, fake_conn
    monkeypatch.setattr(transport, "get_conn",
                        lambda: fake_conn(FakeCursor(rows=[])))
    monkeypatch.setattr(transport, "owner_for_key", lambda cur, key: None)
    assert _verify(BearerVerifier(""), "anything") is None


# --- the http settings -------------------------------------------------------

def test_http_settings_refuses_to_serve_without_a_token():
    with pytest.raises(SystemExit) as exc:
        http_settings(env={})
    assert TOKEN_ENV in str(exc.value)


def test_http_settings_defaults_are_cloud_run_shaped():
    s = http_settings(env={TOKEN_ENV: "tok"})
    assert s["host"] == "0.0.0.0"        # the container must accept the world;
    assert s["port"] == DEFAULT_PORT     # the TOKEN is the door, not the bind
    assert isinstance(s["auth"], BearerVerifier)
    assert len(s["middleware"]) == 1     # exactly one rate limiter


def test_http_settings_reads_env_overrides():
    s = http_settings(env={TOKEN_ENV: "tok", "PORT": "9001",
                           "MCP_HOST": "127.0.0.1",
                           "MCP_RPS": "2.5", "MCP_BURST": "4"})
    assert s["port"] == 9001 and s["host"] == "127.0.0.1"
    limiter = s["middleware"][0]
    from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
    assert isinstance(limiter, RateLimitingMiddleware)


# --- transport selection in main() -------------------------------------------

class _FakeServer:
    def __init__(self):
        self.ran_with = None

    def run(self, **kwargs):
        self.ran_with = kwargs


def test_main_defaults_to_stdio_with_no_auth(monkeypatch):
    import mcp_server.server as srv
    fake = _FakeServer()
    seen = {}

    def fake_build(**kwargs):
        seen.update(kwargs)
        return fake

    monkeypatch.setattr(srv, "build_server", fake_build)
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    srv.main()
    assert fake.ran_with == {"transport": "stdio"}
    assert seen == {}                    # stdio builds the plain local server


def test_main_serves_http_with_token_gate_and_rate_limit(monkeypatch):
    import mcp_server.server as srv
    fake = _FakeServer()
    seen = {}

    def fake_build(**kwargs):
        seen.update(kwargs)
        return fake

    monkeypatch.setattr(srv, "build_server", fake_build)
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv(TOKEN_ENV, "tok")
    monkeypatch.setenv("PORT", "8123")
    srv.main()
    assert fake.ran_with["transport"] == "http"
    assert fake.ran_with["port"] == 8123
    assert isinstance(seen["auth"], BearerVerifier)
    assert len(seen["middleware"]) == 1


def test_main_http_without_token_refuses_to_start(monkeypatch):
    import mcp_server.server as srv
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    with pytest.raises(SystemExit):
        srv.main()
