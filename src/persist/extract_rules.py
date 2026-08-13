"""Rules for reading JDs into the database: read-once selection + no-clobber writes."""
from __future__ import annotations

from normalise.text import norm

# Read-once keys on extracted_at, NOT on whether skills were found — a role
# whose reading legitimately yields zero skills is still done and must never
# be re-sent to the paid API. is_local is the cost cage: keep-all stores
# foreign listings too, but the paid reader only ever sees local ones.
UNREAD_ROLES_SQL = """
select role_id, jd_full from role_listings
 where role_status = 'open' and coalesce(jd_full, '') <> ''
   and extracted_at is null
   and is_local
"""


def persist_reading(cur, role_id, reading, soc_resolver=None,
                    read_quality: str | None = None,
                    provenance: str | None = None) -> int:
    """Write one successful reading. Returns the number of skill rows.

    Always stamps extracted_at (success = read once, even with zero skills).
    COALESCE(new, old) keeps the no-clobber rule: a keyword-fallback re-run's
    NULLs can never erase Gemini-derived values already on the row.
    The raw soc_hint is kept as evidence; soc_code only ever receives a code
    the resolver confirmed against the official occupation table — never the
    raw hint. read_quality ('keywords'|'ai') and provenance label how this
    reading was produced (0039); None leaves the existing labels alone.
    """
    rows = [(role_id, name, norm(name), category) for name, category in reading.skills]
    if rows:
        cur.executemany(
            "insert into role_skills (role_id, skill_asked, skill_norm, skill_type) "
            "values (%s,%s,%s,%s)",
            rows,
        )
    n = len(rows)
    resolved = soc_resolver(reading.soc_hint) if (soc_resolver and reading.soc_hint) else None
    cur.execute(
        """update role_listings set
               salary_text        = coalesce(%s, salary_text),
               sponsors_this_role = coalesce(%s, sponsors_this_role),
               soc_hint           = coalesce(%s, soc_hint),
               soc_code           = coalesce(%s, soc_code),
               read_quality       = coalesce(%s, read_quality),
               read_provenance    = coalesce(%s, read_provenance),
               extracted_at       = now()
           where role_id = %s""",
        (reading.salary_text, reading.sponsor_hint, reading.soc_hint, resolved,
         read_quality, provenance, role_id),
    )
    return n
