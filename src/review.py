"""Read and resolve the review queue — ambiguities the code couldn't decide.

review_items holds things the deterministic engine flagged for a human/Claude to
settle: seeded now from low-confidence skill synonyms, and filled mainly by
Phase 6 discovery. list reads the queue; resolve records a decision and only ever
touches a still-open flag, so resolving twice is a harmless no-op (returns None).
"""
from __future__ import annotations

import json


# A flag is either about a PUBLIC fact — which sponsor a name matches, whether
# two skills are the same skill — or derived from ONE owner's lens. The first
# kind carries owner_id NULL and belongs to everyone: two people settling one
# sponsor ambiguity once is correct, and duplicating that work per user would
# be worse than sharing it. The second kind names its owner, because its
# evidence describes their private search (B-GAE-017).
_SCOPE = "(owner_id is null or owner_id = %s)"


def add_flag(cur, kind: str, ref: str | None, summary: str,
             evidence: dict | None = None, owner_id=None) -> dict | None:
    """Raise one review flag, idempotent by (kind, ref, owner).

    ``owner_id`` is None for a world flag and set for one derived from an
    owner's lens. It is part of the idempotency key, not just the row: keyed
    on (kind, ref) alone, the first owner to flag an organisation would
    silently suppress every other owner's flag for it — the same defect shape
    as a globally-unique dedupe key.

    If a matching item already exists (any status) the insert is skipped and
    None returned, so a daily re-run never spams duplicates. Evidence is
    stored as JSON; callers pass secret-free context only.
    """
    cur.execute(
        "insert into review_items (kind, ref, summary, evidence, owner_id) "
        "select %s, %s, %s, %s, %s "
        "where not exists ("
        "  select 1 from review_items where kind = %s "
        "  and ref is not distinct from %s "
        "  and owner_id is not distinct from %s) "
        "returning review_id, kind, ref, status",
        (kind, ref, summary,
         json.dumps(evidence) if evidence is not None else None, owner_id,
         kind, ref, owner_id))
    return cur.fetchone()


def list_flags(cur, owner_id, status: str = "open",
               limit: int = 50) -> list[dict]:
    """This owner's flags plus the world's, with the given status, oldest first."""
    cur.execute(
        "select review_id, kind, ref, summary, evidence, status, created_at, resolved_at "
        f"from review_items where status = %s and {_SCOPE} "
        "order by created_at limit %s",
        (status, owner_id, limit))
    return cur.fetchall()


def resolve_flag(cur, owner_id, review_id: int, resolution: dict | None = None,
                 dismiss: bool = False) -> dict | None:
    """Resolve (or dismiss) an OPEN flag this owner may act on.

    Returns the updated row, or None if the flag wasn't open **or isn't
    theirs** — the two are deliberately indistinguishable, as everywhere else
    in this codebase. Dismissing another owner's flag would empty a queue they
    are relying on and hold their capped review budget shut.
    """
    status = "dismissed" if dismiss else "resolved"
    cur.execute(
        "update review_items set status=%s, resolution=%s, resolved_at=now() "
        f"where review_id=%s and status='open' and {_SCOPE} "
        "returning review_id, kind, status",
        (status, json.dumps(resolution) if resolution is not None else None,
         review_id, owner_id))
    return cur.fetchone()
