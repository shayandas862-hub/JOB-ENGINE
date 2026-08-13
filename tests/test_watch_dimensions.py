"""The ten dimensions a watch may be made of — and nothing else.

`plans/0011` §1 fixes the combination space at ten dimensions, derived by four
admission gates rather than chosen, and §5 refuses a free-text query language
outright: "combinations of these ten, nothing else. That keeps every watch
explainable, testable, and safe."

That refusal only means something if it is enforced where the filters ENTER
the system, so this file tests the gate rather than the intention. An unknown
key is rejected, not ignored — a silently dropped filter is the worst failure
available here, because the watch would then quietly catch far more than the
owner asked for and every catch would still look correct.
"""
from __future__ import annotations

import pytest

from watch.dimensions import DIMENSIONS, InvalidWatch, validate_filters


def test_the_ten_dimensions_are_exactly_the_ten_the_design_derived():
    # Pinned by NAME, not by count: a rename plus an addition keeps a count
    # test green while changing the space, which is the B-GAE-004 shape.
    assert set(DIMENSIONS) == {
        "company", "industry_codes", "role_words", "location", "salary_floor",
        "source", "rating", "freshness_days", "fit_floor", "deadline_days",
    }
    assert len(DIMENSIONS) == 10


def test_a_single_dimension_watch_is_valid():
    assert validate_filters({"company": ["monzo"]}) == {"company": ["monzo"]}


def test_every_dimension_is_accepted_on_its_own():
    # The catalogue is an inventory, not a menu of favourites (§ appendix):
    # no dimension is special-cased, so each must stand alone.
    samples = {
        "company": ["monzo"],
        "industry_codes": ["62012"],
        "role_words": "data engineer",
        "location": "leeds",
        "salary_floor": 45000,
        "source": "board",
        "rating": "A",
        "freshness_days": 7,
        "fit_floor": 0.5,
        "deadline_days": 14,
    }
    assert set(samples) == set(DIMENSIONS), "a dimension has no sample here"
    for name, value in samples.items():
        assert validate_filters({name: value}) == {name: value}


def test_an_unknown_dimension_is_refused_and_never_silently_dropped():
    # The whole point of the closed space. Dropping it would leave a watch
    # that catches more than the owner asked for, with correct-looking
    # receipts on every catch.
    with pytest.raises(InvalidWatch) as caught:
        validate_filters({"company": ["monzo"], "jd_contains": "python"})
    assert "jd_contains" in str(caught.value)


def test_an_empty_watch_is_refused():
    # A watch with no dimensions is the whole job market every night.
    with pytest.raises(InvalidWatch):
        validate_filters({})


def test_filters_must_be_an_object():
    for bad in ([], "company", 3, None):
        with pytest.raises(InvalidWatch):
            validate_filters(bad)


@pytest.mark.parametrize("filters", [
    {"salary_floor": -1},               # a negative floor is not a floor
    {"salary_floor": "45000"},          # a number, not a string
    {"freshness_days": 0},              # zero days catches nothing, ever
    {"freshness_days": 4000},           # beyond any stored history
    {"fit_floor": 1.5},                 # scores are 0..1
    {"fit_floor": -0.1},
    {"deadline_days": 0},
    {"source": "carrier-pigeon"},       # closed vocabulary
    {"rating": "AAA"},                  # A or any; nothing else exists
    {"company": []},                    # an empty set matches nothing
    {"company": "monzo"},               # a set, not a bare string
    {"industry_codes": []},
    {"role_words": ""},                 # empty words match everything
    {"role_words": "   "},
    {"location": ""},
])
def test_a_dimension_with_a_meaningless_value_is_refused(filters):
    # Each of these would produce a watch that is either always-empty or
    # always-everything, and both read to the owner as "the machine is
    # broken" rather than "my filter was nonsense".
    with pytest.raises(InvalidWatch):
        validate_filters(filters)


def test_values_are_normalised_so_two_spellings_are_one_watch():
    # Case and whitespace must not create two watches that catch the same
    # thing — the overlap maths (§2c) would then report a 1.0 Jaccard and
    # advise merging two rows that were never different.
    out = validate_filters({"company": ["  Monzo  "], "location": " Leeds "})
    assert out["company"] == ["monzo"]
    assert out["location"] == "leeds"


def test_the_salary_wall_can_never_be_switched_off_by_a_filter():
    # § admission gate 3: unconditional protections are never options. The
    # visa wall applies on top of every watch, so naming it as a dimension
    # must be refused rather than quietly honoured.
    for attempt in ({"salary_wall": False}, {"visa_wall": "off"},
                    {"skip_wall": True}):
        with pytest.raises(InvalidWatch):
            validate_filters({"company": ["monzo"], **attempt})
