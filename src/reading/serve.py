"""Serve reading batches — the tray's counter window.

The extraction prompt is SERVER-side, versioned DATA: the engine controls
extraction quality and any vendor's model just complies; a client adds no
prompting of its own. Served rows are claimed (claimed_at) so two clients
don't read the same JD; a claim not accepted within CLAIM_MINUTES is
re-served. The enums here are the one reading vocabulary — pinned by test
to match the caged reader's schema without importing it.
"""
from __future__ import annotations

# Bumped to v2 by Phase 9.5 task 6. The salary gate's SUBJECT changed — a
# claim is now checked against the advert's readable text rather than its raw
# markup — and the served prompt told clients the old rule. A prompt that
# describes a gate that no longer exists is worse than no prompt: the client
# writes to the stricter rule, drops a real salary, and nothing reports it.
PROMPT_VERSION = "extract-v2"

# Must stay in lockstep with the caged reader's schema (test-pinned).
SKILL_CATEGORIES = ["programming", "data", "cloud", "ml", "bi", "solutions",
                    "other"]
SPONSOR_VALUES = ["sponsors", "no_sponsor", "unknown"]

EXTRACTION_PROMPT = (
    "You are reading UK job descriptions for a job-search engine. For EACH "
    "job in this batch, extract ONLY what is explicitly stated in its text; "
    "never infer, guess, or pad. Submit one reading per job via "
    "submit_reading(role_id, reading).\n"
    "- skills: concrete technical/professional skills named in the text, "
    f"each tagged with a category from {SKILL_CATEGORIES}. Use the skill's "
    "name EXACTLY as it appears in the text — the engine verifies every "
    "claim verbatim against the stored description and silently drops "
    "anything it cannot find, so canonicalising ('postgres' -> 'PostgreSQL') "
    "loses the skill.\n"
    "- salary_text: the pay exactly as the advert READS it — quote the "
    "figures as a person sees them ('\u00a377,500 \u2014 \u00a390,000'), not the "
    "markup around them. Board adverts keep their HTML, so a range is often "
    "split across tags; the engine strips tags before checking, so the "
    "human-readable form is what grounds. Null if no salary is stated. If "
    "the engine still refuses it, the listing STAYS in your tray with your "
    "claim: correct that one field and submit again, or submit with "
    "salary_text null to finish the reading.\n"
    "- sponsor_hint: 'sponsors' if the text offers UK visa sponsorship; "
    "'no_sponsor' if it requires existing right to work; else 'unknown'.\n"
    "- soc_hint: the closest UK SOC occupation name if obvious, else null.\n"
)

REQUIRED_SHAPE = {
    "skills": [{"name": "string (verbatim from the JD)",
                "category": f"one of {SKILL_CATEGORIES}"}],
    "salary_text": "string (verbatim from the JD) | null",
    "sponsor_hint": f"one of {SPONSOR_VALUES} | null",
    "soc_hint": "string | null",
}

CLAIM_MINUTES = 60

RECLAIM_SQL = """
update role_listings set claimed_at = null
 where staged_at is not null
   and claimed_at is not null
   and claimed_at < now() - make_interval(mins => %s)
"""

BATCH_SQL = """
select r.role_id, r.role_title, r.jd_full, r.staged_tier
  from role_listings r join target_companies c
    on c.company_id = r.company_id
 where c.owner_id = %s
   and r.staged_at is not null
   and r.claimed_at is null
 order by (r.staged_tier = 'near_miss'), r.staged_at
 limit %s
"""

REMAINING_SQL = """
select count(*) as n
  from role_listings r join target_companies c
    on c.company_id = r.company_id
 where c.owner_id = %s and r.staged_at is not null
"""


def get_batch(cur, owner_id, *, limit: int = 10) -> dict:
    """Claim and serve up to `limit` staged rows with the extraction contract.

    Self-describing: prompt + required shape + claim window ride along, so
    the client needs no prompting of its own.
    """
    cur.execute(RECLAIM_SQL, (CLAIM_MINUTES,))
    cur.execute(BATCH_SQL, (owner_id, limit))
    jobs = cur.fetchall()
    if jobs:
        cur.execute(
            "update role_listings set claimed_at = now() "
            "where role_id = any(%s)", ([j["role_id"] for j in jobs],))
    cur.execute(REMAINING_SQL, (owner_id,))
    row = cur.fetchone()
    return {
        "prompt_version": PROMPT_VERSION,
        "prompt": EXTRACTION_PROMPT,
        "required_shape": REQUIRED_SHAPE,
        "claim_minutes": CLAIM_MINUTES,
        "jobs": jobs,
        "staged_total": row["n"] if row else 0,
    }
