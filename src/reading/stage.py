"""Stage sieve-1/2 survivors into the reading tray.

A row is stageable when the engine can honestly ask someone to read it:
open, local, a stored JD to ground against, not already AI-read, not
already in the tray, not previously skipped. Two tiers since U7 (the tray
had starved: sieve 2 dropped every title outside the owner's patterns —
0 of 1,083 staged, measured 2026-08-10):

  * 'match'     — the owner's target_roles patterns hit; always staged.
  * 'near_miss' — stageable but title-unmatched; staged CAPPED and served
                  labelled, for the client AI to accept or skip. A skip is
                  a STAMP (reading_skipped_at) — keep-all, never re-staged.

Kill keywords are the owner's explicit no and exclude BOTH tiers. The
salary floor is deliberately NOT applied here, because salary facts are
one of the things reading exists to discover. No AI, no network; runs in
the daily loop.
"""
from __future__ import annotations

from criteria.loader import build_role_matcher, load_criteria

NEAR_MISS_CAP = 25      # per run — a drip the client AI can triage, not a flood

STAGEABLE_SQL = """
select r.role_id, r.role_title
  from role_listings r
  join target_companies c on c.company_id = r.company_id
 where c.owner_id = %s
   and r.role_status = 'open'
   and r.is_local
   and coalesce(r.jd_full, '') <> ''
   and r.read_quality is distinct from 'ai'
   and r.staged_at is null
   and r.reading_skipped_at is null
 order by r.created_at desc, r.role_id
"""


def stage_ready(cur, owner_id, *, near_miss_cap: int = NEAR_MISS_CAP) -> dict:
    """Stamp every stageable row into the tray, tiered.

    Returns {'candidates', 'staged' (matches), 'near_miss'}.
    """
    criteria = load_criteria(cur, owner_id)
    matcher = build_role_matcher(criteria.role_patterns)
    kills = [k.lower() for k in criteria.kill_keywords]

    cur.execute(STAGEABLE_SQL, (owner_id,))
    rows = cur.fetchall()

    def killed(row):
        return any(k in (row["role_title"] or "").lower() for k in kills)

    matched, near = [], []
    for r in rows:
        if killed(r):
            continue
        (matched if matcher(r["role_title"]) else near).append(r["role_id"])
    near = near[:near_miss_cap]

    for tier, ids in (("match", matched), ("near_miss", near)):
        if ids:
            cur.execute(
                "update role_listings set staged_at = now(), staged_tier = %s "
                "where role_id = any(%s)", (tier, ids))
    return {"candidates": len(rows), "staged": len(matched),
            "near_miss": len(near)}


def skip_reading(cur, owner_id, role_id: int) -> dict:
    """The client AI looked at a served row and passed — stamp the skip.

    The stamp is what stops re-staging (keep-all: removal is a stamp, the
    row itself stays). Owner-scoped; honest outcomes for unknown/unstaged."""
    cur.execute(
        "select r.role_id, r.staged_at from role_listings r "
        "join target_companies c on c.company_id = r.company_id "
        "where r.role_id = %s and c.owner_id = %s",
        (role_id, owner_id))
    row = cur.fetchone()
    if row is None:
        return {"outcome": "not_found", "role_id": role_id}
    if row["staged_at"] is None:
        return {"outcome": "not_staged", "role_id": role_id}
    cur.execute(
        "update role_listings set reading_skipped_at = now(), "
        "staged_at = null, claimed_at = null, staged_tier = null "
        "where role_id = %s", (role_id,))
    return {"outcome": "skipped", "role_id": role_id}
