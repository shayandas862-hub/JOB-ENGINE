"""Tests for src/cv/assemble — pure, deterministic block selection for a listing.

No DB, no AI: given a listing's required skill_norms and the owner's cv_blocks,
rank the blocks by skill overlap (stable tie-break on sort_hint then block_id).
Different listings must yield visibly different orders — that's what makes two
CVs from one fact base look different.
"""
from __future__ import annotations


def block(block_id, skills, sort_hint=0, kind="role", fact_text="fact"):
    from cv.blocks import CvBlock
    return CvBlock(block_id=block_id, kind=kind, title=f"B{block_id}",
                   organisation="Org", date_range="2020-2023",
                   fact_text=fact_text, skill_norms=list(skills), sort_hint=sort_hint)


def test_score_block_counts_overlap_with_the_listing():
    from cv.assemble import score_block
    b = block(1, ["python", "sql", "etl"])
    assert score_block(b, {"python", "sql"}) == 2
    assert score_block(b, {"java"}) == 0


def test_rank_orders_by_relevance_then_sort_hint_then_id():
    from cv.assemble import rank_blocks
    blocks = [
        block(1, ["python"], sort_hint=5),          # score 1
        block(2, ["python", "sql"], sort_hint=9),   # score 2 — most relevant
        block(3, [], sort_hint=1),                  # score 0
        block(4, ["sql"], sort_hint=5),             # score 1, ties block 1 on sort_hint
    ]
    ranked = rank_blocks(blocks, {"python", "sql"})
    assert [b.block_id for b, _ in ranked] == [2, 1, 4, 3]
    assert [s for _, s in ranked] == [2, 1, 1, 3 * 0]   # scores: 2,1,1,0


def test_assemble_orders_by_relevance_and_two_listings_differ():
    from cv.assemble import assemble_cv
    blocks = [block(1, ["python", "ml"]), block(2, ["sql", "etl"]), block(3, ["excel"])]
    for_ml = [b.block_id for b in assemble_cv(blocks, {"python", "ml"})]
    for_data = [b.block_id for b in assemble_cv(blocks, {"sql", "etl"})]
    assert for_ml[0] == 1 and for_data[0] == 2      # each listing surfaces its own evidence
    assert for_ml != for_data                        # visibly different CVs from one fact base


def test_min_score_selects_only_matching_blocks():
    from cv.assemble import assemble_cv
    blocks = [block(1, ["python"]), block(2, ["java"]), block(3, ["python", "sql"])]
    picked = assemble_cv(blocks, {"python"}, min_score=1)
    assert {b.block_id for b in picked} == {1, 3}    # the non-matching block is dropped


def test_max_blocks_caps_the_selection():
    from cv.assemble import assemble_cv
    blocks = [block(i, ["python"]) for i in range(1, 6)]
    assert len(assemble_cv(blocks, {"python"}, max_blocks=3)) == 3


def test_matching_is_normalised_and_case_insensitive():
    from cv.assemble import score_block
    b = block(1, ["Machine  Learning", "SQL"])       # odd spacing/case in evidence
    assert score_block(b, {"machine learning"}) == 1  # shared norm() collapses both


def test_no_listing_skills_falls_back_to_sort_hint_order():
    from cv.assemble import assemble_cv
    blocks = [block(1, ["python"], sort_hint=2), block(2, ["sql"], sort_hint=1)]
    assert [b.block_id for b in assemble_cv(blocks, set())] == [2, 1]   # all score 0 -> sort_hint
