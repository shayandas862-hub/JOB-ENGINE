-- 0012 · GA-004 — skill synonym map (AI spot #2).
-- Maps each messy role-skill name (raw_norm) to a canonical form. When the
-- canonical equals one of my_skills (canonical_norm = my_skills.skill_norm) the
-- skill-gap join finally reconciles variants like "ai agents" / "gen ai".
-- Decided once by Gemini, cached here, reused forever. 'low' confidence rows are
-- flagged for human review. Engine writes via the direct (RLS-bypassing) role;
-- RLS is enabled with no policy to match the other engine tables (locked).

BEGIN;

CREATE TABLE IF NOT EXISTS skill_synonyms (
    raw_norm        text PRIMARY KEY,
    canonical_label text NOT NULL,
    canonical_norm  text NOT NULL,
    my_skill_match  boolean NOT NULL DEFAULT false,
    confidence      text NOT NULL DEFAULT 'high',   -- 'high' | 'low' (review)
    source          text NOT NULL DEFAULT 'gemini', -- 'gemini' | 'manual'
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS skill_synonyms_canonical_norm_idx ON skill_synonyms (canonical_norm);

ALTER TABLE skill_synonyms ENABLE ROW LEVEL SECURITY;

COMMIT;
