"""Rule-based census promotion — the founder's button becomes a nightly rule.

The census blast-radius wall stands: the sweep never writes target_companies.
This module is the audited crossing, and it crosses ONLY through the same
bridge the manual button uses (promote.promote_from_census) — pinned by test.

One rule row per owner (promotion_rules, 0038): an industry-code set, a
minimum-local-jobs floor, and an auto switch; titles come live from the
owner's target_roles, never stored in the rule. A board_found card promotes
when all three hold — registered industry in the set, at least one local
census job whose title matches the owner's roles, and the local-jobs floor.
EXACTLY ONE condition missing is a borderline card: it gets a capped
promotion_review flag carrying the full evidence, for a human to settle.
Two or more missing is silence — the rule is a door, not a megaphone.
"""
from __future__ import annotations

from audit import record
from criteria.loader import build_role_matcher
from discover.promote import promote_from_census
from review import add_flag

SAVE_AUDIT_TOOL = "promote_rule.save"
PROMOTION_REVIEW_FLAG_KIND = "promotion_review"
# The review list must stay SHORT to stay read: no new borderline flags while
# this many are already open. Promotions are never capped.
PROMOTION_REVIEW_CAP = 20

CANDIDATES_SQL = """
select c.org_name_norm, c.organisation_name, c.industry_codes,
       c.local_jobs_seen
  from sponsor_census c
 where c.probe_outcome = 'board_found' and c.ats_token is not null
 order by c.local_jobs_seen desc nulls last, c.org_name_norm
 limit %s
"""


def load_rule(cur, owner_id) -> dict | None:
    cur.execute(
        "select industry_codes, min_local_jobs, auto, adzuna_category "
        "from promotion_rules where owner_id = %s", (owner_id,))
    return cur.fetchone()


def save_rule(cur, owner_id, *, industry_codes: list[str] | None = None,
              min_local_jobs: int | None = None,
              auto: bool | None = None,
              adzuna_category: str | None = None) -> dict:
    """Upsert the owner's rule; None leaves that field as it is (audited).

    Changing the rule changes what the machine promotes every night — and,
    since U1, what the Pass-2 probe picks and which Adzuna category the ads
    sweep walks. The write is audited like every other deliberate crossing.
    """
    cur.execute(
        "insert into promotion_rules "
        "(owner_id, industry_codes, min_local_jobs, auto, adzuna_category) "
        "values (%s, coalesce(%s::text[], '{}'), coalesce(%s, 1), "
        "        coalesce(%s, true), %s) "
        "on conflict (owner_id) do update set "
        "  industry_codes = coalesce(%s::text[], promotion_rules.industry_codes), "
        "  min_local_jobs = coalesce(%s, promotion_rules.min_local_jobs), "
        "  auto           = coalesce(%s, promotion_rules.auto), "
        "  adzuna_category = coalesce(%s, promotion_rules.adzuna_category), "
        "  updated_at     = now() "
        "returning owner_id, industry_codes, min_local_jobs, auto, "
        "          adzuna_category",
        (owner_id, industry_codes, min_local_jobs, auto, adzuna_category,
         industry_codes, min_local_jobs, auto, adzuna_category))
    row = cur.fetchone()
    record(cur, SAVE_AUDIT_TOOL,
           {"industry_codes": industry_codes,
            "min_local_jobs": min_local_jobs, "auto": auto,
            "adzuna_category": adzuna_category},
           {"stored": {k: row[k] for k in
                       ("industry_codes", "min_local_jobs", "auto",
                        "adzuna_category")}})
    return row


def _local_title_matches(cur, org_name_norm: str, matcher) -> list[str]:
    cur.execute(
        "select title from census_jobs "
        "where org_name_norm = %s and is_local", (org_name_norm,))
    return [r["title"] for r in cur.fetchall() if matcher(r["title"])][:5]


def _open_flag_count(cur, owner_id) -> int:
    # Per-owner, not global. A shared cap lets one owner's unresolved flags
    # hold everybody else's promote pass shut (B-GAE-017).
    cur.execute(
        "select count(*) as n from review_items where kind = %s "
        "and status = 'open' and owner_id = %s",
        (PROMOTION_REVIEW_FLAG_KIND, owner_id))
    row = cur.fetchone()
    return row["n"] if row else 0


def _flag_borderline(cur, owner_id, card, missing: str, evidence: dict) -> bool:
    """Raise the capped borderline flag; False when it already existed."""
    flag = add_flag(
        cur, PROMOTION_REVIEW_FLAG_KIND, card["org_name_norm"],
        f"Promote '{card['organisation_name']}'? Rule almost passes — "
        f"missing: {missing}.",
        evidence, owner_id=owner_id)
    return flag is not None


def evaluate_rule(cur, owner_id, *, limit: int = 500) -> dict:
    """One nightly pass of the owner's promotion rule over board_found cards.

    Returns counts: promoted / flagged / already_flagged / already_tracked /
    skipped / cap_hit — or {'outcome': 'no_rule' | 'auto_off'} when the rule
    is absent or switched off (nothing is touched either way).
    """
    rule = load_rule(cur, owner_id)
    if rule is None:
        return {"outcome": "no_rule"}
    if not rule["auto"]:
        return {"outcome": "auto_off"}

    cur.execute(
        "select search_title from target_roles where owner_id = %s", (owner_id,))
    matcher = build_role_matcher(
        [r["search_title"] for r in cur.fetchall() if r["search_title"]])
    wanted_codes = set(rule["industry_codes"] or [])

    cur.execute(CANDIDATES_SQL, (limit,))
    cards = cur.fetchall()
    counts = {"promoted": 0, "flagged": 0, "already_flagged": 0,
              "already_tracked": 0, "skipped": 0, "cap_hit": False}
    flags_left = max(0, PROMOTION_REVIEW_CAP - _open_flag_count(cur, owner_id))

    for card in cards:
        matched_codes = sorted(wanted_codes & set(card["industry_codes"] or []))
        titles = _local_title_matches(cur, card["org_name_norm"], matcher)
        checks = {
            "industry": bool(matched_codes),
            "title": bool(titles),
            "local_jobs": (card["local_jobs_seen"] or 0) >= rule["min_local_jobs"],
        }
        missing = [name for name, ok in checks.items() if not ok]

        if not missing:
            outcome = promote_from_census(cur, owner_id,
                                          card["org_name_norm"])["outcome"]
            key = outcome if outcome in ("promoted", "already_tracked") else "skipped"
            counts[key] += 1
        elif len(missing) == 1:
            if flags_left <= 0:
                counts["cap_hit"] = True
                continue
            evidence = {
                "org_name_norm": card["org_name_norm"],
                "missing": missing[0],
                "industry_codes": card["industry_codes"],
                "matched_industry_codes": matched_codes,
                "local_jobs_seen": card["local_jobs_seen"],
                "min_local_jobs": rule["min_local_jobs"],
                "matched_titles": titles,
            }
            if _flag_borderline(cur, owner_id, card, missing[0], evidence):
                counts["flagged"] += 1
                flags_left -= 1
            else:
                counts["already_flagged"] += 1
        else:
            counts["skipped"] += 1
    return counts
