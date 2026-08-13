"""The weekly register refresh — download, diff, stamp (never delete).

The licensed-sponsor register is the engine's sieve 1, and it was loaded
once, by hand (gap found 2026-08-02). This module re-downloads the published
CSV and diffs it against licensed_sponsors on (org_name_norm, route):
additions insert (keep-all grows, new orgs get a census card), rows that
vanished are STAMPED licence_removed_at, reappearances clear the stamp.
Each refresh writes one register_refreshes row; refresh_is_due reads that
history so the daily loop can self-schedule the weekly run.
"""
from __future__ import annotations

import csv
import io
import re

from audit import record
from discover.census_store import ensure_census_card
from normalise.text import norm

AUDIT_TOOL = "register.refresh"
PUBLICATION_URL = ("https://www.gov.uk/government/publications/"
                   "register-of-licensed-sponsors-workers")
ASSET_HOST = "https://assets.publishing.service.gov.uk"
SKILLED_WORKER_ROUTE = "Skilled Worker"

_CSV_HREF = re.compile(r'href="([^"]+\.csv)"', re.I)
_RATING = re.compile(r"\(([AB]) rating\)", re.I)
_PROVISIONAL = re.compile(r"provisional", re.I)


def find_csv_url(html: str) -> str | None:
    """The publication page's first .csv link, absolutised."""
    m = _CSV_HREF.search(html or "")
    if not m:
        return None
    href = m.group(1)
    return href if href.startswith("http") else ASSET_HOST + href


def parse_register_csv(text: str) -> list[dict]:
    """Published CSV rows -> register rows with the derived columns.

    Derivations mirror the original hand load exactly (verified against the
    live table 2026-08-02): rating from the '(A rating)' suffix,
    is_skilled_worker means route == 'Skilled Worker', org_name_norm via the
    shared norm().
    """
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        name = (r.get("Organisation Name") or "").strip()
        if not name:
            continue
        type_rating = (r.get("Type & Rating") or "").strip()
        route = (r.get("Route") or "").strip()
        rating = _RATING.search(type_rating)
        rows.append({
            "organisation_name": name,
            "town_city": (r.get("Town/City") or "").strip() or None,
            "county": (r.get("County") or "").strip() or None,
            "type_rating": type_rating,
            "route": route,
            "org_name_norm": norm(name),
            "rating": (rating.group(1).upper() if rating
                       else "Provisional" if _PROVISIONAL.search(type_rating)
                       else None),
            "is_skilled_worker": route == SKILLED_WORKER_ROUTE,
        })
    return rows


def refresh(cur, csv_rows: list[dict], *, source_file: str) -> dict:
    """Diff the downloaded register against the stored one; stamp the changes.

    Returns {'csv_rows', 'added', 'removed', 're_licensed', 'orgs_carded'}.
    The caller commits.
    """
    cur.execute("select id, org_name_norm, route, licence_removed_at "
                "from licensed_sponsors")
    stored = cur.fetchall()
    stored_pairs = {(r["org_name_norm"], r["route"]) for r in stored}
    stored_orgs = {r["org_name_norm"] for r in stored}
    csv_pairs = {(r["org_name_norm"], r["route"]) for r in csv_rows}

    additions = [r for r in csv_rows
                 if (r["org_name_norm"], r["route"]) not in stored_pairs]
    if additions:
        # org_name_norm / rating / is_skilled_worker are GENERATED columns —
        # the DB derives them from the raw facts (verified identical to the
        # python derivations 2026-08-02); only the CSV's own columns insert.
        cur.executemany(
            "insert into licensed_sponsors "
            "(organisation_name, town_city, county, type_rating, route, "
            " source_file) values (%s,%s,%s,%s,%s,%s)",
            [(r["organisation_name"], r["town_city"], r["county"],
              r["type_rating"], r["route"], source_file) for r in additions])

    new_orgs = sorted({r["org_name_norm"] for r in additions} - stored_orgs)
    for org_norm in new_orgs:
        first = next(r for r in additions if r["org_name_norm"] == org_norm)
        ensure_census_card(cur, first)

    removed_ids = [r["id"] for r in stored
                   if (r["org_name_norm"], r["route"]) not in csv_pairs
                   and r["licence_removed_at"] is None]
    if removed_ids:
        cur.execute("update licensed_sponsors set licence_removed_at = now() "
                    "where id = any(%s)", (removed_ids,))

    relicensed_ids = [r["id"] for r in stored
                      if (r["org_name_norm"], r["route"]) in csv_pairs
                      and r["licence_removed_at"] is not None]
    if relicensed_ids:
        cur.execute("update licensed_sponsors set licence_removed_at = null "
                    "where id = any(%s)", (relicensed_ids,))

    counts = {"csv_rows": len(csv_rows), "added": len(additions),
              "removed": len(removed_ids), "re_licensed": len(relicensed_ids),
              "orgs_carded": len(new_orgs)}
    cur.execute(
        "insert into register_refreshes "
        "(source_file, csv_rows, added, removed, re_licensed) "
        "values (%s,%s,%s,%s,%s)",
        (source_file, counts["csv_rows"], counts["added"], counts["removed"],
         counts["re_licensed"]))
    record(cur, AUDIT_TOOL, {"source_file": source_file}, counts)
    return counts


def refresh_is_due(cur, *, days: int = 7) -> bool:
    """True when the newest refresh is older than `days` (or none exists)."""
    cur.execute(
        "select current_date - max(refreshed_at)::date as days_since "
        "from register_refreshes")
    row = cur.fetchone()
    days_since = row["days_since"] if row else None
    return days_since is None or days_since >= days
