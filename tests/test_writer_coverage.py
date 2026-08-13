"""Every module that writes to the database must meet a real one — B-GAE-016's
class guard.

The bug this exists to stop has now shipped twice in two days, in sibling
writers, with full offline coverage both times: B-GAE-013 wrote to a GENERATED
column and B-GAE-014 wrote an untyped `coalesce` against `'{}'`. Neither could
ever have been caught by the `FakeCursor`, and no rewrite of those offline tests
could have caught them either — a fake records the SQL *string*, so it goes red
because a function is missing and green because it exists, and **neither state
is ever about the database**. B-GAE-023 then made the point again from the
privilege side: the suite was green while `submit_reading` was dead.

So this is a test over the tests. It asks one question of every writer in
`src/`: is there at least one test that would run it against a real Postgres?

Deliberately mechanical, because the alternative is a rule someone has to
remember during a fast phase, and this project's own log says documents are its
weakest guard (five entries held shut by a sentence). It reads text; it imports
nothing and needs no database, so it runs in the offline lane and inside the
container.

The allowlist below was MEASURED at the sitting that wrote this file, not copied
from B-GAE-016's entry — and measuring it mattered: the entry's list of thirteen
and this measured list of thirteen are not the same thirteen. `discover.merge`
and `discover.onboarding` gained real coverage later in Phase 9 (B-GAE-018's and
B-GAE-020's fixes), while `audit` and `discover.agg_match` were never on the
entry's list at all.
"""
from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"

# A module "writes" if its text contains a write statement. Quotes are stripped
# before matching so SQL split across adjacent string literals — the style used
# throughout src/ — is still seen as one statement. Measured both ways when this
# was written: identical results today, and the stripped form is the one that
# will still be right when someone wraps a line.
WRITE_SQL = re.compile(
    r"\binsert\s+into\b"
    r"|\bupdate\s+[a-z_][a-z_0-9.]*\s+set\b"
    r"|\bdelete\s+from\b",
    re.I,
)

# The thirteen writers that no real-database test reaches today. This list may
# only ever SHRINK: a new writer does not get an entry, it gets a test.
#
# Where the exposure actually is, from B-GAE-016: most of these run nightly in
# the 06:30 pipeline, so a parse-time error there fails a stage loudly within
# one morning and the run is itself the integration test. The dangerous ones are
# the modules nothing runs except a person — `reading.accept` and `reading.serve`
# (the tray), and `discover.promote_rule`. Both bugs so far were that shape, and
# both were found by a human trying to use a tool.
BLIND_WRITERS = frozenset({
    "audit",
    "discover.agg_match",
    "discover.agg_partition",
    "discover.agg_store",
    "discover.promote_rule",
    "discover.register_refresh",
    "fetch.jd_drip",
    "persist.extract_rules",
    "persist.fetch_rules",
    "reading.accept",
    "reading.serve",
    "reading.stage",
})

# Pinned so the allowlist cannot grow. Lower it when a writer gains coverage;
# there is no legitimate reason to raise it. If a new writer needs to land
# without a database test, that is a conversation, not an edit to this number.
#
# 13 -> 12 (Phase 9 task 3): `pipeline.report` came off the list. The per-owner
# fold turned `stages` from a flat list into a nested structure inside a jsonb
# column, which is precisely the shape a FakeCursor can say nothing true
# about — so it gained
# `test_finish_run_lands_a_real_pipeline_runs_row_with_its_owner_lines`.
MAX_BLIND_WRITERS = 12


def _module_name(path: pathlib.Path) -> str:
    return ".".join(path.relative_to(SRC).with_suffix("").parts)


def writer_modules() -> set[str]:
    """Every module under src/ that issues INSERT, UPDATE or DELETE."""
    found = set()
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text()
        flattened = re.sub(r"\s+", " ", text.replace('"', " ").replace("'", " "))
        if WRITE_SQL.search(flattened):
            found.add(_module_name(path))
    return found


def _imports(nodes) -> set[str]:
    """Module paths reachable from Import/ImportFrom anywhere in these nodes.

    Both `discover.merge` and the `from discover import merge` spelling resolve
    to the same dotted name, because tests use both.
    """
    out: set[str] = set()
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Import):
                out.update(alias.name for alias in sub.names)
            elif isinstance(sub, ast.ImportFrom) and sub.module:
                out.add(sub.module)
                out.update(f"{sub.module}.{a.name}" for a in sub.names)
    return out


def db_covered_modules() -> dict[str, set[str]]:
    """module -> the test files whose RUN_DB_TESTS tests can reach it.

    A test counts as database-gated when its decorator mentions RUN_DB_TESTS
    (directly, or through a module-level marker name like DB_ONLY), or when the
    whole file is gated by `pytestmark`. Both spellings are in use and an
    earlier draft of this scan saw only the named one — which silently reported
    four files as having no database tests at all, and would have pinned four
    wrong names into the allowlist above.

    Module-level imports are credited to a file that has at least one gated
    test. That is deliberately generous: imports are shared across a file, and a
    stricter rule would produce failures people "fix" by shuffling import
    statements rather than by writing a real test.
    """
    covered: dict[str, set[str]] = {}
    for path in sorted(TESTS.glob("test_*.py")):
        text = path.read_text()
        if "RUN_DB_TESTS" not in text:
            continue
        tree = ast.parse(text)

        gate_names: set[str] = set()
        whole_file_gated = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and "RUN_DB_TESTS" in ast.unparse(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        gate_names.add(target.id)
                        if target.id == "pytestmark":
                            whole_file_gated = True

        gated_fns = []
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            decorators = [ast.unparse(d) for d in node.decorator_list]
            if (whole_file_gated
                    or any("RUN_DB_TESTS" in d for d in decorators)
                    or any(g in d for g in gate_names for d in decorators)):
                gated_fns.append(node)

        if not gated_fns:
            continue
        reachable = _imports(gated_fns) | _imports(
            [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        )
        for module in reachable:
            covered.setdefault(module, set()).add(path.name)
    return covered


def blind_writers() -> set[str]:
    return writer_modules() - set(db_covered_modules())


def test_a_new_database_writer_arrives_with_a_real_database_test():
    # The whole point. A writer that no RUN_DB_TESTS test can reach is the
    # B-GAE-013/014 shape, and the failure message has to name it — "coverage
    # dropped" is not actionable, "reading.accept writes and nothing runs it"
    # is.
    unexpected = sorted(blind_writers() - BLIND_WRITERS)
    assert unexpected == [], (
        "these modules write to the database and no RUN_DB_TESTS test reaches "
        f"them: {unexpected}. That is exactly how B-GAE-013 and B-GAE-014 "
        "shipped — both fully covered offline, both dead on arrival. Write a "
        "test that runs the real function against "
        "`create table (like public.x including all)`; do not add a name to "
        "BLIND_WRITERS."
    )


def test_the_allowlist_drops_a_writer_as_soon_as_it_gains_coverage():
    # Keeps the list honest in the other direction. Without this, an entry
    # survives after its test lands and the allowlist slowly stops describing
    # anything — and a renamed or deleted module leaves a dead name behind that
    # nobody notices, which is how a ratchet quietly stops ratcheting.
    stale = sorted(BLIND_WRITERS - blind_writers())
    assert stale == [], (
        f"these are on BLIND_WRITERS but are no longer blind: {stale}. "
        "Delete them from the list and lower MAX_BLIND_WRITERS — that is the "
        "ratchet closing by one."
    )


def test_the_blind_writer_allowlist_can_only_shrink():
    # The pin. test_a_new_database_writer... can be satisfied by adding the new
    # module to BLIND_WRITERS, which would defeat it entirely; this is the test
    # that makes that route fail too.
    assert len(BLIND_WRITERS) <= MAX_BLIND_WRITERS, (
        f"BLIND_WRITERS holds {len(BLIND_WRITERS)} entries but is pinned at "
        f"{MAX_BLIND_WRITERS}. A new writer never gets an entry here."
    )


def test_the_scan_finds_the_writers_this_repo_is_known_to_have():
    # A control, in the B-GAE-011 spirit: every assertion above is about a
    # DIFFERENCE between two measured sets, and both would pass beautifully if
    # the scan silently found nothing — a broken regex, a moved src/, an ast
    # failure. So the counts themselves are asserted.
    writers = writer_modules()
    assert len(writers) >= 22, (
        f"the writer scan found only {len(writers)} modules; it found 22 when "
        "this test was written, so it has probably stopped working rather than "
        "the repo having lost writers"
    )
    covered = set(db_covered_modules()) & writers
    assert covered, "no writer at all appears in a RUN_DB_TESTS test — the coverage scan is broken"
    # Named explicitly: these four were proven against real tables by
    # B-GAE-013/014/017/018's fixes, so if the scan stops seeing them it is the
    # scan that changed.
    for known in ("criteria.writer", "cv.blocks", "discover.merge", "review"):
        assert known in covered, f"{known} has a real-database test but the scan missed it"
