"""The truth gate — no CV line ships unless it traces to a verified fact.

Built on the read.eval grounding idea (a claim is grounded when it appears
verbatim in its source). Applied to CV bullets: every number in a bullet must
be present in its source fact, and the bulk of the bullet's content words must
trace back too. A bullet that fails — an invented metric, a fabricated employer
or tool — is replaced by the verbatim fact. Truth is the product; the fallback
is always safe, so the gate errs strict.
"""
from __future__ import annotations

import re
from dataclasses import replace

from read.eval import check_grounding

# Fraction of a bullet's content words that must trace to the source fact.
MIN_COVERAGE = 0.75

# Function words only — never content. Content words (nouns, verbs, adjectives)
# stay in the coverage check; grounding those is the point.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "on", "at",
    "by", "as", "from", "into", "across", "our", "their", "its", "this", "that",
    "was", "were", "is", "are", "be", "been", "which", "who", "it", "we", "i",
})

_NUM_RE = re.compile(r"\d+")
_WORD_RE = re.compile(r"[a-z]+")


def _numbers(text: str) -> set[str]:
    """Bare digit runs, comma-formatting removed so '70,000' == '70000'."""
    return set(_NUM_RE.findall((text or "").replace(",", "")))


def _content_words(text: str) -> list[str]:
    """Significant words (len ≥ 3, not a stopword), lowercased."""
    return [w for w in _WORD_RE.findall((text or "").lower())
            if len(w) >= 3 and w not in _STOPWORDS]


def trace_bullet(bullet: str, source_fact: str) -> bool:
    """True if every claim in `bullet` traces to `source_fact`."""
    if not bullet or not bullet.strip():
        return False
    if not _numbers(bullet) <= _numbers(source_fact):     # no invented metrics
        return False
    words = _content_words(bullet)
    if not words:
        return True
    grounded = sum(1 for w in words if check_grounding(w, source_fact))
    return grounded / len(words) >= MIN_COVERAGE


def gate_phrased(phrased):
    """Return the blocks with every untraceable bullet replaced by its verified fact."""
    return [p if trace_bullet(p.bullet, p.source_fact)
            else replace(p, bullet=p.source_fact)
            for p in phrased]
