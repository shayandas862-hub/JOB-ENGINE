"""Tests for src/cv/generate — the end-to-end CV builder (blocks -> docx).

Offline and deterministic: with no Gemini key, phrasing falls back to the verbatim
facts, so the whole assemble -> phrase -> truth-gate -> render chain runs without a
network. A routing fake cursor serves cv_blocks / role_skills / profiles.
"""
from __future__ import annotations

import io

from docx import Document


class RoutingCursor:
    def __init__(self, cv_blocks=None, skills=None, profile=None):
        self._cv, self._skills, self._profile = cv_blocks or [], skills or [], profile
        self.executed = []
        self._pending = []

    def execute(self, sql, params=None):
        s = " ".join(sql.split()).lower()
        self.executed.append((s, params))
        if "from cv_blocks" in s:
            self._pending = list(self._cv)
        elif "from role_skills" in s:
            self._pending = list(self._skills)
        elif "from profiles" in s:
            self._pending = [self._profile] if self._profile else []
        else:
            self._pending = []

    def fetchall(self):
        return list(self._pending)

    def fetchone(self):
        return self._pending[0] if self._pending else None


def cvrow(block_id, kind, fact, skills, title=None, org=None, dr=None, sort_hint=0):
    return {"block_id": block_id, "kind": kind, "title": title, "organisation": org,
            "date_range": dr, "fact_text": fact, "skill_norms": list(skills),
            "sort_hint": sort_hint}


BLOCKS = [
    cvrow(1, "role", "Led analytics at Acme, cutting reporting time 40%.",
          ["sql", "python"], "Data Analyst", "Acme", "2021-2023"),
    cvrow(2, "skill_evidence", "SQL, Python and dbt in production.", ["sql", "dbt"]),
    cvrow(3, "role", "Ran marketing campaigns.", ["seo"], "Marketer", "Beta", "2018-2020"),
]


def test_load_listing_skills_reads_role_skills():
    from cv.generate import load_listing_skills
    cur = RoutingCursor(skills=[{"skill_norm": "sql"}, {"skill_norm": "python"}])
    assert load_listing_skills(cur, 917) == ["sql", "python"]
    assert "from role_skills" in cur.executed[0][0]
    assert cur.executed[0][1] == (917,)


def test_load_header_reads_the_profile():
    from cv.generate import load_header
    cur = RoutingCursor(profile={"name": "Shayan Das", "contact_email": "s@x.com"})
    h = load_header(cur, "p-1")
    assert h.name == "Shayan Das" and "s@x.com" in h.contact


def test_generate_cv_builds_a_valid_docx_grounded_in_the_facts():
    from cv.generate import generate_cv
    from cv.render import CvHeader
    cur = RoutingCursor(cv_blocks=BLOCKS)

    build = generate_cv(cur, "p-1", job_title="Data Engineer",
                        listing_skills=["sql", "python"], header=CvHeader("Shayan", "s@x.com"))

    doc = Document(io.BytesIO(build.docx))
    texts = "\n".join(p.text for p in doc.paragraphs)
    assert "Shayan" in texts
    # the SQL/analytics blocks outrank the marketing block for a data role
    assert "Led analytics at Acme" in texts
    # no Gemini key -> every bullet is the verbatim fact (all fell back), so all truthful
    assert build.fallbacks == build.used and build.used >= 2


def test_generate_cv_can_cap_the_block_count():
    from cv.generate import generate_cv
    from cv.render import CvHeader
    cur = RoutingCursor(cv_blocks=BLOCKS)
    build = generate_cv(cur, "p-1", job_title="Data Engineer", listing_skills=["sql"],
                        header=CvHeader("S", ""), max_blocks=1)
    assert build.used == 1
