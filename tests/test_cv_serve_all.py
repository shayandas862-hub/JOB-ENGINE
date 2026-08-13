"""src/cv/serve_all.py — the serve-all CV path (Phase 8.5 task 0 / U8).

The founder's call (2026-08-10, serve-all correction): the client AI
receives EVERY confirmed cv_block and selects relevance itself — a filtered
fact is unknowable to the client, and transferable evidence is exactly what
a literal matcher hides. The engine's skill match survives only as an
optional HINT; the truth gate stays the ceiling (select freely, invent
never); the ENGINE renders the .docx. Offline throughout.
"""
from __future__ import annotations

from tests.test_criteria import RoutingCursor

JOB = {"role_id": 917, "role_title": "Care Coordinator",
       "company_name": "Sunrise Care", "jd_full": "Coordinate care rotas...",
       "role_url": "https://x/1"}

BLOCKS = [
    {"block_id": 1, "kind": "role", "title": "Team Lead",
     "organisation": "Acme", "date_range": "2022-2024",
     "fact_text": "Led a team of 6 through 3 product launches.",
     "skill_norms": ["leadership"], "sort_hint": 1},
    {"block_id": 2, "kind": "skill_evidence", "title": None,
     "organisation": None, "date_range": None,
     "fact_text": "Built rota planning tooling in Python for 40 staff.",
     "skill_norms": ["python"], "sort_hint": 2},
]


def _serve_cursor(job=JOB, blocks=BLOCKS, listing_skills=("python",)):
    return RoutingCursor([
        ("from role_listings r join target_companies", [job] if job else []),
        ("from cv_blocks", blocks),
        ("from role_skills", [{"skill_norm": s} for s in listing_skills]),
    ])


def test_serve_cv_serves_every_confirmed_block_never_a_filtered_subset():
    # THE serve-all pin: listing skills match only block 2, yet BOTH blocks
    # are served — the hint hints, the filter is gone.
    from cv.serve_all import CV_PROMPT_VERSION, serve_cv
    out = serve_cv(_serve_cursor(), "owner-1", 917)
    assert out["outcome"] == "served"
    assert [b["block_id"] for b in out["blocks"]] == [1, 2]
    assert out["skill_hint"] == ["python"]           # a hint, never a limit
    assert out["prompt_version"] == CV_PROMPT_VERSION == "cv-v1"
    assert "invent" in out["prompt"].lower()
    assert out["job"]["role_id"] == 917 and out["job"]["jd_full"]
    # only confirmed blocks are grounding-worthy
    blocks_sql = [s for s, _ in _serve_cursor().executed]  # shape check below
    cur = _serve_cursor()
    serve_cv(cur, "owner-1", 917)
    cv_sql = [s for s, _ in cur.executed if "from cv_blocks" in s.lower()][0]
    assert "confirmed" in cv_sql.lower()


def test_serve_cv_is_honest_about_missing_job_and_empty_blocks():
    from cv.serve_all import serve_cv
    assert serve_cv(_serve_cursor(job=None), "owner-1", 1)["outcome"] == "not_found"
    out = serve_cv(_serve_cursor(blocks=[]), "owner-1", 917)
    assert out["outcome"] == "no_blocks"


def test_accept_cv_gates_each_bullet_and_renders_the_docx(tmp_path):
    from cv.serve_all import accept_cv
    cur = RoutingCursor([
        ("from role_listings r join target_companies", [JOB]),
        ("from cv_blocks", BLOCKS),
        ("from profiles", [{"name": "Test Person",
                            "contact_email": "t@example.com"}]),
    ])
    submission = {"blocks": [
        # grounded rephrase — survives
        {"block_id": 2, "bullet": "Built rota planning tooling in Python"},
        # invented number — the gate replaces it with the verbatim fact
        {"block_id": 1, "bullet": "Led a team of 60 through launches"},
    ]}
    out = accept_cv(cur, "owner-1", 917, submission, cv_dir=tmp_path)
    assert out["outcome"] == "rendered"
    assert out["used"] == 2 and out["fallbacks"] == 1
    assert out["docx"][:2] == b"PK"                  # a real .docx (zip magic)
    assert out["rejected_block_ids"] == []
    assert (tmp_path / "cv-917.docx").exists()       # the engine saved it


def test_accept_cv_rejects_unknown_blocks_and_bad_shapes(tmp_path):
    from cv.serve_all import accept_cv
    cur = RoutingCursor([
        ("from role_listings r join target_companies", [JOB]),
        ("from cv_blocks", BLOCKS),
        ("from profiles", [{"name": "T", "contact_email": ""}]),
    ])
    out = accept_cv(cur, "owner-1", 917, {"blocks": [
        {"block_id": 999, "bullet": "A fabricated block"},
        {"block_id": 1, "bullet": "Led a team of 6 through 3 product launches."},
    ]}, cv_dir=tmp_path)
    assert out["outcome"] == "rendered"
    assert out["rejected_block_ids"] == [999]        # dropped, never invented
    assert out["used"] == 1

    for bad in (None, {}, {"blocks": []}, {"blocks": [{"block_id": 1}]},
                {"blocks": "not-a-list"}):
        result = accept_cv(_serve_cursor(), "owner-1", 917, bad,
                           cv_dir=tmp_path)
        assert result["outcome"] == "invalid", bad


def test_accept_cv_not_found_and_no_blocks_are_honest():
    from cv.serve_all import accept_cv
    missing = RoutingCursor([
        ("from role_listings r join target_companies", [])])
    ok_shape = {"blocks": [{"block_id": 1, "bullet": "x"}]}
    assert accept_cv(missing, "owner-1", 1, ok_shape)["outcome"] == "not_found"


def test_the_prompt_is_server_side_versioned_data():
    from cv.serve_all import CV_PROMPT, CV_PROMPT_VERSION, REQUIRED_SHAPE
    assert CV_PROMPT_VERSION == "cv-v1"
    low = CV_PROMPT.lower()
    for promise in ("only", "invent", "hint", "engine"):
        assert promise in low, promise
    assert "block_id" in str(REQUIRED_SHAPE)
