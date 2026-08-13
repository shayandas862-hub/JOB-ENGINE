"""The ONE text normaliser — the join contract for skill matching.

role_skills.skill_norm <-> skill_synonyms.raw_norm <-> my_skills.skill_norm all
join on this exact function. It exists once; these tests enforce that."""
from __future__ import annotations

from normalise.text import norm


def test_norm_lowercases_trims_and_collapses_whitespace():
    assert norm("  Senior   Engineer ") == "senior engineer"
    assert norm("PostgreSQL") == "postgresql"
    assert norm("Gen  AI\t tools") == "gen ai tools"
    assert norm("") == ""
    assert norm(None) == ""


def test_every_module_uses_the_same_normaliser_object():
    # Identity, not equality: a byte-identical copy would still be a second
    # definition that can drift. There must be exactly one function object.
    from fetch import feeds
    from normalise import synonyms
    from persist import extract_rules
    assert synonyms.norm is norm
    assert feeds.norm is norm
    assert extract_rules.norm is norm
