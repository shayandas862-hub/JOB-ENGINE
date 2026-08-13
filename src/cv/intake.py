"""The served intake interview — intake-v1 (Phase 9 task 4 / M1).

Building a NEW owner's fact base used to be the one unversioned step in the
whole product: reading had extract-v1 and the CV had cv-v1, but whichever AI
a user brought wrote its own interview questions, so the quality of the fact
base — the thing every future CV is traced against — depended on the client.
This module closes that gap the same way the other two did: the prompt is
SERVER-side, versioned DATA. The engine controls interview quality and any
vendor's model just complies.

The interview writes through the U8b writer quartet, which already enforces
the power split: add_cv_block always writes a draft, and only the owner's
approval — never the interviewer's judgement — confirms a fact.
"""
from __future__ import annotations

from cv.blocks import BLOCK_KINDS

# Bumped to v2 by Phase 9.5 task 3 (M7), deliberately rather than editing v1
# in place. The instructions materially changed — one call now records a fact
# and its skills together, where v1 asked for two independent calls — and a
# client that reads "intake-v1" is entitled to the behaviour v1 described.
# The version exists precisely so a prompt cannot change underneath its label.
PROMPT_VERSION = "intake-v2"

INTERVIEW_PROMPT = (
    "You are interviewing the owner to build their career fact base — the "
    "verified facts every future CV will be written from. Ask, listen, "
    "record; the standard is a referee's, not a salesman's.\n"
    "- Walk their life area by area (the coverage list rides with this "
    "prompt): education, every role with its dates, the concrete "
    "achievements inside each role, the tools they actually used, and what "
    "they built or ran outside paid work — unpaid experience carries "
    "transferable evidence on exactly the same footing.\n"
    "- ONE FACT PER BLOCK. Each fact_text is one complete, standalone "
    "sentence in the owner's own true words — it is the exact text every "
    "CV bullet will later be traced against, so a vague fact serves "
    "nobody.\n"
    "- Ask for the dates and the numbers ('led a team of 6', '2022-2024', "
    "'cut waste 12%'). A fact with its numbers is evidence; without them "
    "it is a claim. If the owner is unsure of a number, record the fact "
    "without one — never estimate on their behalf.\n"
    "- Honest tool levels only: record what the owner actually did with a "
    "tool, never a level they aspire to. 'Used daily for two years' beats "
    "'expert'.\n"
    "- Never invent, round up, or improve a fact.\n"
    "- Name credits exactly: certifications, awards and publications go in "
    "with their real names and dates.\n"
    "- Write every experience via record_experience — the fact AND the "
    "skills it evidences in ONE call, so the two are linked. It is always "
    "a DRAFT. Never confirm a block on your own judgement: show the owner "
    "the exact wording via list_cv_blocks, and only after they approve it "
    "call confirm_cv_block.\n"
    "- Name the skills on the SAME call as the fact that proves them, each "
    "with where it was learned (learned_at) and the concrete evidence. A "
    "skill recorded apart from its fact is one a CV can never claim: the "
    "truth gate has nothing to trace it to, so it is silently dropped.\n"
    "- Correcting something already recorded is amend_cv_block, not a new "
    "fact — it supersedes the old wording in one audited step and keeps "
    "the original readable.\n"
    "Stop when the coverage list is walked end to end; a thin fact base "
    "produces thin CVs forever.\n"
)

# What the interview must reach before it is done — served alongside the
# prompt so a client can show the owner where they are.
COVERAGE = [
    "education, with institutions and dates",
    "every role: title, organisation, date range",
    "concrete achievements per role, each with its numbers",
    "tools and skills actually used, at honest levels",
    "projects and responsibilities outside paid work",
    "credits: certifications, awards, publications — named exactly",
]

# The interview's shape IS the writer quartet's signature — test-pinned in
# lockstep with cv.blocks.BLOCK_KINDS so the two can never drift apart.
REQUIRED_SHAPE = {
    "facts": {
        "kind": f"one of {sorted(BLOCK_KINDS)}",
        "fact_text": ("ONE complete, verifiable sentence — the exact words "
                      "every CV bullet will be traced against"),
        "title": "string | null (e.g. the role title)",
        "organisation": "string | null",
        "date_range": "string | null, as the owner states it",
        "skill_norms": "lowercase names of the skills this fact evidences",
    },
    "skills": {
        "name": "the skill, as the owner names it",
        "learned_at": "where or when it was learned",
        "evidence": "the concrete thing that proves it",
        # v2: the skills ride ON the fact's own call rather than being sent
        # separately, which is the whole point of the change. Stated here as
        # well as in the prompt because a client that reads only the shape
        # would otherwise reconstruct exactly the split that caused the drift.
        "_sent": "inside record_experience's `skills`, never as a separate call",
    },
}

COUNTS_SQL = """
select count(*) as blocks,
       count(*) filter (where confirmed) as confirmed
  from cv_blocks
 where owner_id = %s and retired_at is null
"""


def get_interview(cur, owner_id) -> dict:
    """Serve the versioned interview plus the fact base's current state.

    Self-describing like reading's get_batch: prompt, required shape and
    coverage ride along, so the client needs no prompting of its own. The
    state counts let an interviewer distinguish a fresh intake from a
    top-up, and let it see how many drafts await the owner's word.
    """
    cur.execute(COUNTS_SQL, (owner_id,))
    row = cur.fetchone() or {"blocks": 0, "confirmed": 0}
    blocks, confirmed = row["blocks"], row["confirmed"]
    return {
        "prompt_version": PROMPT_VERSION,
        "prompt": INTERVIEW_PROMPT,
        "required_shape": REQUIRED_SHAPE,
        "coverage": COVERAGE,
        "fact_base": {"blocks": blocks, "confirmed": confirmed,
                      "drafts": blocks - confirmed},
    }
