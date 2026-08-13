"""Rules for what a fetch run may do to companies and their listings."""
from __future__ import annotations

from fetch.feeds import dedupe_key, is_uk
from history.fingerprint import fingerprint


def fetch_outcome(job_count: int, previous_feed_status: str | None) -> tuple[str, bool]:
    """New feed_status and whether this company's stale listings may be closed.

    A feed that returned jobs is 'ok' and its vanished listings close normally.
    An empty feed marks the company 'empty' but only allows job-rot after TWO
    consecutive empty runs — a glitchy feed returning [] once must not
    mass-close real listings.
    """
    if job_count > 0:
        return "ok", True
    return "empty", previous_feed_status == "empty"


UPSERT_SQL = """
insert into role_listings
  (company_id, role_title, location, role_url, jd_full, salary_text,
   source, is_local,
   role_status, feed_status, content_fingerprint, dedupe_key, last_seen_run)
values (%s,%s,%s,%s,%s,%s,%s,%s,'open','ok',%s,%s,%s)
on conflict (company_id, dedupe_key) do update set
  role_title   = excluded.role_title,
  location     = excluded.location,
  role_url     = excluded.role_url,
  jd_full      = excluded.jd_full,
  salary_text  = excluded.salary_text,
  source       = excluded.source,
  is_local     = excluded.is_local,
  role_status  = 'open',
  content_fingerprint = excluded.content_fingerprint,
  last_seen_run = excluded.last_seen_run,
  updated_at   = now()
"""


def upsert_jobs(cur, company_id: int, company_name: str, jobs, run_id: int) -> int:
    """Upsert EVERY fetched job for one company, keyed on dedupe_key.

    Keep-all (founder rule 2026-07-16): locality is a stored label
    (is_local via the shared is_uk), never a filter — the caller passes all
    jobs the feed returned. One batched executemany — the DB is remote, so
    row-by-row round trips turn a fetch run into minutes of pure latency.
    The content fingerprint rides along so history can detect changes.
    """
    if not jobs:
        return 0
    cur.executemany(UPSERT_SQL, [
        (company_id, j.title, j.location, j.url, j.jd_text, j.salary_text,
         j.source, is_uk(j.location),
         fingerprint(j.title, j.location, j.salary_text, j.jd_text),
         dedupe_key(company_name, j.title, j.url), run_id)
        for j in jobs
    ])
    return len(jobs)


def close_vanished(cur, rot_ids: list[int], run_id: int) -> list[int]:
    """Job-rot: close listings of rot-eligible companies not seen this run.
    Returns the closed role_ids so 'closed' events can be recorded."""
    cur.execute(
        "update role_listings set role_status='closed', updated_at=now() "
        "where company_id = any(%s) and last_seen_run is distinct from %s "
        "and role_status <> 'closed' returning role_id",
        (rot_ids, run_id))
    return [r["role_id"] for r in cur.fetchall()]


def finish_run(cur, run_id: int, companies_attempted: int, roles_seen: int) -> None:
    """Stamp the fetch_runs row as finished ok with its counts."""
    cur.execute(
        "update fetch_runs set finished_at=now(), companies_attempted=%s, "
        "roles_seen=%s, status='ok' where run_id=%s",
        (companies_attempted, roles_seen, run_id))
