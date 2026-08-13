"""Cross-check aggregator-discovered employers against the licensed-sponsor register.

The register is the unfair advantage: nothing enters the queue without a sponsor
verdict. This matcher is confident on only two grounds — an exact shared-norm()
match, or a unique legal-suffix-normalised match (employer 'Acme AI' == register
'Acme AI Ltd'). Anything ambiguous (several candidates) or merely partial becomes
a 'sponsor_match' review flag carrying the candidates, so a human/Claude settles
it — never a silent guess. No register hit at all is a confident negative.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from audit import record
from normalise.text import norm, strip_legal_suffixes
from review import add_flag

SPONSOR_MATCH_FLAG_KIND = "sponsor_match"
AUDIT_TOOL = "discover.sponsor_match"


@dataclass(frozen=True)
class SponsorMatch:
    status: str                      # 'matched' | 'uncertain' | 'unmatched'
    employer: str
    sponsor_id: int | None = None
    rating: str | None = None
    route: str | None = None
    method: str = ""
    candidates: tuple = field(default_factory=tuple)


# The shared stripper (normalise.text since Phase 7.5); the old private name
# stays as the module's vocabulary.
_strip_legal = strip_legal_suffixes


_COLUMNS = "id as sponsor_id, organisation_name, org_name_norm, rating, route"


def _exact(cur, name_norm: str) -> list[dict]:
    cur.execute(
        f"select {_COLUMNS} from licensed_sponsors where org_name_norm = %s limit 5",
        (name_norm,))
    return cur.fetchall()


def _candidates(cur, name_norm: str, core: str) -> list[dict]:
    cur.execute(
        f"select {_COLUMNS} from licensed_sponsors "
        "where org_name_norm like %s or org_name_norm like %s limit 20",
        (name_norm + "%", core + "%"))
    return cur.fetchall()


def _matched(employer, row, method) -> SponsorMatch:
    return SponsorMatch("matched", employer, sponsor_id=row["sponsor_id"],
                        rating=row.get("rating"), route=row.get("route"),
                        method=method, candidates=(row,))


def match_employer(cur, employer: str) -> SponsorMatch:
    """Decide an employer's sponsor verdict against the register (no writes)."""
    name_norm = norm(employer)
    if not name_norm:
        return SponsorMatch("unmatched", employer, method="empty")

    exact = _exact(cur, name_norm)
    if len(exact) == 1:
        return _matched(employer, exact[0], "exact")
    if len(exact) > 1:
        return SponsorMatch("uncertain", employer, method="exact-ambiguous",
                            candidates=tuple(exact))

    core = _strip_legal(name_norm)
    cands = _candidates(cur, name_norm, core)
    strong = [c for c in cands if _strip_legal(c["org_name_norm"]) == core]
    if len(strong) == 1:
        return _matched(employer, strong[0], "normalised")
    if len(strong) > 1:
        return SponsorMatch("uncertain", employer, method="normalised-ambiguous",
                            candidates=tuple(strong))
    if cands:
        return SponsorMatch("uncertain", employer, method="partial",
                            candidates=tuple(cands))
    return SponsorMatch("unmatched", employer, method="no-register-entry")


def _candidate_summary(rows) -> list[dict]:
    return [{"sponsor_id": r["sponsor_id"], "organisation_name": r["organisation_name"],
             "org_name_norm": r["org_name_norm"]} for r in rows]


def cross_check_employer(cur, employer: str, *, audit: bool = True) -> SponsorMatch:
    """Match an employer and, when uncertain, raise a 'sponsor_match' review flag.

    Matched and unmatched are confident verdicts and write nothing. An uncertain
    verdict flags the candidates for a human/Claude (idempotent by employer), and
    the write is audited.
    """
    m = match_employer(cur, employer)
    if m.status != "uncertain":
        return m

    flag = add_flag(
        cur, SPONSOR_MATCH_FLAG_KIND, norm(employer),
        f"Sponsor match unclear for '{employer}': {len(m.candidates)} register candidate(s).",
        {"employer": employer, "method": m.method,
         "candidates": _candidate_summary(m.candidates)})
    if flag is not None and audit:
        record(cur, AUDIT_TOOL, {"employer": employer},
               {"status": "uncertain", "review_id": flag["review_id"],
                "candidates": len(m.candidates)})
    return m


def cross_check_employers(cur, employers) -> dict:
    """Cross-check a batch of employer names (deduped); return a status tally."""
    tally = {"matched": 0, "uncertain": 0, "unmatched": 0}
    for employer in {e for e in employers if e and e.strip()}:
        status = cross_check_employer(cur, employer).status
        tally[status] = tally.get(status, 0) + 1
    return tally
