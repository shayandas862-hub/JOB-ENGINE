"""Tests for src/discover/daily — the discovery stage the scheduler runs.

Offline: every network-touching call (register walk, onboarding, aggregator
search, cross-check, probe) is monkeypatched. We prove per-source caps, the
per-source report lines, source-skipping when keys are absent, and that one
failing source never sinks the whole discovery stage.
"""
from __future__ import annotations


def _criteria(patterns, floor=40000):
    from criteria.loader import Criteria
    return Criteria(profile_id="p-1", name="T", salary_floor=floor,
                    threshold_standard=None, threshold_new_entrant=None,
                    kill_keywords=[], role_patterns=patterns)


def _settings(adzuna=True, reed=True):
    from config import Settings
    return Settings(database_url="x", gemini_api_key="",
                    adzuna_app_id="ID" if adzuna else "",
                    adzuna_app_key="KEY" if adzuna else "",
                    reed_api_key="RK" if reed else "")


# ---- register source --------------------------------------------------------

def test_run_register_source_caps_and_reports(monkeypatch):
    from discover import daily
    from discover.onboarding import OnboardResult
    from discover.register import SponsorCandidate
    seen = {}
    cands = [SponsorCandidate(1, "A Ltd", "a ltd", "London", None, "A", "Skilled Worker"),
             SponsorCandidate(2, "B Ltd", "b ltd", "Leeds", None, "A", "Skilled Worker")]
    monkeypatch.setattr(daily, "find_candidates_for_profile",
                        lambda cur, pid, limit=None: seen.update(limit=limit) or cands)
    monkeypatch.setattr(daily, "onboard_candidates",
                        lambda cur, pid, cs, session: [
                            OnboardResult("onboarded", "A Ltd", 1, company_id=9),
                            OnboardResult("flagged", "B Ltd", 2, review_id=7)])

    rep = daily.run_register_source(None, "p-1", cap=25, session=None)

    assert seen["limit"] == 25                          # cap becomes the register limit
    assert rep.source == "register" and rep.ok
    assert rep.stats == {"scanned": 2, "onboarded": 1, "flagged": 1}
    assert "1 onboarded" in rep.line and "1 flagged" in rep.line


# ---- aggregator source ------------------------------------------------------

def _job(employer, ext="1", title="MLE"):
    from fetch.feeds import Job
    return Job(employer, "adzuna", ext, title, "London", f"u{ext}", "jd", None)


def test_run_aggregator_source_crosschecks_and_onboards_matched(monkeypatch):
    from discover import daily
    from discover.sponsor_match import SponsorMatch
    jobs = [_job("Acme AI Ltd", "1"), _job("Random LLC", "2"), _job("Acme AI Ltd", "3")]
    monkeypatch.setattr(daily, "search_adzuna", lambda *a, **k: jobs)
    monkeypatch.setattr(daily, "cross_check_employer",
                        lambda cur, emp, **k: SponsorMatch("matched", emp, sponsor_id=10)
                        if emp == "Acme AI Ltd" else SponsorMatch("unmatched", emp))
    onboarded = []
    monkeypatch.setattr(daily, "discover_company",
                        lambda cur, owner, emp, session: (onboarded.append(emp)
                        or {"outcome": "onboarded", "company_id": 99}))

    rep = daily.run_aggregator_source(None, _settings(), _criteria(["MLE"]),
                                      "adzuna", cap=50, onboard_cap=15, session=None)

    assert rep.source == "adzuna" and rep.ok
    assert rep.stats["jobs"] == 3 and rep.stats["employers"] == 2
    assert rep.stats["matched"] == 1 and rep.stats["onboarded"] == 1
    assert onboarded == ["Acme AI Ltd"]                 # only the matched sponsor, once


def test_run_aggregator_source_respects_the_onboard_cap(monkeypatch):
    from discover import daily
    from discover.sponsor_match import SponsorMatch
    monkeypatch.setattr(daily, "search_adzuna",
                        lambda *a, **k: [_job("One Ltd", "1"), _job("Two Ltd", "2"),
                                         _job("Three Ltd", "3")])
    monkeypatch.setattr(daily, "cross_check_employer",
                        lambda cur, emp, **k: SponsorMatch("matched", emp, sponsor_id=1))
    n = {"count": 0}
    monkeypatch.setattr(daily, "discover_company",
                        lambda *a, **k: n.update(count=n["count"] + 1) or {"outcome": "onboarded"})

    rep = daily.run_aggregator_source(None, _settings(), _criteria(["x"]),
                                      "adzuna", cap=50, onboard_cap=1, session=None)
    assert n["count"] == 1                              # stopped onboarding at the cap
    assert rep.stats["matched"] == 3                    # all three still counted as sponsors


def test_run_aggregator_source_flags_uncertain(monkeypatch):
    from discover import daily
    from discover.sponsor_match import SponsorMatch
    monkeypatch.setattr(daily, "search_reed", lambda *a, **k: [_job("Fuzzy Co")])
    monkeypatch.setattr(daily, "cross_check_employer",
                        lambda cur, emp, **k: SponsorMatch("uncertain", emp, candidates=({},)))
    monkeypatch.setattr(daily, "discover_company", lambda *a, **k: {"outcome": "onboarded"})
    rep = daily.run_aggregator_source(None, _settings(), _criteria(["x"]),
                                      "reed", cap=50, onboard_cap=15, session=None)
    assert rep.stats["uncertain"] == 1 and rep.stats["onboarded"] == 0


# ---- the whole discovery stage ---------------------------------------------

def test_run_discovery_runs_register_always_and_keyed_aggregators(monkeypatch):
    from discover import daily
    monkeypatch.setattr(daily, "default_profile_id", lambda cur: "p-1")
    monkeypatch.setattr(daily, "load_criteria", lambda cur, pid: _criteria(["x"]))
    monkeypatch.setattr(daily, "run_register_source",
                        lambda *a, **k: daily.SourceReport("register", True, "register: ok", {}))
    ran = []
    monkeypatch.setattr(daily, "run_aggregator_source",
                        lambda cur, s, c, source, **k: ran.append(source)
                        or daily.SourceReport(source, True, f"{source}: ok", {}))

    reps = daily.run_discovery(None, _settings(adzuna=True, reed=False), session=None)

    assert [r.source for r in reps] == ["register", "adzuna"]   # reed skipped (no key)
    assert ran == ["adzuna"]


def test_run_discovery_isolates_a_failing_source(monkeypatch):
    from discover import daily
    monkeypatch.setattr(daily, "default_profile_id", lambda cur: "p-1")
    monkeypatch.setattr(daily, "load_criteria", lambda cur, pid: _criteria(["x"]))
    monkeypatch.setattr(daily, "run_register_source",
                        lambda *a, **k: daily.SourceReport("register", True, "register: ok", {}))

    def boom(*a, **k):
        raise RuntimeError("adzuna down")
    monkeypatch.setattr(daily, "run_aggregator_source", boom)

    reps = daily.run_discovery(None, _settings(adzuna=True, reed=False), session=None)
    reg, adz = reps
    assert reg.ok and not adz.ok
    assert "down" in adz.line.lower()                   # captured, not raised
