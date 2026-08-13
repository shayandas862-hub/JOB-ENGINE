"""scripts/agg_sweep.py — the aggregator runner's thin shell.

Loaded via importlib (scripts/ is not a package). Pins the two things the
2026-07-27 defect hunt exposed: the status view must read the ledger for the
SAME day the runner writes (local date, not the database's UTC current_date),
and the dead URL-following harvest must be gone from the runner.
"""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

from tests.test_criteria import RoutingCursor

ROOT = Path(__file__).resolve().parents[1]

# One canned row per query the status view runs (routed by substring).
STATUS_ROUTES = [
    ("group by source order by source",
     [{"source": "reed", "seen": 100, "done": 1, "slices": 2}]),
    ("order by slice_key",
     [{"slice_key": "reed|", "next_page": 2, "ads_seen": 100,
       "total_reported": 900, "pass_complete": False}]),
    ("api_quota_ledger", [{"source": "reed", "calls": 7}]),
    ("from aggregator_ads", [{"n": 100, "uk": 99, "matched": 9, "orgs": 4}]),
]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "agg_sweep_script", ROOT / "scripts" / "agg_sweep.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_status_reads_the_quota_ledger_for_the_runners_own_day():
    # Live defect 2026-07-27: the display used Postgres current_date (UTC)
    # while run_slice ledgers on the local date — between midnight and 01:00
    # BST the status showed the PREVIOUS day's calls after a fresh start.
    mod = load_script()
    cur = RoutingCursor(STATUS_ROUTES)
    mod._print_status(cur, today=date(2026, 7, 27))
    quota_calls = [(s, p) for s, p in cur.executed
                   if "api_quota_ledger" in s.lower()]
    assert quota_calls, "status must report the quota ledger"
    sql, params = quota_calls[0]
    assert "current_date" not in sql.lower()          # no timezone mismatch
    assert params == (date(2026, 7, 27),)


def test_runner_no_longer_follows_dead_ad_links():
    # Diagnosed live 2026-07-27: Adzuna's /jobs/details and /jobs/land/ad URLs
    # resolve to themselves and Reed's stay on reed.co.uk, so parse_ats_url
    # could never match — 3,458 links followed, 0 hints planted. The learning
    # loop is now hiring-first probing (scripts/sweep.py --hiring).
    source = (ROOT / "scripts" / "agg_sweep.py").read_text()
    assert "harvest_tokens" not in source
    assert "token_harvest" not in source


# ---- U1: the Adzuna category is the OWNER'S, not a baked default ------------

def _rule_cursor(category):
    rule = {"industry_codes": ["87300"], "min_local_jobs": 1, "auto": True,
            "adzuna_category": category}
    return RoutingCursor([
        ("from profiles", [{"profile_id": "owner-1"}]),
        ("from promotion_rules", [rule]),
    ])


def test_adzuna_category_resolves_from_the_owners_rule():
    # No CLI value -> the owner's lens row decides. A care worker's rule
    # carrying social-work-jobs sweeps social-work ads, no code edit.
    mod = load_script()
    assert mod._adzuna_category(None, _rule_cursor("social-work-jobs")) \
        == "social-work-jobs"


def test_explicit_cli_category_beats_the_rule():
    mod = load_script()
    cur = _rule_cursor("social-work-jobs")
    assert mod._adzuna_category("it-jobs", cur) == "it-jobs"
    # the rule was never even consulted — CLI is an explicit override
    assert cur.executed == []


def test_category_falls_back_to_it_jobs_without_a_rule():
    # Bootstrap: a rule-less database behaves exactly as before U1.
    mod = load_script()
    cur = RoutingCursor([
        ("from profiles", [{"profile_id": "owner-1"}]),
        ("from promotion_rules", []),
    ])
    assert mod._adzuna_category(None, cur) == "it-jobs"


def test_category_all_means_the_whole_inventory():
    # 'all' (CLI or rule) -> None -> the slice carries no category narrowing;
    # Adzuna walks the whole country inventory like Reed already does.
    mod = load_script()
    assert mod._adzuna_category("all", _rule_cursor(None)) is None
    assert mod._adzuna_category(None, _rule_cursor("all")) is None
