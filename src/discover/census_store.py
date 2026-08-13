"""Census persistence: every sweep write lands in sponsor_census/census_jobs.

The blast-radius rule made physical: this module is the sweep's only door to
the database, and its SQL names exactly two tables — sponsor_census (one card
per unique register organisation) and census_jobs (lightweight job rows, no JD
body). Column names stay country-neutral (registry_*, industry_codes,
local_jobs_seen): the UK register is the first dataset, not the schema's
identity. Job identity reuses the shared fetch.feeds.dedupe_key.
"""
from __future__ import annotations

from fetch.feeds import dedupe_key

PROBE_OUTCOMES = ("board_found", "no_board", "already_tracked", "error")
REGISTRY_OUTCOMES = ("matched", "ambiguous", "not_found", "error")


def upsert_probe(cur, org, *, outcome, ats_type=None, ats_token=None,
                 careers_url=None, total_jobs_seen=None, local_jobs_seen=None,
                 probe_error=None) -> None:
    """Write one org's probe result; re-probing (retry-errors) updates in place.

    The conflict branch touches only the probe columns — registry findings on
    the same card survive a re-probe untouched.
    """
    cur.execute(
        "insert into sponsor_census "
        "(org_name_norm, sponsor_id, organisation_name, town_city, "
        " is_skilled_worker, rating, probed_at, probe_outcome, ats_type, "
        " ats_token, careers_url, local_jobs_seen, total_jobs_seen, probe_error) "
        "values (%s, %s, %s, %s, %s, %s, now(), %s, %s, %s, %s, %s, %s, %s) "
        "on conflict (org_name_norm) do update set "
        " probed_at = now(), probe_outcome = excluded.probe_outcome, "
        " ats_type = excluded.ats_type, ats_token = excluded.ats_token, "
        " careers_url = excluded.careers_url, "
        " local_jobs_seen = excluded.local_jobs_seen, "
        " total_jobs_seen = excluded.total_jobs_seen, "
        " probe_error = excluded.probe_error",
        (org["org_name_norm"], org.get("sponsor_id"), org.get("organisation_name"),
         org.get("town_city"), org.get("is_skilled_worker"), org.get("rating"),
         outcome, ats_type, ats_token, careers_url, local_jobs_seen,
         total_jobs_seen, probe_error))


def update_probe_fetch(cur, org_name_norm, *, local_jobs_seen,
                       probe_error=None) -> None:
    """After the one-time job fetch: set the local count, or note its failure.

    NULL local_jobs_seen means the fetch failed; 0 means it worked and found
    no local jobs — the distinction is pinned by tests.
    """
    cur.execute(
        "update sponsor_census set local_jobs_seen = %s, probe_error = %s "
        "where org_name_norm = %s",
        (local_jobs_seen, probe_error, org_name_norm))


def insert_census_jobs(cur, org_name_norm, jobs, title_matcher,
                       local_matcher) -> tuple[int, int]:
    """Store lightweight job rows for one org; returns (attempted, matched).

    Every job the caller passes is stored (founder rule 2026-07-16: keep
    everything, filter at query time). title_matcher (owner's keyword role
    matcher) and local_matcher (register-country check) stamp the title_match
    and is_local labels — no AI in the census, and neither matcher filters.
    ON CONFLICT DO NOTHING: the shared dedupe_key swallows intra-feed
    duplicates and retry re-fetches alike.
    """
    if not jobs:
        return (0, 0)
    rows = [(org_name_norm, j.company_name, j.source, j.title, j.location,
             j.url, j.salary_text, bool(title_matcher(j.title)),
             bool(local_matcher(j.location)),
             dedupe_key(j.company_name, j.title, j.url))
            for j in jobs]
    cur.executemany(
        "insert into census_jobs "
        "(org_name_norm, company_name, source, title, location, url, "
        " salary_text, title_match, is_local, dedupe_key) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "on conflict (dedupe_key) do nothing",
        rows)
    return (len(rows), sum(1 for r in rows if r[7]))


def ensure_census_card(cur, org) -> None:
    """Create a bare census card for an org if none exists yet (idempotent).

    Pass 1 (Companies House classification) calls this before writing registry
    data, so a company that has never been job-probed still gets a card to hang
    its industry code on. probe_outcome stays NULL until Pass 2 probes it.
    """
    cur.execute(
        "insert into sponsor_census "
        "(org_name_norm, sponsor_id, organisation_name, town_city, "
        " is_skilled_worker, rating) values (%s, %s, %s, %s, %s, %s) "
        "on conflict (org_name_norm) do nothing",
        (org["org_name_norm"], org.get("sponsor_id"), org.get("organisation_name"),
         org.get("town_city"), org.get("is_skilled_worker"), org.get("rating")))


def classify_status_counts(cur, software_sic) -> dict:
    """Pass 1 scoreboard: classified totals, outcomes, software-SIC matches."""
    cur.execute(
        "select count(distinct org_name_norm) as total from licensed_sponsors "
        "where org_name_norm is not null and org_name_norm <> ''")
    total = cur.fetchone()["total"]

    cur.execute(
        "select registry_outcome, count(*) as n from sponsor_census "
        "where registry_checked_at is not null group by registry_outcome")
    by_outcome = {r["registry_outcome"]: r["n"] for r in cur.fetchall()}

    cur.execute(
        "select count(*) as n from sponsor_census "
        "where industry_codes && %s::text[]", (list(software_sic),))
    software = cur.fetchone()["n"]

    classified = sum(by_outcome.values())
    return {
        "total_unique_orgs": total,
        "classified": classified,
        "by_outcome": by_outcome,
        "software_companies": software,
        "remaining": max(0, total - classified),
    }


def record_registry_result(cur, org_name_norm, outcome, *, number=None,
                           status=None, company_type=None, industry_codes=None,
                           incorporated=None, error=None) -> None:
    """Write one org's national-registry findings; never touches the ATS columns."""
    cur.execute(
        "update sponsor_census set registry_checked_at = now(), "
        " registry_outcome = %s, registry_number = %s, registry_status = %s, "
        " registry_type = %s, industry_codes = %s, incorporated = %s, "
        " registry_error = %s "
        "where org_name_norm = %s",
        (outcome, number, status, company_type, industry_codes, incorporated,
         error, org_name_norm))


def census_status_counts(cur) -> dict:
    """The census scoreboard: totals, outcomes, jobs, matches, remaining."""
    cur.execute(
        "select count(distinct org_name_norm) as total from licensed_sponsors "
        "where org_name_norm is not null and org_name_norm <> ''")
    total = cur.fetchone()["total"]

    cur.execute(
        "select probe_outcome, count(*) as n from sponsor_census "
        "where probe_outcome is not null group by probe_outcome")
    by_outcome = {r["probe_outcome"]: r["n"] for r in cur.fetchall()}

    cur.execute(
        "select count(*) as jobs, "
        "count(*) filter (where title_match) as matches from census_jobs")
    jobs_row = cur.fetchone()

    cur.execute(
        "select registry_outcome, count(*) as n from sponsor_census "
        "where registry_outcome is not null group by registry_outcome")
    registry = {r["registry_outcome"]: r["n"] for r in cur.fetchall()}

    probed = sum(by_outcome.values())
    return {
        "total_unique_orgs": total,
        "probed": probed,
        "by_outcome": by_outcome,
        "boards_found": by_outcome.get("board_found", 0),
        "census_jobs": jobs_row["jobs"],
        "title_matches": jobs_row["matches"],
        "registry_by_outcome": registry,
        "remaining": max(0, total - probed),
    }
