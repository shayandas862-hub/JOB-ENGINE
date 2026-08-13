"""The client-layer budget gate — offline (Phase 9 task 5).

The point of gating at the HTTP choke point rather than per tool: there are
exactly two functions in this codebase that reach the three metered APIs
(`discover.aggregators._get_json` and `discover.companies_house._get_json`),
so a cap placed there is inherited by every tool that exists now and every one
written later, without anybody remembering to ask.

The dangerous shape here is a gate that silently does nothing — an unmetered
default, a swallowed refusal, a runner that turns "budget spent" into "error".
Each of those is asserted against below, because each of them looks exactly
like success from the outside.
"""
from __future__ import annotations

import pytest

from budget import gate, ledger
from tests.conftest import FakeCursor


class RecordingMeter:
    """A meter that says yes and remembers; the seam every gate test needs."""

    def __init__(self, refuse_on=()):
        self.charged = []
        self.refuse_on = set(refuse_on)

    def charge(self, source):
        self.charged.append(source)
        if source in self.refuse_on:
            raise gate.BudgetExhausted(_spent_verdict(source))
        return None


def _spent_verdict(source="adzuna", owner="own-1"):
    return ledger.Verdict(source=source, owner_id=owner, world_spent=37,
                          world_cap=250, owner_spent=100, owner_cap=100,
                          refused_by="owner")


# ---- which URLs are metered at all -----------------------------------------

def test_every_metered_api_base_is_recognised_from_its_url():
    from discover.aggregators import ADZUNA_BASE, REED_BASE
    from discover.companies_house import CH_BASE
    assert gate.source_for_url(f"{ADZUNA_BASE}/gb/search/1") == "adzuna"
    assert gate.source_for_url(f"{REED_BASE}/search") == "reed"
    assert gate.source_for_url(f"{REED_BASE}/jobs/1234") == "reed"
    assert gate.source_for_url(f"{CH_BASE}/company/0001") == "companies_house"


def test_an_unmetered_host_passes_through_uncharged():
    # Board feeds (Greenhouse, Lever, Ashby, Workable, Workday) cost nothing
    # and must not consume an aggregator budget.
    assert gate.source_for_url("https://boards.greenhouse.io/acme") is None
    meter = RecordingMeter()
    with gate.installed(meter):
        gate.charge_for("https://boards.greenhouse.io/acme")
    assert meter.charged == []


def test_every_ledger_source_is_reachable_from_some_url():
    # A source with a cap row but no URL that maps to it would be a budget
    # nobody can ever spend — a cap that silently guards nothing.
    from discover.aggregators import ADZUNA_BASE, REED_BASE
    from discover.companies_house import CH_BASE
    mapped = {gate.source_for_url(u) for u in
              (ADZUNA_BASE, REED_BASE, CH_BASE)}
    assert mapped == set(ledger.SOURCES)


# ---- the default is metered, which is the whole safety property ------------

def test_the_default_meter_is_the_ledger_and_not_a_pass_through():
    # If the ambient default were "no metering", every runner would have to
    # REMEMBER to open a budget, and the one that forgot would spend the
    # shared quota silently. So: with nothing installed, a charge must reach
    # a real ledgered meter. Proven by making the connection attempt itself
    # observable rather than by trusting the code path.
    opened = []

    def explode():
        opened.append(True)
        raise RuntimeError("no database here")

    with gate.no_meter_installed():
        gate.set_connect(explode)
        try:
            with pytest.raises(RuntimeError, match="no database here"):
                gate.charge_for("https://api.adzuna.com/v1/api/jobs/gb/search/1")
        finally:
            gate.set_connect(None)
    assert opened == [True], "a charge with no meter installed did not meter"


def test_unmetered_is_explicit_and_scoped_to_its_block():
    meter = RecordingMeter()
    with gate.unmetered():
        gate.charge_for("https://api.adzuna.com/v1/api/jobs/gb/search/1")
    with gate.installed(meter):
        gate.charge_for("https://api.adzuna.com/v1/api/jobs/gb/search/1")
    assert meter.charged == ["adzuna"]


# ---- the refusal carries its receipts ---------------------------------------

def test_a_refusal_names_the_reset_and_carries_both_scopes_numbers():
    verdict = _spent_verdict()
    assert verdict.allowed is False
    err = gate.BudgetExhausted(verdict)
    assert "resets at midnight UTC" in str(err)
    assert "budget spent" in str(err)
    receipts = err.receipts
    assert receipts["source"] == "adzuna"
    assert receipts["refused_by"] == "owner"
    assert receipts["owner"] == {"spent": 100, "cap": 100, "remaining": 0}
    assert receipts["world"] == {"spent": 37, "cap": 250,
                                 "remaining": 213}
    assert receipts["resets"] == "midnight UTC"


def test_an_allowed_verdict_still_reports_what_is_left():
    ok = ledger.Verdict(source="reed", owner_id="own-1", world_spent=800,
                        world_cap=950, owner_spent=10, owner_cap=300,
                        refused_by=None)
    assert ok.allowed is True
    assert ok.receipts["world"]["remaining"] == 150
    assert ok.receipts["owner"]["remaining"] == 290


def test_a_world_only_run_reports_no_owner_scope_at_all():
    # The founder's nightly world half: there is no owner to charge, and the
    # receipts must not invent one.
    ok = ledger.Verdict(source="reed", owner_id=None, world_spent=1,
                        world_cap=950, owner_spent=None, owner_cap=None,
                        refused_by=None)
    assert ok.receipts["owner"] is None


# ---- the two choke points actually consult the gate -------------------------

def test_the_aggregator_client_charges_before_it_calls_out():
    import responses

    from discover.aggregators import search_adzuna
    meter = RecordingMeter()
    with responses.RequestsMock() as mock:
        mock.add(responses.GET,
                 "https://api.adzuna.com/v1/api/jobs/gb/search/1",
                 json={"results": []}, status=200)
        with gate.installed(meter):
            search_adzuna("id", "key", what="nurse")
    assert meter.charged == ["adzuna"]


def test_a_refused_aggregator_call_never_reaches_the_network():
    # The refusal has to happen BEFORE the request, or the cap is a counter
    # rather than a cap.
    import responses

    from discover.aggregators import search_reed
    meter = RecordingMeter(refuse_on={"reed"})
    with responses.RequestsMock(assert_all_requests_are_fired=False):
        with gate.installed(meter):
            with pytest.raises(gate.BudgetExhausted):
                search_reed("key", keywords="carer")


def test_the_registry_client_charges_before_it_calls_out(monkeypatch):
    import responses

    from discover import companies_house
    monkeypatch.setattr(companies_house, "_sleep", lambda _s: None)
    meter = RecordingMeter()
    with responses.RequestsMock() as mock:
        mock.add(responses.GET,
                 f"{companies_house.CH_BASE}/company/00000001",
                 json={"company_number": "00000001"}, status=200)
        with gate.installed(meter):
            companies_house.get_profile("00000001", "key", None)
    assert meter.charged == ["companies_house"]


def test_every_retry_attempt_is_charged_because_every_attempt_is_a_call():
    # The provider counts a 503 against the quota exactly as it counts a 200,
    # so ledgering once per logical call would under-report a retried one.
    import responses

    from discover import aggregators
    meter = RecordingMeter()
    with responses.RequestsMock() as mock:
        for _ in range(aggregators.MAX_TRIES):
            mock.add(responses.GET,
                     "https://api.adzuna.com/v1/api/jobs/gb/search/1",
                     json={}, status=503)
        with gate.installed(meter):
            aggregators.search_adzuna("id", "key", what="nurse")
    assert meter.charged == ["adzuna"] * aggregators.MAX_TRIES


# ---- no runner may turn "budget spent" into "error" or "all clear" ----------

def test_the_drip_stops_on_a_refusal_instead_of_calling_it_a_bad_item():
    # fetch.jd_drip catches Exception per item so one bad JD never fails the
    # stage. A budget refusal caught by that same clause would look like 200
    # broken jobs and would keep trying — noise where there should be a stop.
    from fetch.jd_drip import run_drip

    class Settings:
        reed_ready = True
        reed_api_key = "key"

    rows = [{"role_id": f"r{i}", "external_id": str(i)} for i in range(5)]
    calls = []

    def fetcher(_key, external_id, _session):
        calls.append(external_id)
        raise gate.BudgetExhausted(_spent_verdict("reed"))

    cur = FakeCursor()
    report = run_drip(cur, Settings(), cap=5, fetcher=fetcher,
                      picker=lambda _c, _n: rows, session=object())
    assert report["outcome"] == "quota_exhausted"
    assert calls == ["0"], "the drip kept spending after the budget refused it"
    assert report["fetched"] == 0
    assert report.get("errors") == 0, "a refusal was counted as a broken job"


def test_the_registry_batch_stops_instead_of_stamping_every_org_an_error():
    # discover.classify.run_classify has the same per-item `except Exception`.
    # Swallowing a refusal there would write a fake 'error' card for every
    # remaining organisation — 2,000 wrong rows from one exhausted budget.
    from discover import classify

    class Settings:
        ch_ready = True
        companies_house_api_key = "key"

    orgs = [{"org_name_norm": f"o{i}", "organisation_name": f"Org {i}"}
            for i in range(5)]
    stamped = []

    def boom(*_a, **_k):
        raise gate.BudgetExhausted(_spent_verdict("companies_house"))

    cur = FakeCursor()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(classify, "pick_classify_batch", lambda _c, _n: orgs)
        mp.setattr(classify, "ensure_census_card", lambda _c, _o: None)
        mp.setattr(classify.registry, "enrich_org", boom)
        mp.setattr(classify, "record_registry_result",
                   lambda _c, name, outcome, **_k: stamped.append((name, outcome)))
        report = classify.run_classify(cur, Settings(), batch=5,
                                       session=object())
    assert report.budget_stopped is True
    assert report.errors == 0, "a budget refusal was recorded as an org error"
    assert stamped == [], "a budget refusal stamped a census card"


def test_the_ad_sweep_reports_a_refusal_as_the_quota_outcome_it_already_has():
    # run_slice already speaks 'quota_exhausted'; a client-layer refusal must
    # land on that same word rather than on 'source_error', which the wrapper
    # retries.
    from discover.agg_sweep import run_slice, slice_for

    class Conn:
        def __init__(self): self.commits = 0

        def cursor(self):
            import contextlib
            return contextlib.nullcontext(FakeCursor())

        def commit(self): self.commits += 1

    def client(_page):
        raise gate.BudgetExhausted(_spent_verdict("reed"))

    outcome = run_slice(Conn(), slice_for("reed", keywords=None), client,
                        daily_cap=950, page_budget=5)
    assert outcome == "quota_exhausted"


def test_the_census_sweep_stops_instead_of_carding_every_org_an_error():
    # The fourth runner with a per-item `except Exception`, and the one most
    # likely to meet an exhausted budget: the knock-on-demand sweep is started
    # BY an owner, on their lens, and enriches each organisation against the
    # registry. Swallowed, one spent budget would stamp an 'error' probe card
    # on every remaining organisation in the batch.
    from discover import sweep

    class Settings:
        ch_ready = True
        companies_house_api_key = "key"

    orgs = [{"org_name_norm": f"o{i}", "organisation_name": f"Org {i}"}
            for i in range(5)]
    carded = []

    def boom(*_a, **_k):
        raise gate.BudgetExhausted(_spent_verdict("companies_house"))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sweep, "pick_batch", lambda _c, _n, retry_errors=False: orgs)
        mp.setattr(sweep, "default_profile_id", lambda _c: "own-1")
        mp.setattr(sweep, "load_criteria", lambda _c, _o: type("C", (), {"role_patterns": []})())
        mp.setattr(sweep, "build_role_matcher", lambda _p: None)
        mp.setattr(sweep, "load_tracked_orgs", lambda _c, _o: {})
        mp.setattr(sweep, "probe_org", lambda *a: ("no_board", 0, 0))
        mp.setattr(sweep.registry, "enrich_org", boom)
        mp.setattr(sweep, "upsert_probe",
                   lambda _c, org, **kw: carded.append((org["org_name_norm"],
                                                        kw.get("outcome"))))
        report = sweep.run_sweep(FakeCursor(), Settings(), batch=5, pause=0,
                                 session=object())

    assert report.budget_stopped is True
    assert report.errors == 0, "a budget refusal was carded as an org error"
    assert [c for c in carded if c[1] == "error"] == []
