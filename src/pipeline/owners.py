"""Who tonight's personal pass runs for — Phase 9 task 3.

The nightly job splits in two. The expensive half is **shared**: the register,
the census, the ads, the boards. One sweep serves everybody and running it
twice would only cost quota. The cheap half is **personal**: a promotion rule,
a salary wall, an apply window, a tray, a CV, a phone. That half has to happen
once per owner, and — the part that made this a task rather than a loop — it
has to happen with each owner's own values, not the first profile's.

Two defects came out of writing this and both are the same shape: a per-owner
value read blind. [[B-GAE-027]] sent one owner's queue to another owner's
phone; [[B-GAE-028]] applied one owner's apply window to everyone's deadlines.
Neither was reachable with one profile in the table, which is exactly why they
survived the task-1b sweep: that sweep scoped the tools a key holder can call,
and the nightly job calls none of them.

**Fan-out shape, not fan-out deployment.** Cloud Run Jobs set
`CLOUD_RUN_TASK_INDEX` and `CLOUD_RUN_TASK_COUNT` on every task. Reading them
here costs nothing tonight — one task, index 0 of 1, so the shard is every
owner and the run is serial exactly as it is today. The day the job's
`taskCount` is raised, the same code splits the owners across tasks with no
edit at all. Writing the loop first and the fan-out later is how a serial
assumption gets baked into the stage scripts instead.
"""
from __future__ import annotations

import os

# The seven stages that belong to one person, in pinned order. Everything
# before `promote` is world work and runs once a night for everybody.
#
# `salary` and `eval` are worth a word, because neither reads a profile: a
# salary parse and a grounding score are the same answer whoever asks. They
# are here because the ROWS are per-owner — role_listings reach an owner
# through target_companies.owner_id — so running them per owner partitions the
# work rather than duplicating it, and each owner's eval gate then reports on
# their own corpus instead of an average that hides them. Measured before
# relying on that seam: 894 companies, 0 with a null owner, and 0 of 12,923
# listings unreachable by it (2026-08-12).
PERSONAL_STAGES = ("promote", "salary", "deadlines", "eval",
                   "stage_reading", "file", "nudge")


def task_shard() -> tuple[int, int]:
    """(index, count) for this Cloud Run task; (0, 1) anywhere else.

    Defaulting to the whole list is what keeps one code path for the laptop,
    tonight's single-task job, and a future fanned-out one.
    """
    def _read(name: str, fallback: int) -> int:
        try:
            value = int(os.environ.get(name, fallback))
        except ValueError:                  # a malformed env var must not
            return fallback                 # silently drop owners
        return value if value > 0 or name.endswith("INDEX") else fallback

    count = max(1, _read("CLOUD_RUN_TASK_COUNT", 1))
    index = max(0, _read("CLOUD_RUN_TASK_INDEX", 0))
    return (index if index < count else 0), count


def list_owner_ids(cur) -> list[str]:
    """Every owner with a profile, sorted by profile_id.

    Sorted by id and not by `created_at`: the shard has to agree across tasks
    that never talk to each other, and creation order stops being stable the
    first time a profile is removed. Sorted in SQL *and* in Python so the
    guarantee holds even if the query is later edited — the whole fan-out is
    built on this order and a silent change to it would double one owner's
    nudge and drop another's.
    """
    cur.execute("select profile_id from profiles order by profile_id")
    return sorted(str(row["profile_id"]) for row in cur.fetchall())


def shard_owners(owner_ids: list[str], index: int, count: int) -> list[str]:
    """The owners this task is responsible for: position % count == index.

    Round-robin rather than contiguous blocks, so an uneven owner count
    spreads evenly instead of loading the last task.
    """
    return [owner for pos, owner in enumerate(owner_ids) if pos % count == index]


def personal_stage_cmd(cmd: list[str], owner_id: str) -> list[str]:
    """A personal stage's argv, with the owner it runs for appended.

    Every personal stage is *given* its owner. That is the guard against
    B-GAE-027 repeating: a stage that cannot discover an owner cannot discover
    the wrong one.
    """
    return [*cmd, "--owner", owner_id]


def owner_window(cur, owner_id, *, default: int = 21) -> int:
    """One named owner's apply window in days — B-GAE-028's fix.

    The old spelling was `select apply_window_days from profiles order by
    created_at limit 1`, open-coded inside the deadlines stage, which is why
    it stayed invisible to every search for `default_profile_id`.
    """
    cur.execute(
        "select apply_window_days from profiles where profile_id = %s",
        (owner_id,))
    row = cur.fetchone()
    return row["apply_window_days"] if row else default
