"""The operator's key door — scripts/mint_access_key.py (Phase 9 task 1).

Minting decides WHO the machine answers to, so it is a script the founder
runs and not a tool any client AI can reach. These tests pin the three
things that make it safe to run: a key is never minted without a label to
revoke it by, the secret is printed once and never the digest, and revoking
names its outcome rather than failing silently.

Honest note: these were written AFTER the script, not before it — the only
place in this task where red-first was not followed. Each one was checked
against a mutated script before being trusted.

Offline: the DB is a fake cursor.
"""
from __future__ import annotations

import pytest

from tests.conftest import FakeCursor, fake_conn

OWNER = "11111111-1111-4111-a111-111111111111"


def _run(monkeypatch, argv, cur):
    import scripts.mint_access_key as script
    monkeypatch.setattr(script, "get_conn", lambda: fake_conn(cur))
    return script.main(argv)


def test_minting_without_a_label_is_refused():
    # An unlabelled key cannot be revoked with confidence later: the operator
    # would be guessing which row belongs to whom.
    import scripts.mint_access_key as script
    with pytest.raises(SystemExit):
        script.main(["--owner", OWNER])


def test_a_usage_error_is_refused_before_any_environment_is_read(monkeypatch):
    # B-GAE-021. The refusal above passed on the founder's laptop for the wrong
    # reason: `main` opened a connection FIRST and reached the label check
    # second, and the laptop's `.env` made that connection succeed. The image
    # carries no `.env` by design, so in the container — and in CI, which is
    # the same world — the config load raised RuntimeError instead and the
    # test failed. That is a product defect, not a test defect: an operator
    # should not need a database to be told the command is malformed.
    #
    # So the ordering is what this pins, and it pins it WITHOUT depending on
    # the environment — which is precisely what the test above could not do.
    import scripts.mint_access_key as script

    def _refuse():
        raise AssertionError(
            "the database was reached before the arguments were validated")

    monkeypatch.setattr(script, "get_conn", _refuse)
    with pytest.raises(SystemExit):
        script.main(["--owner", OWNER])


def test_the_minted_key_is_printed_once_and_the_digest_never(monkeypatch, capsys):
    # The key is pinned to a sentinel so "once" is counted over the WHOLE
    # output, not over lines that happen to be indented — the first version of
    # this test counted indentation and let a second, unindented print of the
    # same secret straight through.
    import auth.tokens as tokens
    from auth.tokens import hash_key
    monkeypatch.setattr(tokens, "new_key", lambda: "SENTINEL-KEY-VALUE")

    # one dict serves both lookups: the fuse's profile check and the insert's
    # returned key_id (FakeCursor answers every query with the same row)
    cur = FakeCursor(rows=[{"profile_id": OWNER, "key_id": 12}])
    assert _run(monkeypatch, ["--owner", OWNER, "--label", "sam-laptop"], cur) == 0

    out = capsys.readouterr().out
    assert out.count("SENTINEL-KEY-VALUE") == 1, \
        f"the key was not printed exactly once: {out!r}"
    assert hash_key("SENTINEL-KEY-VALUE") not in out, \
        "the digest was printed to the operator"
    assert "ONCE" in out and "Never commit it" in out


def test_listing_keys_shows_state_but_never_a_secret(monkeypatch, capsys):
    cur = FakeCursor(rows=[{"key_id": 1, "owner_id": OWNER, "label": "sam",
                            "created_at": "t", "last_used_at": None,
                            "revoked_at": "2026-08-10", "token_sha256": "a" * 64}])
    assert _run(monkeypatch, ["--list"], cur) == 0
    out = capsys.readouterr().out
    assert "REVOKED" in out and "sam" in out
    assert "a" * 64 not in out


def test_revoking_reports_what_actually_happened(monkeypatch, capsys):
    # not_live, not silence: revoking an already-revoked key must say so.
    assert _run(monkeypatch, ["--revoke", "9"], FakeCursor(rows=[])) == 0
    assert "not_live" in capsys.readouterr().out

    assert _run(monkeypatch, ["--revoke", "9"],
                FakeCursor(rows=[{"key_id": 9, "owner_id": OWNER, "label": "x",
                                  "created_at": "t", "last_used_at": None,
                                  "revoked_at": "now"}])) == 0
    assert "revoked" in capsys.readouterr().out


def test_a_key_can_now_be_minted_for_somebody_who_is_not_the_local_owner(
        monkeypatch, capsys):
    # The fuse task 1a installed, removed in task 1b — the commit that scoped
    # the reads and proved a cross-owner read is refused
    # (tests/test_owner_scoping.py). This is its replacement, asserting the
    # opposite: a second person can be given a key at all, which is the whole
    # point of the friend tier and was impossible for the whole of task 1a.
    import scripts.mint_access_key as script
    cur = FakeCursor(rows=[{"key_id": 1}])
    monkeypatch.setattr(script, "get_conn", lambda: fake_conn(cur))

    friend = "99999999-9999-4999-a999-999999999999"
    assert script.main(["--owner", friend, "--label", "sam-laptop"]) == 0

    minted = [(sql, params) for sql, params in cur.executed
              if "insert into access_keys" in sql]
    assert len(minted) == 1, "no key was minted for the friend"
    assert friend in minted[0][1], "the key was minted against the wrong owner"
    assert friend in capsys.readouterr().out


def test_minting_is_reachable_from_exactly_one_tool_module():
    # A DELIBERATE narrowing, made in Phase 9 task 6 — not a relaxation.
    #
    # This test used to say: minting is not reachable from the skin at all.
    # Its stated fear was "a client could issue itself a key for somebody
    # else's data", and sign-in is what makes the second half of that sentence
    # preventable: `issue_my_key` mints for the VERIFIED caller and takes no
    # owner at all, so there is no argument through which anybody else's data
    # could be named. The old assertion would have blocked the tool without
    # addressing the fear, so the fear is now checked directly:
    #
    #   * mint_key reaches exactly one module, key_tools.py;
    #   * the unscoped revoke_key stays unreachable — only the owner-scoped
    #     revoke_key_for_owner may be called from a tool;
    #   * neither key tool accepts an owner-shaped argument;
    #   * the operator's mint SCRIPT stays entirely off the surface.
    #
    # Imports are read with ast rather than by substring, because
    # "revoke_key" is a prefix of "revoke_key_for_owner" and a substring scan
    # cannot tell the dangerous one from the safe one.
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]

    imported: dict[str, set[str]] = {}
    signatures: dict[str, list[str]] = {}
    for path in sorted((root / "src" / "mcp_server").rglob("*.py")):
        tree = ast.parse(path.read_text())
        names = {alias.name for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom)
                 for alias in node.names}
        names |= {alias.name for node in ast.walk(tree)
                  if isinstance(node, ast.Import) for alias in node.names}
        imported[path.name] = names
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in (
                    "issue_my_key", "revoke_my_key"):
                signatures[node.name] = [a.arg for a in node.args.args]

    mints = sorted(f for f, names in imported.items() if "mint_key" in names)
    assert mints == ["key_tools.py"], \
        f"minting is reachable from {mints}, not from key_tools.py alone"

    unscoped = sorted(f for f, names in imported.items()
                      if "revoke_key" in names)
    assert unscoped == [], \
        f"the unscoped revoke_key is reachable from {unscoped}"

    for module, names in imported.items():
        assert not any("mint_access_key" in n for n in names), \
            f"{module} reaches the operator's mint script"

    assert set(signatures) == {"issue_my_key", "revoke_my_key"}, \
        f"the key tools were renamed or moved: {sorted(signatures)}"
    for tool, args in signatures.items():
        offenders = [a for a in args if "owner" in a or "profile" in a]
        assert offenders == [], \
            f"{tool} takes {offenders} — a caller could name somebody else"
