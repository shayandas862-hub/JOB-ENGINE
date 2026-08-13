"""Shared test fakes, and the one predicate that says which repo this is."""
from __future__ import annotations

import contextlib
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_PUBLIC_WORKFLOW = _ROOT / "ops" / "flip" / "public-ci.yml"
_CHECKED_OUT_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"

#: The second, independent signal (B-GAE-040). `ops/flip/prepare-snapshot.sh`
#: deletes this file on the way out and nothing else in the project removes it,
#: so its absence is a fact about the SCRUB rather than about the workflow —
#: which is what makes it independent of the signal below.
#: `test_the_two_snapshot_signals_are_read_from_the_real_scrub_list` keeps this
#: path honest if the scrub list ever changes.
_SCRUBBED_MARKER = _ROOT / "CLAUDE.md"


def workflow_matches_the_public_one() -> bool:
    """Signal one: the workflow this checkout carries IS the one the scrub installs."""
    try:
        return _CHECKED_OUT_WORKFLOW.read_text() == _PUBLIC_WORKFLOW.read_text()
    except OSError:
        return False        # no workflow at all (the container) — not a snapshot


def scrub_marker_is_gone() -> bool:
    """Signal two: a file only the scrub deletes is absent."""
    return not _SCRUBBED_MARKER.exists()


def _is_snapshot() -> bool:
    """True when this checkout is the PUBLIC snapshot rather than the private repo.

    The snapshot ships one workflow — `ops/flip/public-ci.yml`, installed as
    `.github/workflows/ci.yml` (B-GAE-035) — so any test asserting on the
    private deploy workflow has nothing to read there, and the public repo's
    own first CI run would go red for a brand new reason. Which is the exact
    failure the workflow repair exists to end, arriving from the other side.

    Detected structurally, never by a flag or an environment variable: nothing
    has to be remembered or set.

    **Two signals, and BOTH must agree** (B-GAE-040). Asking only whether the
    workflow matches made the predicate read the very file the `private_only`
    guards exist to protect: `cp ops/flip/public-ci.yml .github/workflows/ci.yml`
    in the PRIVATE repo — the documented "bad fix" for a public red X — flipped
    the answer to True and dismissed seven guards, including the anti-B-GAE-004
    control, leaving a fully green suite over a repo that could no longer
    deploy. Corrupting a subject must never be able to excuse its own guards.
    So a checkout is the snapshot only when the workflow matches AND a file the
    scrub deletes is really gone; a single `cp` moves one signal and not the
    other, and the disagreement is then a loud failure rather than a silence
    (`test_the_snapshot_signals_never_disagree`).
    """
    return workflow_matches_the_public_one() and scrub_marker_is_gone()


SNAPSHOT_CHECKOUT = _is_snapshot()

#: Marks a contract that only exists in the private repository.
private_only = pytest.mark.skipif(
    SNAPSHOT_CHECKOUT,
    reason="private-repo contract: this checkout is the public snapshot")


@pytest.fixture(autouse=True)
def _budget_off():
    """Metering off for the whole suite, on purpose and in one visible place.

    `budget.gate` defaults to METERED — with no meter installed, the first
    call to a priced API opens its own ledger connection. That default is the
    safety property (a runner cannot forget to be metered), but it would make
    every offline client test reach for a database. So the suite opts out
    here, and the tests that care about metering install their own meter,
    which overrides this one for the length of their block.
    """
    from budget import gate
    with gate.unmetered():
        yield


class FakeCursor:
    """Records execute/executemany; serves canned rows for fetchall/fetchone."""

    def __init__(self, rowcount=0, rows=None):
        self.executed = []
        self.executed_many = []
        self.rowcount = rowcount
        self._rows = list(rows or [])

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))

    def executemany(self, sql, params_seq):
        self.executed_many.append((" ".join(sql.split()), list(params_seq)))

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    """A fake psycopg connection whose cursor() yields a preset FakeCursor."""

    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.commits = 0

    @contextlib.contextmanager
    def cursor(self):
        yield self._cursor

    def commit(self):
        self.commits += 1


@contextlib.contextmanager
def fake_conn(cursor: FakeCursor):
    """Drop-in for db.connection.get_conn in offline tool tests.

    Usage: ``monkeypatch.setattr(module, "get_conn", lambda: fake_conn(cur))``.
    """
    yield FakeConn(cursor)


class ScriptedCursor:
    """Routes each execute by SQL substring; serves per-route responses in
    order (the last response repeats). Records everything for assertions."""

    def __init__(self, routes):
        self.routes = [(m, list(rs)) for m, rs in routes]
        self.executed = []
        self._pending = []

    def execute(self, sql, params=None):
        squashed = " ".join(sql.split())
        self.executed.append((squashed, params))
        for marker, responses in self.routes:
            if marker in squashed.lower():
                self._pending = responses.pop(0) if len(responses) > 1 \
                    else list(responses[0])
                return
        self._pending = []

    def executemany(self, sql, params_seq):
        # recorded in the same stream so substring assertions see every write
        self.executed.append((" ".join(sql.split()), list(params_seq)))

    def fetchall(self):
        return list(self._pending)

    def fetchone(self):
        return self._pending[0] if self._pending else None
