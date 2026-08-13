"""The stranger's door: a Google sign-in becomes an owner (Phase 9 task 6).

Task 1 taught the door to resolve a MINTED key to its owner. This is the
second identity source: a JWT issued by Supabase Auth after the user signs in
with Google. Nothing about the friend tier changes — the order is minted key,
then JWT, then the founder's bootstrap token, and the first one that answers
wins.

**Every refusal here is cryptographic, not simulated.** The tests mint a real
P-256 keypair, sign real ES256 tokens with it, and hand them to the real
`fastmcp` verifier configured exactly as the hosted door configures it. A
forged token is refused because the signature does not check out, not because
a fake said so — which is the only version of this test worth having, and the
reason there is no mock verifier anywhere in this file.

Offline by construction: the verifier is built with the public key in hand, so
no JWKS is ever fetched. The hosted door passes a `jwks_uri` instead and
everything downstream of the key is identical.

What is deliberately NOT proven here: that Supabase actually signs with ES256
and issues `aud="authenticated"`. That is live configuration, measured against
the project's own JWKS (`/auth/v1/.well-known/jwks.json` served one ES256
P-256 key on 2026-08-12) and pinned in `http_settings`. A test cannot check
somebody else's issuer, and pretending otherwise would be the kind of test
this project keeps finding: green, and about nothing.
"""
from __future__ import annotations

import asyncio
import time
import uuid

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from tests.conftest import FakeCursor, fake_conn

PROJECT_URL = "https://exampleproject.supabase.co"
ISSUER = f"{PROJECT_URL}/auth/v1"
AUDIENCE = "authenticated"

# The Supabase auth user id (the JWT's `sub`) and the profile it maps to. They
# are different ids on purpose: one belongs to the identity provider, the other
# is this engine's own owner key, and conflating them is how a door starts
# trusting a claim as a primary key.
AUTH_SUB = "99999999-9999-4999-a999-999999999999"
OWNER = "33333333-3333-4333-a333-333333333333"
OWNER_B = "44444444-4444-4444-a444-444444444444"


@pytest.fixture(scope="module")
def keypair():
    """One EC P-256 keypair — the same curve Supabase's JWKS serves."""
    key = ec.generate_private_key(ec.SECP256R1())
    return key, key.public_key()


def _pem(public_key) -> str:
    from cryptography.hazmat.primitives import serialization
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def _token(private_key, *, sub=AUTH_SUB, iss=ISSUER, aud=AUDIENCE,
           exp_in=3600, email="stranger@example.com", full_name="Sam Stranger",
           alg="ES256") -> str:
    claims = {"sub": sub, "iss": iss, "aud": aud,
              "iat": int(time.time()), "exp": int(time.time()) + exp_in}
    if email:
        claims["email"] = email
    if full_name:
        # where Supabase puts what Google told it about the person
        claims["user_metadata"] = {"full_name": full_name, "email": email}
    if alg == "none":
        return pyjwt.encode(claims, key=None, algorithm=None)
    return pyjwt.encode(claims, private_key, algorithm=alg)


def _verifier(monkeypatch, keypair, *, bootstrap="", resolves_to=None,
              owner=OWNER, created=False, with_jwt=True):
    """The real BearerVerifier, with its database answers faked.

    `resolves_to` is what a MINTED key lookup returns; `owner` is what the
    auth-user lookup returns for a verified JWT.
    """
    from fastmcp.server.auth.providers.jwt import JWTVerifier

    from mcp_server import transport
    _, public = keypair
    seen = []
    monkeypatch.setattr(transport, "get_conn",
                        lambda: fake_conn(FakeCursor(rows=[])))
    monkeypatch.setattr(transport, "owner_for_key",
                        lambda cur, key: resolves_to)
    monkeypatch.setattr(transport, "default_profile_id",
                        lambda cur: uuid.UUID(OWNER_B))
    monkeypatch.setattr(
        transport, "owner_for_auth_user",
        lambda cur, sub, email=None, name=None:
            seen.append((sub, email, name)) or (owner, created))
    verifier = transport.BearerVerifier(
        bootstrap,
        jwt_verifier=JWTVerifier(public_key=_pem(public), issuer=ISSUER,
                                 audience=AUDIENCE, algorithm="ES256")
        if with_jwt else None)
    verifier.resolved = seen          # what the door asked the database for
    return verifier


def _verify(verifier, token):
    return asyncio.run(verifier.verify_token(token))


# --- the token that should work -----------------------------------------

def test_a_google_signed_in_stranger_is_resolved_to_their_own_profile(
        monkeypatch, keypair):
    private, _ = keypair
    verifier = _verifier(monkeypatch, keypair)
    granted = _verify(verifier, _token(private))

    assert granted is not None, "a valid Supabase JWT was refused"
    # the owner is OUR profile id, never the provider's subject
    assert granted.client_id == OWNER
    assert granted.client_id != AUTH_SUB
    assert "signed-in" in granted.scopes
    assert "bootstrap" not in granted.scopes, \
        "a stranger must never inherit the operator scope"
    # the door passes on what the provider claimed about the person, and
    # nothing it made up itself
    assert verifier.resolved == [(AUTH_SUB, "stranger@example.com",
                                  "Sam Stranger")]


# --- the four refusals, each for its own reason --------------------------

def test_an_expired_token_is_refused(monkeypatch, keypair):
    private, _ = keypair
    verifier = _verifier(monkeypatch, keypair)
    assert _verify(verifier, _token(private, exp_in=-60)) is None
    assert verifier.resolved == [], "an expired token still reached the database"


def test_a_token_from_another_issuer_is_refused(monkeypatch, keypair):
    # The attack this stops: a valid Google-backed Supabase token minted by
    # SOMEBODY ELSE'S project. Correctly signed, entirely genuine, and about a
    # user of a different system.
    private, _ = keypair
    verifier = _verifier(monkeypatch, keypair)
    other = _token(private, iss="https://someoneelse.supabase.co/auth/v1")
    assert _verify(verifier, other) is None
    assert verifier.resolved == []


def test_a_token_for_another_audience_is_refused(monkeypatch, keypair):
    private, _ = keypair
    verifier = _verifier(monkeypatch, keypair)
    assert _verify(verifier, _token(private, aud="some-other-service")) is None


def test_an_unsigned_token_is_refused(monkeypatch, keypair):
    # alg=none is the oldest JWT attack there is: strip the signature and
    # claim the algorithm was never meant to be checked.
    verifier = _verifier(monkeypatch, keypair)
    assert _verify(verifier, _token(None, alg="none")) is None


def test_a_token_signed_by_the_wrong_key_is_refused(monkeypatch, keypair):
    # A forged token with every claim correct — the signature is the only
    # thing wrong with it, which is the whole point of asymmetric keys.
    forger = ec.generate_private_key(ec.SECP256R1())
    verifier = _verifier(monkeypatch, keypair)
    assert _verify(verifier, _token(forger)) is None
    assert verifier.resolved == []


def test_a_token_cannot_name_its_own_powers(monkeypatch, keypair):
    # The claim that would matter most if it were trusted. A signed-in user's
    # token is signed by Supabase, so anything Supabase can be persuaded to put
    # in it — a `scope` claim, a `role` — arrives correctly signed. The door
    # writes the scopes itself, so a token asking for "bootstrap" gets exactly
    # what every other signed-in caller gets, and `issue_my_key`'s operator
    # refusal cannot be talked around.
    private, _ = keypair
    verifier = _verifier(monkeypatch, keypair)
    claims = {"sub": AUTH_SUB, "iss": ISSUER, "aud": AUDIENCE,
              "exp": int(time.time()) + 3600,
              "scope": "bootstrap owner admin", "role": "service_role"}
    granted = _verify(verifier, pyjwt.encode(claims, private, algorithm="ES256"))

    assert granted is not None
    assert granted.scopes == ["owner", "signed-in"]
    assert "bootstrap" not in granted.scopes and "admin" not in granted.scopes


def test_a_jwt_is_refused_outright_when_no_issuer_is_configured(
        monkeypatch, keypair):
    # The local/stdio and pre-sign-in hosted doors run with no JWT verifier at
    # all. A token must be refused there, never fall through to some other
    # interpretation of the same string.
    private, _ = keypair
    verifier = _verifier(monkeypatch, keypair, with_jwt=False)
    assert _verify(verifier, _token(private)) is None


# --- the friend tier, unchanged ------------------------------------------

def test_a_minted_key_still_wins_and_never_reaches_the_jwt_path(
        monkeypatch, keypair):
    verifier = _verifier(monkeypatch, keypair, resolves_to=OWNER_B)
    granted = _verify(verifier, "a-minted-key")
    assert granted.client_id == OWNER_B
    assert granted.scopes == ["owner"]
    assert verifier.resolved == []


def test_the_founders_bootstrap_token_still_opens_the_door(
        monkeypatch, keypair):
    # Adding a second identity source must not cost the founder his own key.
    verifier = _verifier(monkeypatch, keypair, bootstrap="boot-key")
    granted = _verify(verifier, "boot-key")
    assert granted is not None and granted.client_id == OWNER_B
    assert "bootstrap" in granted.scopes


def test_a_dotted_credential_that_is_not_a_jwt_still_reaches_the_bootstrap(
        monkeypatch, keypair):
    # The shape test (three dot-separated segments) decides which verifier to
    # TRY, never who is refused. A bootstrap token that happens to contain two
    # dots must still open the door it has always opened.
    verifier = _verifier(monkeypatch, keypair, bootstrap="a.b.c")
    granted = _verify(verifier, "a.b.c")
    assert granted is not None and "bootstrap" in granted.scopes


# --- how the hosted door is wired ----------------------------------------

def test_http_settings_pins_the_issuer_audience_and_algorithm():
    from mcp_server.transport import http_settings
    settings = http_settings({"MCP_TOKEN": "t", "SUPABASE_URL":
                              PROJECT_URL})
    verifier = settings["auth"]._jwt
    assert verifier is not None, "sign-in configured but no JWT verifier built"
    assert verifier.issuer == ISSUER
    assert verifier.audience == AUDIENCE
    assert verifier.algorithm == "ES256"
    assert str(verifier.jwks_uri) == f"{ISSUER}/.well-known/jwks.json"


def test_without_the_project_url_the_door_serves_the_friend_tier_only():
    # Sign-in is off until the founder sets one env var. Nothing else about
    # the door changes, and the absence must not be an error — the friend
    # tier is a supported way to run this server, not a degraded one.
    from mcp_server.transport import http_settings
    settings = http_settings({"MCP_TOKEN": "t"})
    assert settings["auth"]._jwt is None


def test_a_blank_credential_is_refused_before_any_verifier_runs(
        monkeypatch, keypair):
    verifier = _verifier(monkeypatch, keypair, bootstrap="boot")
    assert _verify(verifier, "") is None
    assert _verify(verifier, None) is None


# --- the registration gate at the door (B-GAE-048) -----------------------

def test_a_perfectly_valid_stranger_is_refused_while_registration_is_shut(
        monkeypatch, keypair):
    # The door's half of B-GAE-048. The token here is genuine in every way
    # the verifier can check — right signature, right issuer, right audience
    # — and it is still refused, because verifying an identity was never the
    # same question as admitting an owner. Before this, such a token minted
    # itself a profile on arrival.
    import mcp_server.transport as transport
    from auth.signin import RegistrationClosed

    private, _ = keypair
    verifier = _verifier(monkeypatch, keypair)

    def _closed(cur, sub, email=None, name=None):
        raise RegistrationClosed("registration is closed")
    monkeypatch.setattr(transport, "owner_for_auth_user", _closed)

    assert _verify(verifier, _token(private)) is None


def test_being_closed_is_indistinguishable_from_an_unknown_credential(
        monkeypatch, keypair):
    # A door that answers "closed" differently from "who are you" tells a
    # stranger they have found a live system that would admit them if the
    # setting changed. Both are None, and this asserts it rather than
    # trusting that they happen to match today.
    import mcp_server.transport as transport
    from auth.signin import RegistrationClosed

    private, _ = keypair
    verifier = _verifier(monkeypatch, keypair, bootstrap="boot")
    monkeypatch.setattr(
        transport, "owner_for_auth_user",
        lambda cur, sub, email=None, name=None: (_ for _ in ()).throw(
            RegistrationClosed("closed")))

    refused_because_closed = _verify(verifier, _token(private))
    refused_because_unknown = _verify(verifier, "not-a-credential-at-all")
    assert refused_because_closed == refused_because_unknown is None
