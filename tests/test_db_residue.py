"""B-GAE-041 — the live database must carry nothing a test invented.

The DB tests in this suite work by building a throwaway schema that mirrors
real tables (`create table x (like public.x including all)`), doing their work
inside it, and dropping it in a `finally`. That is a good pattern: it proves
things against real column types, real generated columns and real constraints,
which a `FakeCursor` cannot, without touching a row anybody owns.

It has one failure mode, and this file exists because the project hit it.
DDL is transactional in Postgres, so a `drop schema` followed by a
`conn.rollback()` **undoes the drop**. A test that never commits gets away
with it — its final rollback erases the schema and everything in it, same
`finally`, opposite outcome. A test that must commit mid-run (because it
spawns a subprocess that has to SEE its rows) does not: the schema is durable,
the drop is rolled back, and the residue is committed to the production
database on every green run. `drop schema if exists` then makes every
subsequent run look like a successful cleanup.

Nothing noticed for a week. So the guard is not "did this one test clean up"
but "is the live database clean at all", and the list of names it checks is
**read out of the test sources** rather than copied here — two copies of one
list is how a mirror starts drifting (the [[B-GAE-025]] lesson), and a probe
added next month would not be in a copy.

Opt-in like every DB test: `RUN_DB_TESTS=1`.
"""
from __future__ import annotations

import os
import pathlib
import re

import pytest

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

TESTS_DIR = pathlib.Path(__file__).resolve().parent

# `schema = "per_owner_window_probe"` — the one line every probe test writes.
SCHEMA_LITERAL = re.compile(r'^\s*schema = "([a-z0-9_]+)"', re.M)


def invented_schema_names() -> set[str]:
    """Every schema name a test file in this suite creates for itself."""
    names: set[str] = set()
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        names.update(SCHEMA_LITERAL.findall(path.read_text()))
    return names


def test_the_scan_finds_the_probe_names_the_suite_actually_uses():
    # Without this, a parser that silently matched nothing would make the
    # assertion below pass over a database full of residue — this project's
    # most repeated defect (B-GAE-004's shape) applied to a scanner. Pinned
    # names, not just a count, so a rename shows up as this failing rather
    # than as coverage quietly shrinking.
    found = invented_schema_names()
    assert "per_owner_window_probe" in found, (
        f"the scan no longer sees the probe that caused B-GAE-041: {sorted(found)}")
    assert len(found) >= 8, (
        f"the scan found only {len(found)} probe names ({sorted(found)}); there "
        "were 11 when this was written, so the parser has probably broken "
        "rather than the suite having shed probes")


@DB_ONLY
def test_no_schema_a_test_invented_survives_on_the_live_database():
    """The residue check itself. Red before the fix: `per_owner_window_probe`
    was present with 3 tables after two green RUN_DB_TESTS=1 runs."""
    from db.connection import get_conn

    invented = invented_schema_names()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "select nspname from pg_namespace where nspname = any(%s)",
            (sorted(invented),))
        survivors = sorted(r["nspname"] for r in cur.fetchall())

    assert survivors == [], (
        f"these test schemas are still on the live database: {survivors}. A "
        "probe test's cleanup dropped them inside a transaction and then rolled "
        "the drop back — DDL is transactional, so the `finally` must COMMIT the "
        "drop (B-GAE-041). Drop them by hand, then fix the test that left them."
    )


@DB_ONLY
def test_the_residue_scan_can_see_a_schema_that_is_really_there():
    """The control. The assertion above passes if the query is broken, if the
    name list is empty, or if `pg_namespace` is being read wrongly — all three
    look exactly like a clean database. So: plant one, prove the scan sees it,
    remove it the way the fixed tests now do."""
    from db.connection import get_conn

    planted = "residue_scan_control_probe"
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {planted} cascade")
                cur.execute(f"create schema {planted}")
                conn.commit()

                cur.execute(
                    "select nspname from pg_namespace where nspname = any(%s)",
                    ([planted],))
                assert [r["nspname"] for r in cur.fetchall()] == [planted], (
                    "the scan cannot see a schema that is definitely there — "
                    "the residue check above proves nothing")
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(f"drop schema if exists {planted} cascade")
            conn.commit()      # the whole point of B-GAE-041: COMMIT the drop

    # And prove the cleanup this file preaches actually worked, in a NEW
    # connection so nothing can be hiding in the first one's transaction.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("select nspname from pg_namespace where nspname = %s", (planted,))
        assert cur.fetchall() == [], (
            "the control's own committed drop did not stick — which is the bug "
            "this file is about, now in the file that checks for it")
