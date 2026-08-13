"""Auto-onboard discovered sponsors: probe the board, list it or flag it.

A register candidate (register.py) is probed by the existing ATS classifier
(fetch.ats). A board hit joins ``target_companies`` with its ats_type/ats_token
— exactly what the fetch list selects on (scripts/fetch_jobs.py) — so the
company starts being fetched on the next run. No board found → a
``company_onboard`` review flag carrying the probe evidence, for Claude to hunt
the careers URL (Task 3). Every write is audited (provisional-until-confirmed).
"""
from __future__ import annotations

from dataclasses import dataclass

from audit import record
from fetch.ats import ATS_UNKNOWN, candidate_tokens, classify_company
from review import add_flag

# Discovered from the licensed register: a known visa sponsor, but whether it
# sponsors *these* roles is still unconfirmed — matches the existing vocabulary.
REGISTER_SPONSOR_CONFIDENCE = "register-only"
# Onboarded by name/URL but no exact match in the register snapshot — an honest
# negative verdict, so nothing enters the queue pretending to be sponsor-backed.
UNVERIFIED_SPONSOR_CONFIDENCE = "unverified (not in register)"
ONBOARD_FLAG_KIND = "company_onboard"
AUDIT_TOOL = "discover.onboard"


@dataclass(frozen=True)
class OnboardResult:
    outcome: str                 # 'onboarded' | 'flagged' | 'already_flagged'
    company_name: str
    sponsor_id: int | None
    company_id: int | None = None       # set when onboarded
    ats_type: str | None = None
    ats_token: str | None = None
    careers_url: str | None = None
    n_jobs: int | None = None
    review_id: int | None = None        # set when a new flag was raised


def insert_classified_company(cur, owner_id, *, company_name, sponsor_id, city,
                              classification,
                              sponsor_confidence=REGISTER_SPONSOR_CONFIDENCE) -> int:
    """Add a classified company to the fetch list; returns the new company_id.

    Sets ats_type/ats_token — exactly what the fetch list selects on — plus the
    register linkage (sponsor_id) and web_checked. The one write both the batch
    (register-candidate) and interactive (by-name/URL) discovery paths share.
    """
    cur.execute(
        "insert into target_companies "
        "(company_name, sponsor_id, city, careers_url, ats_type, ats_token, "
        " web_checked, sponsor_confidence, owner_id) "
        "values (%s, %s, %s, %s, %s, %s, true, %s, %s) returning company_id",
        (company_name, sponsor_id, city, classification.careers_url,
         classification.ats_type, classification.ats_token,
         sponsor_confidence, owner_id))
    return cur.fetchone()["company_id"]


def onboard_candidate(cur, owner_id, candidate, session=None) -> OnboardResult:
    """Probe one register candidate; add it to the fetch list or flag it.

    Assumes the candidate isn't already targeted — register.find_candidate_sponsors
    guarantees that; the by-name path (Task 3) adds an existence guard. The probe
    is the same ATS classifier the manual pipeline uses.
    """
    c = classify_company(candidate.organisation_name, session)

    if c.ats_type != ATS_UNKNOWN and c.ats_token:
        company_id = insert_classified_company(
            cur, owner_id, company_name=candidate.organisation_name,
            sponsor_id=candidate.sponsor_id, city=candidate.town_city, classification=c)
        record(cur, AUDIT_TOOL,
               {"company": candidate.organisation_name, "sponsor_id": candidate.sponsor_id},
               {"outcome": "onboarded", "company_id": company_id, "ats_type": c.ats_type})
        return OnboardResult(
            outcome="onboarded", company_name=candidate.organisation_name,
            sponsor_id=candidate.sponsor_id, company_id=company_id,
            ats_type=c.ats_type, ats_token=c.ats_token,
            careers_url=c.careers_url, n_jobs=c.n_jobs)

    evidence = {
        "company_name": candidate.organisation_name,
        "sponsor_id": candidate.sponsor_id,
        "org_name_norm": candidate.org_name_norm,
        "town_city": candidate.town_city,
        "tokens_tried": candidate_tokens(candidate.organisation_name),
        "probe": "no ATS board matched (greenhouse/lever/ashby/workable)",
    }
    flag = add_flag(
        cur, ONBOARD_FLAG_KIND, candidate.org_name_norm,
        f"Onboard '{candidate.organisation_name}': no job board found — needs a careers URL.",
        evidence)
    if flag is None:                     # already flagged on an earlier run; no write
        return OnboardResult(
            outcome="already_flagged", company_name=candidate.organisation_name,
            sponsor_id=candidate.sponsor_id)
    record(cur, AUDIT_TOOL,
           {"company": candidate.organisation_name, "sponsor_id": candidate.sponsor_id},
           {"outcome": "flagged", "review_id": flag["review_id"]})
    return OnboardResult(
        outcome="flagged", company_name=candidate.organisation_name,
        sponsor_id=candidate.sponsor_id, review_id=flag["review_id"])


def onboard_candidates(cur, owner_id, candidates, session=None) -> list[OnboardResult]:
    """Onboard a batch of register candidates, in order."""
    return [onboard_candidate(cur, owner_id, cand, session) for cand in candidates]
