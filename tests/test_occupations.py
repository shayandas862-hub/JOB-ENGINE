"""Tests for the SOC occupation resolver — deterministic name→code matching.

The AI reader's soc_hint is an occupation NAME. Resolution to a code uses only
the official reference data (job_type + related_job_titles). Unresolved or
ambiguous hints stay None — the resolver never guesses."""
from __future__ import annotations

from analysis.occupations import build_occupation_index, make_resolver

ROWS = [
    {"occupation_code": "2134",
     "job_type": "Programmers and software development professionals",
     "related_job_titles": "Computer games designers\nComputer programmers\nSoftware developers\nProgrammers and software development professionals not elsewhere classified."},
    {"occupation_code": "2433",
     "job_type": "Actuaries, economists and statisticians",
     "related_job_titles": "Actuaries and actuarial analysts\nEconomists\nMathematicians\nStatistical data scientists\nStatisticians"},
    {"occupation_code": "2131",
     "job_type": "IT project managers",
     "related_job_titles": "IT project managers"},
]


def test_resolves_official_name_and_related_titles():
    fits = make_resolver(build_occupation_index(ROWS))
    assert fits("Programmers and software development professionals") == "2134"
    assert fits("software developers") == "2134"            # related title, case-insensitive
    assert fits("Computer  programmers") == "2134"          # whitespace-insensitive
    assert fits("Statistical data scientists") == "2433"
    assert fits("Economists") == "2433"


def test_trailing_period_is_ignored():
    fits = make_resolver(build_occupation_index(ROWS))
    assert fits("Actuaries, economists and statisticians.") == "2433"


def test_bare_code_passes_through_only_if_known():
    fits = make_resolver(build_occupation_index(ROWS))
    assert fits("2134") == "2134"
    assert fits("9999") is None                             # unknown code: no guess


def test_unknown_and_empty_hints_resolve_to_none():
    fits = make_resolver(build_occupation_index(ROWS))
    assert fits("Software Engineer") is None                # not an official title: no guess
    assert fits("") is None
    assert fits(None) is None


def test_ambiguous_titles_are_dropped_not_guessed():
    rows = ROWS + [{"occupation_code": "9998",
                    "job_type": "Economists",               # collides with 2433's related title
                    "related_job_titles": ""}]
    fits = make_resolver(build_occupation_index(rows))
    assert fits("Economists") is None                       # two codes claim it -> no match