"""Tests for src/discover/sponsor_match — matching aggregator employers to the register.

The unfair advantage is that everything entering the queue carries a sponsor
verdict. This matcher is confident only on an exact (shared-norm) match or a
unique legal-suffix-normalised match; anything ambiguous or merely partial
becomes a 'sponsor_match' review flag — never a silent guess. No register hit at
all is a confident negative (not a sponsor). Offline: a routing fake cursor
serves register rows and records writes.
"""
from __future__ import annotations

import json

from tests.conftest import FakeCursor


class RoutingCursor:
    def __init__(self, exact=None, candidates=None, flag_row=None):
        self.exact = exact or []
        self.candidates = candidates or []
        self.flag_row = flag_row
        self.executed = []
        self._pending = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        self.executed.append((s, params))
        if "org_name_norm = %s" in s:
            self._pending = list(self.exact)
        elif "org_name_norm like" in s:
            self._pending = list(self.candidates)
        elif "insert into review_items" in s:
            self._pending = [self.flag_row] if self.flag_row else []
        else:
            self._pending = []

    def fetchall(self):
        return list(self._pending)

    def fetchone(self):
        return self._pending[0] if self._pending else None


def reg(sponsor_id, name, norm_name):
    return {"sponsor_id": sponsor_id, "organisation_name": name,
            "org_name_norm": norm_name, "rating": "A", "route": "Skilled Worker"}


# ---- the matcher: tricky name pairs ----------------------------------------

def test_exact_normalised_name_is_a_confident_match():
    from discover.sponsor_match import match_employer
    cur = RoutingCursor(exact=[reg(10, "Acme AI Ltd", "acme ai ltd")])
    m = match_employer(cur, "Acme  AI   Ltd")            # extra spaces -> norm collapses
    assert m.status == "matched" and m.sponsor_id == 10 and m.method == "exact"
    assert m.rating == "A"


def test_legal_suffix_difference_is_a_confident_unique_match():
    from discover.sponsor_match import match_employer
    # employer 'Acme AI', register only has 'Acme AI Ltd' -> unique core match
    cur = RoutingCursor(exact=[], candidates=[reg(10, "Acme AI Ltd", "acme ai ltd")])
    m = match_employer(cur, "Acme AI")
    assert m.status == "matched" and m.sponsor_id == 10 and m.method == "normalised"


def test_ambiguous_partial_match_becomes_uncertain_with_candidates():
    from discover.sponsor_match import match_employer
    cur = RoutingCursor(exact=[], candidates=[
        reg(10, "Acme AI Ltd", "acme ai ltd"),
        reg(11, "Acme Roofing Ltd", "acme roofing ltd")])
    m = match_employer(cur, "Acme")                       # neither core equals 'acme'
    assert m.status == "uncertain" and m.sponsor_id is None
    assert {c["sponsor_id"] for c in m.candidates} == {10, 11}


def test_two_identical_register_names_are_uncertain_not_a_guess():
    from discover.sponsor_match import match_employer
    cur = RoutingCursor(exact=[reg(10, "Delta Ltd", "delta ltd"),
                               reg(20, "Delta Ltd", "delta ltd")])
    m = match_employer(cur, "Delta Ltd")
    assert m.status == "uncertain" and m.method == "exact-ambiguous"
    assert len(m.candidates) == 2


def test_no_register_entry_is_a_confident_negative():
    from discover.sponsor_match import match_employer
    cur = RoutingCursor(exact=[], candidates=[])
    m = match_employer(cur, "Totally Unknown Startup")
    assert m.status == "unmatched" and m.sponsor_id is None


def test_blank_employer_is_unmatched_without_querying():
    from discover.sponsor_match import match_employer
    cur = RoutingCursor()
    assert match_employer(cur, "   ").status == "unmatched"
    assert cur.executed == []


# ---- cross_check writes a flag only for uncertain, and audits --------------

def test_uncertain_match_writes_a_sponsor_match_flag_and_audits():
    from discover.sponsor_match import cross_check_employer
    cur = RoutingCursor(
        exact=[],
        candidates=[reg(10, "Acme AI Ltd", "acme ai ltd"),
                    reg(11, "Acme Roofing Ltd", "acme roofing ltd")],
        flag_row={"review_id": 5, "kind": "sponsor_match", "ref": "acme", "status": "open"})
    m = cross_check_employer(cur, "Acme")

    assert m.status == "uncertain"
    flag = next((s, p) for s, p in cur.executed if "insert into review_items" in s)
    assert "sponsor_match" in flag[1]                     # kind
    evidence = json.loads(flag[1][3])
    assert evidence["employer"] == "Acme"
    assert len(evidence["candidates"]) == 2
    assert any("insert into mcp_audit" in s for s, _ in cur.executed)


def test_confident_match_writes_no_flag():
    from discover.sponsor_match import cross_check_employer
    cur = RoutingCursor(exact=[reg(10, "Acme AI Ltd", "acme ai ltd")])
    m = cross_check_employer(cur, "Acme AI Ltd")
    assert m.status == "matched"
    assert not any("insert into review_items" in s for s, _ in cur.executed)


def test_unmatched_writes_no_flag():
    from discover.sponsor_match import cross_check_employer
    cur = RoutingCursor(exact=[], candidates=[])
    cross_check_employer(cur, "Nobody Ltd")
    assert not any("insert into review_items" in s for s, _ in cur.executed)
