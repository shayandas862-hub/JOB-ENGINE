"""Pass 1 — the Companies House classification sweep over the whole register.

Offline: RoutingCursor records SQL; companies_house.enrich_org is monkeypatched
so no HTTP happens. Pins: it picks only un-classified sponsors (software-named
first), ensures a card exists before writing the industry code, isolates
per-company errors, commits per company, and never job-probes.
"""
from __future__ import annotations

from tests.test_sweep import RoutingCursor  # the executemany-capturing subclass

ORG = {"org_name_norm": "acme ai ltd", "sponsor_id": 42,
       "organisation_name": "Acme AI Ltd", "town_city": "London",
       "is_skilled_worker": True, "rating": "A"}
ORG2 = {"org_name_norm": "beta data ltd", "sponsor_id": 43,
        "organisation_name": "Beta Data Ltd", "town_city": "Leeds",
        "is_skilled_worker": True, "rating": "A"}


def _settings(ready=True):
    from config import Settings
    return Settings(database_url="x", gemini_api_key="",
                    companies_house_api_key="CHKEY" if ready else "")


# ---- SOFTWARE_SIC ----------------------------------------------------------

def test_software_sic_covers_the_core_codes():
    from discover.classify import SOFTWARE_SIC
    for code in ("62012", "62020", "63110"):
        assert code in SOFTWARE_SIC


# ---- pick_classify_batch ---------------------------------------------------

def test_pick_classify_batch_skips_already_classified_software_first():
    from discover.classify import pick_classify_batch
    cur = RoutingCursor([("from licensed_sponsors", [ORG])])
    out = pick_classify_batch(cur, 5000)
    assert out == [ORG]
    sql, params = cur.executed[0]
    # only sponsors with no industry code yet — anti-join on registry_checked_at
    assert "registry_checked_at is not null" in sql
    assert "not exists (select 1 from sponsor_census" in sql
    # software-named first
    order = sql.rsplit("order by", 1)[1]
    assert order.strip().startswith("(ls.org_name_norm ~ %(tech)s) desc")
    assert params["n"] == 5000


# ---- run_classify ----------------------------------------------------------

def _patch(monkeypatch, outcomes):
    """enrich_org returns queued outcomes; ensure_census_card recorded."""
    from discover import classify
    calls = {"enrich": [], "cards": []}
    it = iter(outcomes)

    def fake_enrich(cur, norm, name, key, session=None):
        calls["enrich"].append(norm)
        return next(it)

    monkeypatch.setattr(classify.registry, "enrich_org", fake_enrich)
    monkeypatch.setattr(classify, "ensure_census_card",
                        lambda cur, org: calls["cards"].append(org["org_name_norm"]))
    return calls


def test_run_classify_ensures_card_then_classifies_each(monkeypatch):
    from discover import classify
    calls = _patch(monkeypatch, ["matched", "not_found"])
    cur = RoutingCursor([("from licensed_sponsors", [ORG, ORG2])])
    rep = classify.run_classify(cur, _settings(), batch=5000)
    assert calls["cards"] == ["acme ai ltd", "beta data ltd"]     # card first
    assert calls["enrich"] == ["acme ai ltd", "beta data ltd"]
    assert rep.picked == 2 and rep.matched == 1 and rep.not_found == 1


def test_run_classify_isolates_errors_and_records_them(monkeypatch):
    from discover import classify
    recorded = []

    def boom(cur, norm, name, key, session=None):
        if "acme" in norm:
            raise RuntimeError("CH exploded")
        return "matched"

    monkeypatch.setattr(classify.registry, "enrich_org", boom)
    monkeypatch.setattr(classify, "ensure_census_card", lambda cur, org: None)
    monkeypatch.setattr(classify, "record_registry_result",
                        lambda cur, norm, outcome, **k: recorded.append((norm, outcome, k)))
    cur = RoutingCursor([("from licensed_sponsors", [ORG, ORG2])])
    rep = classify.run_classify(cur, _settings(), batch=5000)
    assert rep.errors == 1 and rep.matched == 1 and rep.picked == 2
    assert recorded and recorded[0][1] == "error" and "CH exploded" in str(recorded[0])


def test_run_classify_commits_per_company_and_reports(monkeypatch):
    from discover import classify
    _patch(monkeypatch, ["matched", "ambiguous", "matched"])
    org3 = dict(ORG2, org_name_norm="gamma ltd", organisation_name="Gamma Ltd")
    commits = []
    cur = RoutingCursor([("from licensed_sponsors", [ORG, ORG2, org3])])
    rep = classify.run_classify(cur, _settings(), batch=5000,
                                commit=lambda: commits.append(1))
    assert len(commits) == 3
    assert rep.matched == 2 and rep.ambiguous == 1


def test_run_classify_requires_the_key(monkeypatch):
    from discover import classify
    cur = RoutingCursor([])
    try:
        classify.run_classify(cur, _settings(ready=False), batch=10)
        assert False, "should have refused without the key"
    except RuntimeError as e:
        assert "COMPANIES_HOUSE" in str(e)


def test_run_classify_never_probes_or_touches_daily_tables(monkeypatch):
    from discover import classify
    _patch(monkeypatch, ["matched"])
    cur = RoutingCursor([("from licensed_sponsors", [ORG])])
    classify.run_classify(cur, _settings(), batch=5000)
    for sql, _ in cur.executed:
        assert "target_companies" not in sql
        assert "review_items" not in sql
        # classification does no ATS probing — no census_jobs writes
        assert "census_jobs" not in sql
