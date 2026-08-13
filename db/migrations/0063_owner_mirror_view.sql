-- 0063 · Phase 9.5 task 1 — the mirror, as a curated view.
--
-- src/cv/mirror.py re-forms the same understanding in Python because it needs
-- the RECEIPTS: which block proves which skill, and the names of the skills a
-- CV could not claim. A view cannot carry those without exploding the row.
-- This view carries only the COUNTS, which is all the dashboard renders — and
-- the dashboard may read nothing but curated views (tests/test_dashboard.py
-- pins that by scanning the package source for raw table names).
--
-- Two implementations of one idea is the shape that rotted in B-GAE-025, so
-- they are held together by a test rather than by intention:
-- tests/test_cv_mirror.py::test_the_view_and_the_python_fold_agree_on_the_same_rows
-- builds a fact base in a probe schema and asserts every count matches.
--
-- One row per profile, always — a brand-new owner with nothing recorded still
-- appears, with zeros, because "we have not met you yet" is a real state and
-- an absent row would render as a broken card.
--
-- security_invoker = true, stated rather than assumed (B-GAE-006).
-- Verified after applying: reloptions = {security_invoker=true}; get_advisors
-- reports no new finding (3 pre-existing WARNs unchanged); 1 owner, and the
-- row matches src/cv/mirror.py exactly — 38 confirmed facts, 0 drafts,
-- 1 retired, 21 live skills, 4 evidenced, 17 unevidenced, 4 outside paid work.
BEGIN;

CREATE VIEW public.v_owner_mirror WITH (security_invoker = true) AS
WITH serving AS (
    -- What a CV may actually be built from: confirmed and never retired. The
    -- same test cv.blocks.load_cv_blocks applies, so the mirror can never
    -- promise a line the truth gate would then refuse to write.
    SELECT owner_id, kind, skill_norms
      FROM cv_blocks
     WHERE confirmed AND retired_at IS NULL
), evidence AS (
    SELECT s.owner_id,
           n.skill_norm,
           bool_or(s.kind = 'role')  AS in_paid_work
      FROM serving s
      CROSS JOIN LATERAL unnest(s.skill_norms) AS n(skill_norm)
     GROUP BY s.owner_id, n.skill_norm
), live_skills AS (
    SELECT owner_id, skill_norm
      FROM my_skills
     WHERE status IN ('active', 'in_progress')
)
SELECT p.profile_id AS owner_id,
       p.name,
       (SELECT count(*) FROM cv_blocks b
         WHERE b.owner_id = p.profile_id AND b.confirmed
           AND b.retired_at IS NULL)                          AS facts_confirmed,
       (SELECT count(*) FROM cv_blocks b
         WHERE b.owner_id = p.profile_id AND NOT b.confirmed
           AND b.retired_at IS NULL)                          AS facts_drafts,
       (SELECT count(*) FROM cv_blocks b
         WHERE b.owner_id = p.profile_id
           AND b.retired_at IS NOT NULL)                      AS facts_retired,
       (SELECT count(DISTINCT s.kind) FROM serving s
         WHERE s.owner_id = p.profile_id)                     AS fact_kinds,
       (SELECT count(*) FROM live_skills l
         WHERE l.owner_id = p.profile_id)                     AS skills_live,
       (SELECT count(*) FROM live_skills l
         JOIN evidence e ON e.owner_id = l.owner_id
                        AND e.skill_norm = l.skill_norm
         WHERE l.owner_id = p.profile_id)                     AS skills_evidenced,
       (SELECT count(*) FROM live_skills l
         LEFT JOIN evidence e ON e.owner_id = l.owner_id
                             AND e.skill_norm = l.skill_norm
         WHERE l.owner_id = p.profile_id
           AND e.skill_norm IS NULL)                          AS skills_unevidenced,
       -- A skill proven by a job is proven by the job; only a skill with NO
       -- paid-work evidence counts here, or the honest number inflates.
       (SELECT count(*) FROM live_skills l
         JOIN evidence e ON e.owner_id = l.owner_id
                        AND e.skill_norm = l.skill_norm
         WHERE l.owner_id = p.profile_id
           AND NOT e.in_paid_work)                            AS evidenced_outside_paid_work
  FROM profiles p;

COMMIT;
