"""The per-owner nightly pass — Phase 9 task 3.

World work runs ONCE a night; the personal half loops per owner. Two things
have to be true at the same time and they pull against each other:

  * a second owner's rows must never reach the first owner's phone, Notion
    board or deadlines ([[B-GAE-027]], [[B-GAE-028]]), and
  * for ONE owner the night must be what it was yesterday — same fifteen
    stages, same order, same summaries, and a `pipeline_runs.stages` array the
    public status page still counts as 15.

So most of this file is about the seam between those two: the fold that turns
N owners' results back into fifteen array elements, and the scoping that keeps
each owner's pass inside their own rows.
"""
from __future__ import annotations

import json
import os

import pytest

from tests.conftest import FakeCursor

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

OWNER_A = "11111111-1111-4111-a111-111111111111"
OWNER_B = "22222222-2222-4222-a222-222222222222"

# The pinned nightly order, split where the design says it splits. Written out
# rather than imported so that a change to the source has to change this list
# too — the order is a decision, not an implementation detail.
WORLD = ["register", "classify", "discover", "fetch", "read", "synonyms",
         "merge", "jd_drip"]
PERSONAL = ["promote", "salary", "deadlines", "eval", "stage_reading",
            "file", "nudge"]


# ---- the shard: fan-out shape, not fan-out deployment ---------------------

def test_the_shard_is_the_whole_list_when_nothing_sets_the_cloud_run_vars(monkeypatch):
    # Local and today's single-task Cloud Run job both land here. Defaulting to
    # 0/1 is what lets the same code be serial tonight and parallel later with
    # no edit at all.
    from pipeline.owners import task_shard
    monkeypatch.delenv("CLOUD_RUN_TASK_INDEX", raising=False)
    monkeypatch.delenv("CLOUD_RUN_TASK_COUNT", raising=False)
    assert task_shard() == (0, 1)


def test_the_cloud_run_task_vars_are_read_when_they_are_set(monkeypatch):
    from pipeline.owners import task_shard
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "2")
    monkeypatch.setenv("CLOUD_RUN_TASK_COUNT", "4")
    assert task_shard() == (2, 4)


def test_every_owner_is_claimed_by_exactly_one_task():
    # The property that matters more than any single split: across all tasks,
    # each owner runs once and only once. A modulo that drops or doubles an
    # owner is a missed nudge or a doubled one, and neither is loud.
    from pipeline.owners import shard_owners
    owners = [f"owner-{i}" for i in range(10)]
    for count in (1, 2, 3, 4, 7, 10, 13):
        claimed = [o for i in range(count) for o in shard_owners(owners, i, count)]
        assert sorted(claimed) == sorted(owners), f"count={count} lost or doubled an owner"


def test_the_shard_keeps_the_sorted_order_it_was_given():
    from pipeline.owners import shard_owners
    owners = ["a", "b", "c", "d", "e"]
    assert shard_owners(owners, 0, 2) == ["a", "c", "e"]
    assert shard_owners(owners, 1, 2) == ["b", "d"]


def test_owners_are_listed_sorted_by_profile_id_not_by_creation():
    # Sorted by profile_id, per the design. `order by created_at` is the
    # single-user habit that produced B-GAE-027 and B-GAE-028; a shard has to
    # be stable across runs and across tasks, and creation order is neither
    # once a profile can be deleted.
    from pipeline.owners import list_owner_ids
    cur = FakeCursor(rows=[{"profile_id": OWNER_B}, {"profile_id": OWNER_A}])
    assert list_owner_ids(cur) == [OWNER_A, OWNER_B]
    sql, _ = cur.executed[0]
    assert "order by profile_id" in sql.lower()


# ---- the stage split ------------------------------------------------------

def test_the_pinned_fifteen_stages_split_into_world_then_personal():
    from pipeline.owners import PERSONAL_STAGES
    import importlib.util
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("run_script", root / "scripts" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    names = [name for name, _ in mod.STAGE_CMDS] + ["nudge"]
    assert names == WORLD + PERSONAL, "the pinned stage order moved"
    assert set(PERSONAL_STAGES) == set(PERSONAL)
    # World work runs once: nothing in the world half may be per-owner.
    assert not (set(WORLD) & set(PERSONAL_STAGES))


def test_a_personal_stage_is_handed_the_owner_it_runs_for():
    # The whole point of the split. A stage that discovers its own owner is
    # B-GAE-027; a stage that is given one cannot be.
    from pipeline.owners import personal_stage_cmd
    cmd = personal_stage_cmd(["scripts/promote_by_rule.py", "--limit", "500"], OWNER_A)
    assert cmd == ["scripts/promote_by_rule.py", "--limit", "500", "--owner", OWNER_A]


# ---- the fold: N owners back into fifteen array elements ------------------

def _results(*specs):
    from pipeline.orchestrator import StageResult
    return [StageResult(*s) for s in specs]


def test_the_run_report_holds_one_element_per_stage_name_however_many_owners():
    # v_status_stages counts jsonb_array_elements(stages) and the public page
    # renders it as "N of M stages". Per-owner detail therefore rides as a
    # FIELD on the existing objects; an extra array element would silently
    # turn 15/15 into 29/29 on a page the founder points people at.
    from pipeline.report import finish_run
    cur = FakeCursor()
    finish_run(cur, 7, _results(
        ("register", True, "ok", 1.0, None),
        ("promote", True, "A promoted 2", 2.0, OWNER_A),
        ("promote", True, "B promoted 5", 3.0, OWNER_B),
        ("nudge", True, "nudged 1", 0.5, OWNER_A),
        ("nudge", True, "nudged 4", 0.5, OWNER_B),
    ))
    stages = json.loads(cur.executed[0][1][1])
    assert [s["name"] for s in stages] == ["register", "promote", "nudge"]


def test_a_folded_stage_keeps_every_field_the_old_report_had():
    from pipeline.report import finish_run
    cur = FakeCursor()
    finish_run(cur, 7, _results(("promote", True, "promoted 2", 2.5, OWNER_A)))
    stage = json.loads(cur.executed[0][1][1])[0]
    for field in ("name", "ok", "summary", "duration_s"):
        assert field in stage, f"the run report lost {field}"
    # One owner: the summary is that owner's, verbatim. The founder's own
    # night has to read exactly as it did yesterday.
    assert stage["summary"] == "promoted 2"
    assert stage["duration_s"] == 2.5


def test_a_personal_stage_fails_when_any_one_owner_failed():
    from pipeline.report import finish_run
    cur = FakeCursor()
    finish_run(cur, 7, _results(
        ("promote", True, "ok", 1.0, OWNER_A),
        ("promote", False, "exit 1: boom", 0.2, OWNER_B),
    ))
    stage = json.loads(cur.executed[0][1][1])[0]
    assert stage["ok"] is False, "a stage that failed for one owner reported ok"
    assert cur.executed[0][1][0] == "failed"
    per_owner = {o["seq"]: o["ok"] for o in stage["owners"]}
    assert per_owner == {1: True, 2: False}, "the report hid which owner failed"


def test_the_run_report_never_carries_an_owner_identifier():
    # pipeline_runs is world-readable: every key holder can call
    # get_run_report. A profile_id in there hands out the exact value needed
    # to attempt a cross-owner read, so per-owner lines are numbered, not
    # named. The seq -> owner map lives in the operator's own run log.
    from pipeline.report import finish_run
    cur = FakeCursor()
    finish_run(cur, 7, _results(
        ("nudge", True, "nudged 1", 0.5, OWNER_A),
        ("nudge", True, "nudged 4", 0.5, OWNER_B),
    ))
    blob = cur.executed[0][1][1]
    assert OWNER_A not in blob and OWNER_B not in blob, \
        "an owner uuid reached pipeline_runs.stages"


def test_a_world_stage_gains_no_per_owner_field_at_all():
    from pipeline.report import finish_run
    cur = FakeCursor()
    finish_run(cur, 7, _results(("register", True, "144k rows", 9.0, None)))
    assert "owners" not in json.loads(cur.executed[0][1][1])[0]


def test_a_multi_owner_summary_says_how_many_owners_and_how_many_failed():
    from pipeline.report import finish_run
    cur = FakeCursor()
    finish_run(cur, 7, _results(
        ("nudge", True, "nudged 1", 0.5, OWNER_A),
        ("nudge", False, "push failed", 0.1, OWNER_B),
        ("nudge", True, "nudged 4", 0.4, "33333333-3333-4333-a333-333333333333"),
    ))
    stage = json.loads(cur.executed[0][1][1])[0]
    assert "3 owners" in stage["summary"] and "1 failed" in stage["summary"]
    assert stage["duration_s"] == 1.0                    # summed, not averaged


# ---- failure isolation ----------------------------------------------------

def test_one_owners_failure_does_not_stop_another_owners_pass():
    # The design's hard requirement. Owner A's promote blowing up must not
    # cost owner B their nudge — and must not cost owner A the rest of their
    # own pass either, which is the existing degrade-never-die behaviour.
    from pipeline.orchestrator import run_stages
    ran = []

    def stage(name, owner, boom=False):
        def go():
            if boom:
                raise RuntimeError("exit 1: owner A's rule is malformed")
            ran.append((name, owner))
            return "ok"
        return (name, go, owner)

    results = run_stages([
        stage("promote", OWNER_A, boom=True),
        stage("nudge", OWNER_A),
        stage("promote", OWNER_B),
        stage("nudge", OWNER_B),
    ])
    assert ("nudge", OWNER_B) in ran, "owner A's failure cost owner B their nudge"
    assert ("promote", OWNER_B) in ran
    assert ("nudge", OWNER_A) in ran, "one failure ended owner A's own pass"
    assert [r.ok for r in results] == [False, True, True, True]
    assert results[0].owner == OWNER_A


def test_a_stage_tuple_without_an_owner_still_works():
    # Every existing caller passes 2-tuples. The world half always will.
    from pipeline.orchestrator import run_stages
    results = run_stages([("register", lambda: "144k")])
    assert results[0].owner is None and results[0].ok


# ---- the channel is a secret, in every direction --------------------------

def test_the_nudge_summary_never_carries_the_channel_value():
    # The ntfy topic is a secret that lives only in profiles.notification_channel
    # — anyone holding it can push to the founder's phone. The nudge stage's
    # return value becomes a stage summary in pipeline_runs, which is
    # world-readable, and is also printed to the run log. So the value may
    # never appear in it, in the sending case OR the missing-channel case.
    from notify.nudges import nudge_stage
    secret = "ntfy-topic-that-must-never-be-logged"

    class Cur:
        def __init__(self, channel):
            self.channel, self._rows = channel, []

        def execute(self, sql, params=None):
            low = " ".join(sql.split()).lower()
            self._rows = ([{"notification_channel": self.channel}]
                          if "notification_channel" in low and "update" not in low
                          else [] if "update" in low else
                          [{"role_id": 1, "company_name": "C", "fit_rank": "High",
                            "sponsor_signal": "role-confirmed", "role_title": "R",
                            "role_url": "u", "salary_wall": "ok",
                            "deadline": None, "deadline_source": None}])

        def fetchall(self):
            return list(self._rows)

        def fetchone(self):
            return self._rows[0] if self._rows else None

    sent = nudge_stage(Cur(secret), send=lambda *a: True, owner_id=OWNER_A)
    assert secret not in sent, "the nudge summary leaked the channel value"

    missing = nudge_stage(Cur(None), send=lambda *a: True, owner_id=OWNER_A)
    assert "channel" in missing.lower() and secret not in missing


