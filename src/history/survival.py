"""Survival deadlines — how long roles like this actually stay open.

The machine has watched listings appear and close since Phase 4
(listing_events); that history is the honest basis for an apply-by date:
"roles in this family fill in ~N days". Durations pair each listing's FIRST
appeared with its FIRST closed; families group by SOC code when known, else
coarse title buckets. A family below MIN_SAMPLE never drives a deadline —
the flat profile window stays, labelled 'estimated'. A stated deadline in
the JD always wins. Survival dates ship their receipts (family, n, median):
the machine cites its own history, never a naked date.
"""
from __future__ import annotations

from datetime import date, timedelta

from history.deadline import extract_stated_deadline
from match.stats import summary
from normalise.text import norm

# Below this many observed lifetimes a family's curve is opinion, not
# evidence — the flat window keeps the job.
MIN_SAMPLE = 5

DURATIONS_SQL = """
select r.soc_code, r.role_title,
       extract(epoch from (
           min(e.occurred_at) filter (where e.event_type = 'closed')
         - min(e.occurred_at) filter (where e.event_type = 'appeared')
       )) / 86400.0 as days_open
  from listing_events e
  join role_listings r on r.role_id = e.role_id
 group by e.role_id, r.soc_code, r.role_title
having min(e.occurred_at) filter (where e.event_type = 'closed')
     > min(e.occurred_at) filter (where e.event_type = 'appeared')
"""

# Coarse on purpose: enough families to differ, few enough to fill with
# evidence. Order matters — 'data'/'ml' claim their titles before the
# generic 'software' bucket does.
FAMILY_KEYWORDS = [
    ("data", ("data engineer", "data analyst", "data scientist", "analytics",
              "data platform")),
    ("ml", ("machine learning", "ml engineer", "ai engineer", "deep learning")),
    ("software", ("software", "developer", "engineer", "devops", "platform")),
    ("product", ("product",)),
    ("design", ("designer", "design",)),
    ("sales", ("sales", "account executive", "business development")),
    ("support", ("support", "customer success",)),
]


def role_family(role_title: str | None, soc_code: str | None) -> str:
    """The listing's curve family: official SOC first, else a title bucket."""
    if soc_code:
        return f"soc:{soc_code}"
    title = norm(role_title)
    for family, keywords in FAMILY_KEYWORDS:
        if any(k in title for k in keywords):
            return f"title:{family}"
    return "title:other"


def build_curves(cur) -> dict[str, dict]:
    """Open-duration summaries per family from the event history.

    {family: {"n", "p25", "p50", "p75"}} — every curve carries its sample
    size; the caller decides (via MIN_SAMPLE) whether it is evidence.
    """
    cur.execute(DURATIONS_SQL)
    by_family: dict[str, list[float]] = {}
    for row in cur.fetchall():
        family = role_family(row["role_title"], row["soc_code"])
        by_family.setdefault(family, []).append(float(row["days_open"]))
    return {family: summary(days) for family, days in by_family.items()}


def choose_with_survival(jd_text, first_seen: date, role_title, soc_code,
                         curves: dict[str, dict], *,
                         window_days: int) -> tuple[date, str, dict]:
    """(deadline, source, receipts): stated > survival > flat estimate."""
    stated = extract_stated_deadline(jd_text)
    if stated:
        return stated, "stated", {}
    family = role_family(role_title, soc_code)
    curve = curves.get(family)
    if curve and curve["n"] >= MIN_SAMPLE:
        receipts = {"family": family, **curve}
        return (first_seen + timedelta(days=round(curve["p50"])),
                "survival", receipts)
    return (first_seen + timedelta(days=window_days), "estimated",
            {"family": family, "n": curve["n"] if curve else 0})
