"""Tests for src/discover/agg_sweep — the quota-budgeted, resumable slice runner.

Pure orchestration tests: the store/match seams are monkeypatched at the
module's own namespace (the sweep-test pattern), and the client is a canned
page server. What's pinned: quota refusal, empty-page completion, cursor
resume, page-budget bounds, and the per-page commit that makes any stop safe.

Since task 5 the ledger debit lives in the HTTP client rather than in
run_slice, so the canned page server charges through the gate exactly where
the real one does — otherwise "every call is ledgered" would be a claim these
tests could no longer see either way.
"""
from __future__ import annotations

from datetime import date

from budget import gate
from budget.gate import charge_for
from discover.aggregators import ADZUNA_BASE, REED_BASE
from tests.test_criteria import RoutingCursor

TODAY = date(2026, 7, 22)
AD = {"source": "reed", "external_id": "1", "employer_name": "Sky", "title": "AI",
      "location": "London", "salary_min": None, "salary_max": None,
      "salary_text": None, "posted_at": None, "ad_url": "u", "snippet": ""}


class _State(dict):
    """The recorded seams; `quota_added` reads the meter, live."""

    def __init__(self, meter):
        super().__init__(saved=[], inserted=[])
        self._meter = meter

    def __getitem__(self, key):
        if key == "quota_added":
            return len(self._meter.charged)
        return super().__getitem__(key)


class FakeConn:
    def __init__(self):
        self.commits = 0
        self._cur = RoutingCursor([])

    def cursor(self):
        conn = self

        class _Ctx:
            def __enter__(self):
                return conn._cur

            def __exit__(self, *a):
                return False

        return _Ctx()

    def commit(self):
        self.commits += 1


class _CountingMeter:
    """Stands in for the ledgered meter and counts what the client charges."""

    def __init__(self):
        self.charged = []

    def charge(self, source):
        self.charged.append(source)


def _charging(served, base=REED_BASE):
    """Wrap a canned page server so it charges where the real client does."""
    call = served if callable(served) else (lambda p: served[p])

    def client(page):
        charge_for(f"{base}/search")
        return call(page)
    return client


def _wire(monkeypatch, mod, *, spent=0, cursor_row=None):
    meter = _CountingMeter()
    state = _State(meter)
    monkeypatch.setattr(gate, "current", lambda: meter)
    monkeypatch.setattr(mod, "load_cursor", lambda cur, key: cursor_row)
    monkeypatch.setattr(mod, "quota_spent", lambda cur, src, day: spent)
    monkeypatch.setattr(mod, "insert_ads",
                        lambda cur, ads: state["inserted"].append(len(ads)) or len(ads))
    monkeypatch.setattr(mod, "match_pending", lambda cur, limit=200: {})
    monkeypatch.setattr(mod, "save_cursor",
                        lambda cur, key, src, params, **kw: state["saved"].append(kw))
    return state


def test_run_slice_completes_on_the_first_empty_page(monkeypatch):
    import discover.agg_sweep as agg
    state = _wire(monkeypatch, agg)
    pages = {1: ([AD, AD], 5), 2: ([AD], 5), 3: ([], 5)}
    conn = FakeConn()

    outcome = agg.run_slice(conn, agg.slice_for("reed"), _charging(pages),
                            daily_cap=950, page_budget=10, today=TODAY)

    assert outcome == "pass_complete"
    assert state["inserted"] == [2, 1]
    assert state["quota_added"] == 3                  # every call is ledgered
    assert [s["next_page"] for s in state["saved"]] == [2, 3, 3]
    assert state["saved"][-1]["pass_complete"] is True
    assert conn.commits >= 3                          # per-page commit = safe stop


def test_run_slice_refuses_to_exceed_the_daily_quota(monkeypatch):
    import discover.agg_sweep as agg
    _wire(monkeypatch, agg, spent=950)

    def never_called(page):
        raise AssertionError("client must not be called past the quota")

    outcome = agg.run_slice(FakeConn(), agg.slice_for("reed"), _charging(never_called),
                            daily_cap=950, page_budget=10, today=TODAY)
    assert outcome == "quota_exhausted"


def test_run_slice_resumes_from_the_stored_cursor(monkeypatch):
    import discover.agg_sweep as agg
    _wire(monkeypatch, agg,
          cursor_row={"next_page": 7, "pass_complete": False, "ads_seen": 600})
    seen = []

    def client(page):
        seen.append(page)
        return ([], 5000)                             # immediately completes

    agg.run_slice(FakeConn(), agg.slice_for("reed"), client,
                  daily_cap=950, page_budget=10, today=TODAY)
    assert seen == [7]                                # zero loss, exact resume


def test_run_slice_short_circuits_a_completed_pass(monkeypatch):
    import discover.agg_sweep as agg
    _wire(monkeypatch, agg,
          cursor_row={"next_page": 9, "pass_complete": True, "ads_seen": 800})
    outcome = agg.run_slice(FakeConn(), agg.slice_for("reed"),
                            _charging(lambda p: (_ for _ in ()).throw(AssertionError)),
                            daily_cap=950, page_budget=10, today=TODAY)
    assert outcome == "pass_complete"


def test_run_slice_stops_at_its_page_budget(monkeypatch):
    import discover.agg_sweep as agg
    _wire(monkeypatch, agg)
    outcome = agg.run_slice(FakeConn(), agg.slice_for("reed"),
                            _charging(lambda p: ([AD], 100000)),
                            daily_cap=950, page_budget=2, today=TODAY)
    assert outcome == "page_budget_done"


def test_run_slice_treats_a_silent_source_failure_as_error_not_completion(monkeypatch):
    # _get_json returns None on outage -> ([], None). That must NEVER mark the
    # pass complete (a dead source is not an empty inventory).
    import discover.agg_sweep as agg
    state = _wire(monkeypatch, agg)
    outcome = agg.run_slice(FakeConn(), agg.slice_for("reed"),
                            _charging(lambda p: ([], None)),
                            daily_cap=950, page_budget=10, today=TODAY)
    assert outcome == "source_error"
    assert not any(s.get("pass_complete") for s in state["saved"])


def test_run_slice_declares_saturation_after_stale_pages(monkeypatch):
    # Adzuna's silent clamp (live 2026-07-25): pages keep returning ads but
    # none are NEW. K consecutive zero-new-yield pages => the slice is done —
    # a silent clamp or saturated band wastes a handful of calls, never a
    # quota-day.
    import discover.agg_sweep as agg
    state = _wire(monkeypatch, agg)
    monkeypatch.setattr(agg, "stored_count", lambda cur, src: 5253)  # frozen
    outcome = agg.run_slice(FakeConn(), agg.slice_for("adzuna"),
                            _charging(lambda p: ([AD] * 50, 44000), ADZUNA_BASE),
                            daily_cap=240, page_budget=20, today=TODAY,
                            stale_limit=3)
    assert outcome == "pass_complete"
    assert state["quota_added"] == 3                 # exactly K wasted, then done
    assert state["saved"][-1]["pass_complete"] is True


def test_run_slice_growing_yield_never_trips_the_saturation_guard(monkeypatch):
    import discover.agg_sweep as agg
    _wire(monkeypatch, agg)
    counts = iter(range(0, 5000, 50))                # +50 new rows every page
    monkeypatch.setattr(agg, "stored_count", lambda cur, src: next(counts))
    outcome = agg.run_slice(FakeConn(), agg.slice_for("reed"),
                            _charging(lambda p: ([AD] * 50, 100000)),
                            daily_cap=950, page_budget=4, today=TODAY,
                            stale_limit=3)
    assert outcome == "page_budget_done"             # budget ends it, not the guard


# ---- cross-source verdict: one capped source must not idle the others
# (defect found live 2026-07-27: Adzuna capped in 29 min and the wrapper slept
# 30 min while Reed still held 850 calls) ------------------------------------

def test_overall_verdict_continues_while_any_source_can_still_work():
    from discover.agg_sweep import overall_verdict
    # Adzuna capped, Reed still has budget and pending work -> keep going NOW
    assert overall_verdict({"adzuna": "quota_exhausted",
                            "reed": "page_budget_done"}) == "page_budget_done"
    # a dead source must not stall a healthy one either
    assert overall_verdict({"adzuna": "source_error",
                            "reed": "page_budget_done"}) == "page_budget_done"


def test_overall_verdict_naps_only_when_nothing_can_progress():
    from discover.agg_sweep import overall_verdict
    assert overall_verdict({"adzuna": "quota_exhausted",
                            "reed": "quota_exhausted"}) == "quota_exhausted"
    # a finished source doesn't keep the drip awake for the capped one
    assert overall_verdict({"adzuna": "quota_exhausted",
                            "reed": "pass_complete"}) == "quota_exhausted"


def test_overall_verdict_complete_and_error_cases():
    from discover.agg_sweep import overall_verdict
    assert overall_verdict({"a": "pass_complete",
                            "b": "pass_complete"}) == "pass_complete"
    assert overall_verdict({"a": "source_error",
                            "b": "pass_complete"}) == "source_error"
    assert overall_verdict({}) == "pass_complete"


# ---- the depth wall is permanent, not transient (live defect 2026-07-28:
# band £50,001-£100,000 held 29,495 ads, hit Reed's 10k wall at page 101 and
# was retried 638 times, burning ~317 calls of one quota-day) ---------------

def test_run_slice_calls_a_deep_failure_the_wall_not_a_transient_error(monkeypatch):
    import discover.agg_sweep as agg
    state = _wire(monkeypatch, agg,
                  cursor_row={"next_page": 101, "pass_complete": False,
                              "ads_seen": 10_000})
    outcome = agg.run_slice(FakeConn(), agg.slice_for("reed"),
                            _charging(lambda p: ([], None)),          # provider 500s
                            daily_cap=950, page_budget=10, today=TODAY,
                            wall_at=9_500)
    assert outcome == "depth_wall"
    # the band must be closed so the wrapper can never retry it forever
    assert state["saved"][-1]["pass_complete"] is True
    assert state["quota_added"] == 1                # one probe, then stop


def test_run_slice_still_calls_an_early_failure_transient(monkeypatch):
    import discover.agg_sweep as agg
    state = _wire(monkeypatch, agg)                 # fresh slice, nothing seen
    outcome = agg.run_slice(FakeConn(), agg.slice_for("reed"),
                            _charging(lambda p: ([], None)),
                            daily_cap=950, page_budget=10, today=TODAY,
                            wall_at=9_500)
    assert outcome == "source_error"                # a real outage, retry it
    assert not any(s.get("pass_complete") for s in state["saved"])


def test_overall_verdict_keeps_working_after_a_wall():
    from discover.agg_sweep import overall_verdict
    # a walled band is finished, not broken: other work proceeds immediately
    assert overall_verdict({"reed": "depth_wall"}) == "page_budget_done"
    assert overall_verdict({"reed": "depth_wall",
                            "adzuna": "quota_exhausted"}) == "page_budget_done"
