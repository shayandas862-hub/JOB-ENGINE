"""Select and order a profile's cv_blocks for one listing — pure, deterministic.

Given the listing's required skill_norms and the owner's confirmed blocks, rank
each block by how many of its evidenced skills the listing asks for. Ties break
on sort_hint then block_id, so the order is stable and reproducible — the same
listing always yields the same CV, and two different listings surface different
evidence (that's what makes two CVs from one fact base look different). No DB,
no AI here; the caller loads the blocks and the listing's skills.
"""
from __future__ import annotations

from normalise.text import norm

from cv.blocks import CvBlock


def _norm_set(skills) -> set[str]:
    """Normalise a skill collection with the shared norm(); drop blanks."""
    return {norm(s) for s in (skills or ()) if s and s.strip()}


def score_block(block: CvBlock, listing_skills) -> int:
    """How many of the listing's skills this block evidences (overlap count)."""
    listing = listing_skills if isinstance(listing_skills, set) else _norm_set(listing_skills)
    return len(_norm_set(block.skill_norms) & listing)


def rank_blocks(blocks, listing_skills) -> list[tuple[CvBlock, int]]:
    """(block, score) pairs, most relevant first; stable on sort_hint then id."""
    listing = _norm_set(listing_skills)
    scored = [(b, score_block(b, listing)) for b in blocks]
    scored.sort(key=lambda pair: (-pair[1], pair[0].sort_hint, pair[0].block_id))
    return scored


def assemble_cv(blocks, listing_skills, *, min_score: int = 0,
                max_blocks: int | None = None) -> list[CvBlock]:
    """The ordered block selection for a listing.

    ``min_score`` filters out blocks below that overlap (use 1 to keep only
    blocks that match the listing); ``max_blocks`` caps the count. Defaults keep
    every block, ordered by relevance.
    """
    ranked = [b for b, score in rank_blocks(blocks, listing_skills) if score >= min_score]
    return ranked[:max_blocks] if max_blocks is not None else ranked
