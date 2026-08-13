"""Tests for src/pipeline/trigger — shelling the SAME scripts/run.py the
scheduler uses. The subprocess runner is injected, so nothing is actually spawned
(no fetch, no Gemini spend, no nudges): we only pin the command and env shape.
"""
from __future__ import annotations

import sys


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


# ---- the interpreter, BOTH ways round ----
# The old assertion here was `".venv" in cmd[0]`, which passed on the laptop for
# the wrong reason and hid a container-fatal bug: the image has no .venv, so the
# hardcoded path was a FileNotFoundError for every tool that spawned a script.

def test_python_executable_prefers_the_repo_venv(tmp_path):
    from pipeline.trigger import python_executable
    venv_py = tmp_path / ".venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("")
    assert python_executable(tmp_path) == str(venv_py)


def test_python_executable_falls_back_to_the_running_interpreter(tmp_path):
    from pipeline.trigger import python_executable
    # No .venv — this is the container. Must reuse the image interpreter.
    assert python_executable(tmp_path) == sys.executable


def test_trigger_pipeline_runs_run_py_with_the_resolved_python_and_pythonpath():
    from pipeline.trigger import python_executable, trigger_pipeline
    seen = {}

    def fake_runner(cmd, **kwargs):
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        return FakeProc(returncode=0, stderr="Run 7: all stages ok")

    out = trigger_pipeline(dry_run=False, runner=fake_runner)

    assert out["returncode"] == 0 and out["dry_run"] is False
    assert "all stages ok" in out["summary"]
    assert any(c.endswith("scripts/run.py") for c in seen["cmd"])   # the real entrypoint
    assert seen["cmd"][0] == python_executable()   # resolved, never hardcoded
    assert "--dry-run" not in seen["cmd"]
    assert seen["kwargs"]["env"]["PYTHONPATH"] == "src"


def test_trigger_pipeline_passes_the_dry_run_flag_through():
    from pipeline.trigger import trigger_pipeline
    seen = {}

    def fake_runner(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeProc(returncode=0, stderr="DRY RUN — would nudge 5")

    out = trigger_pipeline(dry_run=True, runner=fake_runner)

    assert out["dry_run"] is True
    assert "--dry-run" in seen["cmd"]
    assert "would nudge 5" in out["summary"]


def test_trigger_pipeline_reports_a_nonzero_exit():
    from pipeline.trigger import trigger_pipeline
    out = trigger_pipeline(
        runner=lambda cmd, **kw: FakeProc(returncode=1, stderr="exit 1: quota blown"))
    assert out["returncode"] == 1
    assert "quota blown" in out["summary"]


# ---- the split: a preview waits, a real run must NOT ----
# A full run takes ~12 minutes. Hosted behind Cloud Run's 300s request timeout,
# a blocking start is a guaranteed 504 — so the real run goes detached.

def test_preview_pipeline_is_synchronous_and_always_a_dry_run():
    from pipeline.trigger import preview_pipeline, python_executable
    seen = {}

    def fake_runner(cmd, **kwargs):
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        return FakeProc(returncode=0, stderr="DRY RUN — would nudge 5")

    out = preview_pipeline(runner=fake_runner)

    assert out["dry_run"] is True and out["returncode"] == 0
    assert "would nudge 5" in out["summary"]        # it WAITED for the output
    assert seen["cmd"][0] == python_executable()
    assert seen["cmd"][1].endswith("scripts/run.py")
    assert "--dry-run" in seen["cmd"]               # never a real run
    assert seen["kwargs"]["env"]["PYTHONPATH"] == "src"


def test_start_pipeline_detaches_and_returns_immediately(tmp_path):
    from pipeline.trigger import python_executable, start_pipeline
    seen = {}

    out = start_pipeline(spawn=lambda cmd, **kw: seen.update(cmd=cmd, **kw) or object(),
                         log_dir=tmp_path / "run-logs")

    assert out["started"] is True
    assert "run-logs" in out["log_path"]            # output is followable
    assert seen["cmd"][0] == python_executable()
    assert seen["cmd"][1].endswith("scripts/run.py")
    assert "--dry-run" not in seen["cmd"]           # this is the REAL run
    assert seen["start_new_session"] is True        # DETACHED — survives the caller
    assert seen["env"]["PYTHONPATH"] == "src"


def test_start_pipeline_never_captures_output_so_it_cannot_block(tmp_path):
    # capture_output/PIPE would make the caller wait on the pipe — the exact
    # 504 this split exists to kill. Output must go to the log file instead.
    from pipeline.trigger import start_pipeline
    seen = {}
    start_pipeline(spawn=lambda cmd, **kw: seen.update(kw) or object(),
                   log_dir=tmp_path / "run-logs")
    assert "capture_output" not in seen
    assert seen["stdout"] is not None and hasattr(seen["stdout"], "write")
