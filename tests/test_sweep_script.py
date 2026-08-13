"""scripts/sweep.py — the thin census runner.

Loaded via importlib (scripts/ is not a package). Everything main() lazily
imports is monkeypatched at its source module, so nothing spawns, connects, or
sleeps. Pins: the sweep takes its OWN .sweep.lock (never .run.lock — sweep and
daily pipeline must coexist), flags reach run_sweep, item errors never turn
into a non-zero exit, and progress/totals go to stderr.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from tests.conftest import FakeCursor, fake_conn

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "sweep_script", ROOT / "scripts" / "sweep.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _report(**overrides):
    from discover.sweep import SweepReport
    base = dict(picked=3, boards_found=1, no_board=1, already_tracked=1,
                errors=0, jobs_stored=2, title_matches=1)
    base.update(overrides)
    return SweepReport(**base)


COUNTS = {"total_unique_orgs": 110000, "probed": 50,
          "by_outcome": {"board_found": 3}, "boards_found": 3,
          "census_jobs": 42, "title_matches": 7,
          "registry_by_outcome": {}, "remaining": 109950}


def _wire(monkeypatch, *, report=None, capture=None):
    """Happy-path plumbing: lock free, settings offline, DB faked, sweep canned."""
    from config import Settings
    monkeypatch.setattr("pipeline.lock.acquire_lock", lambda path: object())
    monkeypatch.setattr("config.get_settings",
                        lambda **kw: Settings(database_url="x", gemini_api_key=""))
    monkeypatch.setattr("db.connection.get_conn",
                        lambda: fake_conn(FakeCursor()))
    monkeypatch.setattr("discover.census_store.census_status_counts",
                        lambda cur: dict(COUNTS))

    def fake_run_sweep(cur, settings, **kwargs):
        if capture is not None:
            capture.update(kwargs)
        return report or _report()

    monkeypatch.setattr("discover.sweep.run_sweep", fake_run_sweep)


def test_sweep_script_declines_when_the_sweep_lock_is_held(monkeypatch, capsys):
    mod = load_script()
    seen = {}
    monkeypatch.setattr("pipeline.lock.acquire_lock",
                        lambda path: seen.update(path=str(path)) or None)
    monkeypatch.setattr("db.connection.get_conn",
                        lambda: (_ for _ in ()).throw(AssertionError("no DB")))
    mod.main([])
    assert "another sweep is in progress" in capsys.readouterr().err
    assert seen["path"].endswith(".sweep.lock")        # its OWN lock, not .run.lock


def test_sweep_script_passes_flags_through_to_run_sweep(monkeypatch):
    mod = load_script()
    captured = {}
    _wire(monkeypatch, capture=captured)
    mod.main(["--batch", "50", "--pause", "0.1", "--retry-errors", "--probe-only"])
    assert captured["batch"] == 50 and captured["pause"] == 0.1
    assert captured["retry_errors"] is True and captured["probe_only"] is True
    assert callable(captured["commit"]) and callable(captured["on_progress"])


def test_sweep_script_defaults_to_a_2000_batch(monkeypatch):
    mod = load_script()
    captured = {}
    _wire(monkeypatch, capture=captured)
    mod.main([])
    assert captured["batch"] == 2000 and captured["pause"] == 0.3
    assert captured["retry_errors"] is False and captured["probe_only"] is False


def test_sweep_script_exits_zero_despite_item_errors(monkeypatch, capsys):
    mod = load_script()
    _wire(monkeypatch, report=_report(errors=5))
    mod.main([])                                       # no SystemExit raised
    assert "5 errors" in capsys.readouterr().err


def test_sweep_script_owner_lens_routes_to_the_lens_sweep(monkeypatch):
    mod = load_script()
    captured = {}
    _wire(monkeypatch, capture=None)
    monkeypatch.setattr("discover.sweep.run_sweep",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("full sweep must not run")))

    def fake_lens(cur, settings, **kwargs):
        captured.update(kwargs)
        return _report()
    monkeypatch.setattr("discover.probe_pick.run_lens_sweep", fake_lens)

    mod.main(["--owner-lens", "--batch", "40"])
    assert captured["batch"] == 40
    assert callable(captured["commit"]) and callable(captured["on_progress"])


def test_sweep_script_still_accepts_the_old_software_only_spelling(monkeypatch):
    # U1 renamed the mode (the lens is the owner's rule now, software is just
    # the bootstrap fallback); the old flag stays as an alias for shell
    # muscle-memory. Same dest, same path.
    mod = load_script()
    called = []
    _wire(monkeypatch, capture=None)
    monkeypatch.setattr("discover.probe_pick.run_lens_sweep",
                        lambda *a, **k: called.append(1) or _report())
    mod.main(["--software-only", "--batch", "5"])
    assert called == [1]


def test_sweep_script_owner_lens_with_workers_goes_parallel(monkeypatch):
    mod = load_script()
    captured = {}
    _wire(monkeypatch, capture=None)
    monkeypatch.setattr("discover.sweep.run_sweep",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("full sweep must not run")))
    monkeypatch.setattr("discover.probe_pick.run_lens_sweep",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("sequential path must not run")))

    def fake_parallel(conn_factory, settings, **kwargs):
        captured.update(kwargs)
        captured["conn_factory"] = conn_factory
        return _report()
    monkeypatch.setattr("discover.probe_pick.run_lens_sweep_parallel",
                        fake_parallel)

    mod.main(["--owner-lens", "--workers", "4", "--batch", "60"])
    assert captured["workers"] == 4 and captured["batch"] == 60
    assert callable(captured["conn_factory"])          # each worker opens its own


def test_sweep_script_rejects_workers_without_owner_lens(monkeypatch):
    import pytest
    mod = load_script()
    _wire(monkeypatch)
    with pytest.raises(SystemExit):
        mod.main(["--workers", "4"])


def test_sweep_script_prints_progress_to_stderr_and_a_final_summary(monkeypatch, capsys):
    mod = load_script()

    def run_and_tick(cur, settings, **kwargs):
        kwargs["on_progress"](1, 50)                   # below the stride: silent
        kwargs["on_progress"](25, 50)
        kwargs["on_progress"](50, 50)                  # the final org always prints
        return _report()

    from config import Settings
    monkeypatch.setattr("pipeline.lock.acquire_lock", lambda path: object())
    monkeypatch.setattr("config.get_settings",
                        lambda **kw: Settings(database_url="x", gemini_api_key=""))
    monkeypatch.setattr("db.connection.get_conn",
                        lambda: fake_conn(FakeCursor()))
    monkeypatch.setattr("discover.census_store.census_status_counts",
                        lambda cur: dict(COUNTS))
    monkeypatch.setattr("discover.sweep.run_sweep", run_and_tick)

    mod.main([])
    err = capsys.readouterr().err
    assert "[sweep] 1/50 orgs" not in err
    assert "[sweep] 25/50 orgs" in err
    assert "[sweep] 50/50 orgs" in err
    assert "[sweep] batch done: 3 picked" in err
    assert "50/110000 censused" in err and "109950 remaining" in err
