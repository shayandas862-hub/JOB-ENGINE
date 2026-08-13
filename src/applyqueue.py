"""Read and act on the ranked apply queue and its adjuncts.

Reads surface engine state for a human or for Claude (via the MCP read tools):
the ranked queue, the skill gaps behind it, and one listing's full record. The
ranking/wall logic itself lives in the SQL views (v_apply_queue, v_skill_gap) —
these functions only read them. The two write helpers act on a single listing
(mark it applied; snooze it out of future nudges).

Everything takes a live cursor and returns plain values, so it is trivially
testable offline with a fake cursor. Read column lists are explicit and curated —
never ``select *`` — so a secret column can never leak into a tool result (the
ATS token lives on target_companies and is never selected here).

Every function takes the owner it is answering for, as a required argument
(Phase 9 task 1b). Not a default: a default owner is correct for user one and
silently wrong for user two, and nothing fails in between. ``role_listings``
has no owner column of its own — deliberately, it is world data about a job —
so listing-level queries reach the owner through ``target_companies.owner_id``,
which is the same seam ``v_apply_queue.owner_id`` is built from. The writes
take that same join rather than trusting a role_id, because a role_id is
guessable and stamping another owner's listing is as damaging as reading it.
"""
from __future__ import annotations

# Curated queue columns: enough to rank, explain a ranking, and judge the wall.
_QUEUE_COLS = (
    "role_id, company_name, fit_rank, sponsor_signal, sponsor_confidence, lane, "
    "salary_wall, wall_basis, role_title, location, salary_text, salary_min, "
    "salary_max, soc_code, role_url, first_seen, age_days, last_changed_at, "
    "deadline, deadline_source"
)

# Curated single-listing columns from role_listings; company_name comes from the
# join. No ats_token, no secret — only what describes the role.
_JOB_COLS = (
    "r.role_id, c.company_name, r.role_title, r.location, r.role_url, "
    "r.salary_text, r.salary_min, r.salary_max, r.soc_code, r.soc_hint, "
    "r.role_status, r.sponsors_this_role, r.date_opened, r.deadline, "
    "r.deadline_source, r.application_status, r.applied_date, r.extracted_at, "
    "r.nudged_at, r.created_at, r.updated_at, r.jd_full"
)


def fetch_queue(cur, owner_id, limit: int = 20) -> list[dict]:
    """Top of one owner's ranked apply queue (fit -> sponsor -> recency)."""
    cur.execute(
        f"select {_QUEUE_COLS} from v_apply_queue "
        "where owner_id = %s limit %s",
        (owner_id, limit),
    )
    return cur.fetchall()


def fetch_skill_gaps(cur, owner_id, limit: int = 20) -> list[dict]:
    """Skills this owner's fit roles ask for that they lack, most-wanted first.

    Both halves of the answer are per-owner since migration 0051: the demand
    comes from THEIR queue, and i_have_it is matched against THEIR my_skills.
    """
    cur.execute(
        "select skill, skill_type, demand, my_level from v_skill_gap "
        "where owner_id = %s and i_have_it = false "
        "order by demand desc limit %s",
        (owner_id, limit),
    )
    return cur.fetchall()


def fetch_job(cur, owner_id, role_id: int) -> dict | None:
    """One of this owner's listings in full (any status), or None.

    None covers both "no such listing" and "not yours" on purpose: telling the
    caller which would confirm that a role_id exists for somebody else.
    """
    cur.execute(
        f"select {_JOB_COLS} from role_listings r "
        "join target_companies c on c.company_id = r.company_id "
        "where r.role_id = %s and c.owner_id = %s",
        (role_id, owner_id),
    )
    return cur.fetchone()


def mark_applied(cur, owner_id, role_id: int) -> str | None:
    """Mark this owner's listing applied (stamps applied_date). Returns its
    title, or None if the id is unknown *or belongs to someone else*. The
    engine never applies for you — this only records that *you* did."""
    cur.execute(
        "update role_listings r set application_status='applied', "
        "applied_date=current_date, updated_at=now() "
        "from target_companies c "
        "where c.company_id = r.company_id "
        "and r.role_id = %s and c.owner_id = %s "
        "returning r.role_title",
        (role_id, owner_id),
    )
    row = cur.fetchone()
    return row["role_title"] if row else None


def snooze_listing(cur, owner_id, role_id: int) -> str | None:
    """Snooze this owner's listing out of future nudge digests by stamping
    nudged_at (the same never-re-nudge marker the nudge stage uses). Returns
    its title, or None if the id is unknown or belongs to someone else."""
    cur.execute(
        "update role_listings r set nudged_at = now() "
        "from target_companies c "
        "where c.company_id = r.company_id "
        "and r.role_id = %s and c.owner_id = %s "
        "returning r.role_title",
        (role_id, owner_id),
    )
    row = cur.fetchone()
    return row["role_title"] if row else None
