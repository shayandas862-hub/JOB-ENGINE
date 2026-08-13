"""Tests for src/discover/aggregators — the Adzuna and Reed API clients.

Offline: the HTTP is mocked with `responses`, driven by fixtures shaped from the
official API docs (tests/fixtures/aggregators/, contracts confirmed 2026-07-11).
We prove request construction (params + Reed's basic auth), the mapping into the
standard Job shape, and that unconfigured sources are skipped.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import requests
import responses

FIX = Path(__file__).parent / "fixtures" / "aggregators"
ADZUNA_SEARCH = json.loads((FIX / "adzuna_search.json").read_text())
REED_SEARCH = json.loads((FIX / "reed_search.json").read_text())

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/gb/search/1"
REED_URL = "https://www.reed.co.uk/api/1.0/search"


# ---- salary formatting ------------------------------------------------------

def test_salary_text_formats_ranges_and_open_ends():
    from discover.aggregators import _salary_text
    assert _salary_text(65000, 85000) == "£65,000 - £85,000"
    assert _salary_text(90000, None) == "£90,000+"
    assert _salary_text(90000, 0) == "£90,000+"      # Reed uses 0 for 'unset'
    assert _salary_text(None, None) is None


# ---- Adzuna -----------------------------------------------------------------

@responses.activate
def test_search_adzuna_maps_results_to_the_standard_job_shape():
    responses.add(responses.GET, ADZUNA_URL, json=ADZUNA_SEARCH, status=200)
    from discover.aggregators import search_adzuna

    jobs = search_adzuna("APPID", "APPKEY", what="Machine Learning Engineer",
                         where="UK", salary_min=60000, session=requests.Session())

    assert len(jobs) == 2
    j = jobs[0]
    assert j.company_name == "Acme AI Ltd" and j.source == "adzuna"
    assert j.external_id == "4200000001"
    assert j.title == "Machine Learning Engineer"
    assert j.location == "London, UK"
    assert j.url == "https://www.adzuna.co.uk/land/ad/4200000001"
    assert j.salary_text == "£65,000 - £85,000"
    assert "ML Engineer" in j.jd_text
    # credentials + query criteria travelled as query params, not a secret in code
    sent = responses.calls[0].request.url
    assert "app_id=APPID" in sent and "app_key=APPKEY" in sent
    assert "salary_min=60000" in sent and "what=Machine" in sent


@responses.activate
def test_search_adzuna_returns_empty_on_error_rather_than_raising():
    responses.add(responses.GET, ADZUNA_URL, json={"exception": "AUTH_FAIL"}, status=401)
    from discover.aggregators import search_adzuna
    assert search_adzuna("bad", "bad", what="x", session=requests.Session()) == []


# ---- Reed -------------------------------------------------------------------

@responses.activate
def test_search_reed_uses_basic_auth_and_maps_results():
    responses.add(responses.GET, REED_URL, json=REED_SEARCH, status=200)
    from discover.aggregators import search_reed

    jobs = search_reed("REEDKEY", keywords="Data Engineer", location="UK",
                       minimum_salary=40000, session=requests.Session())

    assert len(jobs) == 2
    j = jobs[0]
    assert j.company_name == "Beta Data Ltd" and j.source == "reed"
    assert j.external_id == "54123456"
    assert j.title == "Data Engineer" and j.location == "Manchester"
    assert j.url == "https://www.reed.co.uk/jobs/data-engineer/54123456"
    assert j.salary_text == "£50,000 - £60,000"
    assert jobs[1].salary_text == "£70,000+"          # maximumSalary 0 -> open-ended
    # the API key is the basic-auth username, empty password
    auth = responses.calls[0].request.headers["Authorization"]
    assert auth == "Basic " + base64.b64encode(b"REEDKEY:").decode()
    assert "keywords=Data" in responses.calls[0].request.url
    assert "minimumSalary=40000" in responses.calls[0].request.url


@responses.activate
def test_search_reed_returns_empty_on_error():
    responses.add(responses.GET, REED_URL, status=500)
    from discover.aggregators import search_reed
    assert search_reed("k", keywords="x", session=requests.Session()) == []


# ---- query-by-criteria across both sources ---------------------------------

def _criteria(patterns, floor=40000):
    from criteria.loader import Criteria
    return Criteria(profile_id="p-1", name="T", salary_floor=floor,
                    threshold_standard=None, threshold_new_entrant=None,
                    kill_keywords=[], role_patterns=patterns)


def _settings(adzuna=True, reed=True):
    from config import Settings
    return Settings(database_url="x", gemini_api_key="",
                    adzuna_app_id="APPID" if adzuna else "",
                    adzuna_app_key="APPKEY" if adzuna else "",
                    reed_api_key="REEDKEY" if reed else "")


@responses.activate
def test_discover_runs_every_configured_source_and_dedupes():
    responses.add(responses.GET, ADZUNA_URL, json=ADZUNA_SEARCH, status=200)
    responses.add(responses.GET, REED_URL, json=REED_SEARCH, status=200)
    from discover.aggregators import discover_aggregator_jobs

    jobs = discover_aggregator_jobs(_criteria(["Data Engineer"]), _settings(),
                                    session=requests.Session())
    sources = {j.source for j in jobs}
    assert sources == {"adzuna", "reed"}          # both sources ran for the one pattern
    assert len(jobs) == 4                          # 2 + 2, no dupes across the distinct ids


@responses.activate
def test_discover_skips_a_source_without_keys():
    responses.add(responses.GET, REED_URL, json=REED_SEARCH, status=200)
    from discover.aggregators import discover_aggregator_jobs

    jobs = discover_aggregator_jobs(_criteria(["Data Engineer"]), _settings(adzuna=False),
                                    session=requests.Session())
    assert {j.source for j in jobs} == {"reed"}
    # Adzuna was never called (no key) — only the Reed endpoint saw traffic
    assert all("adzuna" not in c.request.url for c in responses.calls)


# ---- broad-sweep pagers (the download-everything mode) ----------------------

@responses.activate
def test_page_adzuna_walks_numbered_pages_with_category():
    responses.add(responses.GET, "https://api.adzuna.com/v1/api/jobs/gb/search/3",
                  json=ADZUNA_SEARCH, status=200)
    from discover.aggregators import page_adzuna
    ads, total = page_adzuna("id", "key", page=3, category="it-jobs")
    assert total == ADZUNA_SEARCH.get("count")
    assert len(ads) == len(ADZUNA_SEARCH["results"])
    url = responses.calls[0].request.url
    assert "category=it-jobs" in url and "what=" not in url
    ad = ads[0]
    assert ad["source"] == "adzuna"
    assert ad["employer_name"] and ad["title"]
    assert "posted_at" in ad and "ad_url" in ad and "external_id" in ad


@responses.activate
def test_page_reed_uses_skip_offset_and_omits_absent_keywords():
    responses.add(responses.GET, REED_URL, json=REED_SEARCH, status=200)
    from discover.aggregators import page_reed
    ads, total = page_reed("k", page=2, results_to_take=100)
    url = responses.calls[0].request.url
    assert "resultsToSkip=100" in url            # page 2 -> skip (2-1)*100
    assert "keywords" not in url                 # full-inventory mode: param omitted
    assert total == REED_SEARCH.get("totalResults")
    assert ads and ads[0]["source"] == "reed"
    assert "posted_at" in ads[0]


def test_reed_date_parses_uk_format_and_survives_garbage():
    from discover.aggregators import _reed_date
    assert _reed_date("20/07/2026") == "2026-07-20"
    assert _reed_date(None) is None
    assert _reed_date("not-a-date") is None


@responses.activate
def test_page_adzuna_carries_salary_band_params():
    responses.add(responses.GET, "https://api.adzuna.com/v1/api/jobs/gb/search/1",
                  json=ADZUNA_SEARCH, status=200)
    from discover.aggregators import page_adzuna
    page_adzuna("id", "key", page=1, category="it-jobs",
                salary_min=25_001, salary_max=32_000)
    url = responses.calls[0].request.url
    assert "salary_min=25001" in url and "salary_max=32000" in url


# ---- attribute partitioning (2026-07-28): salary filters OVERLAP (a £25,155-
# to-£25,155 band reports 12,176 results), so they cannot partition an
# inventory. Location and employer-type are exclusive facts about a job and
# each opens its own depth window. -----------------------------------------

@responses.activate
def test_page_reed_sends_location_distance_and_direct_employer_filters():
    responses.add(responses.GET, REED_URL, json=REED_SEARCH, status=200)
    from discover.aggregators import page_reed
    page_reed("k", page=1, location="Manchester", distance_from_location=15,
              posted_by_direct_employer=True)
    url = responses.calls[0].request.url
    assert "locationName=Manchester" in url
    assert "distanceFromLocation=15" in url
    assert "postedbydirectemployer=true" in url.lower()
    assert "postedbyrecruiter" not in url.lower()      # only one side per slice


@responses.activate
def test_page_reed_recruiter_side_is_the_complement():
    responses.add(responses.GET, REED_URL, json=REED_SEARCH, status=200)
    from discover.aggregators import page_reed
    page_reed("k", page=1, posted_by_recruiter=True)
    url = responses.calls[0].request.url.lower()
    assert "postedbyrecruiter=true" in url
    assert "postedbydirectemployer" not in url


@responses.activate
def test_page_reed_omits_the_new_filters_when_unset():
    responses.add(responses.GET, REED_URL, json=REED_SEARCH, status=200)
    from discover.aggregators import page_reed
    page_reed("k", page=1)
    url = responses.calls[0].request.url.lower()
    for absent in ("locationname", "distancefromlocation",
                   "postedbydirectemployer", "postedbyrecruiter"):
        assert absent not in url
