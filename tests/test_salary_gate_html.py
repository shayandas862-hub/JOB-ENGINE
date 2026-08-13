"""The HTML-split salary gate, and the retry it used to make impossible.

Phase 9.5 task 6, from the 2026-08-10 drainer finding. Board-fetched job
descriptions keep their raw HTML, so a range a human reads as

    £77,500 — £90,000

is stored as

    <span>£77,500</span><span class="divider">&mdash;</span><span>£90,000 GBP</span>

The reading gate checks a claim is a VERBATIM substring of the stored text, so
it refused the range — correctly, on its own terms, and wrongly about the
world. The client had quoted exactly what the advert says; the advert simply
does not contain that sequence of characters anywhere.

Two bugs sat on top of each other, which is why the second matters as much:
the rejected FIELD could not be retried, because the first `submit_reading`
un-staged the row on its way out. The client got "salary_rejected", the
listing left the tray, and there was no way back to it.

Both are fixed here, and neither weakens the principle:

  * salary is grounded against the advert's READABLE text — the same string a
    person sees — using the ONE shared stripper, aliased, never re-written;
  * a rejected salary HOLDS the row in the tray with its claim, so the client
    can correct the one field. Submitting again with a grounded salary, or
    with none, completes the reading and releases it.

Skills keep the strict raw-text gate, deliberately: they feed the match
engine, and a looser gate there admits more ungrounded claims into the number
that decides which jobs the owner sees.
"""
from __future__ import annotations

import pytest

from tests.conftest import ScriptedCursor

OWNER = "11111111-1111-1111-1111-111111111111"

# The real shape, from Ashby listings 7090/7116 (Algolia).
HTML_JD = ('<div><h2>Compensation</h2><span>£77,500</span>'
           '<span class="divider">&mdash;</span>'
           '<span>£90,000 GBP</span><p>You will use Python daily.</p></div>')


def _cursor(jd=HTML_JD, staged=True):
    return ScriptedCursor([
        ("from role_listings r join target_companies", [[{
            "role_id": 1, "jd_full": jd,
            "staged_at": "2026-08-12" if staged else None}]]),
        ("from occupations", [[]]),
        ("select", [[]]),
    ])


def _accept(cur, **payload):
    from reading.accept import accept_reading
    base = {"skills": [], "salary_text": None, "sponsor_hint": None,
            "soc_hint": None}
    base.update(payload)
    return accept_reading(cur, OWNER, 1, base)


def test_a_range_split_across_html_tags_is_now_grounded():
    # The finding itself. A person reads "£77,500 — £90,000" off the page; the
    # stored bytes have three elements and an entity between the numbers.
    result = _accept(_cursor(), salary_text="£77,500 — £90,000")
    assert result["salary_rejected"] is False, (
        "the gate still refuses a range that is plainly in the advert — it is "
        "comparing against markup rather than against what the advert says")


def test_a_salary_that_is_nowhere_in_the_advert_is_still_refused():
    # The control, and the one that matters most: the fix must widen the gate
    # to the readable text, NOT open it. Without this, "grounded" could come
    # to mean nothing at all and every test above would still pass.
    result = _accept(_cursor(), salary_text="£250,000 — £300,000")
    assert result["salary_rejected"] is True


def test_markup_itself_is_not_quotable_as_a_salary():
    # The other direction of the same control. After stripping, the tags are
    # gone from what the claim is checked against, so a client quoting the
    # raw HTML is no longer grounded by it.
    result = _accept(_cursor(), salary_text='<span>£77,500</span>')
    assert result["salary_rejected"] is True


def test_a_plain_text_advert_still_grounds_exactly_as_before():
    result = _accept(_cursor(jd="Salary: £45,000 to £52,000 per annum."),
                     salary_text="£45,000 to £52,000")
    assert result["salary_rejected"] is False


def test_skills_keep_the_strict_gate_and_are_not_widened():
    # Deliberate asymmetry, stated in the module docstring. This test exists
    # so that widening skills later is a decision someone has to make on
    # purpose, with this failing in front of them.
    cur = _cursor(jd="<p>You will use <b>Py</b>thon daily.</p>")
    result = _accept(cur, skills=[{"name": "Python", "category": "tool"}])
    assert result["rejected_skills"] == ["Python"], (
        "the skills gate was widened along with salary — skills feed the "
        "match engine and a looser gate there changes which jobs are shown")


def test_a_rejected_salary_holds_the_row_in_the_tray_for_a_retry():
    # The second half of the bug. Before this, the first submission un-staged
    # the listing whatever happened, so a rejected field could never be
    # corrected — the client was told "rejected" about a row it could no
    # longer reach.
    cur = _cursor()
    result = _accept(cur, salary_text="£250,000")

    assert result["salary_rejected"] is True
    assert result["outcome"] == "held_for_retry"
    unstaged = [sql for sql, _ in cur.executed
                if "staged_at = null" in sql.lower()]
    assert unstaged == [], "the listing was released despite the rejection"


def test_a_clean_reading_still_releases_the_listing():
    # Paired with the test above: without this, "holds the row" could be true
    # of every submission and the tray would never drain.
    cur = _cursor()
    result = _accept(cur, salary_text="£77,500 — £90,000")

    assert result["outcome"] == "accepted"
    assert any("staged_at = null" in sql.lower() for sql, _ in cur.executed)


def test_dropping_the_salary_is_always_a_way_out_of_the_retry():
    # The escape hatch. A held row must never be a trap: a client that cannot
    # find a groundable salary submits without one and the reading completes.
    cur = _cursor()
    result = _accept(cur, salary_text=None)
    assert result["outcome"] == "accepted"
    assert any("staged_at = null" in sql.lower() for sql, _ in cur.executed)


def test_the_skills_of_a_held_reading_are_kept_not_thrown_away():
    # A retry must not cost the client the work it got right. The skills
    # persist on the first pass; only the rejected field is outstanding.
    cur = _cursor()
    result = _accept(cur, skills=[{"name": "Python", "category": "tool"}],
                     salary_text="£250,000")
    assert result["skills_accepted"] == 1
    assert result["outcome"] == "held_for_retry"


def test_the_stripper_is_the_shared_one_never_a_second_copy():
    # There is ONE html stripper in this project and jd_drip already aliases
    # it with that instruction written beside it. A second regex here would
    # drift from the one the fetchers use, and the two would disagree about
    # what an advert says — the B-GAE-025 shape, applied to text.
    import inspect

    from fetch.feeds import _strip_html
    from reading import accept

    assert accept.clean_html is _strip_html, \
        "reading.accept must alias the shared stripper, not define its own"
    source = inspect.getsource(accept)
    assert "re.sub" not in source, \
        "a second HTML-stripping regex appeared in reading/accept.py"
