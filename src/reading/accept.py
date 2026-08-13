"""Accept a client's reading — the deterministic verification boundary.

Whatever model produced the submission, the gate is the same: shape and
enums validated in code, then every claimed skill and the salary line must
appear VERBATIM in the stored JD (read.eval.check_grounding — the same
truth-gate mechanism the CV pipeline uses). Ungrounded claims are dropped
and the rejects recorded; the worst a hallucinating or malicious client can
cause is omission. Grounded facts persist through the one shared write path
(persist.extract_rules.persist_reading), replacing the keyword-derived
skill rows — the listing upgrades in place to read_quality 'ai' and leaves
the tray. Owner-scoped and idempotent: a row not in the tray is a no-op.
"""
from __future__ import annotations

from types import SimpleNamespace

from analysis.occupations import load_occupation_index, make_resolver
from audit import record
from fetch.feeds import _strip_html
from normalise.text import norm
from persist.extract_rules import persist_reading
from read.eval import check_grounding
from reading.serve import SKILL_CATEGORIES, SPONSOR_VALUES

AUDIT_TOOL = "reading.accept"

#: The ONE html stripper, shared — never a copy. `fetch.jd_drip` aliases the
#: same function with the same instruction beside it. A second regex here
#: would drift from the one the fetchers use and the two would disagree about
#: what an advert says.
clean_html = _strip_html


def _validate(payload) -> tuple[dict | None, list[str]]:
    """Shape/enum validation, deterministic and strict on types.

    Unknown categories coerce to 'other'; junk enum values become None —
    they can never land in a row. Returns (clean, errors)."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return None, ["payload must be an object"]
    skills_raw = payload.get("skills")
    if not isinstance(skills_raw, list):
        errors.append("skills must be a list of {name, category}")
        skills_raw = []
    skills: list[tuple[str, str]] = []
    for i, s in enumerate(skills_raw):
        if not isinstance(s, dict) or not isinstance(s.get("name"), str) \
                or not s["name"].strip():
            errors.append(f"skills[{i}] needs a non-empty string name")
            continue
        category = s.get("category")
        if category not in SKILL_CATEGORIES:
            category = "other"
        skills.append((s["name"].strip(), category))

    def _opt_str(key):
        v = payload.get(key)
        if v is None or (isinstance(v, str) and v.strip()):
            return v.strip() if isinstance(v, str) else None
        errors.append(f"{key} must be a non-empty string or null")
        return None

    salary_text = _opt_str("salary_text")
    soc_hint = _opt_str("soc_hint")
    sponsor = payload.get("sponsor_hint")
    if sponsor is not None and sponsor not in SPONSOR_VALUES:
        sponsor = None
    if sponsor not in ("sponsors", "no_sponsor"):
        sponsor = None          # 'unknown' adds nothing to a row
    if errors:
        return None, errors
    return {"skills": skills, "salary_text": salary_text,
            "sponsor_hint": sponsor, "soc_hint": soc_hint}, []


def accept_reading(cur, owner_id, role_id: int, payload, *,
                   provenance: str = "user-ai") -> dict:
    """Verify and persist one submitted reading for one staged listing."""
    cur.execute(
        "select r.role_id, r.jd_full, r.staged_at "
        "from role_listings r join target_companies c "
        "on c.company_id = r.company_id "
        "where r.role_id = %s and c.owner_id = %s",
        (role_id, owner_id))
    row = cur.fetchone()
    if row is None:
        return {"outcome": "not_found", "role_id": role_id}
    if row["staged_at"] is None:
        return {"outcome": "not_staged", "role_id": role_id}

    clean, errors = _validate(payload)
    if errors:
        return {"outcome": "invalid", "role_id": role_id, "errors": errors}

    jd = row["jd_full"] or ""
    # Skills keep the STRICT raw-text gate. Widening them would admit more
    # ungrounded claims into the skill rows, and those rows decide which jobs
    # the owner is shown — the asymmetry is deliberate, and
    # tests/test_salary_gate_html.py fails if it is ever quietly removed.
    grounded = [(name, cat) for name, cat in clean["skills"]
                if check_grounding(norm(name), jd)]
    rejected = [name for name, _ in clean["skills"]
                if not check_grounding(norm(name), jd)]

    # Salary is grounded against what the advert SAYS, not against its markup.
    # Board feeds keep raw HTML, so a range a person reads as "£77,500 —
    # £90,000" is stored as three elements with an entity between them, and a
    # substring test against the bytes refuses a figure that is plainly on the
    # page. Stripping first compares the claim to the same text a human read.
    # This is not a weakening: a salary that appears nowhere in the readable
    # advert is still refused, and the markup itself is no longer quotable.
    salary = clean["salary_text"]
    salary_rejected = bool(salary) and not check_grounding(
        salary, clean_html(jd))
    if salary_rejected:
        salary = None
    if rejected or salary_rejected:
        record(cur, AUDIT_TOOL, {"role_id": role_id, "provenance": provenance},
               {"rejected_skills": rejected,
                "rejected_salary": clean["salary_text"] if salary_rejected
                else None})

    # replace the derived skill rows — the upgrade, not an accumulation
    cur.execute("delete from role_skills where role_id = %s", (role_id,))
    reading = SimpleNamespace(skills=grounded, salary_text=salary,
                              sponsor_hint=clean["sponsor_hint"],
                              soc_hint=clean["soc_hint"])
    resolver = make_resolver(load_occupation_index(cur))
    persist_reading(cur, role_id, reading, soc_resolver=resolver,
                    read_quality="ai", provenance=provenance)

    if salary_rejected:
        # HOLD the row, with its claim, for one corrected submission. Before
        # this, the un-stage below ran whatever happened: the client was told
        # its salary was rejected about a listing it could no longer reach,
        # so a rejected FIELD meant a lost reading rather than a retry.
        # The grounded skills above are already persisted, so nothing correct
        # is thrown away — only the one field is outstanding.
        # This cannot trap a listing: submitting again with a groundable
        # salary, or with none at all, takes the branch below and releases it,
        # and an abandoned claim is freed by the ordinary 60-minute reclaim.
        return {"outcome": "held_for_retry", "role_id": role_id,
                "skills_accepted": len(grounded), "rejected_skills": rejected,
                "salary_rejected": True,
                "retry": "resubmit with a salary quoted from the advert's "
                         "readable text, or with salary_text null to finish"}

    cur.execute(
        "update role_listings set staged_at = null, claimed_at = null, "
        "staged_tier = null where role_id = %s", (role_id,))
    return {"outcome": "accepted", "role_id": role_id,
            "skills_accepted": len(grounded), "rejected_skills": rejected,
            "salary_rejected": False}
