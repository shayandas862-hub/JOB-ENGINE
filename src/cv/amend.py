"""M6 — correcting a fact in one audited step, without ever editing one.

Phase 9.5 task 2. The fact base has always been able to hold a correction:
`retire_cv_block` then `add_cv_block`. Keep-all made that the right shape —
the old wording survives, stamped — but it left the correction as two calls a
client had to sequence itself, and the failure mode is ugly and silent. A
client AI retires the stale fact, something goes wrong before the replacement
lands, and the owner's fact base is now missing a line. Nothing is corrupt;
their next CV is simply thinner and nobody knows why.

So the two halves happen against one cursor, in one call, ordered so that
nothing is stamped until the replacement is known to be writable.

What this deliberately is NOT is an UPDATE. `fact_text` is the exact wording
every CV bullet is traced against by `cv.truth`, and the audit trail is only
worth keeping while the words it refers to still exist. Editing in place would
rewrite history: bullets traced last week against the old sentence would, on
inspection, appear to have been traced against words the owner never approved.
The superseded row therefore keeps its text AND its confirmed state — it was a
confirmed fact, and it remains true that it was one — and gains only its
retirement stamp. The replacement is a fresh DRAFT, because an amendment is a
proposal like any other and only the owner confirms.
"""
from __future__ import annotations

from cv.blocks import BLOCK_KINDS

#: The fields an amendment inherits when the caller does not override them.
#: Corrections are usually one-field ("12%" should have been "12.4%"), and
#: making a client resend the rest is how a fact quietly loses its
#: organisation: the caller omits one key and the new row is born poorer than
#: the row it replaced.
_INHERITED = ("kind", "title", "organisation", "date_range", "skill_norms",
              "sort_hint")

_LOAD_SQL = """
select block_id, kind, title, organisation, date_range, fact_text,
       skill_norms, sort_hint
  from cv_blocks
 where block_id = %s and owner_id = %s and retired_at is null
"""

_INSERT_SQL = """
insert into cv_blocks (owner_id, kind, title, organisation, date_range,
                       fact_text, skill_norms, sort_hint, source, amended_from)
values (%s,%s,%s,%s,%s,%s,coalesce(%s::text[],'{}'),%s,%s,%s)
returning block_id
"""

_RETIRE_SQL = """
update cv_blocks set retired_at = now(), updated_at = now()
 where block_id = %s and owner_id = %s and retired_at is null
"""


def amend_cv_block(cur, owner_id: str, block_id: int, *, fact_text: str,
                   kind: str | None = None, title: str | None = None,
                   organisation: str | None = None,
                   date_range: str | None = None, skill_norms=None,
                   sort_hint: int | None = None,
                   source: str | None = None) -> dict:
    """Supersede one fact with a corrected draft, linked to the original.

    Returns {outcome, block_id, retired_block_id, confirmed} — or
    {outcome: 'not_found'} when the block is not this owner's, is already
    retired, or never existed. Those three are one answer on purpose: telling
    a caller which of them applies would confirm the existence of another
    owner's block.
    """
    if not (fact_text or "").strip():
        raise ValueError("fact_text must not be blank")
    if kind is not None and kind not in BLOCK_KINDS:
        raise ValueError(f"kind must be one of {sorted(BLOCK_KINDS)}: {kind!r}")

    cur.execute(_LOAD_SQL, (block_id, owner_id))
    old = cur.fetchone()
    if not old:
        return {"outcome": "not_found", "block_id": None,
                "retired_block_id": None}

    supplied = {"kind": kind, "title": title, "organisation": organisation,
                "date_range": date_range, "skill_norms": skill_norms,
                "sort_hint": sort_hint}
    # None means "keep what the old block said", which is why every override
    # is keyword-only and defaults to None rather than to the empty value.
    fields = {name: (supplied[name] if supplied[name] is not None
                     else old[name])
              for name in _INHERITED}

    # Insert BEFORE the stamp. If the insert fails — a bad kind, a constraint,
    # a dropped connection — the old fact is still serving, which is the safe
    # direction. The reverse order can leave an owner with no fact at all.
    cur.execute(_INSERT_SQL, (
        owner_id, fields["kind"], fields["title"], fields["organisation"],
        fields["date_range"], fact_text.strip(),
        list(fields["skill_norms"]) if fields["skill_norms"] else None,
        fields["sort_hint"], source, block_id))
    new_id = cur.fetchone()["block_id"]

    cur.execute(_RETIRE_SQL, (block_id, owner_id))

    return {"outcome": "amended", "block_id": new_id,
            "retired_block_id": block_id, "confirmed": False}
