"""Beating Reed's 10,000-result deep-paging wall with adaptive salary bands.

Confirmed live 2026-07-22: Reed returns HTTP 500 at resultsToSkip=10,000, so
no slice with more than ~10k results can ever be fully walked. The fix: split
the inventory into SALARY BANDS (minimumSalary/maximumSalary filters), each
under a target count, discovered adaptively with cheap 1-result count calls.
Probes showed salary filters cover 99.93% of the inventory; the open top band
(smin=ceiling+1, no max) catches the tail above the ceiling.

The plan is persisted as aggregator_cursor rows — computed once, resumed
forever — and the legacy single 'reed|' cursor is retired (it can never
finish). Bands may overlap at edges in Reed's matching; the ads dedupe key
absorbs any repeats.
"""
from __future__ import annotations

from discover.agg_store import save_cursor
from discover.agg_sweep import slice_for


def plan_bands(count_fn, *, target: int = 9_000, ceiling: int = 200_000,
               max_bands: int = 256) -> list[dict]:
    """Split [0, ceiling] into contiguous bands each counting <= target.

    `count_fn(lo, hi) -> int` asks the provider how many ads a band holds
    (hi=None means open-ended). Binary splitting, so planning costs
    O(2·bands) calls. A band one pound wide that still exceeds the target is
    accepted as-is (nothing finer exists). The final open band (> ceiling)
    is appended unconditionally — probes show it is far under target.

    COVERAGE IS SACRED: when max_bands bites, every range still waiting on
    the stack is FLUSHED as an as-is (possibly oversized) leaf — never
    dropped. (Live lesson 2026-07-22: sub-£25k clustering ate a 64-leaf cap
    and silently lost the £25k–£200k professional range. Oversized leaves at
    worst hit the provider's wall and surface as source_error — a visible
    limp, not an invisible hole.)
    """
    leaves: list[dict] = []
    stack: list[tuple[int, int]] = [(0, ceiling)]
    while stack:
        lo, hi = stack.pop()
        if (len(leaves) + len(stack) >= max_bands or hi - lo < 1
                or count_fn(lo, hi) <= target):
            leaves.append({"smin": lo, "smax": hi})   # flush, never drop
            continue
        mid = (lo + hi) // 2
        stack.append((mid + 1, hi))
        stack.append((lo, mid))
    leaves.sort(key=lambda b: b["smin"])
    leaves.append({"smin": ceiling + 1, "smax": None})
    return leaves


def plan_location_slices(cur, *, top_n: int = 40) -> list[dict]:
    """Partition params from the register's OWN towns, split by poster type.

    Salary filters overlap and therefore cannot partition (proved live
    2026-07-28: a zero-pound-wide band still reports 12,176 results). A job
    has exactly one location and exactly one poster type, so every
    (town, direct|recruiter) pair opens its own depth window.

    Person-agnostic by construction: the towns come from this owner's sponsor
    register, so another owner's register yields another country's partition.
    Busiest sponsor towns first — that is where their jobs are.
    """
    # Case-folded: the register holds 'London' AND 'LONDON' as separate rows,
    # and walking one town twice would burn quota for zero new ads.
    cur.execute(
        "select initcap(lower(btrim(town_city))) as town_city, count(*) as n "
        "from sponsor_census "
        "where town_city is not null and btrim(town_city) <> '' "
        "group by initcap(lower(btrim(town_city))) "
        "order by count(*) desc limit %s", (top_n,))
    slices: list[dict] = []
    for row in cur.fetchall():
        town = (row["town_city"] or "").strip()
        if not town:
            continue
        slices.append({"loc": town, "emp": "direct"})
        slices.append({"loc": town, "emp": "recruiter"})
    return slices


def retire_slices(cur, source: str, *, param_key: str) -> int:
    """Close every unfinished cursor of a proven-futile partition kind.

    Walking a known-useless slice still costs its saturation probe (3 calls),
    so the 65 leftover salary sub-bands were retired rather than walked when
    the overlap finding landed (2026-07-28). Returns rows closed."""
    cur.execute(
        "update aggregator_cursor set pass_complete = true, updated_at = now() "
        "where source = %s and params ? %s and not pass_complete",
        (source, param_key))
    return cur.rowcount


def split_band(cur, source: str, band: dict, count_fn, *, target: int = 9_000,
               base_params: dict | None = None, max_bands: int = 64) -> list[dict]:
    """Re-split ONE oversized band inside its own range and persist the parts.

    Live defect 2026-07-28: the 256-band cap flushed £50,001–£100,000 as an
    as-is leaf holding 29,495 ads; it walled at Reed's 10k limit with ~19.5k
    unreachable behind it. Splitting only that range recovers them without
    re-planning (or re-walking) anything else. Contiguous by construction —
    no gap can open between the sub-bands.
    """
    lo, hi = band["smin"], band.get("smax")
    if hi is None:                       # the open top band cannot be split
        return [band]
    leaves: list[dict] = []
    stack: list[tuple[int, int]] = [(lo, hi)]
    while stack:
        a, b = stack.pop()
        if (len(leaves) + len(stack) >= max_bands or b - a < 1
                or count_fn(a, b) <= target):
            leaves.append({"smin": a, "smax": b})      # flush, never drop
            continue
        mid = (a + b) // 2
        stack.append((mid + 1, b))
        stack.append((a, mid))
    leaves.sort(key=lambda x: x["smin"])
    for leaf in leaves:
        sl = slice_for(source, **{**(base_params or {}),
                                  "smin": leaf["smin"], "smax": leaf["smax"]})
        save_cursor(cur, sl.slice_key, source, sl.params, next_page=1,
                    total_reported=None, ads_seen_inc=0, pass_complete=False)
    return leaves


def ensure_bands(cur, source: str, count_fn, *, target: int, ceiling: int,
                 base_params: dict | None = None) -> list[dict]:
    """The persisted band plan for any source: reuse stored cursors, else plan
    once and save.

    Every provider met so far hides a depth wall — Reed 500s at 10k, Adzuna
    silently clamps near 5k — so any big slice gets banded. `base_params`
    (e.g. Adzuna's category) rides along in every band's slice params. On
    first planning, one cursor row per band is created (next_page=1) and the
    source's legacy un-banded cursors are marked complete — they can never
    finish and must stop worrying the status view and the wrapper.
    """
    cur.execute(
        "select params from aggregator_cursor "
        "where source = %s and params ? 'smin' "
        "order by (params->>'smin')::int", (source,))
    rows = cur.fetchall()
    if rows:
        return [{"smin": r["params"]["smin"], "smax": r["params"].get("smax")}
                for r in rows]

    bands = plan_bands(count_fn, target=target, ceiling=ceiling)
    for band in bands:
        sl = slice_for(source, **{**(base_params or {}),
                                  "smin": band["smin"], "smax": band["smax"]})
        save_cursor(cur, sl.slice_key, source, sl.params, next_page=1,
                    total_reported=None, ads_seen_inc=0, pass_complete=False)
    cur.execute(
        "update aggregator_cursor set pass_complete = true, updated_at = now() "
        "where source = %s and not params ? 'smin'", (source,))
    return bands
