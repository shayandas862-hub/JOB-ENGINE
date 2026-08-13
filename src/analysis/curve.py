"""Skills the owner is closest to closing — ranked by effort, not by demand.

Phase 9.5 task 4. This was briefed as a model over `my_skills.learned_at`,
because the card said that column had been "collecting since 2026-08-10" with
"weeks of data". It had not: measured before a line was written, **22 skills,
0 with `learned_at`**, every row six weeks older than the column
([[B-GAE-046]]). A ranking sorted on it would have returned an empty list
forever, from code that runs cleanly.

Rebuilding the question on data that exists turns out to sharpen it. "Closest
to closing" is a claim about EFFORT, and recency was only ever a proxy for
effort. The direct measure is the distance between what roles ask for, what
the owner has, and what a confirmed fact can prove:

    prove it   the owner HAS it and roles ask for it, but no confirmed fact
               evidences it — so `cv.truth`'s gate will not let a CV claim it.
               Closing this costs ONE SENTENCE. Nine of these on the founder's
               own base the day it shipped, and nothing had ever said so.
    finish it  already in progress, and roles are asking. Weeks.
    learn it   in demand, not held at all. Months.

Ordering is tier first and demand second, which is the whole argument: a skill
fifty-five roles ask for that would take months is NOT closer to closing than
one three roles ask for that needs a sentence. Sorting on demand alone — the
obvious implementation — says the opposite, confidently.

Rows-first, no engine AI, and every row carries the numbers its tier was
computed from.
"""
from __future__ import annotations

#: Effort ladder, cheapest first. The index IS the sort key.
TIERS = ("prove it", "finish it", "learn it")

#: Below this many rows carrying `learned_at`, recency is not a signal — it is
#: a mostly-NULL column, and sorting on one silently ranks the rows that
#: happen to have data above the rows that do not. The number is a judgement,
#: stated here rather than buried: a fifth of a small skill set, at least
#: five rows.
_RECENCY_MINIMUM = 5

_DEMAND_SQL = """
select skill_norm, skill, demand
  from v_skill_demand
 where owner_id = %s and demand > 0
"""

_HELD_SQL = """
select skill_norm, skill, status, level, learned_at
  from my_skills
 where owner_id = %s
"""

_PROVEN_SQL = """
select distinct unnest(skill_norms) as skill_norm
  from cv_blocks
 where owner_id = %s and confirmed and retired_at is null
"""

_LIVE = ("active", "in_progress")


def closest_to_closing(cur, owner_id: str, *, limit: int = 10) -> dict:
    """Rank the owner's open skills by how little it would take to close them."""
    cur.execute(_DEMAND_SQL, (owner_id,))
    demand = list(cur.fetchall())
    cur.execute(_HELD_SQL, (owner_id,))
    skills = list(cur.fetchall())
    cur.execute(_PROVEN_SQL, (owner_id,))
    proven = {r["skill_norm"] for r in cur.fetchall()}

    held = {s["skill_norm"]: s for s in skills if s["status"] in _LIVE}
    with_recency = sum(1 for s in skills if s["learned_at"] is not None)

    ranked, already_closed = [], 0
    for row in demand:
        norm = row["skill_norm"]
        mine = held.get(norm)
        is_proven = norm in proven

        if mine is not None and is_proven:
            # Held and evidenced: a CV can already claim it. Nothing to close.
            already_closed += 1
            continue

        if mine is None:
            tier, why = TIERS[2], "not recorded among your skills"
        elif mine["status"] == "in_progress":
            # Deliberately not "prove it": asking someone to evidence a skill
            # they are still learning invites a claim the truth gate would
            # refuse and the interview forbids.
            tier, why = TIERS[1], "in progress — finish it, then record what it proves"
        else:
            tier, why = TIERS[0], ("you have it, but no confirmed fact proves "
                                   "it — a CV cannot claim it yet")

        ranked.append({
            "skill": row["skill"] or (mine or {}).get("skill") or norm,
            "skill_norm": norm,
            "tier": tier,
            "demand": row["demand"],
            "held": mine is not None,
            "proven": is_proven,
            "level": (mine or {}).get("level"),
            "learned_at": (mine or {}).get("learned_at"),
            "why": why,
        })

    # Tier first, demand second. Never demand alone — see the module docstring.
    ranked.sort(key=lambda r: (TIERS.index(r["tier"]), -r["demand"], r["skill"]))
    shown = ranked[:limit]

    return {
        "ranking": shown,
        "basis": {
            "skills_in_demand": len(demand),
            "skills_held": len(held),
            "already_closed": already_closed,
            "ranked": len(shown),
            # Never a silent cap: a top-10 presented without this reads as
            # "these are the only ones", and 902 skills are in demand on the
            # real base.
            "not_shown": max(0, len(ranked) - len(shown)),
            # B-GAE-046 rides in every answer: the column the brief believed
            # was full reports its real population, so an absence can never
            # again be mistaken for a ranking.
            "learned_at_known": with_recency,
            "ranks_on_recency": with_recency >= _RECENCY_MINIMUM,
        },
    }
