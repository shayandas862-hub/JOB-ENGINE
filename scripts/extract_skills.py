"""Read each open role's JD into role_skills (+ salary/sponsor/SOC when Gemini is on).

Pluggable reader (GA-003): if GEMINI_API_KEY is set, each new JD is read once by
Gemini Flash-Lite (skills + salary_text + sponsor_hint + soc_hint); otherwise the
free keyword extractor runs (skills only). Read-once: extracted_at stamps every
successfully read role — even zero-skill readings — so no role is ever re-billed.
All Gemini-derived data is provisional.

Resilient to a long paid batch: each role is read independently, failures are
counted (not fatal), and work is committed every COMMIT_EVERY roles so a crash
never discards calls already paid for.

    python scripts/extract_skills.py
"""
from __future__ import annotations

import sys

from analysis.occupations import load_occupation_index, make_resolver
from config import get_settings
from db.connection import get_conn
from persist.extract_rules import UNREAD_ROLES_SQL, persist_reading
from read.gemini import read_jd_or_fallback

COMMIT_EVERY = 25


def main() -> None:
    api_key = get_settings().gemini_api_key
    mode = "Gemini" if api_key else "keyword fallback"
    print(f"extraction mode: {mode}", file=sys.stderr)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(UNREAD_ROLES_SQL)
            rows = cur.fetchall()
        with conn.cursor() as cur:
            resolve_soc = make_resolver(load_occupation_index(cur))
        print(f"{len(rows)} roles to extract", file=sys.stderr)

        skill_rows = enriched = failures = 0
        cur = conn.cursor()
        quality, provenance = ("ai", "gemini") if api_key else ("keywords", "keywords")
        for i, r in enumerate(rows, 1):
            try:
                reading = read_jd_or_fallback(r["jd_full"], api_key=api_key)
                n = persist_reading(cur, r["role_id"], reading, soc_resolver=resolve_soc,
                                    read_quality=quality, provenance=provenance)
                skill_rows += n
                if reading.salary_text or reading.sponsor_hint or reading.soc_hint:
                    enriched += 1
            except Exception as e:  # one bad JD must not sink the batch
                failures += 1
                print(f"  ! role {r['role_id']} failed: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
            if i % COMMIT_EVERY == 0:
                conn.commit()
                print(f"  ...{i}/{len(rows)} done ({skill_rows} skills, {enriched} enriched, {failures} failed)", file=sys.stderr)
        conn.commit()

        print(
            f"DONE [{mode}]: {len(rows)} roles, {skill_rows} skill rows, "
            f"{enriched} role_listings enriched, {failures} failed",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
