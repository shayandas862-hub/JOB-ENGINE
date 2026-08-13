"""Tests for src/discover/agg_partition — beating Reed's 10,000-result wall.

Reed 500s at resultsToSkip=10,000 (confirmed live 2026-07-22), so the full
inventory is walked as adaptive SALARY BANDS, each under a target count. The
plan is persisted as cursor rows so it is computed once, resumed forever, and
the legacy single-slice cursor is retired (it can never finish).
"""
from __future__ import annotations

from tests.conftest import FakeCursor
from tests.test_criteria import RoutingCursor

CEILING = 200_000
DENSITY = 93_000 / (CEILING + 1)          # uniform fake inventory


def _fake_count(lo, hi):
    if hi is None:                         # open top band
        return 500
    return int((hi - lo + 1) * DENSITY)


def test_plan_bands_splits_until_every_band_fits_under_target():
    from discover.agg_partition import plan_bands
    calls = []

    def counting(lo, hi):
        calls.append((lo, hi))
        return _fake_count(lo, hi)

    bands = plan_bands(counting, target=9_000, ceiling=CEILING)

    closed = [b for b in bands if b["smax"] is not None]
    assert all(_fake_count(b["smin"], b["smax"]) <= 9_000 for b in closed)
    # contiguous integer cover of [0, ceiling], sorted, then one open band
    assert closed[0]["smin"] == 0 and closed[-1]["smax"] == CEILING
    for a, b in zip(closed, closed[1:]):
        assert b["smin"] == a["smax"] + 1
    assert bands[-1] == {"smin": CEILING + 1, "smax": None}
    assert len(closed) >= 10                      # 93k/9k forces real splitting
    assert len(calls) < 60                        # planning stays cheap


def test_ensure_bands_plans_once_and_persists_then_reuses():
    from discover.agg_partition import ensure_bands
    # first run: nothing stored -> plans, saves one cursor per band, retires legacy
    cur = RoutingCursor([("params ? 'smin'", [])])
    bands = ensure_bands(cur, "reed", _fake_count, target=9_000, ceiling=CEILING)
    assert len(bands) >= 11
    inserts = [s for s, _ in cur.executed if s.startswith("insert into aggregator_cursor")]
    assert len(inserts) == len(bands)
    retire = [(s, p) for s, p in cur.executed
              if s.startswith("update aggregator_cursor")]
    assert len(retire) == 1 and retire[0][1] == ("reed",)
    assert "pass_complete = true" in retire[0][0]
    assert "not params ? 'smin'" in retire[0][0]     # retires ONLY legacy cursors

    # second run: rows exist -> reuse them, zero planning calls, zero writes
    stored = [{"params": {"smin": b["smin"], "smax": b["smax"]}} for b in bands]
    cur2 = RoutingCursor([("params ? 'smin'", stored)])

    def explode(lo, hi):
        raise AssertionError("must not re-plan when bands are persisted")

    again = ensure_bands(cur2, "reed", explode, target=9_000, ceiling=CEILING)
    assert again == bands
    assert not any(s.startswith("insert") for s, _ in cur2.executed)


def test_combine_outcomes_precedence():
    from discover.agg_sweep import combine_outcomes
    assert combine_outcomes(["pass_complete", "pass_complete"]) == "pass_complete"
    assert combine_outcomes(["pass_complete", "page_budget_done"]) == "page_budget_done"
    assert combine_outcomes(["page_budget_done", "source_error"]) == "source_error"
    assert combine_outcomes(["source_error", "quota_exhausted"]) == "quota_exhausted"
    assert combine_outcomes([]) == "pass_complete"


def test_page_reed_carries_salary_band_params():
    import responses

    from tests.test_aggregators import REED_SEARCH, REED_URL

    @responses.activate
    def run():
        responses.add(responses.GET, REED_URL, json=REED_SEARCH, status=200)
        from discover.aggregators import page_reed
        page_reed("k", page=1, minimum_salary=25_001, maximum_salary=32_000)
        url = responses.calls[0].request.url
        assert "minimumSalary=25001" in url and "maximumSalary=32000" in url

    run()


def test_plan_bands_never_drops_ranges_when_the_leaf_cap_bites():
    # Live 2026-07-22: heavy sub-£25k clustering ate all 64 leaves and the
    # £25k-£200k professional range was silently DROPPED. Pinned: when the cap
    # bites, the remaining stack is flushed as (possibly oversized) leaves —
    # coverage stays total, contiguous to the ceiling, no matter the density.
    from discover.agg_partition import plan_bands

    def clustered(lo, hi):                    # almost everything under 25k
        if hi is None:
            return 400
        dense = max(0, min(hi, 25_000) - lo + 1) * 8
        sparse = max(0, hi - max(lo, 25_001) + 1) // 50
        return dense + sparse

    bands = plan_bands(clustered, target=9_000, ceiling=200_000, max_bands=16)
    closed = [b for b in bands if b["smax"] is not None]
    assert closed[0]["smin"] == 0 and closed[-1]["smax"] == 200_000   # no hole
    for a, b in zip(closed, closed[1:]):
        assert b["smin"] == a["smax"] + 1
    assert bands[-1]["smax"] is None
    assert len(bands) <= 16 + 1 + 2           # cap respected (flush may add a couple)


def test_ensure_bands_carries_base_params_for_adzuna_category_bands():
    # Adzuna clamps silently at ~5k accessible results (live 2026-07-25), so
    # its category browse gets the same band medicine — each band slice must
    # keep the category in its params alongside smin/smax.
    from discover.agg_partition import ensure_bands
    cur = RoutingCursor([("params ? 'smin'", [])])
    bands = ensure_bands(cur, "adzuna", _fake_count, target=4_500,
                         ceiling=CEILING, base_params={"category": "it-jobs"})
    assert len(bands) >= 2
    inserts = [(s, p) for s, p in cur.executed
               if s.startswith("insert into aggregator_cursor")]
    assert len(inserts) == len(bands)
    key, params_json = inserts[0][1][0], inserts[0][1][2]
    assert key.startswith("adzuna|category=it-jobs|")
    assert '"category": "it-jobs"' in params_json and '"smin"' in params_json


def test_split_band_replans_an_oversized_band_inside_its_own_range():
    """A band that hit the provider's wall is re-split so its unreachable
    remainder becomes reachable (live 2026-07-28: £50,001-£100,000 = 29,495
    ads behind a 10k wall)."""
    from discover.agg_partition import split_band
    from tests.conftest import FakeCursor
    cur = FakeCursor()
    counts = {}

    def count_fn(lo, hi):
        counts[(lo, hi)] = counts.get((lo, hi), 0) + 1
        return 30_000 if (hi - lo) > 25_000 else 5_000

    bands = split_band(cur, "reed", {"smin": 50_001, "smax": 100_000},
                       count_fn, target=9_000)
    assert len(bands) > 1                            # actually split
    assert bands[0]["smin"] == 50_001                # covers the whole range,
    assert bands[-1]["smax"] == 100_000              # start to end, no gaps
    for a, b in zip(bands, bands[1:]):
        assert b["smin"] == a["smax"] + 1            # contiguous
    saved = [s for s, _ in cur.executed if "aggregator_cursor" in s.lower()]
    assert len(saved) >= len(bands)                  # one cursor per sub-band


# ---- location x employer-type partitioning (2026-07-28) --------------------

def test_plan_location_slices_uses_the_registers_own_towns_split_by_employer():
    """Person-agnostic: the partition comes from the owner's register data,
    not a hardcoded city list."""
    from discover.agg_partition import plan_location_slices
    from tests.test_criteria import RoutingCursor
    cur = RoutingCursor([("town_city", [{"town_city": "London", "n": 900},
                                        {"town_city": "Manchester", "n": 120}])])
    slices = plan_location_slices(cur, top_n=2)
    assert slices == [{"loc": "London", "emp": "direct"},
                      {"loc": "London", "emp": "recruiter"},
                      {"loc": "Manchester", "emp": "direct"},
                      {"loc": "Manchester", "emp": "recruiter"}]
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "town_city" in low and "sponsor_census" in low
    assert "count(*) desc" in low.split("order by", 1)[1]   # busiest towns first
    assert params == (2,)


def test_plan_location_slices_skips_blank_towns():
    from discover.agg_partition import plan_location_slices
    from tests.test_criteria import RoutingCursor
    cur = RoutingCursor([("town_city", [{"town_city": None, "n": 5},
                                        {"town_city": "  ", "n": 4},
                                        {"town_city": "Leeds", "n": 3}])])
    assert plan_location_slices(cur, top_n=9) == [
        {"loc": "Leeds", "emp": "direct"}, {"loc": "Leeds", "emp": "recruiter"}]


def test_retire_slices_closes_futile_cursors_without_walking_them():
    """The 65 salary sub-bands are known-futile (overlap filter): closing them
    saves ~195 calls that would learn nothing."""
    from discover.agg_partition import retire_slices
    from tests.conftest import FakeCursor
    cur = FakeCursor(rowcount=65)
    n = retire_slices(cur, "reed", param_key="smin")
    assert n == 65
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "update aggregator_cursor" in low
    assert "pass_complete = true" in low
    assert "params ? %s" in low and "not pass_complete" in low
    assert params == ("reed", "smin")


def test_plan_location_slices_folds_town_case_so_no_town_is_walked_twice():
    """The register holds 'London' AND 'LONDON' (33,021 + 2,915 rows live);
    walking both would spend quota re-fetching the same city."""
    from discover.agg_partition import plan_location_slices
    from tests.test_criteria import RoutingCursor
    cur = RoutingCursor([("town_city", [{"town_city": "London", "n": 33021}])])
    plan_location_slices(cur, top_n=40)
    sql, _ = cur.executed[0]
    low = " ".join(sql.split()).lower()
    assert "lower(btrim(town_city))" in low          # folded before grouping
    assert low.count("group by initcap(lower(btrim(town_city)))") == 1
