import responses

from fetch.feeds import (
    dedupe_key,
    fetch_ashby,
    fetch_greenhouse,
    fetch_lever,
    fetch_workable,
    is_uk,
    norm,
)
import requests


# ---- UK filter ----

def test_is_uk_strings():
    assert is_uk("London, UK")
    assert is_uk("London, United Kingdom")
    assert is_uk("Remote - UK")
    assert is_uk("Reading, England")
    assert not is_uk("San Francisco, CA")
    assert not is_uk("Remote")
    assert not is_uk("Tukwila, WA")   # must not match the 'uk' substring
    assert not is_uk("")


def test_is_uk_dict():
    assert is_uk({"city": "London", "country": "United Kingdom", "countryCode": "GB"})
    assert not is_uk({"city": "Berlin", "country": "Germany", "countryCode": "DE"})


# Pinning tests for the migration-0011 residue class: UK city names inside
# foreign locations must NOT pass the filter.
def test_is_uk_rejects_foreign_locations_with_uk_city_names():
    assert not is_uk("Cambridge, MA")                 # the original residue row
    assert not is_uk("Reading, PA")
    assert not is_uk("Birmingham, AL")
    assert not is_uk("London, Ontario, Canada")
    assert not is_uk("Newcastle, South Africa")
    assert not is_uk("Boston or Cambridge, MA (Hybrid)")


def test_is_uk_still_accepts_bare_and_qualified_uk_cities():
    assert is_uk("London")                            # bare UK city stays valid (Lever style)
    assert is_uk("Cambridge")
    assert is_uk("Cambridge, England")
    assert is_uk("Remote (London)")
    assert is_uk("London or Manchester")              # 'or' must not read as Oregon


def test_is_uk_dict_foreign_country_code_is_authoritative():
    assert not is_uk({"city": "London", "country": "Canada", "countryCode": "CA"})
    assert is_uk({"city": "London", "country": "United Kingdom"})   # full name, no code


# ---- helpers ----

def test_title_normalisation_in_dedupe_uses_shared_norm():
    assert norm("  Senior   Engineer ") == "senior engineer"


def test_dedupe_key_golden_value():
    # Pins the exact algorithm: changing normalisation or the base format
    # changes every stored dedupe_key and breaks upsert matching against the
    # ~750 existing rows. If this test fails, you are migrating data, not
    # "just refactoring".
    assert dedupe_key("Anthropic", "Solutions Engineer", "https://x/1") == \
        "60899a95bc2b7f8865e77463b8906adf0a98b3a4"


# salary text extraction moved to analysis.salary.salary_text_from (GA-007);
# fetch no longer reads salary — see tests/test_salary.py::test_salary_text_from.


def test_dedupe_key_stable_and_distinct():
    a = dedupe_key("Anthropic", "Solutions Engineer", "https://x/1")
    b = dedupe_key("anthropic", "  solutions   engineer ", "https://x/1")
    c = dedupe_key("Anthropic", "Solutions Engineer", "https://x/2")
    assert a == b          # case/space-insensitive
    assert a != c          # different url -> different role


# ---- parsers ----

@responses.activate
def test_fetch_greenhouse():
    responses.add(
        responses.GET,
        "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true",
        json={"jobs": [{
            "id": 123, "title": "Solutions Engineer",
            "location": {"name": "London, UK"},
            "absolute_url": "https://boards.greenhouse.io/anthropic/jobs/123",
            "content": "<p>Build things. Salary £80,000.</p>",
        }]},
        status=200,
    )
    jobs = fetch_greenhouse("Anthropic", "anthropic", requests.Session())
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Solutions Engineer"
    assert is_uk(j.location)
    assert j.salary_text is None   # fetch no longer reads salary (GA-007); the reader fills it
    assert "Build things" in j.jd_text


@responses.activate
def test_fetch_lever():
    responses.add(
        responses.GET,
        "https://api.lever.co/v0/postings/palantir?mode=json",
        json=[{
            "id": "abc", "text": "Forward Deployed Engineer",
            "categories": {"location": "London"},
            "hostedUrl": "https://jobs.lever.co/palantir/abc",
            "description": "<div>Deploy forward.</div>",
        }],
        status=200,
    )
    jobs = fetch_lever("Palantir", "palantir", requests.Session())
    assert len(jobs) == 1
    assert jobs[0].location == "London"
    assert "Deploy forward" in jobs[0].jd_text


@responses.activate
def test_fetch_ashby():
    responses.add(
        responses.GET,
        "https://api.ashbyhq.com/posting-api/job-board/cohere?includeCompensation=true",
        json={"jobs": [{
            "id": "j1", "title": "AI Engineer",
            "location": "London, United Kingdom",
            "jobUrl": "https://jobs.ashbyhq.com/cohere/j1",
            "descriptionPlain": "Train models.",
        }]},
        status=200,
    )
    jobs = fetch_ashby("Cohere", "cohere", requests.Session())
    assert len(jobs) == 1
    assert is_uk(jobs[0].location)
    assert jobs[0].jd_text == "Train models."


# ---- retry on transient HTTP failures ----

GH_URL = "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true"


@responses.activate
def test_fetch_retries_transient_503_then_succeeds(monkeypatch):
    from fetch import feeds
    sleeps = []
    monkeypatch.setattr(feeds, "_sleep", lambda s: sleeps.append(s))
    responses.add(responses.GET, GH_URL, json={"error": "overloaded"}, status=503)
    responses.add(responses.GET, GH_URL, json={"jobs": []}, status=200)
    jobs = fetch_greenhouse("Anthropic", "anthropic", requests.Session())
    assert jobs == []
    assert len(responses.calls) == 2    # one failure, one retry that succeeded
    assert sleeps == [1]


@responses.activate
def test_fetch_gives_up_after_max_tries(monkeypatch):
    from fetch import feeds
    monkeypatch.setattr(feeds, "_sleep", lambda s: None)
    for _ in range(feeds.MAX_TRIES):
        responses.add(responses.GET, GH_URL, json={}, status=503)
    try:
        fetch_greenhouse("Anthropic", "anthropic", requests.Session())
        assert False, "expected HTTPError after retries exhausted"
    except requests.HTTPError:
        pass
    assert len(responses.calls) == feeds.MAX_TRIES


@responses.activate
def test_fetch_does_not_retry_hard_404():
    responses.add(responses.GET, GH_URL, json={}, status=404)
    try:
        fetch_greenhouse("Anthropic", "anthropic", requests.Session())
        assert False, "expected HTTPError"
    except requests.HTTPError:
        pass
    assert len(responses.calls) == 1    # a 404 is a real answer, not a blip


@responses.activate
def test_fetch_workable():
    responses.add(
        responses.POST,
        "https://apply.workable.com/api/v3/accounts/starling-bank/jobs",
        json={"results": [{
            "shortcode": "X1", "title": "ML Engineer",
            "location": {"city": "London", "country": "United Kingdom", "countryCode": "GB"},
            "url": "https://apply.workable.com/starling-bank/j/X1",
        }]},
        status=200,
    )
    jobs = fetch_workable("Starling Bank", "starling-bank", requests.Session())
    assert len(jobs) == 1
    assert is_uk(jobs[0].location)
    assert jobs[0].external_id == "X1"
