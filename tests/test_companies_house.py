"""The UK registry plug-in: Companies House search → match → profile.

Offline via `responses`; fixtures recorded from the developer docs (contract
confirmed 2026-07-11: Basic auth is key-as-username with a blank password,
same shape as Reed; the public-data rate limit is 600 requests per 5 minutes).
Matching mirrors sponsor_match's philosophy — exact norm, unique suffix-
stripped, single-ACTIVE disambiguation; ambiguity is recorded, never guessed.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import responses

from tests.conftest import FakeCursor

FIX = Path(__file__).parent / "fixtures" / "companies_house"
SEARCH_URL = "https://api.company-information.service.gov.uk/search/companies"
PROFILE_URL = "https://api.company-information.service.gov.uk/company/09876543"


def fx(name):
    return json.loads((FIX / name).read_text())


def _no_pace(monkeypatch):
    from discover import companies_house
    naps = []
    monkeypatch.setattr(companies_house, "_sleep", naps.append)
    return naps


# ---- HTTP client ------------------------------------------------------------

@responses.activate
def test_search_companies_uses_basic_auth_key_as_username(monkeypatch):
    from discover.companies_house import search_companies
    _no_pace(monkeypatch)
    responses.add(responses.GET, SEARCH_URL, json=fx("search_companies.json"),
                  status=200)
    search_companies("Acme AI Ltd", "CHKEY", None)
    auth = responses.calls[0].request.headers["Authorization"]
    assert auth == "Basic " + base64.b64encode(b"CHKEY:").decode()
    assert "items_per_page=5" in responses.calls[0].request.url


@responses.activate
def test_search_companies_maps_candidates(monkeypatch):
    from discover.companies_house import search_companies
    _no_pace(monkeypatch)
    responses.add(responses.GET, SEARCH_URL, json=fx("search_companies.json"),
                  status=200)
    out = search_companies("Acme AI Ltd", "CHKEY", None)
    assert [c["company_number"] for c in out] == ["09876543", "01234567"]
    assert out[0]["title"] == "ACME AI LTD"
    assert out[0]["company_status"] == "active"


@responses.activate
def test_search_companies_returns_none_on_failure_not_empty(monkeypatch):
    from discover.companies_house import search_companies
    _no_pace(monkeypatch)
    responses.add(responses.GET, SEARCH_URL, json={}, status=403)
    assert search_companies("Acme AI Ltd", "CHKEY", None) is None


@responses.activate
def test_get_profile_returns_status_type_sic_codes_incorporated(monkeypatch):
    from discover.companies_house import get_profile
    _no_pace(monkeypatch)
    responses.add(responses.GET, PROFILE_URL, json=fx("company_profile.json"),
                  status=200)
    p = get_profile("09876543", "CHKEY", None)
    assert p["company_number"] == "09876543"
    assert p["company_status"] == "active"
    assert p["type"] == "ltd"
    assert p["sic_codes"] == ["62012", "62020"]
    assert p["date_of_creation"] == "2015-03-01"


@responses.activate
def test_client_retries_429_and_paces_with_swappable_sleep(monkeypatch):
    from discover import companies_house
    naps = []
    monkeypatch.setattr(companies_house, "_sleep", naps.append)
    responses.add(responses.GET, SEARCH_URL, json={}, status=429)
    responses.add(responses.GET, SEARCH_URL, json=fx("search_companies.json"),
                  status=200)
    out = companies_house.search_companies("Acme AI Ltd", "CHKEY", None)
    assert len(out) == 2                          # survived the 429
    assert len(responses.calls) == 2
    assert companies_house.PAUSE in naps          # paced under 600/5min


# ---- match_company ----------------------------------------------------------

def _cand(title, number="09876543", status="active"):
    return {"title": title, "company_number": number, "company_status": status,
            "company_type": "ltd", "date_of_creation": "2015-03-01"}


def test_match_company_exact_norm_match_wins():
    from discover.companies_house import match_company
    outcome, hit = match_company(
        [_cand("ACME AI LTD"), _cand("ACME AI GROUP LTD", "1")], "acme ai ltd")
    assert outcome == "matched" and hit["company_number"] == "09876543"


def test_match_company_unique_legal_suffix_stripped_match_wins():
    from discover.companies_house import match_company
    # register says "Acme AI"; Companies House has it registered as a LTD
    outcome, hit = match_company([_cand("ACME AI LTD")], "acme ai")
    assert outcome == "matched" and hit["company_number"] == "09876543"


def test_match_company_multiple_active_candidates_is_ambiguous_never_a_guess():
    from discover.companies_house import match_company
    outcome, hit = match_company(
        [_cand("ACME AI LTD", "1"), _cand("ACME AI LIMITED", "2")], "acme ai")
    assert (outcome, hit) == ("ambiguous", None)


def test_match_company_single_active_among_dissolved_namesakes_matches():
    from discover.companies_house import match_company
    cands = [_cand("ACME AI LTD", "1", status="dissolved"),
             _cand("ACME AI LTD", "2", status="active"),
             _cand("ACME AI LTD", "3", status="dissolved")]
    outcome, hit = match_company(cands, "acme ai ltd")
    assert outcome == "matched" and hit["company_number"] == "2"


def test_match_company_no_candidates_is_not_found():
    from discover.companies_house import match_company
    assert match_company([], "acme ai ltd") == ("not_found", None)
    assert match_company([_cand("UTTERLY DIFFERENT PLC")], "acme ai ltd") == \
        ("not_found", None)


# ---- enrich_org -------------------------------------------------------------

@responses.activate
def test_enrich_org_records_matched_profile_columns(monkeypatch):
    from discover.companies_house import enrich_org
    _no_pace(monkeypatch)
    responses.add(responses.GET, SEARCH_URL, json=fx("search_companies.json"),
                  status=200)
    responses.add(responses.GET, PROFILE_URL, json=fx("company_profile.json"),
                  status=200)
    cur = FakeCursor()
    assert enrich_org(cur, "acme ai ltd", "Acme AI Ltd", "CHKEY") == "matched"
    sql, params = cur.executed[0]
    assert "update sponsor_census" in sql.lower()
    assert "matched" in params and "09876543" in params
    assert ["62012", "62020"] in params and "2015-03-01" in params


@responses.activate
def test_enrich_org_records_ambiguous_without_a_profile_fetch(monkeypatch):
    from discover.companies_house import enrich_org
    _no_pace(monkeypatch)
    two_active = fx("search_companies.json")
    two_active["items"][1]["company_status"] = "active"
    two_active["items"][1]["title"] = "ACME AI LIMITED"
    responses.add(responses.GET, SEARCH_URL, json=two_active, status=200)
    cur = FakeCursor()
    assert enrich_org(cur, "acme ai", "Acme AI", "CHKEY") == "ambiguous"
    assert len(responses.calls) == 1              # never fetched a profile
    _, params = cur.executed[0]
    assert "ambiguous" in params


@responses.activate
def test_enrich_org_records_error_when_search_fails(monkeypatch):
    from discover.companies_house import enrich_org
    _no_pace(monkeypatch)
    responses.add(responses.GET, SEARCH_URL, json={}, status=500)
    responses.add(responses.GET, SEARCH_URL, json={}, status=500)
    responses.add(responses.GET, SEARCH_URL, json={}, status=500)
    cur = FakeCursor()
    assert enrich_org(cur, "acme ai ltd", "Acme AI Ltd", "CHKEY") == "error"
    _, params = cur.executed[0]
    assert "error" in params


# ---- config gate ------------------------------------------------------------

def test_settings_ch_ready_requires_the_key():
    from config import Settings
    assert not Settings(database_url="x", gemini_api_key="").ch_ready
    assert Settings(database_url="x", gemini_api_key="",
                    companies_house_api_key="K").ch_ready
