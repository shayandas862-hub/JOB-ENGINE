"""Wire 2 — register-matched aggregator ads become queue listings.

The raw ads layer stays keep-all: this pass only STAMPS each matched ad
(merge_outcome + merged_role_id + merged_at, migration 0037) and, for the
ads that qualify, writes the pipeline's own tables. Qualifying means all
three: register-matched (the blast-radius pin — an unmatched ad can never
touch role_listings), local, and not matched to a known recruitment agency
(census industry_codes in SIC division 78 'Employment activities' — the
fact-based stand-in for Reed's poster-type filter, which was a query-time
parameter the ads never carried; an org with no census card is not a KNOWN
agency and merges). Stamped rows are final; re-running costs nothing.

A qualifying ad's org gets a target_companies row if it has none (audited —
this is a second deliberate crossing beside census promotion; no board is
copied, so the fetch list ignores it until promotion finds one), then the ad
is compared against the company's existing listings with prob.py: at or
above SAME_JOB_DUPLICATE_P the listing absorbs the ad (stamped 'duplicate',
never a second row); below it the ad becomes its own shallow row — no JD
until a board or reader supplies one — and is history from birth.
"""
from __future__ import annotations

from audit import record
from discover.agg_store import ad_fingerprint
from discover.onboarding import REGISTER_SPONSOR_CONFIDENCE
from fetch.feeds import dedupe_key
from history.fingerprint import fingerprint
from match.prob import same_job_probability

AUDIT_TOOL = "discover.merge"

# Absorb as a duplicate at/above this; insert below it. Sits between an
# exact-title/same-town/overlapping-salary twin (~0.97) and a Senior-variant
# near-title (~0.91) — seniority variants are different jobs (pinned by test).
SAME_JOB_DUPLICATE_P = 0.93

PENDING_SQL = """
select a.ad_id, a.source, a.employer_name, a.title, a.location, a.is_local,
       a.salary_min, a.salary_max, a.salary_text, a.posted_at, a.ad_url,
       a.content_fingerprint, a.matched_org_norm,
       s.id as sponsor_id, s.organisation_name, s.town_city,
       exists (select 1 from sponsor_census c
                where c.org_name_norm = a.matched_org_norm
                  and exists (select 1 from unnest(c.industry_codes) code
                               where code like '78%%')) as is_agency
  from aggregator_ads a
  join lateral (select id, organisation_name, town_city
                  from licensed_sponsors
                 where org_name_norm = a.matched_org_norm
                 order by id limit 1) s on true
 where a.merged_at is null
   and a.matched_org_norm is not null
 order by a.ad_id
 limit %s
"""

STAMP_SQL = """
update aggregator_ads
   set merge_outcome = %s, merged_role_id = %s, merged_at = now()
 where ad_id = %s
"""

INSERT_LISTING_SQL = """
insert into role_listings
  (company_id, role_title, location, role_url, salary_text, salary_min,
   salary_max, source, is_local, role_status, date_opened,
   content_fingerprint, dedupe_key)
values (%s,%s,%s,%s,%s,%s,%s,%s,true,'open',%s,%s,%s)
on conflict (company_id, dedupe_key) do nothing
returning role_id
"""


def _ensure_company(cur, owner_id, ad, cache: dict) -> tuple[int, bool]:
    """The org's target_companies row (created boardless if absent, audited)."""
    org = ad["matched_org_norm"]
    if org in cache:
        return cache[org], False
    cur.execute(
        "select company_id from target_companies "
        "where owner_id = %s and (company_name ilike %s "
        "or (sponsor_id is not null and sponsor_id = %s))",
        (owner_id, ad["organisation_name"], ad["sponsor_id"]))
    row = cur.fetchone()
    if row is not None:
        cache[org] = row["company_id"]
        return row["company_id"], False
    cur.execute(
        "insert into target_companies "
        "(company_name, sponsor_id, city, sponsor_confidence, owner_id) "
        "values (%s,%s,%s,%s,%s) returning company_id",
        (ad["organisation_name"], ad["sponsor_id"], ad["town_city"],
         REGISTER_SPONSOR_CONFIDENCE, owner_id))
    company_id = cur.fetchone()["company_id"]
    record(cur, AUDIT_TOOL, {"org_name_norm": org},
           {"outcome": "company_created", "company_id": company_id,
            "via": "aggregator_ad"})
    cache[org] = company_id
    return company_id, True


def _absorbing_listing(cur, company_id: int, company_name: str, ad) -> int | None:
    """role_id of an existing listing that IS this job (prob >= threshold)."""
    cur.execute(
        "select role_id, role_title, location, salary_min, salary_max "
        "from role_listings where company_id = %s", (company_id,))
    ad_side = {"title": ad["title"], "location": ad["location"],
               "salary_min": ad["salary_min"], "salary_max": ad["salary_max"],
               "fingerprint": ad["content_fingerprint"]}
    best_id, best_p = None, 0.0
    for listing in cur.fetchall():
        p = same_job_probability(ad_side, {
            "title": listing["role_title"], "location": listing["location"],
            "salary_min": listing["salary_min"],
            "salary_max": listing["salary_max"],
            "fingerprint": ad_fingerprint(company_name, listing["role_title"],
                                          listing["location"]),
        })["p"]
        if p > best_p:
            best_id, best_p = listing["role_id"], p
    return best_id if best_p >= SAME_JOB_DUPLICATE_P else None


def _insert_listing(cur, company_id: int, company_name: str, ad) -> tuple[int, str]:
    """Insert the ad as a shallow listing; on a dedupe_key collision the
    existing row absorbs it instead. Returns (role_id, outcome)."""
    key = dedupe_key(company_name, ad["title"], ad["ad_url"])
    cur.execute(INSERT_LISTING_SQL, (
        company_id, ad["title"], ad["location"], ad["ad_url"],
        ad["salary_text"], ad["salary_min"], ad["salary_max"], ad["source"],
        ad["posted_at"],
        fingerprint(ad["title"], ad["location"], ad["salary_text"], None),
        key))
    row = cur.fetchone()
    if row is None:
        # Scoped to the company we just tried to insert against, not to the
        # world: the key is unique per company since 0058, and an unscoped
        # lookup here is what handed the second owner the FIRST owner's
        # role_id — B-GAE-018, where they then never received the job at all.
        cur.execute("select role_id from role_listings "
                    "where company_id = %s and dedupe_key = %s",
                    (company_id, key))
        return cur.fetchone()["role_id"], "duplicate"
    cur.execute(
        "insert into listing_events (role_id, event_type, changes, run_id) "
        "values (%s,'appeared',null,null)", (row["role_id"],))
    return row["role_id"], "merged"


def merge_pending(cur, owner_id, *, limit: int = 200) -> dict:
    """Merge up to `limit` never-attempted matched ads; stamp every one.

    Returns {'merged', 'duplicate', 'skipped_recruiter', 'skipped_not_local',
    'companies_created'}. The caller commits (per-batch in the runner).
    """
    cur.execute(PENDING_SQL, (limit,))
    ads = cur.fetchall()
    counts = {"merged": 0, "duplicate": 0, "skipped_recruiter": 0,
              "skipped_not_local": 0, "companies_created": 0}
    company_cache: dict[str, int] = {}
    for ad in ads:
        if ad["is_agency"]:
            outcome, role_id = "skipped_recruiter", None
        elif not ad["is_local"]:
            outcome, role_id = "skipped_not_local", None
        else:
            company_id, created = _ensure_company(cur, owner_id, ad,
                                                  company_cache)
            counts["companies_created"] += int(created)
            company_name = ad["organisation_name"]
            absorbed = _absorbing_listing(cur, company_id, company_name, ad)
            if absorbed is not None:
                outcome, role_id = "duplicate", absorbed
            else:
                role_id, outcome = _insert_listing(cur, company_id,
                                                   company_name, ad)
        cur.execute(STAMP_SQL, (outcome, role_id, ad["ad_id"]))
        counts[outcome] += 1
    return counts
