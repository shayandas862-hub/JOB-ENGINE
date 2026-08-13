"""A scratch table must be a COPY of the real one, never an imitation — the
class guard for B-GAE-015, 020 and 022.

Three bugs, one mechanism. A test builds itself a scratch table with a
hand-written `CREATE TABLE`, a migration later adds a column, and the two drift
apart in silence. B-GAE-015 had been failing since migration 0049 and nobody
saw it. B-GAE-020's scaffold predated 0056. B-GAE-022 was two migrations stale
AND hiding a second defect underneath the first. Each was fixed one table at a
time, and each entry said the same thing: the class stays open until something
mechanical closes it, and until then the only guard is a sentence in a document.

This is that mechanical thing. The rule it enforces:

    create table x (like public.x including all)

`INCLUDING ALL` brings the column types, defaults, generated expressions, check
constraints and indexes — which is precisely the set a fake cursor cannot model
and where B-GAE-013 (a generated column) and B-GAE-014 (an untyped coalesce)
both lived. A LIKE cannot drift, because there is nothing in it to drift.

What LIKE does NOT copy is FOREIGN KEYS. Where a test's assertion depends on
referential integrity it has to re-add them by hand — B-GAE-022 makes the point
sharply: without re-adding `census_jobs`' FK, that test's ForeignKeyViolation
assertion would have quietly stopped asserting anything, which is its own
B-GAE-004.

Text-only, so it runs offline and inside the container: db/ and tests/ both
ship in the image.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
MIGRATIONS = ROOT / "db" / "migrations"

# The eight tables that predate db/migrations/ — measured for B-GAE-024, and a
# closed historical set: they were created through the Supabase dashboard in
# Phase 1, before the log existed, so no migration will ever create them.
GENESIS_TABLES = frozenset({
    "cowork_findings", "decisions", "licensed_sponsors", "role_listings",
    "role_skills", "skilled_worker_occupations", "target_companies",
    "target_roles",
})

CREATE_TABLE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?([a-z_0-9]+)"
    r"\s*\(\s*(like\s+public\.[a-z_0-9]+)?",
    re.I,
)


def _flatten(text: str) -> str:
    """Quotes out, whitespace squashed — so SQL split across adjacent string
    literals and across lines reads as one statement."""
    return re.sub(r"\s+", " ", text.replace('"', " ").replace("'", " "))


def _test_files() -> list[pathlib.Path]:
    """Every test file except this one.

    This file has to be excluded from its own scan: it quotes both the right and
    the WRONG spelling of a scaffold as documentation, and a text scan cannot
    tell an example from an offence. Skipping it was not a tidying-up — the
    exclusion is what makes the scan correct, and its absence made three of these
    four tests fail on the day they were written. B-GAE-009 is the same shape: a
    check that must name the thing it forbids belongs outside its own net.
    """
    return [p for p in sorted(TESTS.glob("*.py")) if p.name != pathlib.Path(__file__).name]


def real_tables() -> set[str]:
    """Every table that exists in public, derived without a database.

    Tables any migration creates, plus the genesis eight. Derived rather than
    hardcoded so a table added next week is covered with no edit here; measured
    against the live database when this was written and the count agreed exactly
    (28).
    """
    tables = set(GENESIS_TABLES)
    for path in sorted(MIGRATIONS.glob("*.sql")):
        for match in CREATE_TABLE.finditer(_flatten(path.read_text())):
            tables.add(match.group(1).lower())
    return tables


def scaffolds() -> list[tuple[str, str, bool]]:
    """(test file, table name, uses_like) for every CREATE TABLE in tests/."""
    out = []
    for path in _test_files():
        for match in CREATE_TABLE.finditer(_flatten(path.read_text())):
            out.append((path.name, match.group(1).lower(), bool(match.group(2))))
    return out


def test_no_test_hand_writes_a_table_that_already_exists_in_public():
    # The guard. A scratch table named after a real one must be a LIKE copy of
    # it; a table under any other name is a genuine scratch object and is free
    # to be written by hand.
    real = real_tables()
    handwritten = sorted(
        f"{file}: {table}"
        for file, table, uses_like in scaffolds()
        if table in real and not uses_like
    )
    assert handwritten == [], (
        "these tests hand-write a table that exists in public, so they will "
        f"drift from it the next time a migration lands: {handwritten}. Use "
        "`create table x (like public.x including all)` instead — and re-add "
        "any FOREIGN KEY the test's assertions actually depend on, because "
        "LIKE does not copy them (B-GAE-022)."
    )


def test_the_scan_still_sees_the_scaffolds_it_is_meant_to_police():
    # The control, without which the test above passes on an empty list. Both
    # halves have to be non-empty for the guard to mean anything: real tables
    # must be discoverable, and the LIKE scaffolds must be found.
    real = real_tables()
    assert len(real) >= 28, (
        f"only {len(real)} real tables derived; 28 were derivable when this was "
        "written and the count matched the live database exactly, so the "
        "migration scan has probably broken"
    )
    copies = [s for s in scaffolds() if s[1] in real and s[2]]
    assert len(copies) >= 20, (
        f"only {len(copies)} LIKE-based scaffolds found; there were 20. If they "
        "have genuinely gone, this guard is now policing nothing."
    )


def test_a_like_copy_names_the_same_table_it_imitates():
    # `create table role_listings (like public.target_companies including all)`
    # is a copy of the wrong table, and every assertion built on it would be
    # about something else entirely. Cheap to check, and it cannot be caught by
    # reading the test that does it.
    wrong = []
    for path in _test_files():
        flat = _flatten(path.read_text())
        for match in re.finditer(
            r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?([a-z_0-9]+)"
            r"\s*\(\s*like\s+public\.([a-z_0-9]+)",
            flat, re.I,
        ):
            scratch, source = match.group(1).lower(), match.group(2).lower()
            if scratch != source:
                wrong.append(f"{path.name}: {scratch} copies {source}")
    assert wrong == [], f"a scratch table imitates a different table: {wrong}"


def test_including_all_is_not_quietly_downgraded():
    # `like public.x` on its own copies column names and types and NOTHING
    # else — no defaults, no generated expressions, no check constraints. That
    # is the exact blind spot B-GAE-013 and B-GAE-014 lived in, so a LIKE
    # without INCLUDING ALL is barely better than a hand-written table.
    weak = []
    for path in _test_files():
        flat = _flatten(path.read_text())
        for match in re.finditer(
            r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?[a-z_0-9]+"
            r"\s*\(\s*like\s+public\.([a-z_0-9]+)([^)]*)\)",
            flat, re.I,
        ):
            if "including all" not in match.group(2).lower():
                weak.append(f"{path.name}: like public.{match.group(1)}")
    assert weak == [], (
        "these copy a real table without INCLUDING ALL, so they get its column "
        f"types but none of its defaults, generated columns or checks: {weak}"
    )
