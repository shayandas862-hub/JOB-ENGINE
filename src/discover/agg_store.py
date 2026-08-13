"""Aggregator raw-layer writes: keep-all ads, quota ledger, resume cursors.

Doctrine (founder, 2026-07-22): store EVERY ad the sweep downloads, matched or
not — matching and token harvest are label passes over stored rows that cost
zero API quota and can be re-run forever as matchers improve. A refresh of an
already-seen ad updates its content and last_seen but NEVER clobbers the label
columns (matched_*, harvest_checked_at). Blast radius: the aggregator sweep
writes only the three 0036 tables through this module.
"""
from __future__ import annotations

import hashlib
import json
import re

from fetch.feeds import FOREIGN_REGION_CODE_RE, NON_UK_RE, is_uk
from normalise.text import norm


def _ad_is_local(location) -> bool:
    """Locality for COUNTRY-SCOPED sources (Adzuna's /gb endpoint, Reed UK).

    is_uk stays the strong positive; beyond it, the API's own country scope
    decides — a bare UK town ('Basingstoke') is local unless the location
    carries an explicit foreign marker. Empty stays False (no evidence)."""
    if is_uk(location):
        return True
    text = str(location or "")
    if not text.strip():
        return False
    return not (NON_UK_RE.search(text) or FOREIGN_REGION_CODE_RE.search(text))


def ad_dedupe_key(source: str, external_id: str) -> str:
    """Per-source identity: the provider's own id namespaced by the source."""
    return hashlib.sha1(f"{source}|{external_id}".encode("utf-8")).hexdigest()


def _scrub(text: str | None) -> str:
    """Alphanumeric-only lowering for the cross-source fingerprint — 'Sky UK
    Ltd.' on Reed and 'Sky UK Ltd' on Adzuna must collide."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def ad_fingerprint(employer: str, title: str, location: str | None) -> str:
    """Cross-source content identity: same employer+title+location = same job,
    whichever aggregator (or board) it surfaced on."""
    base = f"{_scrub(employer)}|{_scrub(title)}|{_scrub(location)}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


INSERT_ADS_SQL = """
insert into aggregator_ads
  (source, external_id, employer_name, employer_norm, title, location, is_local,
   salary_min, salary_max, salary_text, posted_at, ad_url, snippet,
   dedupe_key, content_fingerprint)
values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
on conflict (dedupe_key) do update set
  title       = excluded.title,
  location    = excluded.location,
  is_local    = excluded.is_local,
  salary_min  = excluded.salary_min,
  salary_max  = excluded.salary_max,
  salary_text = excluded.salary_text,
  posted_at   = coalesce(excluded.posted_at, aggregator_ads.posted_at),
  ad_url      = excluded.ad_url,
  snippet     = excluded.snippet,
  last_seen   = now()
"""


def insert_ads(cur, ads: list[dict]) -> int:
    """Store every ad labelled (is_local via the shared is_uk). Returns count."""
    if not ads:
        return 0
    rows = []
    for a in ads:
        employer = a.get("employer_name") or ""
        ext = a.get("external_id") or a.get("ad_url") or f"{employer}|{a.get('title', '')}"
        rows.append((
            a["source"], str(ext), employer, norm(employer),
            a.get("title") or "", a.get("location"),
            _ad_is_local(a.get("location")),
            a.get("salary_min"), a.get("salary_max"), a.get("salary_text"),
            a.get("posted_at"), a.get("ad_url"), a.get("snippet"),
            ad_dedupe_key(a["source"], str(ext)),
            ad_fingerprint(employer, a.get("title") or "", a.get("location")),
        ))
    cur.executemany(INSERT_ADS_SQL, rows)
    return len(rows)


def stored_count(cur, source: str) -> int:
    """Distinct ads banked for a source — the saturation guard's yardstick."""
    cur.execute("select count(*) as n from aggregator_ads where source = %s",
                (source,))
    row = cur.fetchone()
    return row["n"] if row else 0


# The write half of this ledger moved to budget.ledger in task 5: one writer,
# at the one place a call is actually made, so a path nobody remembered still
# counts. What stays here is the read the sweep uses for its own slice cap.


def quota_spent(cur, source: str, day) -> int:
    cur.execute("select calls from api_quota_ledger where source=%s and day=%s",
                (source, day))
    row = cur.fetchone()
    return row["calls"] if row else 0


def load_cursor(cur, slice_key: str) -> dict | None:
    cur.execute(
        "select next_page, total_reported, ads_seen, pass_complete "
        "from aggregator_cursor where slice_key = %s", (slice_key,))
    return cur.fetchone()


def save_cursor(cur, slice_key: str, source: str, params: dict, *,
                next_page: int, total_reported, ads_seen_inc: int,
                pass_complete: bool) -> None:
    cur.execute(
        "insert into aggregator_cursor "
        "  (slice_key, source, params, next_page, total_reported, ads_seen, "
        "   pass_complete, updated_at) "
        "values (%s,%s,%s::jsonb,%s,%s,%s,%s,now()) "
        "on conflict (slice_key) do update set "
        "  next_page = excluded.next_page, "
        "  total_reported = coalesce(excluded.total_reported, "
        "                            aggregator_cursor.total_reported), "
        "  ads_seen = aggregator_cursor.ads_seen + excluded.ads_seen, "
        "  pass_complete = excluded.pass_complete, "
        "  updated_at = now()",
        (slice_key, source, json.dumps(params), next_page, total_reported,
         ads_seen_inc, pass_complete))
