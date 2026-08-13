"""Tests for src/fetch/workday — the Workday CXS board adapter.

Offline: the CXS list/detail endpoints are mocked with `responses`, driven by
fixtures recorded from real tenants on 2026-07-11 (tests/fixtures/workday/,
captured from NVIDIA, Adobe, Salesforce). We prove URL parsing, pagination, the
UK filter, detail-fetch, the Job mapping, and that fetch_company dispatches
Workday through the standard pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests
import responses

FIX = Path(__file__).parent / "fixtures" / "workday"


def fx(name):
    return json.loads((FIX / name).read_text())


NV_LIST = fx("nvidia_list_uk_p1.json")
NV_DETAIL = fx("nvidia_detail_uk.json")
CXS = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"


# ---- URL parsing ------------------------------------------------------------

def test_parse_workday_url_from_careers_and_cxs_and_locale_forms():
    from fetch.workday import parse_workday_url
    b = parse_workday_url("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite")
    assert (b.host, b.tenant, b.site) == (
        "nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite")
    assert b.cxs_base == CXS
    # locale segment is skipped
    assert parse_workday_url(
        "https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced").site == "external_experienced"
    # the CXS form is parsed straight back
    assert parse_workday_url(CXS + "/jobs").site == "NVIDIAExternalCareerSite"


def test_parse_workday_url_rejects_non_workday_urls():
    from fetch.workday import parse_workday_url
    assert parse_workday_url("https://boards.greenhouse.io/acme") is None
    assert parse_workday_url("") is None
    assert parse_workday_url(None) is None


# ---- fetch (paginate -> UK filter -> detail -> Job) ------------------------

@responses.activate
def test_fetch_workday_pages_filters_uk_and_maps_jobs():
    # page 1 has two UK postings; total=3 forces a second page which comes back
    # empty (end of results).
    responses.add(responses.POST, f"{CXS}/jobs", json=NV_LIST, status=200)
    responses.add(responses.POST, f"{CXS}/jobs", json={"total": 3, "jobPostings": []}, status=200)
    # each posting's detail (same fixture body is fine for the shape)
    responses.add(responses.GET, f"{CXS}/job/UK-Remote/GSI-Client-Manager_JR2015716",
                  json=NV_DETAIL, status=200)
    responses.add(
        responses.GET,
        f"{CXS}/job/UK-Remote/Senior-Developer-Relations-Manager---Capital-Markets_JR2016616-1",
        json=NV_DETAIL, status=200)

    from fetch.workday import fetch_workday
    jobs = fetch_workday("NVIDIA",
                         "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
                         requests.Session())

    assert len(jobs) == 2
    j = jobs[0]
    assert j.company_name == "NVIDIA" and j.source == "workday"
    assert j.external_id == "JR2015716"
    assert j.title == "GSI Client Manager"
    assert j.location == "UK, Remote" and __import__("fetch.feeds", fromlist=["is_uk"]).is_uk(j.location)
    assert j.url.endswith("/job/UK-Remote/GSI-Client-Manager_JR2015716")
    assert "Build GPU systems." in j.jd_text and "<p>" not in j.jd_text   # HTML stripped
    assert j.salary_text is None


@responses.activate
def test_fetch_workday_keeps_non_uk_postings_shallow_without_detail_call():
    # Keep-all (founder rule 2026-07-16): a non-UK posting is STORED from the
    # cheap listing row — labelled by its location — but never costs a detail
    # call, so the per-company call bound is unchanged.
    non_uk = {"total": 1, "jobPostings": [{
        "title": "Senior Applied Scientist", "externalPath": "/job/San-Jose/ML_R1",
        "locationsText": "San Jose", "postedOn": "Posted Today", "bulletFields": ["R1"]}]}
    responses.add(responses.POST, f"{CXS}/jobs", json=non_uk, status=200)

    from fetch.workday import fetch_workday
    jobs = fetch_workday("NVIDIA", CXS + "/jobs", requests.Session())

    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Senior Applied Scientist"
    assert j.location == "San Jose" and j.external_id == "R1"
    assert j.jd_text == ""                                  # shallow: no JD fetched
    assert j.url == ("https://nvidia.wd5.myworkdayjobs.com/"
                     "NVIDIAExternalCareerSite/job/San-Jose/ML_R1")
    # only the list POST happened — no detail GET for a non-UK job
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_workday_keeps_detail_relocated_job_labelled_not_dropped():
    # Listing said UK, the precise detail says Canada: the job is KEPT with the
    # precise location (label), not silently dropped as before.
    lst = {"total": 1, "jobPostings": [{
        "title": "GSI Client Manager",
        "externalPath": "/job/UK-Remote/GSI-Client-Manager_JR2015716",
        "locationsText": "UK, Remote", "bulletFields": ["JR2015716"]}]}
    detail = {**NV_DETAIL,
              "jobPostingInfo": {**NV_DETAIL["jobPostingInfo"],
                                 "location": "Toronto, Ontario, Canada"}}
    responses.add(responses.POST, f"{CXS}/jobs", json=lst, status=200)
    responses.add(responses.GET,
                  f"{CXS}/job/UK-Remote/GSI-Client-Manager_JR2015716",
                  json=detail, status=200)

    from fetch.workday import fetch_workday
    jobs = fetch_workday("NVIDIA", CXS + "/jobs", requests.Session())

    assert len(jobs) == 1
    assert jobs[0].location == "Toronto, Ontario, Canada"
    assert jobs[0].jd_text                                  # detail JD kept


@responses.activate
def test_fetch_workday_respects_max_jobs_cap():
    responses.add(responses.POST, f"{CXS}/jobs", json=NV_LIST, status=200)
    responses.add(responses.GET, f"{CXS}/job/UK-Remote/GSI-Client-Manager_JR2015716",
                  json=NV_DETAIL, status=200)

    from fetch.workday import fetch_workday
    jobs = fetch_workday("NVIDIA", CXS, requests.Session(), max_jobs=1)
    assert len(jobs) == 1                    # stopped after the cap, no second detail


def test_fetch_workday_returns_empty_for_a_non_workday_url():
    from fetch.workday import fetch_workday
    assert fetch_workday("Acme", "https://acme.com/careers") == []


# ---- integration with the standard dispatch --------------------------------

@responses.activate
def test_fetch_company_dispatches_workday_through_the_standard_entrypoint():
    responses.add(responses.POST, f"{CXS}/jobs",
                  json={"total": 0, "jobPostings": []}, status=200)
    from fetch.feeds import fetch_company
    # ats_token carries the careers URL for Workday companies
    jobs = fetch_company("NVIDIA", "workday", CXS, requests.Session())
    assert jobs == []
    assert len(responses.calls) == 1


# ---- the recorded fixtures are real, cross-tenant Workday shapes ------------

def test_recorded_fixtures_share_the_workday_shape_across_three_tenants():
    for name in ("nvidia_list_uk_p1", "adobe_list_sample", "salesforce_list_sample"):
        data = fx(f"{name}.json")
        assert "total" in data and "jobPostings" in data
        post = data["jobPostings"][0]
        assert {"title", "externalPath", "locationsText", "bulletFields"} <= post.keys()
