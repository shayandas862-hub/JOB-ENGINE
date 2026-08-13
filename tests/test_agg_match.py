"""Tests for src/discover/agg_match — the re-runnable register-match label pass.

The register is the filter (founder design 2026-07-22): ads are matched by
employer name against licensed sponsors and LABELLED — never deleted. A
no-match stamps the attempt (matched_at) so the pass is resumable, and the
label can be re-derived later by better matchers at zero API cost.
"""
from __future__ import annotations

from discover.sponsor_match import SponsorMatch
from tests.test_criteria import RoutingCursor

EMPLOYERS = [
    {"employer_norm": "sky uk ltd", "employer_name": "Sky UK Ltd"},
    {"employer_norm": "unknowco", "employer_name": "UnknowCo"},
]


def _fake_match(cur, employer):
    if employer == "Sky UK Ltd":
        return SponsorMatch("matched", employer, sponsor_id=1, method="exact",
                            candidates=({"org_name_norm": "sky uk limited"},))
    return SponsorMatch("unmatched", employer)


def test_match_pending_labels_matched_and_stamps_no_match_attempts(monkeypatch):
    import discover.agg_match as agg_match
    monkeypatch.setattr(agg_match, "match_employer", _fake_match)
    cur = RoutingCursor([("matched_at is null group by", EMPLOYERS)])

    counts = agg_match.match_pending(cur, limit=10)

    assert counts == {"matched": 1, "uncertain": 0, "unmatched": 1}
    updates = [(s, p) for s, p in cur.executed if s.startswith("update aggregator_ads")]
    assert len(updates) == 2
    assert "matched_at is null" in updates[0][0]        # never re-stamps old labels
    assert updates[0][1] == ("sky uk limited", "exact", "sky uk ltd")
    assert updates[1][1] == (None, "unmatched", "unknowco")


def test_match_pending_uncertain_is_stamped_without_an_org(monkeypatch):
    import discover.agg_match as agg_match
    monkeypatch.setattr(
        agg_match, "match_employer",
        lambda cur, e: SponsorMatch("uncertain", e,
                                    candidates=({"org_name_norm": "a"},
                                                {"org_name_norm": "b"})))
    cur = RoutingCursor([("matched_at is null group by",
                          [{"employer_norm": "ambiguous co", "employer_name": "Ambiguous Co"}])])
    counts = agg_match.match_pending(cur, limit=10)
    assert counts == {"matched": 0, "uncertain": 1, "unmatched": 0}
    update = [p for s, p in cur.executed if s.startswith("update aggregator_ads")][0]
    assert update == (None, "uncertain", "ambiguous co")  # no silent guess, ever
