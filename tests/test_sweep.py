"""The census sweep: picker, tracked-org map, probe, and orchestration.

Offline throughout: RoutingCursor serves canned rows and records SQL;
classify/fetch are monkeypatched at the sweep's own seam. The one invariant
that matters most — the sweep NEVER writes target_companies or review_items —
is pinned here (test_run_sweep_never_writes_target_companies_or_review_items).
"""
from __future__ import annotations

from tests.test_criteria import RoutingCursor as _RoutingCursor


class RoutingCursor(_RoutingCursor):
    """The shared routing fake + executemany capture (census_jobs batch writes)."""

    def __init__(self, routes):
        super().__init__(routes)
        self.executed_many = []

    def executemany(self, sql, params_seq):
        self.executed_many.append((" ".join(sql.split()).lower(), list(params_seq)))

BATCH_ROW = {
    "org_name_norm": "acme ai ltd",
    "sponsor_id": 42,
    "organisation_name": "Acme AI Ltd",
    "town_city": "London",
    "is_skilled_worker": True,
    "rating": "A",
}


def _register_query(cur):
    """The one query that hit licensed_sponsors."""
    hits = [(s, p) for s, p in cur.executed if "from licensed_sponsors ls" in s]
    assert len(hits) == 1
    return hits[0]


# ---- pick_batch -------------------------------------------------------------

def test_pick_batch_groups_register_rows_by_org_norm_and_skips_censused():
    from discover.sweep import pick_batch
    cur = RoutingCursor([("from licensed_sponsors", [BATCH_ROW])])
    out = pick_batch(cur, 10)
    assert out == [BATCH_ROW]
    sql, params = _register_query(cur)
    assert "group by ls.org_name_norm" in sql
    assert "not exists (select 1 from sponsor_census" in sql
    assert "limit %(n)s" in sql and params["n"] == 10


def test_pick_batch_orders_skilled_worker_then_a_rating_then_id():
    from discover.sweep import pick_batch
    cur = RoutingCursor([("from licensed_sponsors", [])])
    pick_batch(cur, 5)
    sql, params = _register_query(cur)
    order = sql.split("order by", 1)[1]
    assert "bool_or(ls.is_skilled_worker) desc" in order
    assert "bool_or(ls.rating = %(a_rating)s) desc" in order
    assert "min(ls.id)" in order
    assert params["a_rating"] == "A"


def test_pick_batch_excludes_null_and_blank_org_norms():
    from discover.sweep import pick_batch
    cur = RoutingCursor([("from licensed_sponsors", [])])
    pick_batch(cur, 5)
    sql, _ = _register_query(cur)
    assert "ls.org_name_norm is not null" in sql
    assert "ls.org_name_norm <> ''" in sql


def test_pick_batch_prioritises_software_like_names_first():
    from discover.sweep import TECH_NAME_PATTERN, pick_batch
    cur = RoutingCursor([("from licensed_sponsors", [])])
    pick_batch(cur, 5)
    sql, params = _register_query(cur)
    # the TOP-LEVEL order-by is the last one (the array_agg()s each carry their own)
    order = sql.rsplit("order by", 1)[1]
    # software-likelihood is the FIRST sort key, ahead of skilled-worker/rating/id
    assert order.strip().startswith("(ls.org_name_norm ~ %(tech)s) desc")
    assert order.index("~ %(tech)s") < order.index("is_skilled_worker")
    # the pattern is bound as a param (never string-interpolated) and covers the
    # strong software signals
    assert params["tech"] == TECH_NAME_PATTERN
    for kw in ("software", "technolog", "data", "\\yai\\y"):
        assert kw in TECH_NAME_PATTERN


def test_pick_batch_retry_errors_picks_error_rows_instead():
    from discover.sweep import pick_batch
    errored = dict(BATCH_ROW, probe_outcome="error")
    cur = RoutingCursor([("from sponsor_census", [errored])])
    out = pick_batch(cur, 7, retry_errors=True)
    assert out == [errored]
    sql, params = cur.executed[0]
    assert "from sponsor_census" in sql
    assert "probe_outcome = 'error'" in sql
    assert "order by probed_at" in sql
    assert "limit %(n)s" in sql and params["n"] == 7
    assert "licensed_sponsors" not in sql          # retry never re-walks the register


# ---- load_tracked_orgs ------------------------------------------------------

def test_load_tracked_orgs_maps_python_norms_and_register_linked_norms():
    from discover.sweep import load_tracked_orgs
    from normalise.text import norm
    cur = RoutingCursor([
        ("from target_companies", [
            {"company_name": "Acme", "ats_type": "greenhouse", "ats_token": "acme",
             "careers_url": "https://boards.greenhouse.io/acme", "linked_norm": None},
            {"company_name": "Beta Ltd", "ats_type": "lever", "ats_token": "beta",
             "careers_url": "https://jobs.lever.co/beta",
             "linked_norm": "beta data ltd"},      # tracked under a DIFFERENT name
        ]),
    ])
    tracked = load_tracked_orgs(cur, "p-1")
    assert norm("Acme") in tracked
    assert norm("Beta Ltd") in tracked
    assert "beta data ltd" in tracked              # the register-linked norm too
    assert tracked["beta data ltd"]["ats_type"] == "lever"
    sql, params = cur.executed[0]
    assert "left join licensed_sponsors ls on ls.id = tc.sponsor_id" in sql
    assert params == ("p-1",)


def test_load_tracked_orgs_only_reads_never_writes():
    from discover.sweep import load_tracked_orgs
    cur = RoutingCursor([("from target_companies", [])])
    load_tracked_orgs(cur, "p-1")
    for sql, _ in cur.executed:
        assert sql.startswith("select")


# ---- probe_org --------------------------------------------------------------

BETA_ROW = {
    "org_name_norm": "beta data ltd",
    "sponsor_id": 43,
    "organisation_name": "Beta Data Ltd",
    "town_city": "Leeds",
    "is_skilled_worker": True,
    "rating": "A",
}


def _job(title, url, location="London, UK", company="Acme AI Ltd"):
    from fetch.feeds import Job
    return Job(company_name=company, source="greenhouse", external_id=url,
               title=title, location=location, url=url, jd_text="",
               salary_text=None)


def _classification(name="Acme AI Ltd", n_jobs=5):
    from fetch.ats import ATS_GREENHOUSE, Classification
    return Classification(name, ATS_GREENHOUSE, "acmeai",
                          "https://boards.greenhouse.io/acmeai", n_jobs)


def _unknown(name):
    from fetch.ats import ATS_UNKNOWN, Classification
    return Classification(name, ATS_UNKNOWN, None, None, None)


def _matcher(title):
    return "engineer" in title.lower()


def test_probe_org_board_found_fetches_once_stores_all_jobs_labelled(monkeypatch):
    """Founder rule (2026-07-16): keep every job the board lists — foreign rows
    land labelled is_local=False; local_jobs_seen still counts locals only."""
    from discover import sweep
    fetches = []
    monkeypatch.setattr(sweep, "classify_company",
                        lambda name, session=None: _classification(name))
    monkeypatch.setattr(
        sweep, "fetch_company",
        lambda name, ats, token, session=None: fetches.append(token) or [
            _job("Senior Solutions Engineer", "https://a/1"),
            _job("Accountant", "https://a/2"),
            _job("Engineer", "https://a/3", location="New York, NY, US"),
        ])
    cur = RoutingCursor([])
    outcome, stored, matched = sweep.probe_org(cur, BATCH_ROW, None, _matcher)
    assert (outcome, stored, matched) == ("board_found", 3, 2)
    assert fetches == ["acmeai"]                        # fetched exactly once
    probe_sql, probe_params = next(
        (s, p) for s, p in cur.executed if "insert into sponsor_census" in s)
    assert "board_found" in probe_params and 5 in probe_params
    _, rows = cur.executed_many[0]
    assert len(rows) == 3                               # the US job lands too
    us_row = next(r for r in rows if "https://a/3" in r)
    assert us_row[8] is False                           # ...labelled foreign
    assert next(r for r in rows if "https://a/1" in r)[8] is True
    update_sql, update_params = next(
        (s, p) for s, p in cur.executed if "update sponsor_census" in s)
    assert update_params == (2, None, "acme ai ltd")    # local count = locals only


def test_probe_org_cap_keeps_local_jobs_first(monkeypatch):
    """When the agency-board cap bites, local jobs are kept ahead of foreign."""
    from discover import sweep
    monkeypatch.setattr(sweep, "MAX_JOBS_PER_ORG", 2)
    monkeypatch.setattr(sweep, "classify_company",
                        lambda name, session=None: _classification(name))
    monkeypatch.setattr(
        sweep, "fetch_company",
        lambda name, ats, token, session=None: [
            _job("Engineer", "https://a/us", location="New York, NY, US"),
            _job("Platform Engineer", "https://a/uk1"),
            _job("Data Engineer", "https://a/uk2"),
        ])
    cur = RoutingCursor([])
    outcome, stored, _ = sweep.probe_org(cur, BATCH_ROW, None, _matcher)
    assert (outcome, stored) == ("board_found", 2)
    _, rows = cur.executed_many[0]
    assert [r[5] for r in rows] == ["https://a/uk1", "https://a/uk2"]
    _, update_params = next(
        (s, p) for s, p in cur.executed if "update sponsor_census" in s)
    assert update_params == (2, None, "acme ai ltd")


def test_probe_org_no_board_records_no_board_and_never_fetches(monkeypatch):
    from discover import sweep
    monkeypatch.setattr(sweep, "classify_company",
                        lambda name, session=None: _unknown(name))
    monkeypatch.setattr(sweep, "fetch_company",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no fetch")))
    cur = RoutingCursor([])
    assert sweep.probe_org(cur, BATCH_ROW, None, _matcher) == ("no_board", 0, 0)
    _, params = cur.executed[0]
    assert "no_board" in params
    assert cur.executed_many == []


def test_probe_org_fetch_failure_still_records_board_found_with_error_noted(monkeypatch):
    from discover import sweep
    monkeypatch.setattr(sweep, "classify_company",
                        lambda name, session=None: _classification(name))
    monkeypatch.setattr(sweep, "fetch_company",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("500 from board")))
    cur = RoutingCursor([])
    outcome, stored, matched = sweep.probe_org(cur, BATCH_ROW, None, _matcher)
    assert (outcome, stored, matched) == ("board_found", 0, 0)
    _, params = next((s, p) for s, p in cur.executed if "update sponsor_census" in s)
    assert params == (None, "fetch failed: 500 from board", "acme ai ltd")


def test_probe_org_caps_jobs_per_org(monkeypatch):
    from discover import sweep
    monkeypatch.setattr(sweep, "classify_company",
                        lambda name, session=None: _classification(name, n_jobs=600))
    monkeypatch.setattr(
        sweep, "fetch_company",
        lambda name, ats, token, session=None: [
            _job(f"Engineer {i}", f"https://a/{i}") for i in range(600)])
    cur = RoutingCursor([])
    _, stored, _ = sweep.probe_org(cur, BATCH_ROW, None, _matcher)
    assert stored == sweep.MAX_JOBS_PER_ORG == 500      # agency-board guard
    _, rows = cur.executed_many[0]
    assert len(rows) == 500


# ---- run_sweep --------------------------------------------------------------

def _patch_loaders(monkeypatch, patterns=("Solutions Engineer",)):
    from criteria.loader import Criteria

    from discover import sweep
    monkeypatch.setattr(sweep, "default_profile_id", lambda cur: "p-1")
    monkeypatch.setattr(
        sweep, "load_criteria",
        lambda cur, pid=None: Criteria(
            profile_id="p-1", name="T", salary_floor=40000,
            threshold_standard=None, threshold_new_entrant=None,
            kill_keywords=[], role_patterns=list(patterns)))


def _settings():
    from config import Settings
    return Settings(database_url="x", gemini_api_key="")


TRACKED_ACME = {"company_name": "Acme AI Ltd", "ats_type": "greenhouse",
                "ats_token": "acmeai",
                "careers_url": "https://boards.greenhouse.io/acmeai",
                "linked_norm": None}


def test_run_sweep_marks_already_tracked_without_probing(monkeypatch):
    from discover import sweep
    _patch_loaders(monkeypatch)
    monkeypatch.setattr(sweep, "classify_company",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no probe")))
    monkeypatch.setattr(sweep, "_sleep", lambda s: None)
    cur = RoutingCursor([("from target_companies", [TRACKED_ACME]),
                         ("from licensed_sponsors", [BATCH_ROW])])
    report = sweep.run_sweep(cur, _settings(), batch=10, pause=0)
    assert report.picked == 1 and report.already_tracked == 1
    _, params = next((s, p) for s, p in cur.executed
                     if "insert into sponsor_census" in s)
    assert "already_tracked" in params and "greenhouse" in params


def test_run_sweep_isolates_per_org_errors_and_continues(monkeypatch):
    from discover import sweep
    _patch_loaders(monkeypatch)

    def explode_on_acme(name, session=None):
        if "Acme" in name:
            raise RuntimeError("probe boom")
        return _unknown(name)

    monkeypatch.setattr(sweep, "classify_company", explode_on_acme)
    monkeypatch.setattr(sweep, "_sleep", lambda s: None)
    cur = RoutingCursor([("from target_companies", []),
                         ("from licensed_sponsors", [BATCH_ROW, BETA_ROW])])
    report = sweep.run_sweep(cur, _settings(), batch=10, pause=0)
    assert report.errors == 1 and report.no_board == 1 and report.picked == 2
    _, params = next((s, p) for s, p in cur.executed
                     if "insert into sponsor_census" in s and "error" in (p or ()))
    assert "probe boom" in params


def test_run_sweep_never_writes_target_companies_or_review_items(monkeypatch):
    """THE blast-radius pin: a full mixed sweep touches only the census tables."""
    from discover import sweep
    _patch_loaders(monkeypatch)
    gamma = dict(BETA_ROW, org_name_norm="gamma co", organisation_name="Gamma Co")

    def classify(name, session=None):
        return _classification(name) if "Beta" in name else _unknown(name)

    monkeypatch.setattr(sweep, "classify_company", classify)
    monkeypatch.setattr(sweep, "fetch_company",
                        lambda name, ats, token, session=None: [
                            _job("Solutions Engineer", "https://b/1", company=name)])
    monkeypatch.setattr(sweep, "_sleep", lambda s: None)
    cur = RoutingCursor([("from target_companies", [TRACKED_ACME]),
                         ("from licensed_sponsors", [BATCH_ROW, BETA_ROW, gamma])])
    report = sweep.run_sweep(cur, _settings(), batch=10, pause=0)
    assert (report.already_tracked, report.boards_found, report.no_board) == (1, 1, 1)
    every_sql = [s for s, _ in cur.executed] + [s for s, _ in cur.executed_many]
    for sql in every_sql:
        assert "insert into target_companies" not in sql
        assert "update target_companies" not in sql
        assert "review_items" not in sql


def test_run_sweep_paces_with_swappable_sleep(monkeypatch):
    from discover import sweep
    _patch_loaders(monkeypatch)
    monkeypatch.setattr(sweep, "classify_company",
                        lambda name, session=None: _unknown(name))
    naps = []
    monkeypatch.setattr(sweep, "_sleep", naps.append)
    cur = RoutingCursor([("from target_companies", []),
                         ("from licensed_sponsors", [BATCH_ROW, BETA_ROW])])
    sweep.run_sweep(cur, _settings(), batch=10, pause=0.25)
    assert naps == [0.25, 0.25]


def test_run_sweep_commits_per_org_and_reports_totals(monkeypatch):
    from discover import sweep
    _patch_loaders(monkeypatch)
    gamma = dict(BETA_ROW, org_name_norm="gamma co", organisation_name="Gamma Co")

    def classify(name, session=None):
        return _classification(name) if "Beta" in name else _unknown(name)

    monkeypatch.setattr(sweep, "classify_company", classify)
    monkeypatch.setattr(sweep, "fetch_company",
                        lambda name, ats, token, session=None: [
                            _job("Solutions Engineer", "https://b/1", company=name),
                            _job("Accountant", "https://b/2", company=name)])
    monkeypatch.setattr(sweep, "_sleep", lambda s: None)
    commits = []
    cur = RoutingCursor([("from target_companies", [TRACKED_ACME]),
                         ("from licensed_sponsors", [BATCH_ROW, BETA_ROW, gamma])])
    report = sweep.run_sweep(cur, _settings(), batch=10, pause=0,
                             commit=lambda: commits.append(1))
    assert len(commits) == 3                            # one commit per org
    assert report.picked == 3
    assert report.already_tracked == 1 and report.boards_found == 1
    assert report.no_board == 1 and report.errors == 0
    assert report.jobs_stored == 2 and report.title_matches == 1


# ---- registry gating --------------------------------------------------------

def _ch_settings(key=""):
    from config import Settings
    return Settings(database_url="x", gemini_api_key="",
                    companies_house_api_key=key)


def _run_gated(monkeypatch, settings, probe_only=False):
    import types

    from discover import sweep
    _patch_loaders(monkeypatch)
    monkeypatch.setattr(sweep, "classify_company",
                        lambda name, session=None: _unknown(name))
    monkeypatch.setattr(sweep, "_sleep", lambda s: None)
    enriched = []
    monkeypatch.setattr(sweep, "registry", types.SimpleNamespace(
        enrich_org=lambda cur, org_norm, name, key, session=None:
            enriched.append((org_norm, key)) or "matched"))
    cur = RoutingCursor([("from target_companies", []),
                         ("from licensed_sponsors", [BATCH_ROW])])
    sweep.run_sweep(cur, settings, batch=10, pause=0, probe_only=probe_only)
    return enriched


def test_run_sweep_enriches_via_registry_when_key_ready(monkeypatch):
    enriched = _run_gated(monkeypatch, _ch_settings("CHKEY"))
    assert enriched == [("acme ai ltd", "CHKEY")]


def test_run_sweep_skips_registry_when_unready_or_probe_only(monkeypatch):
    assert _run_gated(monkeypatch, _ch_settings("")) == []
    assert _run_gated(monkeypatch, _ch_settings("CHKEY"), probe_only=True) == []


def test_probe_org_tries_harvested_token_hint_before_guessing(monkeypatch):
    # Token harvest plants ats_type/ats_token hints on census cards; the probe
    # must verify the hint with ONE call and skip slug guessing entirely.
    from fetch.ats import Classification
    from fetch.feeds import Job
    import discover.sweep as sweep

    org = {**BATCH_ROW, "ats_type": "lever", "ats_token": "acme"}
    probed, fetched = [], []
    monkeypatch.setattr(sweep, "probe_token",
                        lambda ats, tok, s: probed.append((ats, tok)) or
                        Classification("", "lever", "acme",
                                       "https://jobs.lever.co/acme", 1))
    monkeypatch.setattr(sweep, "classify_company",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("guesser must not run when the hint verifies")))
    monkeypatch.setattr(sweep, "fetch_company",
                        lambda name, ats, tok, s: fetched.append((ats, tok)) or
                        [Job(name, "lever", "1", "ML Engineer", "London, UK",
                             "https://jobs.lever.co/acme/1", "", None)])
    cur = RoutingCursor({})
    outcome, stored, matched = sweep.probe_org(cur, org, session=None,
                                               title_matcher=lambda t: True)
    assert outcome == "board_found" and stored == 1
    assert probed == [("lever", "acme")]
    assert fetched == [("lever", "acme")]


def test_probe_org_falls_back_to_guessing_when_hint_is_dead(monkeypatch):
    from fetch.ats import Classification
    import discover.sweep as sweep

    org = {**BATCH_ROW, "ats_type": "lever", "ats_token": "gone-stale"}
    guessed = []
    monkeypatch.setattr(sweep, "probe_token", lambda *a: None)   # hint is dead
    monkeypatch.setattr(sweep, "classify_company",
                        lambda name, s: guessed.append(name) or
                        Classification(name, "unknown", None, None, None))
    cur = RoutingCursor({})
    outcome, stored, matched = sweep.probe_org(cur, org, session=None,
                                               title_matcher=lambda t: True)
    assert outcome == "no_board"
    assert guessed == [BATCH_ROW["organisation_name"]]
