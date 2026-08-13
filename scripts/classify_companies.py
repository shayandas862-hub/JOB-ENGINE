"""Classify each target company's ATS and (optionally) write it back to the DB.

Two modes:
  * DB mode (default): read company names from target_companies, classify, and
    UPDATE ats_type/ats_token/careers_url. Requires DATABASE_URL in .env.
  * Offline mode (--offline --names FILE [--out FILE]): read names from a JSON
    array, classify, write results JSON. No DB needed (bootstrap/testing).

Run from the project root with the venv active, e.g.:
    python scripts/classify_companies.py                       # DB mode
    python scripts/classify_companies.py --offline --names names.json --out out.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import asdict

import requests

from fetch.ats import classify_company


def classify_names(names: list[str], pause: float = 0.0) -> list[dict]:
    session = requests.Session()
    results: list[dict] = []
    for i, name in enumerate(names, 1):
        c = classify_company(name, session)
        results.append(asdict(c))
        print(
            f"[{i:>2}/{len(names)}] {name:22} -> {c.ats_type:10} "
            f"token={c.ats_token} jobs={c.n_jobs}",
            file=sys.stderr,
        )
        if pause:
            time.sleep(pause)
    return results


def print_summary(results: list[dict]) -> None:
    counts = Counter(r["ats_type"] for r in results)
    print("\n=== coverage by ats_type ===", file=sys.stderr)
    for ats, n in counts.most_common():
        print(f"  {ats:10} {n}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="classify from a names file, no DB")
    ap.add_argument("--names", help="JSON array of company names (offline mode)")
    ap.add_argument("--out", help="write results JSON here (offline mode)")
    args = ap.parse_args()

    if args.offline:
        with open(args.names) as fh:
            names = json.load(fh)
        results = classify_names(names)
        print_summary(results)
        if args.out:
            with open(args.out, "w") as fh:
                json.dump(results, fh, indent=2)
            print(f"\nwrote {len(results)} results to {args.out}", file=sys.stderr)
        return

    # DB mode
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company_name FROM target_companies ORDER BY company_name")
            names = [row["company_name"] for row in cur.fetchall()]
        results = classify_names(names)
        print_summary(results)
        with conn.cursor() as cur:
            for r in results:
                cur.execute(
                    "UPDATE target_companies "
                    "SET ats_type=%s, ats_token=%s, careers_url=%s, "
                    "    web_checked=true, updated_at=now() "
                    "WHERE company_name=%s",
                    (r["ats_type"], r["ats_token"], r["careers_url"], r["company_name"]),
                )
    print("DB updated.", file=sys.stderr)


if __name__ == "__main__":
    main()
