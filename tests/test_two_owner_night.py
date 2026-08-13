"""A two-owner night, end to end through the real orchestration — task 3's
done proof, kept as a test rather than run once and described.

This drives the actual `scripts/run.py` stage table, the actual split, the
actual `personal_stage_cmd`, the actual orchestrator and the actual report
fold. Only the subprocess call is stubbed, so nothing here touches the
network, an API quota, or anybody's phone — but every decision under test is
the one that runs at 06:30.

Three questions, which are the three the founder asked for:
  1. does each owner's personal pass actually run, with their own owner id?
  2. does one owner's failure leave the other owner's night intact?
  3. is a single owner's night still exactly what it was before any of this?
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

from tests.conftest import FakeCursor

ROOT = pathlib.Path(__file__).resolve().parents[1]
OWNER_A = "11111111-1111-4111-a111-111111111111"
OWNER_B = "22222222-2222-4222-a222-222222222222"

WORLD = ["register", "classify", "discover", "fetch", "read", "synonyms",
         "merge", "jd_drip"]
# `nudge` is a closure built in main() against the live connection, so the
# stage table holds six of the seven; the seventh is asserted separately.
PERSONAL_IN_TABLE = ["promote", "salary", "deadlines", "eval",
                     "stage_reading", "file"]


def load_run():
    spec = importlib.util.spec_from_file_location("run_night", ROOT / "scripts" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeCompleted:
    def __init__(self, returncode, stderr):
        self.returncode, self.stderr, self.stdout = returncode, stderr, ""


def drive(monkeypatch, owners, fail_on=()):
    """Run a night for `owners`, failing the given (stage_script, owner) pairs.

    Returns (calls, results) where calls is every argv the night shelled.
    """
    mod = load_run()
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        script = pathlib.Path(cmd[1]).name
        owner = cmd[cmd.index("--owner") + 1] if "--owner" in cmd else None
        if (script, owner) in fail_on:
            return FakeCompleted(1, f"{script} blew up for this owner")
        return FakeCompleted(0, f"{script} ok")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    stages = mod.build_stages(owners)
    return calls, mod, stages


def test_each_owner_gets_their_own_personal_pass_and_the_world_runs_once(monkeypatch):
    from pipeline.orchestrator import run_stages

    calls, _mod, stages = drive(monkeypatch, [OWNER_A, OWNER_B])
    run_stages(stages)

    scripts = [pathlib.Path(c[1]).name for c in calls]
    # World work once, however many owners there are — that is the whole
    # economic argument for the split: the expensive data is shared.
    assert scripts.count("refresh_register.py") == 1
    assert scripts.count("discover_companies.py") == 1
    assert scripts.count("fetch_jobs.py") == 1
    # …and the personal half once per owner, each carrying its own owner.
    for script in ("promote_by_rule.py", "enrich_salary.py", "enrich_deadlines.py",
                   "eval_extraction.py", "stage_reading.py", "file_applications.py"):
        owned = [c for c in calls if pathlib.Path(c[1]).name == script]
        assert len(owned) == 2, f"{script} ran {len(owned)} times for 2 owners"
        assert {c[c.index("--owner") + 1] for c in owned} == {OWNER_A, OWNER_B}, \
            f"{script} did not run for both owners"
    # No world stage was ever handed an owner.
    for call in calls:
        script = pathlib.Path(call[1]).name
        if script in ("refresh_register.py", "discover_companies.py", "fetch_jobs.py",
                      "extract_skills.py", "build_synonyms.py", "merge_ads.py",
                      "jd_drip.py", "classify_sponsors.py"):
            assert "--owner" not in call, f"world stage {script} was scoped to an owner"


def test_one_owners_failure_leaves_the_other_owners_night_intact(monkeypatch):
    from pipeline.orchestrator import failed_stages, run_stages
    from pipeline.report import finish_run

    # Owner A's promote blows up — a malformed rule, say.
    calls, _mod, stages = drive(monkeypatch, [OWNER_A, OWNER_B],
                                fail_on=[("promote_by_rule.py", OWNER_A)])
    results = run_stages(stages)

    by_owner = {}
    for r in results:
        by_owner.setdefault(r.owner, []).append(r)

    # Owner A: the one stage failed, the REST of A's own pass still ran.
    a_failed = [r.name for r in by_owner[OWNER_A] if not r.ok]
    assert a_failed == ["promote"], f"A's night lost more than promote: {a_failed}"
    assert len(by_owner[OWNER_A]) == len(PERSONAL_IN_TABLE)

    # Owner B: untouched. This is the requirement in one line.
    assert all(r.ok for r in by_owner[OWNER_B]), \
        "owner A's failure cost owner B part of their night"
    assert {r.name for r in by_owner[OWNER_B]} == set(PERSONAL_IN_TABLE)

    # World work is unaffected and still reported once.
    assert all(r.ok for r in by_owner[None])

    # The run report stays honest about it: the stage is failed, and the
    # per-owner lines say which owner it failed for.
    assert failed_stages(results) == ["promote"]
    cur = FakeCursor()
    finish_run(cur, 42, results)
    status, blob, _run_id = cur.executed[0][1]
    assert status == "failed"
    promote = [s for s in json.loads(blob) if s["name"] == "promote"][0]
    assert promote["ok"] is False
    assert [o["ok"] for o in promote["owners"]] == [False, True]
    assert "2 owners" in promote["summary"] and "1 failed" in promote["summary"]


def test_a_single_owner_night_is_what_it_was_before_the_split(monkeypatch):
    """The founder's own night. Same stages, same order, same fifteen-element
    report — the loop is simply one iteration long."""
    from pipeline.orchestrator import run_stages
    from pipeline.report import finish_run

    calls, mod, stages = drive(monkeypatch, [OWNER_A])
    results = run_stages(stages)

    # The pinned order, unchanged and unrepeated.
    assert [r.name for r in results] == WORLD + PERSONAL_IN_TABLE
    assert [name for name, _ in mod.STAGE_CMDS] == WORLD + PERSONAL_IN_TABLE
    assert len(calls) == 14                     # + nudge = the pinned 15

    cur = FakeCursor()
    finish_run(cur, 7, results)
    status, blob, _ = cur.executed[0][1]
    stages_json = json.loads(blob)
    assert status == "ok"
    assert len(stages_json) == 14, "the report gained or lost an array element"

    # Every world stage's object is byte-identical to the pre-split shape.
    register = [s for s in stages_json if s["name"] == "register"][0]
    assert set(register) == {"name", "ok", "summary", "duration_s"}
    assert register["summary"] == "refresh_register.py ok"

    # A personal stage keeps all four and gains only the additive owners line,
    # whose single entry repeats that same summary verbatim.
    promote = [s for s in stages_json if s["name"] == "promote"][0]
    assert set(promote) == {"name", "ok", "summary", "duration_s", "owners"}
    assert promote["summary"] == "promote_by_rule.py ok"
    assert promote["owners"] == [{"seq": 1, "ok": True,
                                  "summary": "promote_by_rule.py ok",
                                  "duration_s": promote["duration_s"]}]
    assert OWNER_A not in blob


def test_the_shard_splits_a_two_owner_night_across_two_cloud_run_tasks(monkeypatch):
    # Fan-out shape, proven without fanning anything out: the same code, run
    # as task 0 of 2 and task 1 of 2, covers both owners exactly once between
    # them. Raising the job's taskCount is then a console change, not a patch.
    from pipeline.orchestrator import run_stages
    from pipeline.owners import shard_owners, task_shard

    seen = []
    for index in (0, 1):
        monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", str(index))
        monkeypatch.setenv("CLOUD_RUN_TASK_COUNT", "2")
        idx, count = task_shard()
        mine = shard_owners([OWNER_A, OWNER_B], idx, count)
        calls, _mod, stages = drive(monkeypatch, mine)
        run_stages(stages)          # the stage callables are lazy until run
        owners = {c[c.index("--owner") + 1] for c in calls if "--owner" in c}
        assert len(owners) == 1, f"task {index} claimed {owners}"
        seen.extend(owners)

    assert sorted(seen) == sorted([OWNER_A, OWNER_B]), \
        "two tasks did not cover both owners exactly once"
