"""Owner isolation in the nightly pass — the two bugs task 3 closed.

[[B-GAE-027]] sent one owner's queue to another owner's phone and stamped the
rows so the real owner was never nudged for them. [[B-GAE-028]] applied one
owner's apply window to everyone's deadlines. Both were measured against the
pre-fix source before these guards were written — the fixes add a required
owner argument, so the old code cannot be called the new way and a TypeError
would have proved nothing on its own.

The mechanics of the split — the shard, the fold, failure isolation — are in
`test_per_owner_pass.py`. This file is only about whose rows go where.
"""
from __future__ import annotations

import json
import os

import pytest

from tests.conftest import FakeCursor

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

OWNER_A = "11111111-1111-4111-a111-111111111111"
OWNER_B = "22222222-2222-4222-a222-222222222222"


def _results(*specs):
    from pipeline.orchestrator import StageResult
    return [StageResult(*s) for s in specs]


# ---- the two bugs this task closes ---------------------------------------

def test_the_eligible_queue_query_is_scoped_to_one_owner():
    # B-GAE-027. v_apply_queue carries owner_id and ELIGIBLE_SQL named no
    # owner at all, so the digest was built from every owner's rows.
    from notify.nudges import ELIGIBLE_SQL
    low = " ".join(ELIGIBLE_SQL.split()).lower()
    assert "owner_id = %s" in low, "the nudge still selects every owner's queue"


def test_the_personal_stages_cannot_be_called_the_old_ownerless_way():
    # B-GAE-027's real guard against a repeat: the signature. A stage that can
    # still be called without an owner will be, eventually.
    from cv.filing import run_filing_stage
    from notify.nudges import nudge_stage
    with pytest.raises(TypeError):
        nudge_stage(FakeCursor(rows=[]), send=lambda *a: True)
    with pytest.raises(TypeError):
        run_filing_stage(FakeCursor(rows=[]), settings=object())


def test_the_nudge_asks_for_the_owner_it_was_given_not_the_first_profile():
    from notify.nudges import load_channel
    cur = FakeCursor(rows=[{"notification_channel": "ch"}])
    load_channel(cur, OWNER_B)
    sql, params = cur.executed[0]
    assert "profile_id = %s" in sql.lower() and params == (OWNER_B,)
    assert "order by created_at" not in sql.lower()


FIRST_PROFILE_RE = __import__("re").compile(
    r"from\s+profiles\s+order\s+by\s+created_at\s+limit\s+1", __import__("re").I)


def code_without_prose(text: str) -> str:
    """Source with docstrings and comments removed, whitespace flattened.

    String literals are KEPT — the pattern being hunted lives inside SQL
    literals, so stripping strings wholesale would leave the scan unable to
    find anything. Docstrings and comments go because a file is allowed to
    *describe* the defect it fixed; this file's own guard first fired on the
    paragraph in `pipeline/owners.py` explaining B-GAE-028, which is prose
    doing its job, not a bug.
    """
    import ast
    import io
    import tokenize

    lines = text.splitlines()
    prose: set[int] = set()
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        first = node.body[0] if node.body else None
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            prose.update(range(first.lineno, first.end_lineno + 1))

    # Comment spans from the tokenizer, not a naive '#' split — a '#' inside a
    # string literal would otherwise truncate real code and hide an offender.
    cut_at: dict[int, int] = {}
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            cut_at.setdefault(tok.start[0], tok.start[1])

    kept = [line[:cut_at[n]] if n in cut_at else line
            for n, line in enumerate(lines, start=1) if n not in prose]
    return " ".join(" ".join(kept).split())


def test_no_stage_script_open_codes_the_first_profile_lookup():
    # B-GAE-028's class guard. That bug hid from `grep default_profile_id`
    # because it was open-coded as `order by created_at limit 1` over
    # profiles. This scans for the PATTERN, and allows it in the one module
    # where it legitimately belongs.
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    allowed = {root / "src" / "criteria" / "loader.py"}
    offenders = []
    for folder in ("src", "scripts"):
        for path in sorted((root / folder).rglob("*.py")):
            if path in allowed or "__pycache__" in path.parts:
                continue
            if FIRST_PROFILE_RE.search(code_without_prose(path.read_text())):
                offenders.append(str(path.relative_to(root)))
    assert offenders == [], (
        f"these pick an owner by creation order instead of being given one: "
        f"{offenders}. That is B-GAE-028 — a per-owner value read blind, "
        f"invisible to a search for default_profile_id.")


def test_the_first_profile_scan_still_catches_the_code_it_was_written_for():
    # The control, in the B-GAE-011 spirit: the test above now passes because
    # the defect is gone, and it would pass just as happily if the scan were
    # broken. So the scan is run against the exact source B-GAE-028 was found
    # in, and must still see it.
    before = (
        'def main():\n'
        '    """Set apply-by dates on open roles."""\n'
        '    cur.execute("select apply_window_days '
        'from profiles order by created_at limit 1")\n'
    )
    assert FIRST_PROFILE_RE.search(code_without_prose(before)), \
        "the scan can no longer see B-GAE-028's own code"
    # …and prose describing it is not an offence.
    assert not FIRST_PROFILE_RE.search(code_without_prose(
        '"""It read: from profiles order by created_at limit 1. Not any more."""\n'
        'x = 1\n'))


# ---- against a real database ---------------------------------------------

@DB_ONLY
def test_owner_bs_roles_never_reach_owner_as_nudge():
    """B-GAE-027, proven by trying it: two owners, two companies, two
    listings, and a digest built for A that must contain none of B's."""
    from db.connection import get_conn
    from notify.nudges import nudge_stage

    schema = "per_owner_nudge_probe"
    sent = []
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
                cur.execute(f"create schema {schema}")
                cur.execute(f"set search_path to {schema}, public")
                for table in ("profiles", "target_companies", "role_listings"):
                    cur.execute(f"create table {table} "
                                f"(like public.{table} including all)")
                cur.execute(
                    "insert into profiles (profile_id, name, notification_channel) "
                    "values (%s,'A','channel-a'),(%s,'B','channel-b')",
                    (OWNER_A, OWNER_B))
                cur.execute(
                    "insert into target_companies (owner_id, company_name) "
                    "values (%s,'A Corp'),(%s,'B Corp') returning company_id",
                    (OWNER_A, OWNER_B))
                cur.execute("select company_id, owner_id from target_companies "
                            "order by company_id")
                # str() on the way out: the column is uuid and psycopg returns a
                # uuid.UUID, not the string these tests key by. Treating the two
                # as interchangeable is what hid B-GAE-007.
                companies = {str(r["owner_id"]): r["company_id"]
                             for r in cur.fetchall()}

                # v_apply_queue is a view over public tables; the probe schema
                # cannot reproduce it, so the queue rows are supplied directly
                # and only the OWNER filter is under test here.
                rows = []
                for owner, label in ((OWNER_A, "A"), (OWNER_B, "B")):
                    # fit_rank and sponsor_signal are computed by v_apply_queue,
                    # not stored — the LIKE scaffold refused them, which is the
                    # scaffold doing its job (B-GAE-015's lesson).
                    cur.execute(
                        "insert into role_listings (company_id, role_title, role_url, "
                        "role_status) values (%s,%s,%s,'open') returning role_id",
                        (companies[owner], f"{label} Engineer",
                         f"https://example.invalid/{label}"))
                    rows.append((owner, label, cur.fetchone()["role_id"]))

                queue = [
                    {"role_id": rid, "company_name": f"{label} Corp",
                     "fit_rank": "High", "sponsor_signal": "role-confirmed",
                     "role_title": f"{label} Engineer", "role_url": "u",
                     "salary_wall": "ok", "deadline": None,
                     "deadline_source": None, "owner_id": owner}
                    for owner, label, rid in rows
                ]

                class QueueCursor:
                    """Serves the queue rows the scoped ELIGIBLE_SQL asks for,
                    and passes every other statement to the real cursor."""

                    def __init__(self, inner):
                        self.inner = inner

                    def execute(self, sql, params=None):
                        if "v_apply_queue" in sql:
                            owner = params[0] if params else None
                            self._rows = [r for r in queue if r["owner_id"] == owner]
                            return
                        self._rows = None
                        self.inner.execute(sql, params)

                    def fetchall(self):
                        return self._rows if self._rows is not None else self.inner.fetchall()

                    def fetchone(self):
                        return self._rows[0] if self._rows else self.inner.fetchone()

                shim = QueueCursor(cur)
                out = nudge_stage(shim, send=lambda ch, t, b: sent.append((ch, b)) or True,
                                  owner_id=OWNER_A)

                assert len(sent) == 1, out
                channel, body = sent[0]
                assert channel == "channel-a"
                assert "B Corp" not in body and "B Engineer" not in body, \
                    "owner B's roles reached owner A's phone"
                assert "A Corp" in body

                # …and B's row is left UNSTAMPED, so B's own pass still finds it.
                b_role = [rid for owner, _, rid in rows if owner == OWNER_B][0]
                cur.execute("select nudged_at from role_listings where role_id=%s",
                            (b_role,))
                assert cur.fetchone()["nudged_at"] is None, \
                    "A's nudge stamped B's listing — B is now never nudged for it"
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.commit()       # B-GAE-041: a rolled-back drop is not a drop


@DB_ONLY
def test_finish_run_lands_a_real_pipeline_runs_row_with_its_owner_lines():
    """The writer ratchet for `pipeline.report` (B-GAE-016's class).

    `stages` is jsonb, and the fold now builds a nested structure rather than
    a flat list — exactly the shape a FakeCursor cannot say anything true
    about. This runs the real functions against real column types.
    """
    from db.connection import get_conn
    from pipeline.report import finish_run, run_report, start_run

    schema = "per_owner_report_probe"
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
                cur.execute(f"create schema {schema}")
                cur.execute(f"set search_path to {schema}")
                cur.execute("create table pipeline_runs "
                            "(like public.pipeline_runs including all)")

                run_id = start_run(cur)
                assert isinstance(run_id, int)

                finish_run(cur, run_id, _results(
                    ("register", True, "144k rows", 9.0, None),
                    ("promote", True, "promoted 2", 2.0, OWNER_A),
                    ("promote", False, "exit 1: boom", 0.5, OWNER_B),
                ))

                row = run_report(cur, run_id)
                assert row["status"] == "failed"
                stages = row["stages"]          # jsonb comes back parsed
                assert [s["name"] for s in stages] == ["register", "promote"]
                assert stages[0].get("owners") is None
                assert [o["seq"] for o in stages[1]["owners"]] == [1, 2]
                assert stages[1]["ok"] is False
                assert OWNER_A not in json.dumps(stages)

                # The status page's query, run for real against the fold: it
                # must still see one row per stage NAME.
                cur.execute(
                    "select count(*) as n from pipeline_runs pr, "
                    "lateral jsonb_array_elements(pr.stages) as o(s) "
                    "where pr.run_id = %s", (run_id,))
                assert cur.fetchone()["n"] == 2, \
                    "the status page's stage count changed shape"
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.commit()       # B-GAE-041: a rolled-back drop is not a drop


@DB_ONLY
def test_each_owner_gets_their_own_apply_window():
    """B-GAE-028, proven by trying it: two owners with different windows and
    one open listing each — the two estimated deadlines must differ by exactly
    the difference between the windows."""
    import subprocess
    import sys
    from pathlib import Path

    from db.connection import get_conn

    root = Path(__file__).resolve().parents[1]
    schema = "per_owner_window_probe"
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
                cur.execute(f"create schema {schema}")
                cur.execute(f"set search_path to {schema}, public")
                for table in ("profiles", "target_companies", "role_listings"):
                    cur.execute(f"create table {table} "
                                f"(like public.{table} including all)")
                cur.execute(
                    "insert into profiles (profile_id, name, apply_window_days) "
                    "values (%s,'A',21),(%s,'B',7)", (OWNER_A, OWNER_B))
                cur.execute(
                    "insert into target_companies (owner_id, company_name) "
                    "values (%s,'A Corp'),(%s,'B Corp')", (OWNER_A, OWNER_B))
                cur.execute("select company_id, owner_id from target_companies")
                companies = {str(r["owner_id"]): r["company_id"]
                             for r in cur.fetchall()}
                for owner in (OWNER_A, OWNER_B):
                    cur.execute(
                        "insert into role_listings (company_id, role_title, role_url, "
                        "role_status, jd_full) values (%s,'Engineer',%s,'open',"
                        "'No closing date is stated anywhere in this advert.')",
                        (companies[owner], f"https://example.invalid/{owner}"))
                conn.commit()

                from history.survival import build_curves
                from pipeline.owners import owner_window

                assert owner_window(cur, OWNER_A) == 21
                assert owner_window(cur, OWNER_B) == 7
                build_curves(cur)   # must not explode on a two-owner schema

                # The stage itself, run per owner, in the probe schema.
                env = {**os.environ, "PYTHONPATH": "src",
                       "PGOPTIONS": f"-c search_path={schema},public"}
                for owner in (OWNER_A, OWNER_B):
                    proc = subprocess.run(
                        [sys.executable, "scripts/enrich_deadlines.py", "--owner", owner],
                        cwd=root, capture_output=True, text=True, env=env)
                    assert proc.returncode == 0, proc.stderr

                cur.execute(
                    "select tc.owner_id, rl.deadline, rl.created_at::date as seen "
                    "from role_listings rl join target_companies tc using (company_id) "
                    "order by tc.owner_id")
                by_owner = {str(r["owner_id"]): r for r in cur.fetchall()}
                gap_a = (by_owner[OWNER_A]["deadline"] - by_owner[OWNER_A]["seen"]).days
                gap_b = (by_owner[OWNER_B]["deadline"] - by_owner[OWNER_B]["seen"]).days
                assert gap_a == 21, f"owner A got a {gap_a}-day window, not 21"
                assert gap_b == 7, (
                    f"owner B got a {gap_b}-day window, not 7 — B-GAE-028: "
                    f"the first profile's window was applied to everyone")
        finally:
            # B-GAE-041. This test MUST commit mid-run — it spawns
            # scripts/enrich_deadlines.py as a subprocess, which is a separate
            # connection and can only see committed rows — so its schema is
            # durable and the drop below is the only thing that removes it.
            # DDL is transactional, so the `conn.rollback()` that used to end
            # this block UNDID the drop on every run, and `if exists` made each
            # run look like a clean one. The two sibling probes never commit,
            # so their final rollback erased schema and all: same `finally`,
            # opposite outcome, which is why only this one lingered on the
            # production database and nobody noticed for a week.
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {schema} cascade")
            conn.commit()       # B-GAE-041: a rolled-back drop is not a drop
