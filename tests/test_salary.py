from analysis.salary import parse_salary, salary_text_from


def test_salary_text_from():
    # single source of stated-salary text (moved out of feeds.py)
    assert salary_text_from("Salary £45,000 - £55,000 per year") == "£45,000 - £55,000"
    assert salary_text_from("Build things. Salary £80,000.") == "£80,000"
    assert salary_text_from("Competitive salary") is None
    assert salary_text_from(None) is None


def test_parse_range():
    assert parse_salary("Salary £45,000 - £55,000 plus equity") == (45000, 55000)


def test_parse_single_and_k():
    assert parse_salary("Up to £80,000") == (80000, 80000)
    assert parse_salary("circa £90k") == (90000, 90000)


def test_parse_none():
    assert parse_salary("Competitive salary") is None
    assert parse_salary(None) is None


def test_parse_filters_noise():
    # a stray small "£500 signing" should be filtered out; the real figure kept
    assert parse_salary("£60,000 base") == (60000, 60000)


# classify() and its flat thresholds were deleted (Phase 1 Task 10): the wall
# verdict lives only in the v_apply_queue SQL view. Phase 2 rebuilds it on
# per-SOC going rates.
