"""The Reed JD drip (U5): full descriptions for ad-only listings, nightly.

Ad-merged listings carry only a snippet; industries that rarely rent the
four guessable boards (care, hospitality, retail) live almost entirely on
ads, so this drip is the primary description supply for most non-software
users. Reed's details endpoint serves the full text; Adzuna has none, so
its ads wait on board discovery. Budget honesty is the core contract: the
drip shares Reed's ledgered ~950/day with the broad sweep — it reads the
ledger first and never overspends the day.

Since task 5 it no longer WRITES that ledger. The debit moved down to the one
place Reed is actually called (`budget.gate`, at the client choke point), so
there is a single writer rather than one per runner, and the same cap now
covers paths the drip has never heard of. What is left here is the stage's
own politeness cap and the honest stop when the shared day runs out.
"""
from __future__ import annotations

from datetime import date

from budget.gate import BudgetExhausted
from discover.agg_store import quota_spent
from discover.aggregators import reed_job_details
from fetch.feeds import _strip_html

clean_html = _strip_html    # the ONE html stripper, shared — never a copy

DRIP_CAP = 200              # the stage's own nightly politeness cap
REED_DAILY_CAP = 950        # the provider's free day, shared with the sweep


def pick_drip_batch(cur, n) -> list[dict]:
    """The highest-value ad-only rows: open, Reed-merged (only Reed has a
    details API), still JD-less — queue rows first (they are what the owner
    will actually read), then newest. Deterministic, so a stopped drip
    resumes exactly."""
    cur.execute(
        "select r.role_id, max(a.external_id) as external_id, "
        "bool_or(q.role_id is not null) as in_queue "
        "from role_listings r "
        "join aggregator_ads a on a.merged_role_id = r.role_id "
        "and a.source = 'reed' "
        "left join v_apply_queue q on q.role_id = r.role_id "
        "where r.role_status = 'open' and coalesce(r.jd_full, '') = '' "
        "group by r.role_id, r.created_at "
        "order by bool_or(q.role_id is not null) desc, r.created_at desc, "
        "r.role_id limit %(n)s",
        {"n": n})
    return cur.fetchall()


def run_drip(cur, settings, *, cap: int = DRIP_CAP, fetcher=None, picker=None,
             session=None, commit=None, today: date | None = None) -> dict:
    """One nightly drip pass; per-item commit = exact resume.

    A bad item costs one item, never the stage — but an exhausted budget
    stops the pass, because every further item would refuse identically."""
    if not getattr(settings, "reed_ready", False):
        return {"outcome": "no_key", "picked": 0, "fetched": 0, "errors": 0}
    today = today or date.today()
    spent = quota_spent(cur, "reed", today)
    budget = min(cap, max(0, REED_DAILY_CAP - spent))
    if budget <= 0:
        return {"outcome": "quota_exhausted", "picked": 0, "fetched": 0,
                "errors": 0}

    rows = (picker or pick_drip_batch)(cur, budget)
    fetch = fetcher or reed_job_details
    if rows and session is None:
        import requests
        session = requests.Session()

    fetched = errors = 0
    for row in rows:
        try:
            jd = fetch(settings.reed_api_key, row["external_id"], session)
        except BudgetExhausted as refusal:
            # NOT a bad item. The clause below would turn one exhausted
            # budget into 200 "broken jobs" and keep trying every one of
            # them — noise where the honest answer is to stop.
            return {"outcome": "quota_exhausted", "picked": len(rows),
                    "fetched": fetched, "errors": errors,
                    "budget": refusal.receipts}
        except Exception:       # per-item isolation, as every other stage
            jd = None
        if jd:
            cur.execute(
                "update role_listings set jd_full=%s, updated_at=now() "
                "where role_id=%s", (jd, row["role_id"]))
            fetched += 1
        else:
            errors += 1
        if commit is not None:
            commit()
    # Read back rather than add up: the gate is the writer now, and it counts
    # retries the arithmetic here never could.
    return {"outcome": "ok", "picked": len(rows), "fetched": fetched,
            "errors": errors, "reed_spent_today": quota_spent(cur, "reed", today)}
