"""Tests for src/match/score.py — overlap × rarity scoring with receipts.

The contract these tests pin (phase rule: no naked numbers):
  * score == weight_matched / weight_total, recomputable from the receipts;
  * matched + missing partition the required set exactly;
  * missing is sorted heaviest-first — it IS the "what would close the gap" list;
  * a role with no scorable requirements gets score None, never a fake 0.
Pure functions: no DB, no AI, no network.
"""
from __future__ import annotations

import math

import pytest

from match.score import rarity_weight, score_role


# --- rarity_weight -----------------------------------------------------------

def test_everywhere_skill_weighs_baseline_one():
    # A skill demanded by every role carries no ranking information: weight 1.0.
    assert rarity_weight(100, 100) == pytest.approx(1.0)


def test_rarer_skills_weigh_strictly_more():
    common = rarity_weight(90, 100)
    mid = rarity_weight(10, 100)
    rare = rarity_weight(1, 100)
    assert rare > mid > common >= 1.0


def test_never_seen_skill_weighs_heaviest_for_the_corpus():
    unseen = rarity_weight(0, 100)
    seen_once = rarity_weight(1, 100)
    assert unseen > seen_once


def test_empty_corpus_has_no_opinion_weight_is_one():
    assert rarity_weight(0, 0) == pytest.approx(1.0)


def test_rarity_weight_is_idf_shaped():
    # Pinned formula: 1 + ln((total+1)/(demand+1)) — receipts must be recomputable.
    assert rarity_weight(4, 99) == pytest.approx(1.0 + math.log(100 / 5))


def test_rarity_weight_rejects_impossible_counts():
    with pytest.raises(ValueError):
        rarity_weight(-1, 10)
    with pytest.raises(ValueError):
        rarity_weight(11, 10)
    with pytest.raises(ValueError):
        rarity_weight(0, -5)


# --- score_role --------------------------------------------------------------

def _req(skill, weight):
    return {"skill": skill, "weight": weight}


def test_perfect_match_scores_one_with_empty_missing():
    result = score_role([_req("python", 2.0), _req("sql", 1.0)], ["python", "sql"])
    assert result["score"] == pytest.approx(1.0)
    assert result["missing"] == []
    assert {m["skill"] for m in result["matched"]} == {"python", "sql"}
    assert result["weight_matched"] == pytest.approx(3.0)
    assert result["weight_total"] == pytest.approx(3.0)


def test_no_overlap_scores_zero_with_empty_matched():
    result = score_role([_req("python", 2.0)], ["excel"])
    assert result["score"] == pytest.approx(0.0)
    assert result["matched"] == []
    assert [m["skill"] for m in result["missing"]] == ["python"]


def test_rare_skill_dominates_the_score():
    # Matching only the heavy skill (3.0 of 4.0 total) must score 0.75.
    result = score_role([_req("kubernetes", 3.0), _req("email", 1.0)], ["kubernetes"])
    assert result["score"] == pytest.approx(0.75)


def test_score_is_recomputable_from_its_receipts():
    result = score_role(
        [_req("a", 1.5), _req("b", 2.5), _req("c", 1.0)], ["a", "c"])
    assert result["score"] == pytest.approx(
        result["weight_matched"] / result["weight_total"])
    assert result["weight_matched"] == pytest.approx(
        sum(m["weight"] for m in result["matched"]))
    assert result["weight_total"] == pytest.approx(
        sum(m["weight"] for m in result["matched"] + result["missing"]))
    # matched + missing partition the required set — nothing dropped, nothing added
    assert {m["skill"] for m in result["matched"]} | \
           {m["skill"] for m in result["missing"]} == {"a", "b", "c"}


def test_no_requirements_means_no_score_not_zero():
    result = score_role([], ["python"])
    assert result["score"] is None
    assert result["matched"] == [] and result["missing"] == []
    assert result["weight_total"] == 0.0


def test_all_zero_weights_means_no_score():
    result = score_role([_req("a", 0.0)], ["a"])
    assert result["score"] is None


def test_matching_is_norm_insensitive_but_receipts_echo_input():
    result = score_role([_req("  Python ", 1.0)], ["PYTHON"])
    assert result["score"] == pytest.approx(1.0)
    assert result["matched"][0]["skill"] == "  Python "


def test_duplicate_requirements_collapse_keeping_max_weight():
    result = score_role(
        [_req("python", 1.0), _req("Python", 3.0)], ["python"])
    assert result["weight_total"] == pytest.approx(3.0)
    assert result["score"] == pytest.approx(1.0)
    assert len(result["matched"]) == 1


def test_missing_is_sorted_heaviest_gap_first():
    result = score_role(
        [_req("rare", 3.0), _req("mid", 2.0), _req("common", 1.0),
         _req("also-mid", 2.0)],
        [])
    assert [m["skill"] for m in result["missing"]] == \
        ["rare", "also-mid", "mid", "common"]   # weight desc, ties alphabetical


def test_extra_owned_skills_never_inflate_the_score():
    result = score_role([_req("python", 1.0)], ["python", "sql", "excel"])
    assert result["score"] == pytest.approx(1.0)


def test_negative_weight_is_a_caller_bug():
    with pytest.raises(ValueError):
        score_role([_req("a", -1.0)], [])
