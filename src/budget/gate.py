"""The client-layer gate: one line at each HTTP choke point (task 5).

There are exactly two functions in this codebase that reach a metered API —
`discover.aggregators._get_json` and `discover.companies_house._get_json` —
so the cap goes THERE rather than on each tool. Every tool that spends today
inherits it, and so does every tool written later, without anyone having to
remember. `source_for_url` is what makes that true: a future helper pointed at
`REED_BASE` is metered because of where it points, not because of who wrote it.

**The default is metered.** With nothing installed, the first charge opens its
own ledger connection from the environment. That direction matters: if the
default were "no metering", a runner that forgot to open a budget would spend
the shared quota in silence, which is the failure this module exists to stop.
Tests opt OUT explicitly (`unmetered()`, applied suite-wide by conftest) so
that opting out is a visible act rather than an accident.

The meter is a module global rather than a contextvar on purpose: the owner-lens
sweep probes with parallel workers, and a contextvar set on the main thread is
not visible inside them — the gate would silently stop metering exactly when
concurrency made it matter most.

Who is spending comes from GOAL_A_BUDGET_OWNER, an environment variable rather
than a flag, because the spending happens in DETACHED grandchildren: an MCP
tool spawns `scripts/run.py`, which spawns `scripts/jd_drip.py`, which is where
the Reed call finally happens. Environment crosses both hops on its own; a flag
would have to be threaded through every stage. Unset means the nightly world
half, which debits nobody.

**A limit worth knowing before it bites.** That design is correct because every
metered call happens in a process started FOR one owner. The ambient meter
reads the environment once, so inside the long-lived MCP server process it
would resolve to the server's own environment — nobody — and charge the world
alone no matter who called. No tool does that today: all five spending paths
detach. A tool that ever calls a metered API **in-process** must open its own
scope with `metered(conn, owner)` rather than rely on the ambient one. Nothing
enforces that but this paragraph, which makes it the weakest guard in the
module.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager

from budget import ledger

OWNER_ENV = "GOAL_A_BUDGET_OWNER"

_lock = threading.Lock()
_installed = None           # an explicit meter, or None to use the ambient one
_ambient = None             # the lazily-built ledgered meter
_connect = None             # test seam: how the ambient meter gets a connection


class BudgetExhausted(RuntimeError):
    """A metered call refused because its day is spent. Carries the numbers."""

    def __init__(self, verdict: ledger.Verdict):
        super().__init__(verdict.message)
        self.verdict = verdict

    @property
    def receipts(self) -> dict:
        return self.verdict.receipts


def source_for_url(url: str) -> str | None:
    """Which metered source a URL belongs to, or None for a free one.

    Board feeds (Greenhouse, Lever, Ashby, Workable, Workday) cost no quota
    and must never draw down an aggregator budget.
    """
    from discover.aggregators import ADZUNA_BASE, REED_BASE
    from discover.companies_house import CH_BASE
    for base, source in ((ADZUNA_BASE, "adzuna"), (REED_BASE, "reed"),
                         (CH_BASE, "companies_house")):
        if url.startswith(base):
            return source
    return None


def owner_from_env(env=os.environ) -> str | None:
    """The owner this process spends for; None is the nightly world half."""
    return (env.get(OWNER_ENV) or "").strip() or None


def charge_for(url: str) -> None:
    """Gate one outbound call. Raises BudgetExhausted when the day is spent."""
    source = source_for_url(url)
    if source is not None:
        current().charge(source)


def current():
    """The meter in force — installed, else the ambient ledgered one."""
    if _installed is not None:
        return _installed
    return _ambient_meter()


class LedgeredMeter:
    """Charges the real ledger on its own connection, under a lock.

    Its own connection because the spend must survive the caller's rollback —
    the provider does not refund a call because the surrounding transaction
    failed. Under a lock because the parallel sweep shares this one meter
    across worker threads and a psycopg connection is not reentrant.
    """

    def __init__(self, conn, owner_id: str | None):
        self.conn = conn
        self.owner_id = owner_id
        self._lock = threading.Lock()

    def charge(self, source: str) -> ledger.Verdict:
        with self._lock, self.conn.cursor() as cur:
            verdict = ledger.charge(cur, source, self.owner_id)
        if not verdict.allowed:
            raise BudgetExhausted(verdict)
        return verdict


class _Unmetered:
    """Spends nothing and refuses nothing — tests, and only tests."""

    def charge(self, source: str) -> None:
        return None


def _ambient_meter():
    global _ambient
    with _lock:
        if _ambient is None:
            _ambient = LedgeredMeter(_open_connection(), owner_from_env())
        return _ambient


def _open_connection():
    if _connect is not None:
        return _connect()
    import psycopg
    from psycopg.rows import dict_row

    from config import get_settings
    return psycopg.connect(get_settings().database_url, row_factory=dict_row,
                           autocommit=True)


def set_connect(factory) -> None:
    """Test seam: how the ambient meter opens its ledger connection."""
    global _connect, _ambient
    _connect, _ambient = factory, None


@contextmanager
def installed(meter):
    """Run a block against a specific meter."""
    global _installed
    previous, _installed = _installed, meter
    try:
        yield meter
    finally:
        _installed = previous


@contextmanager
def unmetered():
    """Run a block with metering off. Explicit by design — see the module note."""
    with installed(_Unmetered()):
        yield


@contextmanager
def no_meter_installed():
    """Run a block with no installed meter, so the ambient default is used."""
    with installed(None):
        yield


@contextmanager
def metered(conn, owner_id: str | None = None):
    """Run a block charging a given connection and owner."""
    with installed(LedgeredMeter(conn, owner_id)) as meter:
        yield meter
