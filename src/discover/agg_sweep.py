"""The aggregator broad sweep: quota-budgeted, cursor-resumable, keep-all.

One slice = one inventory walk (a source plus its narrowing params, e.g.
Reed full-UK or Adzuna it-jobs). Each page: check the day's quota ledger,
download, store everything labelled, match new employers against the register,
advance the cursor, COMMIT — so a stop (founder, quota, crash, laptop lid)
loses nothing and the next start resumes at the exact page. The daily quota is
a hard refusal, not a warning; after midnight the same command simply
continues. Person-agnostic by design: slices are parameters, not code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from budget.gate import BudgetExhausted
from discover.agg_match import match_pending
from discover.agg_store import (insert_ads, load_cursor, quota_spent,
                                save_cursor, stored_count)


@dataclass(frozen=True)
class Slice:
    slice_key: str
    source: str
    params: dict


def combine_outcomes(outcomes) -> str:
    """One verdict for a source walked as several sub-slices (salary bands).

    Worst-first precedence: quota beats error beats unfinished budget; only
    all-complete means complete. An empty list is trivially complete."""
    for worst in ("quota_exhausted", "source_error", "page_budget_done"):
        if worst in outcomes:
            return worst
    return "pass_complete"


def overall_verdict(per_source: dict) -> str:
    """One verdict across ALL sources — what the wrapper should do next.

    Defect found live 2026-07-27: Adzuna spent its cap in 29 minutes and the
    wrapper then slept 30 minutes while Reed still held 850 unused calls,
    because ANY capped source declared "quota exhausted". The drip may only
    nap when NOTHING can progress: a source with budget and pending work
    (page_budget_done) keeps the cycle going immediately, and it also outranks
    another source's transient error.
    """
    outcomes = set(per_source.values())
    if not outcomes or outcomes == {"pass_complete"}:
        return "pass_complete"
    # A walled band is FINISHED (as far as the provider allows), not broken:
    # it must never buy the drip a nap or an error-retry.
    if {"page_budget_done", "depth_wall"} & outcomes:
        return "page_budget_done"
    if "source_error" in outcomes:
        return "source_error"
    return "quota_exhausted"


def slice_for(source: str, **params) -> Slice:
    """A deterministic slice identity from its narrowing params (None = omit),
    so the same command always resumes the same cursor."""
    clean = {k: v for k, v in sorted(params.items()) if v is not None}
    key = source + "|" + "|".join(f"{k}={v}" for k, v in clean.items())
    return Slice(key, source, clean)


def run_slice(conn, sl: Slice, client, *, daily_cap: int, page_budget: int,
              today: date | None = None, match_limit: int = 200,
              stale_limit: int = 3, wall_at: int = 9_500, on_page=None) -> str:
    """Walk one slice until done, quota-stopped, or page budget spent.

    `client(page) -> (ads, total)` hides the HTTP (and the keys) from the
    orchestration. Returns 'pass_complete' | 'quota_exhausted' |
    'page_budget_done' | 'source_error'. A dead source (no ads AND no total —
    the clients' outage shape) is an error, never a completed pass.

    Two caps, and they are not the same cap. `daily_cap` is THIS sweep's own
    politeness limit, checked here before each page. The WORLD cap lives in
    the ledger and is enforced inside the client (task 5), which is why the
    debit that used to happen on this line is gone: one writer, at the one
    place the call is actually made.

    The SATURATION GUARD (live lesson 2026-07-25 — Adzuna clamps silently at
    ~5k accessible results, repeating pages without erroring): `stale_limit`
    consecutive non-empty pages that bank ZERO new rows declare the slice
    complete. A silent clamp or an overlap-saturated band costs a handful of
    calls, never a quota-day.

    The WALL GUARD (live defect 2026-07-28): a failure DEEP in a slice — past
    `wall_at` rows already seen — is Reed's hard 10k depth wall, not an
    outage, and retrying it can never succeed. Such a slice returns
    'depth_wall' and is closed, so the wrapper stops burning a call every 60s
    on a dead page (it had retried one band 638 times). An oversized band that
    walls is re-split by `agg_partition.split_band` so the unreachable
    remainder becomes reachable; an early failure stays 'source_error'.
    """
    today = today or date.today()
    with conn.cursor() as cur:
        state = load_cursor(cur, sl.slice_key)
        if state and state.get("pass_complete"):
            return "pass_complete"
        page = (state or {}).get("next_page") or 1
        seen = (state or {}).get("ads_seen") or 0
        banked = stored_count(cur, sl.source)
        stale = 0

        for _ in range(page_budget):
            if quota_spent(cur, sl.source, today) >= daily_cap:
                conn.commit()
                return "quota_exhausted"
            try:
                ads, total = client(page)
            except BudgetExhausted:
                # The world cap emptied under us mid-slice (the pre-check
                # above is this slice's OWN cap, which can be lower). Same
                # outcome word, so the wrapper stops rather than retrying a
                # call that cannot succeed until midnight.
                conn.commit()
                return "quota_exhausted"
            if not ads and total is None:
                if seen >= wall_at:    # the provider's depth wall, not an outage
                    save_cursor(cur, sl.slice_key, sl.source, sl.params,
                                next_page=page, total_reported=None,
                                ads_seen_inc=0, pass_complete=True)
                    conn.commit()
                    return "depth_wall"
                conn.commit()          # the attempted call stays ledgered
                return "source_error"
            if not ads:
                save_cursor(cur, sl.slice_key, sl.source, sl.params,
                            next_page=page, total_reported=total,
                            ads_seen_inc=0, pass_complete=True)
                conn.commit()
                return "pass_complete"
            insert_ads(cur, ads)
            match_pending(cur, limit=match_limit)
            now_banked = stored_count(cur, sl.source)
            stale = stale + 1 if now_banked == banked else 0
            banked = now_banked
            seen += len(ads)
            page += 1
            complete = ((total is not None and seen >= total)
                        or stale >= stale_limit)
            save_cursor(cur, sl.slice_key, sl.source, sl.params,
                        next_page=page, total_reported=total,
                        ads_seen_inc=len(ads), pass_complete=complete)
            conn.commit()
            if on_page is not None:
                on_page(sl, page - 1, len(ads), total)
            if complete:
                return "pass_complete"
        return "page_budget_done"
