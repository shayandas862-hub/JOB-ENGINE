"""Adzuna and Reed job-search API clients — discovery beyond the target list.

Both are official, free, documented job-search APIs (no scraping):
  * Adzuna: GET api.adzuna.com/v1/api/jobs/gb/search/1?app_id=&app_key=&what=&where=
  * Reed:   GET www.reed.co.uk/api/1.0/search?keywords=&locationName=  (HTTP Basic
            auth: the API key is the username, the password is empty)

Contracts confirmed 2026-07-11 from the providers' docs; response fixtures live
in tests/fixtures/aggregators/. Results are normalised into the standard Job so
the rest of the pipeline treats them like any feed. Employers still have to be
cross-checked against the sponsor register (Task 6) before they carry a verdict.
Keys come from .env via config; a blank key means that source is simply skipped.
"""
from __future__ import annotations

import time

import requests

from budget.gate import charge_for
from fetch.ats import HEADERS, MAX_TRIES, RETRY_STATUSES
from fetch.feeds import Job, _strip_html, dedupe_key

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"
REED_BASE = "https://www.reed.co.uk/api/1.0"
UK_COUNTRY = "gb"
TIMEOUT = 15
_sleep = time.sleep     # module-level so tests can stub the backoff


def _salary_text(low, high) -> str | None:
    """A human salary string from a numeric range; None when nothing is stated.

    Adzuna omits the field; Reed uses 0 for an unset bound — both read as open."""
    low = low or None
    high = high or None
    if low and high:
        return f"£{low:,.0f} - £{high:,.0f}"
    if low:
        return f"£{low:,.0f}+"
    if high:
        return f"up to £{high:,.0f}"
    return None


def _get_json(url: str, session, *, params=None, auth=None):
    """GET JSON with transient-retry; returns parsed JSON or None on any failure.

    Aggregators degrade quietly — a down or rate-limited source must never crash
    the discovery run or the daily pipeline.

    The ONE place Adzuna and Reed are actually called, and therefore where the
    budget is enforced (task 5): every tool that reaches these APIs, now or
    later, inherits the cap from here. Charged per ATTEMPT, because a retried
    503 costs the provider's quota exactly what a 200 costs it. A refusal
    raises out — it is the one failure here that must not degrade quietly,
    since continuing would mean spending a budget that is already gone."""
    for attempt in range(MAX_TRIES):
        charge_for(url)
        try:
            resp = session.get(url, headers=HEADERS, params=params, auth=auth,
                               timeout=TIMEOUT)
        except requests.RequestException:
            if attempt == MAX_TRIES - 1:
                return None
            _sleep(2 ** attempt)
            continue
        if resp.status_code in RETRY_STATUSES and attempt < MAX_TRIES - 1:
            _sleep(2 ** attempt)
            continue
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None
    return None


def search_adzuna(app_id: str, app_key: str, *, what: str, where: str = "UK",
                  results_per_page: int = 50, salary_min=None, max_days_old=None,
                  country: str = UK_COUNTRY, session=None) -> list[Job]:
    """Query Adzuna for one keyword; return standard Job rows (employer per result)."""
    session = session or requests.Session()
    params = {"app_id": app_id, "app_key": app_key, "what": what, "where": where,
              "results_per_page": results_per_page, "content-type": "application/json"}
    if salary_min:
        params["salary_min"] = int(salary_min)
    if max_days_old:
        params["max_days_old"] = int(max_days_old)
    data = _get_json(f"{ADZUNA_BASE}/{country}/search/1", session, params=params)

    jobs: list[Job] = []
    for r in (data or {}).get("results", []):
        jobs.append(Job(
            company_name=(r.get("company") or {}).get("display_name", "") or "",
            source="adzuna", external_id=str(r.get("id", "")),
            title=r.get("title", "") or "",
            location=(r.get("location") or {}).get("display_name", "") or "",
            url=r.get("redirect_url", "") or "",
            jd_text=_strip_html(r.get("description")),
            salary_text=_salary_text(r.get("salary_min"), r.get("salary_max"))))
    return jobs


def search_reed(api_key: str, *, keywords: str, location: str = "",
                results_to_take: int = 50, minimum_salary=None, distance=None,
                session=None) -> list[Job]:
    """Query Reed for one keyword; return standard Job rows (employer per result)."""
    session = session or requests.Session()
    params = {"keywords": keywords, "resultsToTake": results_to_take}
    if location:
        params["locationName"] = location
    if minimum_salary:
        params["minimumSalary"] = int(minimum_salary)
    if distance:
        params["distanceFromLocation"] = int(distance)
    # Reed auth: API key as the basic-auth username, empty password.
    data = _get_json(f"{REED_BASE}/search", session, params=params, auth=(api_key, ""))

    jobs: list[Job] = []
    for r in (data or {}).get("results", []):
        job_id = r.get("jobId")
        jobs.append(Job(
            company_name=r.get("employerName", "") or "",
            source="reed", external_id=str(job_id or ""),
            title=r.get("jobTitle", "") or "",
            location=r.get("locationName", "") or "",
            url=r.get("jobUrl") or (f"https://www.reed.co.uk/jobs/{job_id}" if job_id else ""),
            jd_text=_strip_html(r.get("jobDescription")),
            salary_text=_salary_text(r.get("minimumSalary"), r.get("maximumSalary"))))
    return jobs


def reed_job_details(api_key: str, job_id: str, session=None) -> str | None:
    """One Reed job's full description — the JD drip's supply (U5), cleaned
    by the shared stripper. None on any failure: the drip degrades, never
    dies. Adzuna has no equivalent endpoint, which is why the drip is
    Reed-only."""
    session = session or requests.Session()
    data = _get_json(f"{REED_BASE}/jobs/{job_id}", session, auth=(api_key, ""))
    text = _strip_html((data or {}).get("jobDescription"))
    return text or None


# ---- broad-sweep pagers (the download-everything mode) ----------------------
# Unlike the keyword helpers above, these walk a WHOLE inventory page by page
# and return raw ad dicts for the keep-all raw layer (aggregator_ads) — the
# founder's jobs-first design 2026-07-22: no role-keyword map; the register is
# the filter, applied later in SQL at zero API cost.

def _reed_date(raw: str | None) -> str | None:
    """Reed's dd/mm/yyyy posting date as ISO, or None when absent/garbled."""
    if not raw:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(raw.strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _adzuna_ad(r: dict) -> dict:
    return {
        "source": "adzuna", "external_id": str(r.get("id", "") or ""),
        "employer_name": (r.get("company") or {}).get("display_name", "") or "",
        "title": r.get("title", "") or "",
        "location": (r.get("location") or {}).get("display_name", "") or "",
        "salary_min": r.get("salary_min"), "salary_max": r.get("salary_max"),
        "salary_text": _salary_text(r.get("salary_min"), r.get("salary_max")),
        "posted_at": (r.get("created") or "")[:10] or None,
        "ad_url": r.get("redirect_url", "") or "",
        "snippet": _strip_html(r.get("description")),
    }


def _reed_ad(r: dict) -> dict:
    job_id = r.get("jobId")
    return {
        "source": "reed", "external_id": str(job_id or ""),
        "employer_name": r.get("employerName", "") or "",
        "title": r.get("jobTitle", "") or "",
        "location": r.get("locationName", "") or "",
        "salary_min": r.get("minimumSalary"), "salary_max": r.get("maximumSalary"),
        "salary_text": _salary_text(r.get("minimumSalary"), r.get("maximumSalary")),
        "posted_at": _reed_date(r.get("date")),
        "ad_url": r.get("jobUrl")
                  or (f"https://www.reed.co.uk/jobs/{job_id}" if job_id else ""),
        "snippet": _strip_html(r.get("jobDescription")),
    }


def page_adzuna(app_id: str, app_key: str, *, page: int, what: str | None = None,
                category: str | None = None, where: str | None = None,
                results_per_page: int = 50, max_days_old=None,
                salary_min: int | None = None, salary_max: int | None = None,
                country: str = UK_COUNTRY,
                session=None) -> tuple[list[dict], int | None]:
    """One numbered Adzuna page as raw ads + the provider's total count.

    With neither `what` nor `category` this walks the entire country inventory;
    a category (e.g. 'it-jobs') narrows the slice without any keyword leak.
    The salary bounds are band-partition filters — Adzuna silently stops
    yielding new ads at roughly 5k results per query (live 2026-07-25), so
    big slices are walked as salary bands like Reed."""
    session = session or requests.Session()
    params = {"app_id": app_id, "app_key": app_key,
              "results_per_page": results_per_page,
              "content-type": "application/json"}
    if what:
        params["what"] = what
    if category:
        params["category"] = category
    if where:
        params["where"] = where
    if max_days_old:
        params["max_days_old"] = int(max_days_old)
    if salary_min is not None:
        params["salary_min"] = int(salary_min)
    if salary_max is not None:
        params["salary_max"] = int(salary_max)
    data = _get_json(f"{ADZUNA_BASE}/{country}/search/{page}", session,
                     params=params) or {}
    total = data.get("count")
    return [_adzuna_ad(r) for r in data.get("results", [])], total


def page_reed(api_key: str, *, page: int, keywords: str | None = None,
              location: str | None = None, results_to_take: int = 100,
              minimum_salary: int | None = None,
              maximum_salary: int | None = None,
              distance_from_location: int | None = None,
              posted_by_direct_employer: bool = False,
              posted_by_recruiter: bool = False,
              session=None) -> tuple[list[dict], int | None]:
    """One Reed page (1-based; offset = (page-1)*take) as raw ads + total.

    `keywords=None` omits the parameter entirely — the full-inventory mode.

    Two kinds of narrowing, and the difference decides coverage (proved live
    2026-07-28): the salary bounds OVERLAP — a job advertised '£20k-£30k'
    answers every band between them, so a £25,155-to-£25,155 band still
    reports 12,176 results and salary can never partition the inventory.
    Location and poster type are exclusive facts about a job, so each
    combination opens its OWN 10k-deep window past Reed's wall."""
    session = session or requests.Session()
    params = {"resultsToTake": results_to_take,
              "resultsToSkip": (page - 1) * results_to_take}
    if keywords:
        params["keywords"] = keywords
    if location:
        params["locationName"] = location
    if distance_from_location is not None:
        params["distanceFromLocation"] = int(distance_from_location)
    if posted_by_direct_employer:
        params["postedByDirectEmployer"] = "true"
    if posted_by_recruiter:
        params["postedByRecruiter"] = "true"
    if minimum_salary is not None:
        params["minimumSalary"] = int(minimum_salary)
    if maximum_salary is not None:
        params["maximumSalary"] = int(maximum_salary)
    data = _get_json(f"{REED_BASE}/search", session, params=params,
                     auth=(api_key, "")) or {}
    total = data.get("totalResults")
    return [_reed_ad(r) for r in data.get("results", [])], total


def discover_aggregator_jobs(criteria, settings, *, session=None,
                             per_query: int = 50, max_days_old=None) -> list[Job]:
    """Run every configured aggregator over the profile's role patterns; dedupe.

    A source with no key is skipped. Deduped by the shared dedupe_key so the same
    role surfacing on both sources (or on repeated patterns) counts once.
    """
    session = session or requests.Session()
    collected: list[Job] = []
    for pattern in criteria.role_patterns or []:
        if settings.adzuna_ready:
            collected += search_adzuna(
                settings.adzuna_app_id, settings.adzuna_app_key, what=pattern,
                where="UK", results_per_page=per_query,
                salary_min=criteria.salary_floor, max_days_old=max_days_old,
                session=session)
        if settings.reed_ready:
            collected += search_reed(
                settings.reed_api_key, keywords=pattern, location="UK",
                results_to_take=per_query, minimum_salary=criteria.salary_floor,
                session=session)

    seen: set[str] = set()
    unique: list[Job] = []
    for job in collected:
        key = dedupe_key(job.company_name, job.title, job.url)
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique
