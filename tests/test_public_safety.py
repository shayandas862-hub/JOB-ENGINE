"""Pre-flip safety net (Phase 8 task 6) — what must never be in a public repo.

An audit is a moment; a test is a habit. Task 6 found two real leaks in tracked
files — a snapshot of the owner's own job queue, and the Supabase project ref in
a retired runbook. Both are fixed. These tests exist so they cannot come back
quietly, and so the next person adding a file learns the rule by failing rather
than by reading a document.

Scope is the WORKING TREE, deliberately. Git history still carries the project
ref in three commits; that is not fixable by a test and is exactly why task 7
publishes a squashed snapshot instead of pushing history.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# These read the git INDEX to ask "what would be published". The container
# image carries no .git (and no git binary), so inside the artefact there is
# nothing here to assert — same precedent as tests/test_record_ids.py and
# tests/test_cloud_setup.py. Skip rather than error: a suite that is
# permanently red inside the image trains everyone to ignore it, which is how
# the container suite stayed broken for two commits in 83aa52c.
pytestmark = pytest.mark.skipif(
    not (ROOT / ".git").exists(),
    reason="repo-only contract: no git index in the container image")


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def _read(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(errors="ignore")
    except (OSError, UnicodeDecodeError):
        return ""


def test_no_env_file_is_ever_tracked():
    # .env holds every live credential: the database URL, the aggregator keys,
    # the dashboard token and the MCP bearer token.
    leaked = [p for p in _tracked()
              if p == ".env" or (p.startswith(".env.") and p != ".env.example")]
    assert leaked == [], f"credential file tracked: {leaked}"


def test_no_supabase_project_ref_in_tracked_files():
    # The ref is the database's address. Not a credential on its own, but it
    # names the target, and it is the specific thing plan 0012 flagged as
    # blocking a public push. Matched by SHAPE (20 lowercase letters next to a
    # supabase mention) so it fails for a NEW project too, not just this one.
    offenders = []
    for rel in _tracked():
        if rel.startswith("tests/test_public_safety"):
            continue
        text = _read(rel)
        if "supabase" not in text.lower():
            continue
        for match in re.findall(r"\b[a-z]{20}\b", text):
            if match not in ("supabaseprojectref",):
                offenders.append(f"{rel}: {match[:4]}…")
    assert offenders == [], f"possible Supabase project ref tracked: {offenders}"


def test_the_owners_own_job_queue_is_never_tracked():
    # ops/apply-shortlist.md was tracked until task 6: 15 named roles the owner
    # was targeting, with live application links. Operational output about a
    # PERSON, not source code.
    leaked = [p for p in _tracked()
              if "apply-shortlist" in p or re.search(r"ops/shortlist-.*\.md$", p)]
    assert leaked == [], f"personal job queue tracked: {leaked}"


def test_no_real_api_key_shaped_string_is_tracked():
    # Placeholders are fine and useful; full-length keys are not. A real Google
    # key is 39 chars, an OpenAI-style key far longer than its prefix.
    offenders = []
    for rel in _tracked():
        if rel.startswith("tests/test_public_safety"):
            continue
        text = _read(rel)
        for match in re.findall(r"\bAIza[A-Za-z0-9_\-]{30,}\b", text):
            offenders.append(f"{rel}: AIza… ({len(match)} chars)")
        for match in re.findall(r"\bsk-[A-Za-z0-9]{32,}\b", text):
            offenders.append(f"{rel}: sk-… ({len(match)} chars)")
    assert offenders == [], f"real-looking API keys tracked: {offenders}"


# A password segment made of a placeholder is a template, which is the POINT of
# .env.example. Only a real-looking secret counts.
_PLACEHOLDER = re.compile(r"[\[\]<>${}]|YOUR|PASSWORD|EXAMPLE|CHANGE", re.I)
_CONN = re.compile(r"postgres(?:ql)?://[^\s\"':]+:([^\s\"'@/]+)@")
# The live topic is 32 hex characters — that shape is the secret. Test fixtures
# like "goala-secret-topic" are words, and must not trip this.
_NTFY = re.compile(r"ntfy\.sh/[0-9a-f]{24,}", re.I)


def test_no_connection_string_carries_a_real_password():
    # .env.example must stay a SHAPE, never a working credential.
    # The detector proves it still bites before it is trusted — a scanner that
    # cannot fire is the exact defect this project keeps finding.
    assert _CONN.search("postgresql://postgres:hunter2@db.abc.supabase.co:5432/x")
    assert not _PLACEHOLDER.search("hunter2")

    offenders = []
    for rel in _tracked():
        if rel.startswith("tests/test_public_safety"):
            continue
        for password in _CONN.findall(_read(rel)):
            if not _PLACEHOLDER.search(password):
                offenders.append(rel)
    assert offenders == [], f"connection string with a real password: {offenders}"


def test_the_ntfy_topic_never_appears_in_the_repo():
    # The topic IS the access control for the founder's phone (ntfy.sh is
    # obscurity-only): 32 hex characters living ONLY in
    # profiles.notification_channel. The base URL is fine; the topic is not.
    assert _NTFY.search("https://ntfy.sh/" + "a1b2c3d4" * 4)   # the detector bites
    assert not _NTFY.search("https://ntfy.sh/goala-secret-topic")   # fixtures do not

    offenders = [rel for rel in _tracked()
                 if not rel.startswith("tests/test_public_safety")
                 and _NTFY.search(_read(rel))]
    assert offenders == [], f"an ntfy topic is in the repo: {offenders}"


def test_the_readme_makes_no_retired_claim():
    # The README is the public face and had drifted badly: it advertised 402
    # tests, 34 migrations, 24 tools, "caged AI with Gemini" and "a hard spend
    # cap" — none of which were true by August. Prose rots silently; this makes
    # it rot loudly. Claims about RETIRED things, which can only be wrong.
    readme = _read("README.md")
    for gone in ("caged AI", "Gemini", "spend cap", "402 tests",
                 "34 migrations", "24 tools"):
        assert gone not in readme, f"README still claims: {gone}"


def test_the_readme_test_count_matches_reality():
    # The specific number that drifted. Collected, not recalled.
    readme = _read("README.md")
    # sys.executable, never the name "python" — the same resolution bug Stage C
    # fixed in pipeline/trigger.py: there is no guarantee "python" is on PATH.
    # NOT "-q": pyproject already sets addopts="-q", so adding another makes it
    # -qq, which SILENCES the count line — and a skip here would read exactly
    # like a pass. That trap cost time twice in one evening; it is not allowed
    # to cost a third.
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": "src"})
    match = re.search(r"(\d+) tests? collected", out.stdout)
    assert match, ("could not read a test count from pytest — the check is "
                   f"broken, not the README. stdout tail: {out.stdout[-200:]!r}")
    collected = match.group(1)
    assert f"**{collected}**" in readme or f"{collected} tests" in readme, \
        f"README does not state the real test count ({collected})"


def test_the_readme_states_one_test_count_and_it_is_the_real_one():
    # B-GAE-029. The check above is an OR over PRESENCE: the right number
    # anywhere satisfies it, so a SECOND, stale number is invisible to it.
    # That is exactly what happened — the numbers table said 934 while the
    # Quick start eleven lines below still said 913, two tasks after the
    # count moved, in the file that ships to the public repo. Presence can
    # never prove absence, so this assertion is over EVERY occurrence.
    readme = _read("README.md")
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": "src"})
    match = re.search(r"(\d+) tests? collected", out.stdout)
    assert match, f"could not read a test count: {out.stdout[-200:]!r}"
    collected = match.group(1)
    stale = [n for n in re.findall(r"(\d+) tests?\b", readme) if n != collected]
    assert stale == [], (
        f"README states {stale} tests as well as the real {collected} — one "
        "place in the file owns the count, and it is the numbers table")


def test_the_public_status_page_stays_the_only_unauthenticated_surface():
    # The dashboard and the MCP must each keep refusing to serve without their
    # token. If either ever loses that, the status page is no longer the only
    # thing a stranger can read.
    assert 'TOKEN_ENV = "DASHBOARD_TOKEN"' in _read("src/dashboard/server.py")
    assert 'BIND_HOST = "127.0.0.1"' in _read("src/dashboard/server.py")
    assert 'TOKEN_ENV = "MCP_TOKEN"' in _read("src/mcp_server/transport.py")
    assert "raise SystemExit" in _read("src/mcp_server/transport.py")
