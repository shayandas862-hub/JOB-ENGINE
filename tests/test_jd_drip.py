"""src/fetch/jd_drip.py — the Reed JD drip (Phase 8.5 / U5).

Ad-merged listings carry only a snippet; care/hospitality/retail live almost
entirely on ads, so the drip is the primary description supply for most
non-software users. Budget honesty is the core contract: the drip shares
Reed's ledgered ~950/day with the broad sweep and never overspends it.
Offline: routes serve rows, the fetcher is injected.
"""
from __future__ import annotations

from tests.test_criteria import RoutingCursor

CANDIDATE = {"role_id": 917, "external_id": "55512345", "in_queue": True}


def _cursor(candidates=None, spent=0):
    return RoutingCursor([
        ("from api_quota_ledger", [{"calls": spent}]),
        ("from role_listings", candidates if candidates is not None
         else [CANDIDATE]),
    ])


class _Settings:
    reed_ready = True
    reed_api_key = "k"


def test_pick_drip_batch_targets_reed_ad_only_open_listings_queue_first():
    from fetch.jd_drip import pick_drip_batch
    cur = RoutingCursor([("from role_listings", [CANDIDATE])])
    out = pick_drip_batch(cur, 50)
    assert out == [CANDIDATE]
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "merged_role_id" in low                 # the ad linkage is the truth
    assert "a.source = 'reed'" in low              # only reed has a details api
    assert "role_status = 'open'" in low
    assert "jd_full" in low                        # only rows still missing one
    assert "v_apply_queue" in low                  # queue rows are highest value
    order = low.rsplit("order by", 1)[1]
    assert "desc" in order
    assert params["n"] == 50


def test_run_drip_fetches_writes_and_ledgers_each_call():
    from fetch.jd_drip import run_drip
    cur = _cursor()
    fetched = []

    def fake_fetch(api_key, external_id, session):
        fetched.append(external_id)
        return "Full description of the care assistant role."
    report = run_drip(cur, _Settings(), fetcher=fake_fetch, session=object(),
                      commit=None)
    assert fetched == ["55512345"]
    assert report["fetched"] == 1 and report["errors"] == 0
    executed = " ".join(s for s, _ in cur.executed).lower()
    assert "update role_listings" in executed
    assert "insert into api_quota_ledger" in executed or "quota" in executed
    update = [(s, p) for s, p in cur.executed
              if "update role_listings" in s.lower()][0]
    assert "Full description of the care assistant role." in update[1]


def test_run_drip_never_overspends_the_shared_reed_budget():
    from fetch.jd_drip import run_drip
    # 900 of the 950 already spent by the sweep -> at most 50 calls today,
    # whatever the drip's own cap says.
    cur = _cursor(spent=900)
    seen = {}

    def picker_spy(c, n):
        seen["n"] = n
        return []
    report = run_drip(cur, _Settings(), fetcher=lambda *a: None,
                      picker=picker_spy, commit=None)
    assert seen["n"] == 50
    assert report["fetched"] == 0

    exhausted = run_drip(_cursor(spent=950), _Settings(),
                         fetcher=lambda *a: None, commit=None)
    assert exhausted["outcome"] == "quota_exhausted"


def test_run_drip_own_cap_bounds_a_fresh_day():
    from fetch.jd_drip import run_drip
    seen = {}

    def picker_spy(c, n):
        seen["n"] = n
        return []
    run_drip(_cursor(spent=0), _Settings(), fetcher=lambda *a: None,
             picker=picker_spy, cap=200, commit=None)
    assert seen["n"] == 200


def test_run_drip_isolates_a_bad_fetch_and_keeps_going():
    from fetch.jd_drip import run_drip
    rows = [dict(CANDIDATE, role_id=1, external_id="a"),
            dict(CANDIDATE, role_id=2, external_id="b")]
    cur = _cursor(candidates=rows)

    def flaky(api_key, external_id, session):
        if external_id == "a":
            raise RuntimeError("reed hiccup")
        return "jd text"
    commits = []
    report = run_drip(cur, _Settings(), fetcher=flaky,
                      commit=lambda: commits.append(1))
    assert report["errors"] == 1 and report["fetched"] == 1
    assert len(commits) == 2                       # per-item commit = resume


def test_run_drip_without_a_key_degrades_cleanly():
    from fetch.jd_drip import run_drip

    class NoKey:
        reed_ready = False
        reed_api_key = None
    report = run_drip(RoutingCursor([]), NoKey(), commit=None)
    assert report["outcome"] == "no_key" and report["fetched"] == 0


def test_clean_html_strips_tags_and_entities():
    from fetch.jd_drip import clean_html
    got = clean_html("<p>Care &amp; support<br>worker</p> <b>needed</b>")
    assert got == "Care & support worker needed"
