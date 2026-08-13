"""Tests for src/match/prob.py — name-match + same-job probability.

Pins the decision-log tricky pairs (2026-07-14 boundary): Monzo-class brand
prefixes must land BETWEEN suffix-stripped certainty and token-soup junk, so
the uncertain pile sorts real matches to the top. Every probability ships its
receipts: p is recomputable from base_p + the factor shifts.
"""
from __future__ import annotations

import math

import pytest

from match.prob import name_match_probability, same_job_probability


def _logit(p):
    return math.log(p / (1 - p))


def _sigmoid(x):
    return 1 / (1 + math.exp(-x))


# --- name relation ladder ----------------------------------------------------

def test_exact_norm_match_is_near_certain():
    r = name_match_probability("Sky UK Ltd", "sky uk ltd")
    assert r["method"] == "exact"
    assert r["p"] >= 0.98


def test_suffix_stripped_match_is_high():
    r = name_match_probability("Acme AI", "Acme AI Ltd")
    assert r["method"] == "suffix_stripped"
    assert 0.9 <= r["p"] < 0.99


def test_monzo_class_brand_prefix_is_orderable_middle_ground():
    # The register says 'Monzo Bank Ltd'; the ad says 'Monzo'. Not provable by
    # suffix-stripping — but far likelier than junk. Must sort above overlap noise.
    r = name_match_probability("Monzo", "Monzo Bank Ltd")
    assert r["method"] == "brand_prefix"
    assert 0.5 < r["p"] < 0.9


@pytest.mark.parametrize("ad_name,register_name", [
    ("Thought Machine", "Thought Machine Group Limited"),
    ("Improbable", "Improbable Worlds Ltd"),
    ("Wayve", "Wayve Technologies Ltd"),
])
def test_decision_log_tricky_pairs_all_rank_as_brand_prefix(ad_name, register_name):
    r = name_match_probability(ad_name, register_name)
    assert r["method"] == "brand_prefix"
    assert r["p"] > 0.5


def test_shared_generic_token_is_not_a_brand_prefix():
    # 'Monzo Bank' vs 'Deutsche Bank AG' share only the word 'bank'.
    monzo = name_match_probability("Monzo", "Monzo Bank Ltd")
    junk = name_match_probability("Monzo Bank", "Deutsche Bank AG")
    assert junk["method"] == "token_overlap"
    assert junk["p"] < monzo["p"]


def test_no_shared_tokens_is_a_confident_negative():
    r = name_match_probability("Monzo", "Greggs PLC")
    assert r["method"] == "no_match"
    assert r["p"] <= 0.02


def test_the_evidence_ladder_is_strictly_ordered():
    exact = name_match_probability("Acme AI Ltd", "Acme AI Ltd")["p"]
    stripped = name_match_probability("Acme AI", "Acme AI Ltd")["p"]
    prefix = name_match_probability("Acme", "Acme AI Ltd")["p"]
    nothing = name_match_probability("Zebra", "Acme AI Ltd")["p"]
    assert exact > stripped > prefix > nothing


def test_empty_names_carry_no_evidence():
    r = name_match_probability("", "Acme Ltd")
    assert r["method"] == "empty"
    assert r["p"] <= 0.01


# --- corroborating evidence --------------------------------------------------

def test_town_agreement_lifts_and_disagreement_lowers():
    base = name_match_probability("Monzo", "Monzo Bank Ltd")["p"]
    same = name_match_probability("Monzo", "Monzo Bank Ltd",
                                  town_a="London", town_b="London")["p"]
    other = name_match_probability("Monzo", "Monzo Bank Ltd",
                                   town_a="London", town_b="Cardiff")["p"]
    assert same > base > other


def test_town_prefix_counts_as_agreement():
    r = name_match_probability("Monzo", "Monzo Bank Ltd",
                               town_a="London", town_b="London, UK")
    factors = {f["factor"]: f for f in r["factors"]}
    assert factors["town"]["agree"] is True


def test_york_is_not_new_york():
    r = name_match_probability("Monzo", "Monzo Bank Ltd",
                               town_a="York", town_b="New York")
    factors = {f["factor"]: f for f in r["factors"]}
    assert factors["town"]["agree"] is False


def test_industry_agreement_shifts_the_same_way():
    base = name_match_probability("Monzo", "Monzo Bank Ltd")["p"]
    same = name_match_probability("Monzo", "Monzo Bank Ltd", same_industry=True)["p"]
    other = name_match_probability("Monzo", "Monzo Bank Ltd", same_industry=False)["p"]
    assert same > base > other


def test_prefix_plus_town_plus_industry_clears_point_nine():
    # The whole point of evidence combination: a Monzo-class pair with the town
    # AND the industry agreeing should rank as near-certain for review ordering.
    r = name_match_probability("Monzo", "Monzo Bank Ltd",
                               town_a="London", town_b="London",
                               same_industry=True)
    assert r["p"] > 0.9


def test_unknown_evidence_is_absent_from_receipts():
    r = name_match_probability("Monzo", "Monzo Bank Ltd")
    assert r["factors"] == []


def test_name_probability_is_recomputable_from_receipts():
    r = name_match_probability("Monzo", "Monzo Bank Ltd",
                               town_a="London", town_b="London",
                               same_industry=False)
    rebuilt = _sigmoid(_logit(r["base_p"]) + sum(f["shift"] for f in r["factors"]))
    assert r["p"] == pytest.approx(rebuilt)


# --- same-job probability ----------------------------------------------------

def _ad(**kw):
    base = {"title": "Software Engineer", "location": "London",
            "salary_min": 60_000, "salary_max": 80_000}
    base.update(kw)
    return base


def test_equal_fingerprints_are_the_same_job():
    a = _ad(fingerprint="abc123")
    b = _ad(fingerprint="abc123")
    r = same_job_probability(a, b)
    assert r["method"] == "fingerprint"
    assert r["p"] >= 0.98


def test_exact_title_same_town_overlapping_salary_is_high():
    r = same_job_probability(_ad(), _ad(salary_min=70_000, salary_max=90_000))
    assert r["p"] > 0.9


def test_same_title_different_towns_is_probably_two_postings():
    r = same_job_probability(_ad(), _ad(location="Manchester"))
    assert r["p"] < 0.6


def test_near_title_is_weaker_than_exact():
    exact = same_job_probability(_ad(), _ad())["p"]
    near = same_job_probability(_ad(), _ad(title="Senior Software Engineer"))["p"]
    assert exact > near > 0.3


def test_unrelated_titles_are_different_jobs_even_in_the_same_town():
    r = same_job_probability(_ad(), _ad(title="Care Assistant"))
    assert r["p"] < 0.3


def test_disjoint_salaries_pull_down():
    both = same_job_probability(_ad(), _ad())["p"]
    disjoint = same_job_probability(
        _ad(), _ad(salary_min=20_000, salary_max=25_000))["p"]
    assert disjoint < both


def test_missing_salary_is_no_evidence_either_way():
    r = same_job_probability(_ad(salary_min=None, salary_max=None), _ad())
    assert all(f["factor"] != "salary" for f in r["factors"])


def test_same_job_probability_is_recomputable_from_receipts():
    r = same_job_probability(_ad(), _ad(location="Manchester",
                                        salary_min=20_000, salary_max=25_000))
    rebuilt = _sigmoid(_logit(r["base_p"]) + sum(f["shift"] for f in r["factors"]))
    assert r["p"] == pytest.approx(rebuilt)
