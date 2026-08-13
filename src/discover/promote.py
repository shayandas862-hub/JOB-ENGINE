"""Promote a census company onto the fetch list — the census→pipeline bridge.

The census itself NEVER writes target_companies (the blast-radius rule the
sweep tests pin). Promotion is the deliberate act on the other side of that
wall: founder-triggered, one org at a time, audited. A promoted company's
board is copied straight from its census card — no re-probe needed — and the
daily pipeline starts fetching its jobs on the next run. Register-sourced, so
its sponsor confidence is the shared 'register-only' verdict.
"""
from __future__ import annotations

from types import SimpleNamespace

from audit import record
from discover.onboarding import (REGISTER_SPONSOR_CONFIDENCE,
                                 insert_classified_company)

AUDIT_TOOL = "census.promote"


def promote_from_census(cur, owner_id, org_name_norm) -> dict:
    """Copy one census card's board onto target_companies; guarded + audited.

    Outcomes: 'not_found' (no such census card), 'already_tracked' (on the
    fetch list already — returns its company_id), 'no_board' (nothing to copy;
    returns the probe evidence so Claude can hunt a careers URL instead), or
    'promoted' (returns the new company_id).
    """
    cur.execute(
        "select org_name_norm, sponsor_id, organisation_name, town_city, "
        "probe_outcome, ats_type, ats_token, careers_url, local_jobs_seen "
        "from sponsor_census where org_name_norm = %s",
        (org_name_norm,))
    card = cur.fetchone()
    if card is None:
        return {"outcome": "not_found", "org_name_norm": org_name_norm}

    cur.execute(
        "select company_id from target_companies "
        "where owner_id = %s and (company_name ilike %s "
        "or (sponsor_id is not null and sponsor_id = %s))",
        (owner_id, card["organisation_name"], card["sponsor_id"]))
    tracked = cur.fetchone()
    if tracked is not None:
        return {"outcome": "already_tracked",
                "company_id": tracked["company_id"],
                "org_name_norm": org_name_norm}

    if card["probe_outcome"] != "board_found" or not card["ats_token"]:
        return {"outcome": "no_board", "org_name_norm": org_name_norm,
                "organisation_name": card["organisation_name"],
                "probe_outcome": card["probe_outcome"],
                "careers_url": card["careers_url"]}

    classification = SimpleNamespace(ats_type=card["ats_type"],
                                     ats_token=card["ats_token"],
                                     careers_url=card["careers_url"])
    company_id = insert_classified_company(
        cur, owner_id, company_name=card["organisation_name"],
        sponsor_id=card["sponsor_id"], city=card["town_city"],
        classification=classification,
        sponsor_confidence=REGISTER_SPONSOR_CONFIDENCE)
    result = {"outcome": "promoted", "company_id": company_id,
              "org_name_norm": org_name_norm,
              "organisation_name": card["organisation_name"],
              "ats_type": card["ats_type"],
              "local_jobs_seen": card["local_jobs_seen"]}
    record(cur, AUDIT_TOOL, {"org_name_norm": org_name_norm},
           {"outcome": "promoted", "company_id": company_id})
    return result
