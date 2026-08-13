"""scripts/classify_sponsors.py — the Pass 1 runner (loaded via importlib)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from tests.conftest import FakeCursor, fake_conn

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    return _load("classify_script", "classify_sponsors.py")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


COUNTS = {"total_unique_orgs": 126000, "classified": 5000,
          "by_outcome": {"matched": 3200, "not_found": 1800},
          "software_companies": 640, "remaining": 121000}


def _report(**kw):
    from discover.classify import ClassifyReport
    base = dict(picked=5000, matched=3200, ambiguous=0, not_found=1800, errors=0)
    base.update(kw)
    return ClassifyReport(**base)


def _wire(monkeypatch, *, report=None, capture=None):
    from config import Settings
    monkeypatch.setattr("pipeline.lock.acquire_lock", lambda path: object())
    monkeypatch.setattr("config.get_settings",
                        lambda **kw: Settings(database_url="x", gemini_api_key="",
                                              companies_house_api_key="CHKEY"))
    monkeypatch.setattr("db.connection.get_conn", lambda: fake_conn(FakeCursor()))
    monkeypatch.setattr("discover.census_store.classify_status_counts",
                        lambda cur, sic: dict(COUNTS))

    def fake_run(cur, settings, **kwargs):
        if capture is not None:
            capture.update(kwargs)
        return report or _report()

    monkeypatch.setattr("discover.classify.run_classify", fake_run)


def test_declines_on_its_own_lock_not_the_sweep_lock(monkeypatch, capsys):
    mod = load_script()
    seen = {}
    monkeypatch.setattr("pipeline.lock.acquire_lock",
                        lambda path: seen.update(path=str(path)) or None)
    monkeypatch.setattr("db.connection.get_conn",
                        lambda: (_ for _ in ()).throw(AssertionError("no DB")))
    mod.main([])
    assert "another classification run" in capsys.readouterr().err
    assert seen["path"].endswith(".classify.lock")     # its OWN lock


def test_passes_batch_through(monkeypatch):
    mod = load_script()
    cap = {}
    _wire(monkeypatch, capture=cap)
    mod.main(["--batch", "100"])
    assert cap["batch"] == 100 and callable(cap["commit"])


def test_defaults_to_a_5000_batch(monkeypatch):
    mod = load_script()
    cap = {}
    _wire(monkeypatch, capture=cap)
    mod.main([])
    assert cap["batch"] == 5000


def test_exits_zero_and_prints_software_total(monkeypatch, capsys):
    mod = load_script()
    _wire(monkeypatch, report=_report(errors=3))
    mod.main([])
    err = capsys.readouterr().err
    assert "3 errors" in err
    assert "640 software" in err and "5000/126000" in err


def test_skips_without_the_key_instead_of_failing_the_daily_loop(monkeypatch, capsys):
    # The daily loop shells this script and treats a nonzero exit as a failed
    # stage — an unset key must say so and end quietly.
    mod = load_script()
    from config import Settings
    monkeypatch.setattr("pipeline.lock.acquire_lock", lambda path: object())
    monkeypatch.setattr("config.get_settings",
                        lambda **kw: Settings(database_url="x", gemini_api_key=""))
    monkeypatch.setattr("db.connection.get_conn",
                        lambda: (_ for _ in ()).throw(AssertionError("no DB")))
    assert mod.main([]) is None                     # returns = exit 0
    err = capsys.readouterr().err
    assert "COMPANIES_HOUSE_API_KEY" in err and "skipping" in err


def test_a_current_census_is_a_fast_no_op(monkeypatch, capsys):
    """Nothing left to classify: one line, no scoreboard aggregate, exit 0."""
    mod = load_script()
    _wire(monkeypatch, report=_report(picked=0, matched=0, not_found=0))
    scoreboards = []
    monkeypatch.setattr("discover.census_store.classify_status_counts",
                        lambda cur, sic: scoreboards.append(1) or dict(COUNTS))
    assert mod.main([]) is None
    assert "no unclassified sponsors" in capsys.readouterr().err
    assert scoreboards == []


def test_daily_loop_classifies_newcomers_between_register_and_discover():
    names = [name for name, _ in _load("run_script", "run.py").STAGE_CMDS]
    assert names.index("register") < names.index("classify") < names.index("discover")


def test_daily_classify_stage_is_capped():
    """Companies House paces at 0.6 s/company — an uncapped batch could run
    for hours inside the nightly loop."""
    cmd = dict(_load("run_script", "run.py").STAGE_CMDS)["classify"]
    assert cmd[0].endswith("classify_sponsors.py")
    assert "--batch" in cmd
    assert 0 < int(cmd[cmd.index("--batch") + 1]) <= 2000
