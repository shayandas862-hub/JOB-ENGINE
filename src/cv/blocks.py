"""The CV maker's fact base: load verified career facts; write drafts (U8b).

The read side returns only *confirmed*, never-retired blocks by default —
the CV is built from verified facts alone, and the truth gate traces every
output line back to one of these fact_text values. The write side (U8b,
founder's 2026-08-10 amendment) is the "propose, don't decide" door:
add_cv_block always writes a DRAFT (confirmed=false — a client AI proposes,
only the owner confirms), confirm/retire are owner-scoped stamps, and
retiring keeps the row (keep-all: removals are stamps).
"""
from __future__ import annotations

from dataclasses import dataclass

_COLUMNS = ("block_id, kind, title, organisation, date_range, fact_text, "
           "skill_norms, sort_hint")

# The render sections' kinds (cv.render.SECTION_ORDER) — the writer's whitelist.
BLOCK_KINDS = frozenset({"role", "achievement", "skill_evidence", "education"})


@dataclass(frozen=True)
class CvBlock:
    block_id: int
    kind: str                    # 'role' | 'achievement' | 'skill_evidence' | 'education'
    title: str | None
    organisation: str | None
    date_range: str | None
    fact_text: str               # the verified statement — the grounding source
    skill_norms: list[str]       # normalised skills this block evidences
    sort_hint: int


def load_cv_blocks(cur, owner_id: str, *, kinds=None,
                   confirmed_only: bool = True) -> list[CvBlock]:
    """One owner's career-fact blocks, ordered by sort_hint then block_id.

    Only confirmed (human-verified) blocks by default — pass confirmed_only=False
    to include drafts. Optionally restrict to certain kinds.
    """
    where = ["owner_id = %s", "retired_at is null"]
    params: list = [owner_id]
    if confirmed_only:
        where.append("confirmed")
    if kinds is not None:
        where.append("kind = any(%s)")
        params.append(list(kinds))

    cur.execute(
        f"select {_COLUMNS} from cv_blocks where " + " and ".join(where) +
        " order by sort_hint, block_id",
        tuple(params))
    return [
        CvBlock(
            block_id=r["block_id"], kind=r["kind"], title=r["title"],
            organisation=r["organisation"], date_range=r["date_range"],
            fact_text=r["fact_text"], skill_norms=list(r["skill_norms"] or []),
            sort_hint=r["sort_hint"],
        )
        for r in cur.fetchall()
    ]


def list_cv_blocks(cur, owner_id: str) -> list[dict]:
    """Both states, retired excluded — so a client can show drafts for the
    owner to approve. Plain dicts (confirmed rides along)."""
    cur.execute(
        f"select {_COLUMNS}, confirmed, retired_at from cv_blocks "
        "where owner_id = %s and retired_at is null "
        "order by sort_hint, block_id", (owner_id,))
    return cur.fetchall()


def add_cv_block(cur, owner_id: str, *, kind: str, fact_text: str,
                 title: str | None = None, organisation: str | None = None,
                 date_range: str | None = None, skill_norms=None,
                 sort_hint: int = 0, source: str | None = None) -> dict:
    """Write one fact as a DRAFT (confirmed=false, always).

    A client AI proposes; only the owner confirms — the reading tray's
    "propose, don't decide", applied to the fact base. The confirmed-only
    CV path can never see an unapproved draft."""
    if kind not in BLOCK_KINDS:
        raise ValueError(f"kind must be one of {sorted(BLOCK_KINDS)}: {kind!r}")
    if not (fact_text or "").strip():
        raise ValueError("fact_text must not be blank")
    cur.execute(
        "insert into cv_blocks (owner_id, kind, title, organisation, "
        "date_range, fact_text, skill_norms, sort_hint, source) "
        # ::text[] is load-bearing (B-GAE-014): without it Postgres types the
        # whole coalesce as text against the untyped '{}' literal and EVERY
        # insert fails at parse time, skills or no skills.
        "values (%s,%s,%s,%s,%s,%s,coalesce(%s::text[],'{}'),%s,%s) "
        "returning block_id",
        (owner_id, kind, title, organisation, date_range, fact_text.strip(),
         list(skill_norms) if skill_norms else None, sort_hint, source))
    return {"block_id": cur.fetchone()["block_id"], "confirmed": False}


def confirm_cv_block(cur, owner_id: str, block_id: int) -> dict:
    """The owner's yes — the draft becomes a fact the CV path may serve."""
    cur.execute(
        "update cv_blocks set confirmed = true, updated_at = now() "
        "where block_id = %s and owner_id = %s and retired_at is null",
        (block_id, owner_id))
    outcome = "confirmed" if cur.rowcount else "not_found"
    return {"block_id": block_id, "outcome": outcome}


def retire_cv_block(cur, owner_id: str, block_id: int) -> dict:
    """A stamp, never a delete — the block stops serving, the row stays."""
    cur.execute(
        "update cv_blocks set retired_at = now(), updated_at = now() "
        "where block_id = %s and owner_id = %s and retired_at is null",
        (block_id, owner_id))
    outcome = "retired" if cur.rowcount else "not_found"
    return {"block_id": block_id, "outcome": outcome}
