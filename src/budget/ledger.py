"""The spend ledger: one call, two scopes, atomic (Phase 9 task 5).

Generalises the JD drip's shared 950/day Reed ledger. Every metered call is
counted twice — against the WORLD cap, which is the provider's quota and
belongs to everybody, and against the calling OWNER's daily budget, so one
key holder can never eat the shared day. The nightly world half passes no
owner and therefore debits only the world half; that is what keeps the
founder's own night byte-identical to what it was before this existed.

Both debits are conditional upserts whose WHERE clause IS the cap, so the
check and the spend are one statement and two processes cannot both squeeze
through a gap between them. The world is debited first because it always
applies; if the owner half then refuses, the world debit is handed straight
back, which is why a refused call costs the shared quota nothing.

Fail closed twice over: a source with no cap row makes both subselects NULL,
`calls < NULL` is NULL, no row comes back, and the call is refused rather
than granted an infinite budget. And a spend is spent — the ledger is written
on the *attempt*, including a retry and including a call that then failed,
because the provider counts those too.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

SOURCES = ("adzuna", "reed", "companies_house")
RESETS = "midnight UTC"

_DEBIT_WORLD = """
insert into api_quota_ledger (source, day, calls)
select %(source)s, %(day)s, 1
 where (select world_daily from api_budget_caps
         where source = %(source)s) > 0
    on conflict (source, day) do update
   set calls = api_quota_ledger.calls + 1
 where api_quota_ledger.calls < (select world_daily from api_budget_caps
                                  where source = %(source)s)
returning calls
"""

_DEBIT_OWNER = """
insert into api_owner_spend (owner_id, source, day, calls)
select %(owner)s, %(source)s, %(day)s, 1
 where (select owner_daily from api_budget_caps
         where source = %(source)s) > 0
    on conflict (owner_id, source, day) do update
   set calls = api_owner_spend.calls + 1
 where api_owner_spend.calls < (select owner_daily from api_budget_caps
                                 where source = %(source)s)
returning calls
"""

_REFUND_WORLD = ("update api_quota_ledger set calls = calls - 1 "
                 "where source = %(source)s and day = %(day)s")

_READ = """
select coalesce((select world_daily from api_budget_caps
                  where source = %(source)s), 0)              as world_cap,
       coalesce((select calls from api_quota_ledger
                  where source = %(source)s and day = %(day)s), 0)
                                                              as world_spent,
       (select owner_daily from api_budget_caps
         where source = %(source)s)                           as owner_cap,
       coalesce((select calls from api_owner_spend
                  where owner_id = %(owner)s and source = %(source)s
                    and day = %(day)s), 0)                    as owner_spent
"""


def utc_day() -> date:
    """Today in UTC — the day the refusal message promises a reset on.

    Deliberately not `date.today()`: the container runs UTC and agrees, but a
    laptop in London would otherwise split one provider-day across two ledger
    rows for an hour each summer evening.
    """
    return datetime.now(timezone.utc).date()


@dataclass(frozen=True)
class Verdict:
    """One charge, with the numbers that justify it — no naked refusals."""

    source: str
    owner_id: str | None
    world_spent: int
    world_cap: int
    owner_spent: int | None
    owner_cap: int | None
    refused_by: str | None      # None | "world" | "owner"

    @property
    def allowed(self) -> bool:
        return self.refused_by is None

    @property
    def receipts(self) -> dict:
        owner = None
        if self.owner_id is not None and self.owner_cap is not None:
            owner = _scope(self.owner_spent, self.owner_cap)
        return {"source": self.source, "owner_id": self.owner_id,
                "refused_by": self.refused_by, "resets": RESETS,
                "world": _scope(self.world_spent, self.world_cap),
                "owner": owner}

    @property
    def message(self) -> str:
        if self.allowed:
            return (f"{self.source}: {self.world_spent}/{self.world_cap} "
                    f"world calls used today")
        scope = (f"owner {self.owner_spent}/{self.owner_cap}"
                 if self.refused_by == "owner"
                 else f"world {self.world_spent}/{self.world_cap}")
        return (f"{self.source} budget spent — resets at {RESETS} "
                f"({scope} today)")


def _scope(spent: int, cap: int) -> dict:
    return {"spent": spent, "cap": cap, "remaining": max(0, cap - spent)}


def _read(cur, source: str, owner_id: str | None, day) -> dict:
    cur.execute(_READ, {"source": source, "owner": owner_id, "day": day})
    return cur.fetchone()


def _refused(cur, source, owner_id, day, by: str) -> Verdict:
    row = _read(cur, source, owner_id, day)
    return Verdict(source=source, owner_id=owner_id,
                   world_spent=row["world_spent"], world_cap=row["world_cap"],
                   owner_spent=row["owner_spent"] if owner_id else None,
                   owner_cap=row["owner_cap"] if owner_id else None,
                   refused_by=by)


def charge(cur, source: str, owner_id: str | None = None, day=None) -> Verdict:
    """Debit one call against the world cap and, when given, an owner budget.

    Returns a Verdict either way — the caller decides whether a refusal is
    fatal. Nothing is left half-spent: a world debit is refunded when the
    owner half refuses.
    """
    day = day or utc_day()
    args = {"source": source, "owner": owner_id, "day": day}

    cur.execute(_DEBIT_WORLD, args)
    world = cur.fetchone()
    if world is None:
        return _refused(cur, source, owner_id, day, "world")

    if owner_id is None:
        row = _read(cur, source, None, day)
        return Verdict(source=source, owner_id=None,
                       world_spent=world["calls"], world_cap=row["world_cap"],
                       owner_spent=None, owner_cap=None, refused_by=None)

    cur.execute(_DEBIT_OWNER, args)
    owner = cur.fetchone()
    if owner is None:
        cur.execute(_REFUND_WORLD, args)
        return _refused(cur, source, owner_id, day, "owner")

    row = _read(cur, source, owner_id, day)
    return Verdict(source=source, owner_id=owner_id,
                   world_spent=world["calls"], world_cap=row["world_cap"],
                   owner_spent=owner["calls"], owner_cap=row["owner_cap"],
                   refused_by=None)


def remaining(cur, source: str, owner_id: str | None = None, day=None) -> dict:
    """What is left today, in both scopes — what sweep_status shows."""
    day = day or utc_day()
    row = _read(cur, source, owner_id, day)
    return {"source": source, "day": str(day), "resets": RESETS,
            "world": _scope(row["world_spent"], row["world_cap"]),
            "owner": (_scope(row["owner_spent"], row["owner_cap"] or 0)
                      if owner_id else None)}
