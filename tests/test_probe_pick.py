"""Pass 2 owner-lens probing: picker + runners (sequential and parallel).

The sequence: classify ALL orgs first (Pass 1), THEN probe — inside the
OWNER'S lens first (U1: the codes come from THEIR promotion rule, so a
care-home rule picks care-home cards with no code edit; the software set is
only the bootstrap fallback for a rule-less database). probe_pick reuses the
existing probe machinery (probe_org / upsert_probe) untouched. The parallel
runner is the one real Pass-2 efficiency win: N workers, each with its OWN
connection, per-org commit preserved. No registry calls here — Pass 1
already did that.
"""
from __future__ import annotations

import threading

from tests.conftest import FakeConn, FakeCursor
from tests.test_criteria import RoutingCursor

ORG = {"org_name_norm": "acme software ltd", "sponsor_id": 7,
       "organisation_name": "Acme Software Ltd", "town_city": "London",
       "is_skilled_worker": True, "rating": "A"}
ORG2 = {"org_name_norm": "beta systems ltd", "sponsor_id": 8,
        "organisation_name": "Beta Systems Ltd", "town_city": "Leeds",
        "is_skilled_worker": True, "rating": "A"}

CARE_RULE = {"industry_codes": ["87300", "87100"], "min_local_jobs": 1,
             "auto": True}


def _lens_cursor(rule_rows, census_rows):
    return RoutingCursor([
        ("from profiles", [{"profile_id": "owner-1"}]),
        ("from promotion_rules", rule_rows),
        ("from sponsor_census", census_rows),
    ])


# ---- pick_owner_lens_batch --------------------------------------------------

def test_pick_owner_lens_batch_narrows_to_the_owners_rule_codes():
    from discover.probe_pick import pick_owner_lens_batch
    cur = _lens_cursor([CARE_RULE], [ORG])
    out = pick_owner_lens_batch(cur, 500)
    assert out == [ORG]
    sql, params = [(s, p) for s, p in cur.executed
                   if "from sponsor_census" in s.lower()][0]
    lowered = sql.lower()
    # the exact narrowing: never probed + registry-matched + THE OWNER'S codes
    assert "probe_outcome is null" in lowered
    assert "registry_outcome = 'matched'" in lowered
    assert "industry_codes && %(codes)s::text[]" in lowered
    assert "ats_type" in lowered and "ats_token" in lowered   # harvest hints ride along
    # active companies first, then stable name order — deterministic resume
    order = lowered.rsplit("order by", 1)[1]
    assert "registry_status = 'active'" in order
    assert params["n"] == 500
    assert params["codes"] == ["87300", "87100"]   # the rule, not SOFTWARE_SIC


def test_a_care_home_rule_and_a_software_rule_use_the_same_code_path():
    # The phase's keystone acceptance: switching lens = switching ROWS.
    # Same function, no code edit — only the rule row differs.
    from discover.probe_pick import pick_owner_lens_batch
    care = _lens_cursor([CARE_RULE], [])
    pick_owner_lens_batch(care, 10)
    soft = _lens_cursor([{"industry_codes": ["62012"], "min_local_jobs": 1,
                          "auto": True}], [])
    pick_owner_lens_batch(soft, 10)

    def codes_sent(cur):
        return [p["codes"] for s, p in cur.executed
                if "from sponsor_census" in s.lower()][0]
    assert codes_sent(care) == ["87300", "87100"]
    assert codes_sent(soft) == ["62012"]


def test_pick_owner_lens_batch_falls_back_to_software_without_a_rule():
    # Bootstrap: a rule-less database (or an empty code set) behaves exactly
    # as before U1 — the software set, not an empty pick.
    from discover.classify import SOFTWARE_SIC
    from discover.probe_pick import pick_owner_lens_batch
    for rule_rows in ([], [{"industry_codes": [], "min_local_jobs": 1,
                            "auto": True}]):
        cur = _lens_cursor(rule_rows, [])
        pick_owner_lens_batch(cur, 10)
        params = [p for s, p in cur.executed
                  if "from sponsor_census" in s.lower()][0]
        assert set(params["codes"]) == set(SOFTWARE_SIC)


# ---- run_lens_sweep (sequential) ----------------------------------------

def _stub_criteria(monkeypatch, pp):
    monkeypatch.setattr(pp, "default_profile_id", lambda cur: "owner-1")

    class _Crit:
        role_patterns = ["engineer"]
    monkeypatch.setattr(pp, "load_criteria", lambda cur, owner: _Crit())
    monkeypatch.setattr(pp, "build_role_matcher",
                        lambda patterns: (lambda title: False))


def test_run_lens_sweep_probes_each_and_commits_per_org(monkeypatch):
    from discover import probe_pick as pp
    _stub_criteria(monkeypatch, pp)
    monkeypatch.setattr(pp, "pick_owner_lens_batch", lambda cur, n: [ORG, ORG2])
    monkeypatch.setattr(pp, "load_tracked_orgs", lambda cur, owner: {})
    probed = []
    monkeypatch.setattr(pp, "probe_org",
                        lambda cur, org, session, matcher:
                        probed.append(org["org_name_norm"]) or ("board_found", 3, 1))
    commits = []
    report = pp.run_lens_sweep(FakeCursor(), object(), batch=10, pause=0,
                                   session=object(),
                                   commit=lambda: commits.append(1))
    assert probed == [ORG["org_name_norm"], ORG2["org_name_norm"]]
    assert len(commits) == 2                       # per-org commit = exact resume
    assert report.picked == 2 and report.boards_found == 2
    assert report.jobs_stored == 6 and report.title_matches == 2


def test_run_lens_sweep_skips_tracked_and_isolates_errors(monkeypatch):
    from discover import probe_pick as pp
    _stub_criteria(monkeypatch, pp)
    monkeypatch.setattr(pp, "pick_owner_lens_batch", lambda cur, n: [ORG, ORG2])
    monkeypatch.setattr(
        pp, "load_tracked_orgs",
        lambda cur, owner: {ORG["org_name_norm"]: {"ats_type": "greenhouse",
                                                   "ats_token": "acme",
                                                   "careers_url": "u"}})

    def boom(cur, org, session, matcher):
        raise RuntimeError("probe exploded")
    monkeypatch.setattr(pp, "probe_org", boom)
    cur = FakeCursor()
    report = pp.run_lens_sweep(cur, object(), batch=10, pause=0,
                                   session=object(), commit=None)
    # tracked org was carded as already_tracked, the error org as error —
    # one bad org costs one org, never the run
    assert report.already_tracked == 1 and report.errors == 1
    sqls = " ".join(s for s, _ in cur.executed).lower()
    assert "insert into sponsor_census" in sqls


def test_run_lens_sweep_never_calls_the_registry(monkeypatch):
    """Pass 2 is probe-only by definition — Pass 1 already classified."""
    import inspect

    from discover import probe_pick as pp
    source = inspect.getsource(pp)
    assert "enrich_org" not in source
    assert "companies_house" not in source


# ---- run_lens_sweep_parallel --------------------------------------------

def test_parallel_sweep_probes_all_with_own_connection_per_worker(monkeypatch):
    from discover import probe_pick as pp
    _stub_criteria(monkeypatch, pp)
    orgs = [dict(ORG, org_name_norm=f"org {i}") for i in range(8)]
    monkeypatch.setattr(pp, "pick_owner_lens_batch", lambda cur, n: list(orgs))
    monkeypatch.setattr(pp, "load_tracked_orgs", lambda cur, owner: {})
    seen, lock = [], threading.Lock()

    def fake_probe(cur, org, session, matcher):
        with lock:
            seen.append(org["org_name_norm"])
        return ("board_found", 1, 0)
    monkeypatch.setattr(pp, "probe_org", fake_probe)

    made = []

    def conn_factory():
        conn = FakeConn(FakeCursor())
        made.append(conn)
        return _ctx(conn)

    report = pp.run_lens_sweep_parallel(conn_factory, object(), batch=8,
                                            workers=3, pause=0)
    assert sorted(seen) == sorted(o["org_name_norm"] for o in orgs)
    assert report.picked == 8 and report.boards_found == 8
    # picker conn + one per worker, each with per-org commits summing to 8
    assert len(made) == 4
    assert sum(c.commits for c in made[1:]) == 8


def test_parallel_sweep_isolates_a_bad_org_per_worker(monkeypatch):
    from discover import probe_pick as pp
    _stub_criteria(monkeypatch, pp)
    orgs = [dict(ORG, org_name_norm=f"org {i}") for i in range(4)]
    monkeypatch.setattr(pp, "pick_owner_lens_batch", lambda cur, n: list(orgs))
    monkeypatch.setattr(pp, "load_tracked_orgs", lambda cur, owner: {})

    def flaky(cur, org, session, matcher):
        if org["org_name_norm"].endswith("2"):
            raise RuntimeError("one bad org")
        return ("board_found", 1, 0)
    monkeypatch.setattr(pp, "probe_org", flaky)

    report = pp.run_lens_sweep_parallel(
        lambda: _ctx(FakeConn(FakeCursor())), object(), batch=4, workers=2,
        pause=0)
    assert report.errors == 1 and report.boards_found == 3
    assert report.picked == 4


def _ctx(conn):
    import contextlib

    @contextlib.contextmanager
    def cm():
        yield conn
    return cm()


# ---- hiring-first probing: aggregator ads say WHO is hiring; the free board
# probe then finds their boards (replaces the dead URL-following harvest,
# 2026-07-27) --------------------------------------------------------------

def test_pick_hiring_batch_narrows_to_unprobed_sponsors_with_live_ads():
    from discover.probe_pick import pick_hiring_batch
    cur = RoutingCursor([("aggregator_ads", [ORG])])
    out = pick_hiring_batch(cur, 250)
    assert out == [ORG]
    sql, params = cur.executed[0]
    low = sql.lower()
    assert "join aggregator_ads" in low
    assert "matched_org_norm" in low
    assert "probe_outcome is null" in low          # never probed only
    assert "ats_type" in low and "ats_token" in low
    order = low.split("order by", 1)[1]
    assert "count(*) desc" in order                # busiest hirers first
    assert params["n"] == 250


def test_run_lens_sweep_accepts_an_injected_picker(monkeypatch):
    """One runner, swappable batch source: software lot OR hiring-first."""
    from discover import probe_pick as pp
    _stub_criteria(monkeypatch, pp)
    monkeypatch.setattr(pp, "load_tracked_orgs", lambda cur, owner: {})
    probed = []
    monkeypatch.setattr(pp, "probe_org",
                        lambda cur, org, session, matcher:
                        probed.append(org["org_name_norm"]) or ("board_found", 1, 0))
    monkeypatch.setattr(pp, "pick_owner_lens_batch",
                        lambda cur, n: (_ for _ in ()).throw(
                            AssertionError("the injected picker must be used")))
    report = pp.run_lens_sweep(FakeCursor(), object(), batch=2, pause=0,
                                   session=object(),
                                   picker=lambda cur, n: [ORG2])
    assert probed == [ORG2["org_name_norm"]]
    assert report.picked == 1


def test_parallel_sweep_accepts_an_injected_picker(monkeypatch):
    from discover import probe_pick as pp
    _stub_criteria(monkeypatch, pp)
    monkeypatch.setattr(pp, "load_tracked_orgs", lambda cur, owner: {})
    monkeypatch.setattr(pp, "probe_org",
                        lambda cur, org, session, matcher: ("board_found", 2, 1))
    report = pp.run_lens_sweep_parallel(
        lambda: _ctx(FakeConn(FakeCursor())), object(), batch=2, workers=2,
        pause=0, picker=lambda cur, n: [ORG, ORG2])
    assert report.picked == 2 and report.boards_found == 2
