"""Populate skill_synonyms (GA-004) — map messy role-skill names to canonical forms.

Read-once: only canonicalises distinct role skill_norms not already in the map.
Anchors on my_skills so equivalents reconcile. 'low' confidence rows are flagged
for review. Needs GEMINI_API_KEY.

    PYTHONPATH=src python scripts/build_synonyms.py
"""
from __future__ import annotations

import sys

from config import get_settings
from db.connection import get_conn
from normalise.synonyms import canonicalize_batches


def main() -> None:
    if not get_settings().gemini_api_key:
        # Engine-side AI is retired (2026-08-03): no key is the designed state,
        # not an error. Existing mappings persist and keep reconciling; new
        # variants wait for the user-side synonym tool (plan 0010 item 17).
        print("synonyms: skipped — mapping is user-side now; "
              "existing mappings persist.", file=sys.stderr)
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select skill from my_skills")
            my_labels = [r["skill"] for r in cur.fetchall()]

            cur.execute(
                """select distinct rs.skill_asked, rs.skill_norm
                   from role_skills rs join role_listings r on r.role_id = rs.role_id
                   where r.role_status = 'open'
                     and rs.skill_norm not in (select raw_norm from skill_synonyms)"""
            )
            todo = cur.fetchall()
        # Model sees the display names; SynonymRow.raw_norm == role_skills.skill_norm
        # (both are norm(skill_asked)), so it keys the map straight into the view join.
        names = [r["skill_asked"] for r in todo]
        print(f"{len(names)} new skill names to canonicalise (anchored on {len(my_labels)} my_skills)",
              file=sys.stderr)

        counters = {"upserts": 0, "matches": 0, "low": 0}

        def persist(batch_rows):
            # One batch = one transaction (banked immediately) = one round trip.
            if not batch_rows:
                return
            with conn.cursor() as cur:
                cur.executemany(
                    """insert into skill_synonyms
                           (raw_norm, canonical_label, canonical_norm, my_skill_match, confidence, source)
                       values (%s,%s,%s,%s,%s,'gemini')
                       on conflict (raw_norm) do update set
                           canonical_label = excluded.canonical_label,
                           canonical_norm  = excluded.canonical_norm,
                           my_skill_match  = excluded.my_skill_match,
                           confidence      = excluded.confidence""",
                    [(sr.raw_norm, sr.canonical_label, sr.canonical_norm,
                      sr.my_skill_match, sr.confidence) for sr in batch_rows],
                )
            conn.commit()
            counters["upserts"] += len(batch_rows)
            counters["matches"] += sum(int(sr.my_skill_match) for sr in batch_rows)
            counters["low"] += sum(int(sr.confidence == "low") for sr in batch_rows)

        ok, failed = canonicalize_batches(names, my_labels, persist=persist)

        print(f"upserted {counters['upserts']} synonyms across {ok} batch(es); "
              f"{counters['matches']} matched my_skills; {counters['low']} flagged 'low' for review"
              + (f"; {failed} batch(es) FAILED and will retry next run" if failed else ""),
              file=sys.stderr)


if __name__ == "__main__":
    main()
