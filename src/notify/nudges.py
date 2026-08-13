"""Nudge policy: what deserves a push, one digest per run, never twice.

Hard gates: High fit AND a positive sponsor signal. role-excluded is a hard
negative; 'weak' has no sponsor evidence — neither is worth the founder's
attention. Listings are stamped nudged_at only AFTER a successful send, so a
failed push retries next run instead of vanishing.
"""
from __future__ import annotations

POSITIVE_SIGNALS = ("role-confirmed", "company-confirmed", "register-only")

# nudged_at lives on role_listings (not the view) — join for the stamp filter.
#
# The owner predicate is B-GAE-027's fix and takes one bind parameter. Without
# it this selected every owner's eligible rows and the stage then pushed them
# all to whichever profile was created first — and stamped them, so the owner
# they actually belonged to was never nudged for them at all.
ELIGIBLE_SQL = """
select q.role_id, q.company_name, q.fit_rank, q.sponsor_signal, q.role_title,
       q.role_url, q.salary_wall, q.deadline, q.deadline_source
  from v_apply_queue q
  join role_listings r using (role_id)
 where r.nudged_at is null
   and q.owner_id = %s
"""


def select_nudges(rows) -> list:
    return [r for r in rows
            if r["fit_rank"] == "High" and r["sponsor_signal"] in POSITIVE_SIGNALS]


def digest(rows, limit: int = 5, footer: str = "") -> tuple[str, str]:
    title = f"{len(rows)} role{'s' if len(rows) != 1 else ''} ready to apply"
    lines = []
    for r in rows[:limit]:
        line = f"{r['company_name']} — {r['role_title']} [{r['salary_wall']}]"
        if r.get("deadline"):
            est = " est." if r.get("deadline_source") == "estimated" else ""
            line += f" (apply by{est} {r['deadline']})"
        lines.append(line)
    if len(rows) > limit:
        lines.append(f"+{len(rows) - limit} more in the queue")
    if footer:
        lines.append(footer)          # e.g. the Notion applications board link
    return title, "\n".join(lines)


def load_channel(cur, owner_id) -> str | None:
    """One named owner's push channel. Never "whoever came first".

    The owner is required (Phase 9 task 1b) because this is the only read in
    the engine whose answer leaves the building: getting it wrong does not
    return the wrong rows, it fires a push at somebody else's phone.
    """
    cur.execute(
        "select notification_channel from profiles where profile_id = %s",
        (owner_id,))
    row = cur.fetchone()
    return row["notification_channel"] if row else None


def mark_nudged(cur, role_ids: list[int]) -> None:
    cur.execute(
        "update role_listings set nudged_at = now() where role_id = any(%s)",
        (role_ids,))


def nudge_stage(cur, send, *, owner_id, dry_run: bool = False,
                footer: str = "") -> str:
    """The pipeline's final stage, for ONE owner. Returns a run-report summary.

    `owner_id` is keyword-only and required on purpose: this is the one place
    in the engine whose output leaves the building, so getting the owner wrong
    does not return the wrong rows, it fires a push at somebody else's phone.
    A signature that cannot be called without an owner is the guard against
    B-GAE-027 returning — a stage that resolves its own owner eventually
    resolves the wrong one.
    """
    cur.execute(ELIGIBLE_SQL, (owner_id,))
    picks = select_nudges(cur.fetchall())
    if not picks:
        return "nothing new to nudge"
    title, body = digest(picks, footer=footer)
    if dry_run:
        return f"DRY RUN — would nudge {len(picks)}:\n{title}\n{body}"
    channel = load_channel(cur, owner_id)
    if not channel:
        return (f"{len(picks)} ready but no notification channel configured "
                "on the profile")
    if not send(channel, title, body):
        raise RuntimeError("push failed — nudged_at not stamped; will retry next run")
    mark_nudged(cur, [r["role_id"] for r in picks])
    return f"nudged {len(picks)} listing(s)"
