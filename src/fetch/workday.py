"""Workday board adapter — the public CXS (Career eXperience Service) JSON API.

A company's Workday careers site is backed by two endpoints:
  * POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    — a paginated listing (body: appliedFacets/limit/offset/searchText).
  * GET  .../wday/cxs/{tenant}/{site}{externalPath}
    — one job's detail, including the HTML description.

Shapes captured 2026-07-11 from real tenants (NVIDIA, Adobe, Salesforce) — see
tests/fixtures/workday/. Workday boards can't be guessed by a slug probe, so a
company is onboarded from its careers URL (stored in ats_token); this adapter
parses that URL, pages the listing, UK-filters on the cheap listing field, then
fetches detail only for survivors — bounding the per-job calls. Output is the
standard Job, so history/read/persist treat it like any other feed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from fetch.feeds import Job, _get, _strip_html, is_uk

_WORKDAY_HOST_RE = re.compile(r"\.myworkdayjobs\.com$", re.I)
_LOCALE_RE = re.compile(r"^[a-z]{2}-[a-z]{2}$", re.I)      # skip 'en-US' path segments

PAGE_SIZE = 20
DEFAULT_MAX_JOBS = 100        # cap on UK jobs (and detail calls) per company/run
DEFAULT_MAX_PAGES = 50        # cap on listing pages scanned (large boards)


@dataclass(frozen=True)
class WorkdayBoard:
    host: str        # nvidia.wd5.myworkdayjobs.com
    tenant: str      # nvidia
    site: str        # NVIDIAExternalCareerSite

    @property
    def cxs_base(self) -> str:
        return f"https://{self.host}/wday/cxs/{self.tenant}/{self.site}"


def parse_workday_url(url: str | None) -> WorkdayBoard | None:
    """Derive a WorkdayBoard from a myworkdayjobs careers or CXS URL, else None."""
    if not url:
        return None
    parsed = urlparse(url if "//" in url else "https://" + url)
    host = parsed.netloc.lower()
    if not _WORKDAY_HOST_RE.search(host):
        return None
    segs = [s for s in parsed.path.split("/") if s]
    # CXS form: /wday/cxs/{tenant}/{site}/... — tenant + site are explicit.
    if segs[:2] == ["wday", "cxs"] and len(segs) >= 4:
        return WorkdayBoard(host, segs[2], segs[3])
    # Careers form: /{locale?}/{site}/... — site is the first non-locale segment.
    path_segs = [s for s in segs if not _LOCALE_RE.match(s)]
    if not path_segs:
        return None
    return WorkdayBoard(host, host.split(".")[0], path_segs[0])


def _list_page(board: WorkdayBoard, session, offset: int) -> dict | None:
    return _get(f"{board.cxs_base}/jobs", session, method="POST",
                json_body={"appliedFacets": {}, "limit": PAGE_SIZE,
                           "offset": offset, "searchText": ""})


def _detail(board: WorkdayBoard, external_path: str, session) -> dict | None:
    return _get(f"{board.cxs_base}{external_path}", session)


def _to_job(company_name: str, posting: dict, info: dict, location: str) -> Job:
    bullet = (posting.get("bulletFields") or [""])
    return Job(
        company_name=company_name,
        source="workday",
        external_id=info.get("jobReqId") or (bullet[0] if bullet else ""),
        title=info.get("title") or posting.get("title", ""),
        location=location,
        url=info.get("externalUrl") or "",
        jd_text=_strip_html(info.get("jobDescription")),
        salary_text=None,          # the reader fills salary later (GA-007)
    )


def _shallow_job(company_name: str, board: WorkdayBoard, posting: dict) -> Job:
    """A listing-level Job for a non-UK posting: labelled, stored, no JD call."""
    bullet = (posting.get("bulletFields") or [""])
    path = posting.get("externalPath") or ""
    return Job(
        company_name=company_name,
        source="workday",
        external_id=bullet[0] if bullet else "",
        title=posting.get("title", ""),
        location=posting.get("locationsText") or "",
        url=f"https://{board.host}/{board.site}{path}",
        jd_text="",
        salary_text=None,
    )


def fetch_workday(company_name: str, board_url, session=None, *,
                  max_jobs: int = DEFAULT_MAX_JOBS,
                  max_pages: int = DEFAULT_MAX_PAGES) -> list[Job]:
    """Fetch a company's Workday listings as standard Job rows — keep-all.

    Pages the CXS listing (bounded by max_pages) and keeps EVERY posting
    (founder rule 2026-07-16: labels, never filters). UK-looking postings get
    a detail call for the full JD and a precise location; non-UK postings are
    stored shallow from the listing row — no detail call, so the per-company
    call bound is unchanged. A detail that relocates a job abroad keeps the
    job with its precise location. Stops at max_jobs stored. A bad single
    detail is skipped, not fatal. Returns [] for a non-Workday URL.
    """
    board = board_url if isinstance(board_url, WorkdayBoard) else parse_workday_url(board_url)
    if board is None:
        return []
    session = session or requests.Session()

    jobs: list[Job] = []
    for page in range(max_pages):
        data = _list_page(board, session, page * PAGE_SIZE) or {}
        postings = data.get("jobPostings") or []
        if not postings:
            break
        for posting in postings:
            if not is_uk(posting.get("locationsText") or ""):
                jobs.append(_shallow_job(company_name, board, posting))
                if len(jobs) >= max_jobs:
                    return jobs
                continue
            external_path = posting.get("externalPath")
            if not external_path:
                continue
            try:
                detail = _detail(board, external_path, session) or {}
            except requests.RequestException:
                continue                       # one dud detail never sinks the company
            info = detail.get("jobPostingInfo") or {}
            location = info.get("location") or posting.get("locationsText") or ""
            jobs.append(_to_job(company_name, posting, info, location))
            if len(jobs) >= max_jobs:
                return jobs
        if (page + 1) * PAGE_SIZE >= data.get("total", 0):
            break
    return jobs
