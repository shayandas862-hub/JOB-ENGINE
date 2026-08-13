"""The register-match label pass over stored aggregator ads.

The register is the filter (founder design 2026-07-22): every stored ad's
employer is checked against licensed sponsors and LABELLED — matched, uncertain
(several candidates: no silent guess, ever), or unmatched (a confident
negative). A no-match still stamps matched_at so the pass resumes cleanly and
never rework-loops; better matchers later can clear matched_at and re-derive
every label at zero API cost.
"""
from __future__ import annotations

from discover.sponsor_match import match_employer

PENDING_SQL = """
select employer_norm, min(employer_name) as employer_name
  from aggregator_ads
 where matched_at is null
 group by employer_norm
 order by employer_norm
 limit %s
"""

STAMP_SQL = """
update aggregator_ads
   set matched_org_norm = %s, match_method = %s, matched_at = now()
 where employer_norm = %s and matched_at is null
"""


def match_pending(cur, *, limit: int = 500) -> dict:
    """Match up to `limit` distinct never-attempted employers; stamp every ad.

    One register lookup per distinct employer (not per ad) — a 100-ad page from
    one big employer costs one match. Returns {'matched': n, 'uncertain': n,
    'unmatched': n}.
    """
    cur.execute(PENDING_SQL, (limit,))
    employers = cur.fetchall()
    counts = {"matched": 0, "uncertain": 0, "unmatched": 0}
    for row in employers:
        m = match_employer(cur, row["employer_name"])
        if m.status == "matched" and m.candidates:
            org = m.candidates[0]["org_name_norm"]
            method = m.method or "matched"
        else:
            org, method = None, m.status
        cur.execute(STAMP_SQL, (org, method, row["employer_norm"]))
        counts[m.status if m.status in counts else "unmatched"] += 1
    return counts
