"""Name-match and same-job probability — evidence combined in the open.

Two questions the engine keeps meeting: "is this ad's employer that register
sponsor?" and "is this ad the same job as that board listing?". Neither is
certain, so both answers are probabilities with receipts: a base relation
(the method), plus corroborating factors each carrying its log-odds shift —
p is always recomputable as sigmoid(logit(base_p) + sum(shifts)).

The name ladder pins the decision-log boundary (2026-07-14): exact norm >
legal-suffix-stripped > brand prefix (the Monzo / Thought Machine class —
never auto-matched, but sorted to the top of the uncertain pile) > token
overlap > nothing. Pure functions: no DB, no AI, no network.
"""
from __future__ import annotations

import math
import re

from normalise.text import norm, strip_legal_suffixes

# Probability is never allowed to reach 0 or 1 — evidence, not proof.
P_FLOOR, P_CEIL = 0.005, 0.995

# Name-relation base probabilities (the ladder).
NAME_BASE = {"exact": 0.99, "suffix_stripped": 0.95, "brand_prefix": 0.70,
             "no_match": 0.01}
# Corroboration shifts (log-odds) for the employer-name question.
TOWN_AGREE, TOWN_DISAGREE = math.log(4), -math.log(4)
INDUSTRY_AGREE, INDUSTRY_DISAGREE = math.log(3), -math.log(3)

# Same-job bases and shifts. A different town outweighs everything else:
# the same title in two cities is two postings, applied to separately.
FINGERPRINT_P, TITLE_EXACT_P, TITLE_FAR_P = 0.98, 0.85, 0.05
NEAR_TITLE_JACCARD = 0.6
JOB_TOWN_AGREE, JOB_TOWN_DISAGREE = math.log(3), -math.log(12)
JOB_SALARY_AGREE, JOB_SALARY_DISAGREE = math.log(2), -math.log(4)


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _tokens(s: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+", norm(s))


def _jaccard(a: list[str], b: list[str]) -> float:
    union = set(a) | set(b)
    return len(set(a) & set(b)) / len(union) if union else 0.0


def _is_token_prefix(short: list[str], long: list[str]) -> bool:
    return 0 < len(short) < len(long) and long[:len(short)] == short


def _towns_agree(town_a, town_b) -> bool | None:
    """Equal token lists or a strict token prefix ('London' ~ 'London, UK').

    Prefix-only on purpose: 'York' must not agree with 'New York' (a suffix
    rule would merge them). Cost: 'Greater Manchester' vs 'Manchester' reads
    as disagreement — a duplicate row at worst, never a wrong merge.
    """
    ta, tb = _tokens(town_a), _tokens(town_b)
    if not ta or not tb:
        return None
    return ta == tb or _is_token_prefix(ta, tb) or _is_token_prefix(tb, ta)


def _combine(method: str, base_p: float, factors: list[dict]) -> dict:
    p = _sigmoid(_logit(base_p) + sum(f["shift"] for f in factors))
    return {"p": min(max(p, P_FLOOR), P_CEIL), "method": method,
            "base_p": base_p, "factors": factors}


def name_match_probability(name_a: str, name_b: str, *,
                           town_a: str | None = None,
                           town_b: str | None = None,
                           same_industry: bool | None = None) -> dict:
    """P(these two employer names are the same company), with receipts.

    Returns {"p", "method", "base_p", "factors"}; factors carry only KNOWN
    evidence (unknown town/industry is absent, shifting nothing).
    """
    na, nb = norm(name_a), norm(name_b)
    if not na or not nb:
        return {"p": P_FLOOR, "method": "empty", "base_p": P_FLOOR, "factors": []}

    sa, sb = strip_legal_suffixes(na), strip_legal_suffixes(nb)
    ta, tb = _tokens(sa), _tokens(sb)
    if na == nb:
        method, base_p = "exact", NAME_BASE["exact"]
    elif sa and sa == sb:
        method, base_p = "suffix_stripped", NAME_BASE["suffix_stripped"]
    elif _is_token_prefix(ta, tb) or _is_token_prefix(tb, ta):
        method, base_p = "brand_prefix", NAME_BASE["brand_prefix"]
    else:
        j = _jaccard(ta, tb)
        if j > 0:
            method, base_p = "token_overlap", 0.05 + 0.45 * j
        else:
            method, base_p = "no_match", NAME_BASE["no_match"]

    factors = []
    town = _towns_agree(town_a, town_b)
    if town is not None:
        factors.append({"factor": "town", "agree": town,
                        "shift": TOWN_AGREE if town else TOWN_DISAGREE})
    if same_industry is not None:
        factors.append({"factor": "industry", "agree": same_industry,
                        "shift": INDUSTRY_AGREE if same_industry
                        else INDUSTRY_DISAGREE})
    return _combine(method, base_p, factors)


def _salary_range(side: dict) -> tuple[float, float] | None:
    lo, hi = side.get("salary_min"), side.get("salary_max")
    if lo is None and hi is None:
        return None
    lo = lo if lo is not None else hi
    hi = hi if hi is not None else lo
    return float(lo), float(hi)


def same_job_probability(a: dict, b: dict) -> dict:
    """P(these two postings are the same job), with receipts.

    Sides are dicts of title / location / salary_min / salary_max, plus an
    optional precomputed cross-source ``fingerprint`` (agg_store.ad_fingerprint
    — employer|title|location); equal fingerprints ARE the same job and skip
    the evidence weighing entirely.
    """
    fa, fb = a.get("fingerprint"), b.get("fingerprint")
    if fa and fb and fa == fb:
        return {"p": FINGERPRINT_P, "method": "fingerprint",
                "base_p": FINGERPRINT_P, "factors": []}

    title_a, title_b = norm(a.get("title")), norm(b.get("title"))
    if title_a and title_a == title_b:
        method, base_p = "title_exact", TITLE_EXACT_P
    else:
        j = _jaccard(_tokens(title_a), _tokens(title_b))
        if j >= NEAR_TITLE_JACCARD:
            method, base_p = "title_near", 0.3 + 0.5 * j
        else:
            method, base_p = "title_far", TITLE_FAR_P

    factors = []
    town = _towns_agree(a.get("location"), b.get("location"))
    if town is not None:
        factors.append({"factor": "town", "agree": town,
                        "shift": JOB_TOWN_AGREE if town else JOB_TOWN_DISAGREE})
    ra, rb = _salary_range(a), _salary_range(b)
    if ra is not None and rb is not None:
        overlap = ra[0] <= rb[1] and rb[0] <= ra[1]
        factors.append({"factor": "salary", "agree": overlap,
                        "shift": JOB_SALARY_AGREE if overlap
                        else JOB_SALARY_DISAGREE})
    return _combine(method, base_p, factors)
