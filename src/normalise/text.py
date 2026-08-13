"""The ONE text normaliser.

This is the join contract for skill matching: role_skills.skill_norm,
skill_synonyms.raw_norm/canonical_norm, and my_skills.skill_norm are all
produced by this function, and dedupe_key normalises titles with it too.
Never define a second copy — import this one. Changing it means migrating
every normalised value already stored in the database.
"""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")

# Legal-entity suffixes only — deliberately NOT geographic (uk/gb) or descriptive
# tokens, so stripping can't over-merge distinct companies. Shared by the sponsor
# matcher, the board-slug guesser, and the registry plug-in (moved here Phase 7.5).
LEGAL_SUFFIXES = frozenset({
    "ltd", "ltd.", "limited", "plc", "llp", "llc", "lp", "inc", "inc.",
    "incorporated", "gmbh", "ltda",
})


def norm(s: str | None) -> str:
    return _WS.sub(" ", (s or "").strip()).lower()


def strip_legal_suffixes(name_norm: str) -> str:
    """Drop trailing legal-form tokens ('acme ai ltd' -> 'acme ai').

    Operates on norm() output (lowercase, single-spaced).
    """
    toks = name_norm.split()
    while toks and toks[-1] in LEGAL_SUFFIXES:
        toks.pop()
    return " ".join(toks)
