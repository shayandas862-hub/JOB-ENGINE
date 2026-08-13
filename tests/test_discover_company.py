"""Tests for src/discover/company — interactive by-name discovery + URL onboarding.

Offline: classify_company / _probe_specific are monkeypatched (no HTTP) and a
routing fake cursor pins the reads/writes. discover_company either onboards a
company (with a sponsor-register verdict) or returns probe evidence; classify_from_url
onboards from a board URL Claude found.
"""
from __future__ import annotations

from tests.conftest import FakeCursor


class RoutingCursor:
    """Fake cursor answering each query from a routing table by substring."""

    def __init__(self, routes):
        self.routes = routes
        self.executed = []
        self._pending = []

    def execute(self, sql, params=None):
        squashed = " ".join(sql.split()).lower()
        self.executed.append((squashed, params))
        for marker, rows in self.routes:
            if marker in squashed:
                self._pending = list(rows)
                return
        self._pending = []

    def fetchall(self):
        return list(self._pending)

    def fetchone(self):
        return self._pending[0] if self._pending else None


def verdict_row(sponsor_id=42, name="Acme AI Ltd", town="London"):
    return {"sponsor_id": sponsor_id, "organisation_name": name, "town_city": town,
            "rating": "A", "route": "Skilled Worker", "is_skilled_worker": True}


def gh(name, token="acme", n=9):
    from fetch.ats import ATS_GREENHOUSE, Classification
    return Classification(name, ATS_GREENHOUSE, token, f"https://boards.greenhouse.io/{token}", n)


# ---- ATS URL parsing --------------------------------------------------------

def test_parse_ats_url_recognizes_each_supported_board():
    from discover.company import parse_ats_url
    assert parse_ats_url("https://boards.greenhouse.io/acme") == ("greenhouse", "acme")
    assert parse_ats_url("https://boards-api.greenhouse.io/v1/boards/acme/jobs") == ("greenhouse", "acme")
    assert parse_ats_url("https://jobs.lever.co/beta-co") == ("lever", "beta-co")
    assert parse_ats_url("https://jobs.ashbyhq.com/gamma") == ("ashby", "gamma")
    assert parse_ats_url("https://apply.workable.com/delta/") == ("workable", "delta")


def test_parse_ats_url_returns_none_for_an_unknown_or_empty_url():
    from discover.company import parse_ats_url
    assert parse_ats_url("https://acme.com/careers") is None
    assert parse_ats_url("") is None
    assert parse_ats_url(None) is None


# ---- discover_company (by name) --------------------------------------------

def test_discover_company_onboards_when_a_board_is_found_with_register_verdict(monkeypatch):
    from discover import company
    monkeypatch.setattr(company, "classify_company", lambda name, session=None: gh(name))
    cur = RoutingCursor([
        ("from target_companies", []),                    # nothing targeted yet
        ("licensed_sponsors", [verdict_row()]),           # in the register
        ("insert into target_companies", [{"company_id": 700}]),
    ])

    out = company.discover_company(cur, "p-1", "Acme AI Ltd")

    assert out["outcome"] == "onboarded" and out["company_id"] == 700
    assert out["ats_type"] == "greenhouse" and out["ats_token"] == "acme"
    assert out["sponsor_verdict"] == {"in_register": True, "sponsor_id": 42,
                                      "rating": "A", "route": "Skilled Worker"}
    ins = next((s, p) for s, p in cur.executed if "insert into target_companies" in s)
    assert 42 in ins[1] and "register-only" in ins[1] and "p-1" in ins[1]


def test_discover_company_returns_evidence_when_no_board_is_found(monkeypatch):
    from discover import company
    from fetch.ats import ATS_UNKNOWN, Classification
    monkeypatch.setattr(company, "classify_company",
                        lambda name, session=None: Classification(name, ATS_UNKNOWN, None, None, None))
    cur = RoutingCursor([
        ("from target_companies", []),
        ("licensed_sponsors", [verdict_row(name="Dark Co", town="Leeds")]),
    ])

    out = company.discover_company(cur, "p-1", "Dark Co")

    assert out["outcome"] == "no_board"
    assert out["evidence"]["tokens_tried"]                 # a probe trail for Claude
    assert out["sponsor_verdict"]["in_register"] is True
    assert not any("insert into target_companies" in s for s, _ in cur.executed)


def test_discover_company_reports_already_targeted_without_probing(monkeypatch):
    from discover import company
    monkeypatch.setattr(company, "classify_company",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not probe")))
    cur = RoutingCursor([("from target_companies",
                          [{"sponsor_id": 1, "company_name": "Acme AI Ltd"}])])

    out = company.discover_company(cur, "p-1", "acme   ai   ltd")   # norm() matches

    assert out["outcome"] == "already_targeted"
    assert not any("insert" in s for s, _ in cur.executed)


# ---- classify_from_url (Claude hands back a board URL) ----------------------

def test_classify_from_url_onboards_a_verified_board(monkeypatch):
    from discover import company
    from fetch.ats import ATS_LEVER, Classification
    monkeypatch.setattr(company, "_probe_specific",
                        lambda ats_type, token, session=None: Classification(
                            "", ats_type, token, f"https://jobs.lever.co/{token}", 5))
    cur = RoutingCursor([
        ("from target_companies", []),
        ("licensed_sponsors", []),                          # not in the register
        ("insert into target_companies", [{"company_id": 800}]),
    ])

    out = company.classify_from_url(cur, "p-1", "Beta Co", "https://jobs.lever.co/betaco")

    assert out["outcome"] == "onboarded" and out["company_id"] == 800
    assert out["ats_type"] == "lever" and out["ats_token"] == "betaco"
    assert out["sponsor_verdict"] == {"in_register": False}
    ins = next((s, p) for s, p in cur.executed if "insert into target_companies" in s)
    assert "unverified (not in register)" in ins[1]         # honest negative verdict


def test_classify_from_url_rejects_an_unrecognized_url():
    from discover import company
    out = company.classify_from_url(FakeCursor(), "p-1", "Beta Co", "https://beta.com/careers")
    assert out["outcome"] == "unrecognized_url"


def test_classify_from_url_reports_a_board_that_does_not_verify(monkeypatch):
    from discover import company
    monkeypatch.setattr(company, "_probe_specific", lambda ats_type, token, session=None: None)
    out = company.classify_from_url(FakeCursor(), "p-1", "Beta Co", "https://jobs.lever.co/betaco")
    assert out["outcome"] == "unverified"
