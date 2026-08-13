"""HTTP transport config for the hosted MCP — token gate + rate limits.

Phase 8 task 3: the skin gains transport CONFIG, never logic. One bearer
token from the environment guards every HTTP request — no token configured
means the server refuses to start (the dashboard's rule), and the comparison
is constant-time. Rate limits ride as FastMCP middleware: they protect the
server and the free quotas reachable through tools. (The monthly spend cap
was retired with Gemini, decision-log 2026-08-03 — the engine pays for no
AI; if a paid spot ever returns, the cap returns with it.)

stdio stays the default transport and carries no auth — it is the local,
single-user door. The 0.0.0.0 bind here is deliberate and unlike the
dashboard's pinned 127.0.0.1: inside Cloud Run the container must accept
the world, and the TOKEN is the door, not the bind.
"""
from __future__ import annotations

import hmac
import os

from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier

from auth.signin import RegistrationClosed, owner_for_auth_user
from auth.tokens import owner_for_key
from criteria.loader import default_profile_id
from db.connection import get_conn

TOKEN_ENV = "MCP_TOKEN"
PROJECT_URL_ENV = "SUPABASE_URL"
DEFAULT_PORT = 8080          # Cloud Run's convention; it injects PORT anyway
DEFAULT_RPS = 5.0
DEFAULT_BURST = 15

# What Supabase Auth signs and stamps. Measured against this project's own
# JWKS on 2026-08-12: one ES256 key on curve P-256. `authenticated` is the
# audience Supabase puts on every signed-in user's token.
JWT_ALGORITHM = "ES256"
JWT_AUDIENCE = "authenticated"
AUTH_ROUTE = "auth/v1"


def _looks_like_a_jwt(token: str) -> bool:
    """Three dot-separated segments, the first two non-empty.

    This decides which verifier to TRY, never who is refused. A credential
    that is not a JWT goes on to the bootstrap comparison exactly as before,
    and a JWT that fails verification is refused by the verifier that
    understands why.
    """
    parts = token.split(".")
    return len(parts) == 3 and bool(parts[0]) and bool(parts[1])


def supabase_verifier(project_url: str) -> JWTVerifier:
    """The JWT verifier for one Supabase project's signed-in users.

    Issuer and audience are both pinned. Without the issuer, a token minted by
    ANY Supabase project — genuine, correctly signed, about a user of an
    entirely different system — would open this door.
    """
    base = f"{project_url.rstrip('/')}/{AUTH_ROUTE}"
    return JWTVerifier(jwks_uri=f"{base}/.well-known/jwks.json",
                       issuer=base,
                       audience=JWT_AUDIENCE,
                       algorithm=JWT_ALGORITHM)


class BearerVerifier(TokenVerifier):
    """Resolve a presented key to the owner it belongs to (Phase 9 task 1).

    ``client_id`` carries the owner's profile id, which is what every tool
    reads back through mcp_server.identity.current_owner. It used to be the
    constant "founder" — a guess that was right only while there was one
    user, and the reason a second key holder would have read the first one's
    data.

    Three paths, in order:
      1. A minted key (access_keys, hashed at rest) resolves to ITS OWN
         owner. This is the friend tier, and the only path that scales.
      2. A Supabase-signed JWT — the stranger tier (task 6). Verified
         cryptographically against the project's JWKS with the issuer and
         audience pinned, then its `sub` resolved to a profile, which is
         CREATED on a first sign-in. This is the only path that admits
         somebody the founder has never met, which is why it is the only one
         whose failure modes each have their own test.
      3. The bootstrap token from MCP_TOKEN — the founder's existing operator
         key — resolves to the local profile. It is a guess, it is the only
         one left, and it is scoped "bootstrap" so it is visible as such. It
         can be retired the day the founder mints himself a row.
    A minted key always wins: neither the JWT path nor the bootstrap can
    override a stored owner. A verified sign-in never inherits the bootstrap
    scope — a stranger is an owner, never the operator. Anything else is
    refused, and a blank key never reaches the database at all.

    A database outage is deliberately NOT swallowed into a refusal. "Your key
    is wrong" and "the server is broken" are different facts, and turning the
    second into the first sends the holder hunting for a key problem that
    does not exist — the same silent-success-looks-like-silent-breakage trap
    the rest of this codebase is built to avoid. Every tool would fail on the
    same outage anyway.
    """

    def __init__(self, bootstrap: str, jwt_verifier: JWTVerifier | None = None):
        super().__init__()
        self._bootstrap = bootstrap
        self._jwt = jwt_verifier

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        with get_conn() as conn, conn.cursor() as cur:
            owner = owner_for_key(cur, token)
        if owner:
            return AccessToken(token=token, client_id=owner, scopes=["owner"])
        if self._jwt is not None and _looks_like_a_jwt(token):
            signed_in = await self._jwt.verify_token(token)
            if signed_in is not None:
                claims = signed_in.claims or {}
                metadata = claims.get("user_metadata") or {}
                try:
                    with get_conn() as conn, conn.cursor() as cur:
                        owner, _created = owner_for_auth_user(
                            cur, claims["sub"], email=claims.get("email"),
                            name=metadata.get("full_name")
                            or metadata.get("name"))
                except RegistrationClosed:
                    # B-GAE-048. The token is genuine and the person is real;
                    # this engine simply does not accept new owners. Refusing
                    # here — rather than letting it become a 500 — is what
                    # keeps "we are closed" from reading as "we are broken",
                    # and it is deliberately the same answer an unknown
                    # credential gets: a door that distinguishes the two tells
                    # a stranger whether they have found a live system worth
                    # pushing on.
                    return None
                # The scopes are written HERE, never read off the token. A
                # signed-in user controls nothing about what they may do: a
                # `scope` claim in their JWT is data about their session with
                # the identity provider, and treating it as our authorisation
                # would let anyone who can sign in name their own powers.
                return AccessToken(token=token, client_id=owner,
                                   scopes=["owner", "signed-in"])
        if self._bootstrap and hmac.compare_digest(token, self._bootstrap):
            with get_conn() as conn, conn.cursor() as cur:
                # str(): profile_id is a uuid column and psycopg hands back a
                # uuid.UUID, whatever default_profile_id's annotation says.
                # AccessToken declares client_id: str and pydantic refuses the
                # object — which turned every bootstrap request into a 500
                # until a test stopped faking this as a string.
                local = str(default_profile_id(cur))
            return AccessToken(token=token, client_id=local,
                               scopes=["owner", "bootstrap"])
        return None


def http_settings(env=os.environ) -> dict:
    """Everything main() needs to serve HTTP: auth, middleware, host, port.

    Raises SystemExit when no token is configured — the hosted door must
    never open unguarded, even for one request.

    Sign-in is switched on by ONE variable: SUPABASE_URL, the project URL from
    the Supabase dashboard. Absent, the server runs the friend tier alone and
    refuses every JWT — a supported way to run this door, not a degraded one,
    which is why its absence is silent rather than an error. The URL is
    configuration, not a secret; it travels through Secret Manager only
    because it carries the project ref, and that never goes into a public
    repository.
    """
    token = (env.get(TOKEN_ENV) or "").strip()
    if not token:
        raise SystemExit(
            f"{TOKEN_ENV} is not set — the hosted MCP refuses to serve "
            "without a bearer token (no token, no door).")
    project_url = (env.get(PROJECT_URL_ENV) or "").strip()
    from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
    return {
        "auth": BearerVerifier(
            token,
            jwt_verifier=supabase_verifier(project_url) if project_url else None),
        "middleware": [RateLimitingMiddleware(
            max_requests_per_second=float(env.get("MCP_RPS", DEFAULT_RPS)),
            burst_capacity=int(env.get("MCP_BURST", DEFAULT_BURST)))],
        "host": env.get("MCP_HOST", "0.0.0.0"),
        "port": int(env.get("PORT", DEFAULT_PORT)),
    }
