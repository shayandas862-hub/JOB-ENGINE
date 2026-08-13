"""Tests for src/reading/ — the sieve-3 staged work queue.

Pins the boundary design (decision log 2026-08-02 15:21): the tray serves
sieve-1/2 survivors with a stored JD; the extraction prompt is SERVER-side,
versioned data; every submission is verified deterministically — a claimed
skill or salary that is not verbatim in the stored JD is dropped and the
reject recorded; rows upgrade in place (read_quality -> 'ai') and the flow
is idempotent and owner-scoped. A hallucinating client can only cause
omission, never poison.
"""
from __future__ import annotations

from reading import accept as accept_mod
from reading import serve, stage
from reading.accept import accept_reading
from reading.serve import EXTRACTION_PROMPT, PROMPT_VERSION, get_batch
from reading.stage import stage_ready

from tests.conftest import ScriptedCursor

OWNER = "00000000-0000-4000-a000-000000000001"

JD = ("We are hiring. You will build data pipelines in Python and SQL on "
      "AWS. Salary £70,000 - £90,000. Visa sponsorship available.")


def _sql(cur, fragment):
    return [(s, p) for s, p in cur.executed if fragment in s.lower()]


# --- stage -------------------------------------------------------------------

def _stage_cursor(rows):
    return ScriptedCursor([
        ("from profiles", [[{"profile_id": OWNER, "name": "T"}]]),
        ("from my_constraints", [[
            {"kind": "kill_keyword", "value": "audit", "numeric_value": None}]]),
        ("from target_roles", [[{"search_title": "Data Engineer"},
                                {"search_title": "Software Engineer"}]]),
        ("select r.role_id, r.role_title from role_listings", [rows]),
        ("update role_listings set staged_at", [[]]),
    ])


def test_stage_stamps_matches_and_labels_near_misses():
    # U7: the tray starved because sieve 2 dropped every non-matching title
    # (0 of 1,083 staged, measured 2026-08-10). Non-matching survivors now
    # stage as a LABELLED near-miss tier the client AI may accept or skip.
    cur = _stage_cursor([
        {"role_id": 1, "role_title": "Senior Data Engineer"},
        {"role_id": 2, "role_title": "Head Chef"},
        {"role_id": 3, "role_title": "Software Engineer (Platform)"},
    ])
    result = stage_ready(cur, OWNER)
    assert result == {"candidates": 3, "staged": 2, "near_miss": 1}
    updates = _sql(cur, "set staged_at")
    stamped = {params[0]: params[1] for _s, params in updates}
    assert stamped == {"match": [1, 3], "near_miss": [2]}


def test_stage_respects_kill_keywords_in_both_tiers():
    # A kill keyword is the owner's explicit no — it never reaches the tray,
    # not even as a near miss.
    cur = _stage_cursor([{"role_id": 9, "role_title": "Data Engineer (Audit)"}])
    result = stage_ready(cur, OWNER)
    assert result["staged"] == 0 and result["near_miss"] == 0
    assert _sql(cur, "set staged_at") == []


def test_near_miss_tier_is_capped_per_run():
    rows = [{"role_id": i, "role_title": f"Care Assistant {i}"}
            for i in range(30)]
    cur = _stage_cursor(rows)
    result = stage_ready(cur, OWNER, near_miss_cap=25)
    assert result["near_miss"] == 25
    stamped = {p[0]: p[1] for _s, p in _sql(cur, "set staged_at")}
    assert stamped["near_miss"] == [r["role_id"] for r in rows[:25]]


def test_pin_stage_selects_open_local_jd_rows_not_yet_ai_read():
    sql = " ".join(stage.STAGEABLE_SQL.split()).lower()
    for predicate in ("role_status = 'open'", "is_local",
                      "coalesce(r.jd_full, '') <> ''",
                      "read_quality is distinct from 'ai'",
                      "staged_at is null", "owner_id",
                      # a skipped row stays skipped — the stamp survives
                      "reading_skipped_at is null"):
        assert predicate in sql, predicate
    # deterministic near-miss pick: newest candidates first
    assert "order by" in sql and "created_at desc" in sql


def test_skip_reading_stamps_and_unstages():
    from reading.stage import skip_reading
    cur = ScriptedCursor([
        ("select r.role_id, r.staged_at",
         [[{"role_id": 7, "staged_at": "2026-08-10"}]]),
        ("update role_listings", [[]]),
    ])
    out = skip_reading(cur, OWNER, 7)
    assert out == {"outcome": "skipped", "role_id": 7}
    update_sql = _sql(cur, "reading_skipped_at = now()")[0][0].lower()
    assert "staged_at = null" in update_sql
    assert "claimed_at = null" in update_sql


def test_skip_reading_is_owner_scoped_and_honest_about_state():
    from reading.stage import skip_reading
    not_found = ScriptedCursor([("select r.role_id, r.staged_at", [[]])])
    assert skip_reading(not_found, OWNER, 99)["outcome"] == "not_found"
    unstaged = ScriptedCursor([
        ("select r.role_id, r.staged_at",
         [[{"role_id": 7, "staged_at": None}]])])
    assert skip_reading(unstaged, OWNER, 7)["outcome"] == "not_staged"


# --- serve -------------------------------------------------------------------

def test_batch_serves_prompt_shape_and_jobs_and_claims_them():
    cur = ScriptedCursor([
        ("set claimed_at = null", [[]]),
        ("select count(*) as n", [[{"n": 4}]]),
        ("from role_listings r join target_companies",
         [[{"role_id": 1, "role_title": "Data Engineer", "jd_full": JD,
            "staged_tier": "match"}]]),
        ("update role_listings set claimed_at = now()", [[]]),
    ])
    batch = get_batch(cur, OWNER, limit=5)
    assert batch["prompt_version"] == PROMPT_VERSION
    assert batch["prompt"] == EXTRACTION_PROMPT
    for key in ("skills", "salary_text", "sponsor_hint", "soc_hint"):
        assert key in str(batch["required_shape"])
    assert batch["jobs"][0]["role_id"] == 1
    assert batch["jobs"][0]["jd_full"] == JD
    assert len(_sql(cur, "set claimed_at = now()")) == 1


def test_batch_serves_the_tier_label_and_matches_first():
    # U7: near-miss rows ride LABELLED so the client AI can accept or skip;
    # title-matched rows always claim ahead of them.
    sql = " ".join(serve.BATCH_SQL.split()).lower()
    assert "staged_tier" in sql
    order = sql.rsplit("order by", 1)[1]
    assert "near_miss" in order            # matches sort before near misses


def test_prompt_is_server_side_versioned_data():
    # The prompt lives with the engine and warns about the grounding gate;
    # clients receive it per batch and add nothing of their own.
    assert PROMPT_VERSION.startswith("extract-v")
    assert "never infer" in EXTRACTION_PROMPT
    assert "verbatim" in EXTRACTION_PROMPT.lower()


def test_stale_claims_are_reclaimed_before_serving():
    sql = " ".join(serve.RECLAIM_SQL.split()).lower()
    assert "claimed_at = null" in sql
    assert "make_interval" in sql


# --- accept ------------------------------------------------------------------

def _accept_cursor(*, staged=True, jd=JD, found=True):
    row = {"role_id": 1, "jd_full": jd,
           "staged_at": "2026-08-02T09:00:00Z" if staged else None}
    return ScriptedCursor([
        ("select r.role_id, r.jd_full, r.staged_at", [[row] if found else []]),
        ("from skilled_worker_occupations", [[]]),
        ("delete from role_skills", [[]]),
        ("insert into role_skills", [[]]),
        ("update role_listings set", [[]]),
    ])


def _payload(**kw):
    base = {"skills": [{"name": "Python", "category": "programming"},
                       {"name": "SQL", "category": "programming"}],
            "salary_text": "£70,000 - £90,000",
            "sponsor_hint": "sponsors", "soc_hint": None}
    base.update(kw)
    return base


def test_grounded_submission_is_accepted_and_upgrades_in_place():
    cur = _accept_cursor()
    result = accept_reading(cur, OWNER, 1, _payload(), provenance="user-ai")
    assert result["outcome"] == "accepted"
    assert result["skills_accepted"] == 2
    assert result["rejected_skills"] == []
    # old derived rows are replaced, not duplicated
    assert len(_sql(cur, "delete from role_skills")) == 1
    assert len(_sql(cur, "insert into role_skills")) == 1
    # the row upgrades in place: read_quality 'ai' + provenance, tray cleared
    updates = " ".join(s for s, _ in _sql(cur, "update role_listings set"))
    assert "read_quality" in updates
    assert "staged_at = null" in updates


def test_ungrounded_skill_is_dropped_and_the_reject_recorded():
    cur = _accept_cursor()
    result = accept_reading(
        cur, OWNER, 1,
        _payload(skills=[{"name": "Python", "category": "programming"},
                         {"name": "Kubernetes", "category": "cloud"}]))
    assert result["outcome"] == "accepted"
    assert result["skills_accepted"] == 1
    assert result["rejected_skills"] == ["Kubernetes"]
    audits = _sql(cur, "insert into mcp_audit")
    assert len(audits) == 1 and "Kubernetes" in str(audits[0][1])


def test_fabricated_salary_is_dropped_as_ungrounded():
    # The outcome changed in Phase 9.5 task 6, deliberately: a rejected salary
    # now HOLDS the listing in the tray so the one field can be corrected,
    # where before the row was released and the client was told "rejected"
    # about a listing it could no longer reach. What this test has always
    # guarded is unchanged and still asserted — an ungrounded salary never
    # reaches a row.
    cur = _accept_cursor()
    result = accept_reading(cur, OWNER, 1,
                            _payload(salary_text="£150,000 - £200,000"))
    assert result["outcome"] == "held_for_retry"
    assert result["salary_rejected"] is True
    written = [p for _, params in _sql(cur, "update role_listings set")
               for p in (params or ()) if isinstance(p, str)]
    assert "£150,000 - £200,000" not in written


def test_submission_for_unstaged_row_is_an_idempotent_no_op():
    cur = _accept_cursor(staged=False)
    result = accept_reading(cur, OWNER, 1, _payload())
    assert result == {"outcome": "not_staged", "role_id": 1}
    assert _sql(cur, "insert into role_skills") == []
    assert _sql(cur, "update role_listings set") == []


def test_wrong_owner_sees_nothing():
    cur = _accept_cursor(found=False)
    result = accept_reading(cur, "someone-else", 1, _payload())
    assert result == {"outcome": "not_found", "role_id": 1}
    assert _sql(cur, "update role_listings set") == []


def test_malformed_payload_is_rejected_with_errors_and_no_writes():
    cur = _accept_cursor()
    result = accept_reading(cur, OWNER, 1, {"skills": "python, sql"})
    assert result["outcome"] == "invalid"
    assert result["errors"]
    assert _sql(cur, "insert into role_skills") == []
    assert _sql(cur, "update role_listings set") == []


def test_enums_are_validated_junk_never_lands():
    cur = _accept_cursor()
    result = accept_reading(
        cur, OWNER, 1,
        _payload(skills=[{"name": "Python", "category": "wizardry"}],
                 sponsor_hint="definitely!"))
    assert result["outcome"] == "accepted"
    skill_rows = _sql(cur, "insert into role_skills")[0][1]
    assert skill_rows == [(1, "Python", "python", "other")]
    update_params = _sql(cur, "update role_listings set")[0][1]
    assert "definitely!" not in [p for p in update_params if isinstance(p, str)]


def test_pin_the_reading_boundary_imports_no_ai():
    # The verification boundary is deterministic: none of the tray modules may
    # touch the AI SDK or the caged Gemini reader, even transitively by name.
    import inspect
    for mod in (stage, serve, accept_mod):
        source = inspect.getsource(mod).lower()
        assert "gemini" not in source
        assert "genai" not in source


def test_pin_served_enums_match_the_caged_reader():
    # One vocabulary for readings, wherever they come from: the serve contract
    # must agree with the Gemini reader's schema without importing it.
    from read.gemini import SKILL_CATEGORIES, SPONSOR_VALUES
    assert serve.SKILL_CATEGORIES == SKILL_CATEGORIES
    assert serve.SPONSOR_VALUES == SPONSOR_VALUES
