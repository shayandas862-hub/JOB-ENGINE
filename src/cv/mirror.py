"""The mirror — what the system understands about a person, read back.

Phase 9.5 task 1. Everything else in this engine looks outward at the world:
who can sponsor, what they are hiring for, which of those jobs fit. This looks
the other way, at the owner, and says what it has understood — with the
evidence, including the parts that are missing.

**Nothing here is stored.** The facts are stored; the understanding is
re-formed from them on every read. A stored summary is a snapshot of a person
taken once and then quietly kept as if it were still true, and the first thing
it does is drift: the owner adds five facts and the machine goes on describing
who they were in August. Re-deriving costs two queries against a few dozen
rows, which is nothing, and it cannot be wrong about the present.

The number this exists for is not the flattering one. Counting facts and
skills is easy and tells the owner what they already know. The useful number
is how much of what they claim the machine **cannot prove** — because
`cv.truth`'s gate traces every CV line back to a confirmed `cv_blocks` fact,
so an unevidenced skill is one the CV will silently decline to mention. Better
to hear it here, with the skill named, than to notice the absence in a
finished document. Measured on the founder's own fact base the day this was
written: 21 live skills, 4 evidenced, 17 not.

Same rule as everywhere else in this project: no naked numbers. Every count
below ships the rows it was counted from.
"""
from __future__ import annotations

# A block only evidences a skill when it is CONFIRMED and not retired — the
# same test `cv.blocks.load_cv_blocks` applies when it builds a CV. If the
# mirror were more generous than the truth gate, it would promise lines that
# `cv.generate` then refused to write, which is a worse failure than silence.
BLOCKS_SQL = """
select block_id, kind, confirmed, retired_at, skill_norms, organisation
  from cv_blocks
 where owner_id = %s
"""

# 'dormant' is deliberately not live, matching every gap query in the codebase
# (applyqueue.fetch_skill_gaps, analysis.job_gap, analysis.search).
SKILLS_SQL = """
select skill, skill_norm, level, evidence, learned_at, status
  from my_skills
 where owner_id = %s
"""

LIVE_STATUSES = ("active", "in_progress")

#: Paid work. Every other kind of block is evidence from somewhere else, and
#: for someone whose paid history in this country is thin, that is most of what
#: they have — the product exists for exactly that person, so the split is
#: worth naming rather than burying in a total.
PAID_WORK_KIND = "role"


def build_mirror(cur, owner_id: str) -> dict:
    """Re-form what is understood about one owner. Reads only; writes nothing."""
    cur.execute(BLOCKS_SQL, (owner_id,))
    blocks = list(cur.fetchall())
    cur.execute(SKILLS_SQL, (owner_id,))
    skills = list(cur.fetchall())

    facts = _fold_facts(blocks)
    evidence = _evidence_by_skill_norm(blocks)
    provable, unprovable = _split_skills(skills, evidence)

    live = len(provable) + len(unprovable)
    evidenced = len(provable)
    outside = sum(1 for s in provable if s["outside_paid_work"])

    return {
        "facts": facts,
        "skills": {
            "live": live,
            "active": sum(1 for s in skills if s["status"] == "active"),
            "in_progress": sum(1 for s in skills if s["status"] == "in_progress"),
            "dormant": sum(1 for s in skills
                           if s["status"] not in LIVE_STATUSES),
            "evidenced": evidenced,
            "unevidenced": live - evidenced,
            "evidenced_outside_paid_work": outside,
        },
        # The receipts. `unprovable` is the one that does work: it names the
        # skills a CV cannot claim, so the owner can go and add the fact.
        "provable": provable,
        "unprovable": unprovable,
        # None, never 0 — an owner with no skills recorded has no coverage to
        # report, and 0% would read as a judgement on someone the machine has
        # simply not met yet. (match.score and discover.census_queries take the
        # same line for the same reason.)
        "coverage": (evidenced / live) if live else None,
        "headline": (f"{facts['confirmed']} facts · {live} skills · "
                     f"{outside} evidenced outside paid work"),
    }


def _fold_facts(blocks) -> dict:
    """Counts by state, and by kind over the blocks that actually serve."""
    live = [b for b in blocks if b["retired_at"] is None]
    serving = [b for b in live if b["confirmed"]]
    by_kind: dict[str, int] = {}
    for block in serving:
        by_kind[block["kind"]] = by_kind.get(block["kind"], 0) + 1
    return {
        "confirmed": len(serving),
        "drafts": len(live) - len(serving),
        "retired": len(blocks) - len(live),
        "by_kind": by_kind,
        "organisations": len({b["organisation"] for b in serving
                              if (b["organisation"] or "").strip()}),
    }


def _evidence_by_skill_norm(blocks) -> dict[str, list[dict]]:
    """skill_norm -> the serving blocks that evidence it."""
    found: dict[str, list[dict]] = {}
    for block in blocks:
        if block["retired_at"] is not None or not block["confirmed"]:
            continue
        for norm in (block["skill_norms"] or []):
            found.setdefault(norm, []).append(block)
    return found


def _split_skills(skills, evidence) -> tuple[list[dict], list[dict]]:
    """Live skills, in two piles: what can be proven and what cannot."""
    provable: list[dict] = []
    unprovable: list[dict] = []
    for skill in skills:
        if skill["status"] not in LIVE_STATUSES:
            continue
        blocks = evidence.get(skill["skill_norm"], [])
        if not blocks:
            unprovable.append({
                "skill": skill["skill"],
                "level": skill["level"],
                # Its own stated evidence, if the owner gave one. It is a
                # sentence in a text column, not a traced fact — which is
                # exactly why the skill still counts as unprovable.
                "claimed_evidence": skill["evidence"],
                "learned_at": skill["learned_at"],
            })
            continue
        provable.append({
            "skill": skill["skill"],
            "level": skill["level"],
            "evidenced_by": sorted(b["block_id"] for b in blocks),
            # A skill proven by a job is proven by the job. Only a skill with
            # NO paid-work evidence counts as evidenced outside it — otherwise
            # the honest number would be inflated by the ordinary case.
            "outside_paid_work": all(b["kind"] != PAID_WORK_KIND for b in blocks),
            "learned_at": skill["learned_at"],
        })
    return provable, unprovable
