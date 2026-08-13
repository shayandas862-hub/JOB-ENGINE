"""M7 — one life experience, written to the fact base AND the gap model.

Phase 9.5 task 3. Two doors already existed: `add_cv_block` records what the
owner did, `add_skill` records what they can do. Nothing joined them, and
`intake-v1` has told clients to call both since Phase 9 — so the cheap option,
"let the prompt instruct it", is not a proposal here. It shipped, and this is
what a year of it produced on the founder's own base, measured while building
the mirror:

    21 live skills · 4 evidenced · 17 with no fact behind them
    6 role blocks evidencing "teamwork", "call handling", "cinematography" —
    not one of which matches a my_skills row

Every one of those norms is correctly normalised, so this was never a
normalisation bug. It is drift: the sessions that recorded career facts and
the sessions that recorded skills chose different words, months apart, and
nothing required them to agree. A sentence in a prompt cannot make two
independent writes agree on a vocabulary — only a single write can.

So this is that single write, and its one real property is that the two sides
join **by construction**. The block's `skill_norms` are the values `add_skill`
hands back, and those come from `normalise.text.norm`, the one normaliser
whose equivalence to `my_skills.skill_norm`'s generated expression is already
asserted by a database test. Nothing here normalises anything. If a second
normalisation ever appears in this file, the drift it was written to end comes
straight back, wearing the fix's clothes.

The fact is still a DRAFT, and the owner still confirms it. This changes how
many calls a correction takes, never who decides.
"""
from __future__ import annotations

from criteria.writer import add_skill as _add_skill
from cv.blocks import BLOCK_KINDS
from cv.blocks import add_cv_block as _add_cv_block


def _skill_payload(skill) -> dict:
    """Accept "Python" or {"name": "Python", "evidence": ...}.

    The interview often has a name and nothing else; refusing that shape would
    push a client back to calling `add_skill` separately, which is the exact
    behaviour this module exists to end.
    """
    if isinstance(skill, str):
        return {"name": skill}
    if not isinstance(skill, dict):
        raise ValueError(f"a skill must be a name or a mapping: {skill!r}")
    if not (skill.get("name") or "").strip():
        raise ValueError(f"a skill needs a name: {skill!r}")
    return skill


def record_experience(cur, owner_id: str, *, kind: str, fact_text: str,
                      skills=(), title: str | None = None,
                      organisation: str | None = None,
                      date_range: str | None = None, sort_hint: int = 0,
                      source: str | None = None,
                      add_skill=_add_skill, add_block=_add_cv_block) -> dict:
    """Write one experience as a fact plus the skills it evidences.

    Returns {block_id, confirmed, skills: [{skill, skill_norm, outcome}]}.
    The injected writers exist so the ordering and the joining can be tested
    without a database; production never passes them.
    """
    # Everything that can be refused is refused BEFORE anything is written.
    # The skills are written first (the block has to cite their norms), so a
    # payload that failed halfway would leave skills claimed with no fact
    # behind them — manufacturing precisely the state the mirror exists to
    # complain about.
    if kind not in BLOCK_KINDS:
        raise ValueError(f"kind must be one of {sorted(BLOCK_KINDS)}: {kind!r}")
    if not (fact_text or "").strip():
        raise ValueError("fact_text must not be blank")
    payloads = [_skill_payload(s) for s in skills]

    written = []
    for skill in payloads:
        written.append(add_skill(
            cur, owner_id, skill["name"],
            level=skill.get("level"), evidence=skill.get("evidence"),
            learned_at=skill.get("learned_at"),
            category=skill.get("category"), source=source))

    block = add_block(
        cur, owner_id, kind=kind, fact_text=fact_text, title=title,
        organisation=organisation, date_range=date_range,
        # NOT recomputed here — see the module docstring. These are the norms
        # the skill writer just used, so the join cannot miss.
        skill_norms=[s["skill_norm"] for s in written],
        sort_hint=sort_hint, source=source)

    return {"block_id": block["block_id"], "confirmed": block["confirmed"],
            "skills": written}
