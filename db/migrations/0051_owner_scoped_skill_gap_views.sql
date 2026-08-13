-- 0051 · Phase 9 task 1b — the skill-gap views learn WHOSE gap it is.
--
-- v_skill_gap was the one read in the task-1b scoping map that could not be
-- scoped from the caller: it carried no owner column at all, so a second
-- owner's skill demand and a second owner's my_skills both leaked into every
-- answer. Both views gain owner_id, carried down from v_apply_queue (which
-- already exposes target_companies.owner_id), and my_skills now joins on the
-- SAME owner rather than on skill_norm alone.
--
-- DROP + CREATE, not CREATE OR REPLACE: replace can only append columns, and
-- owner_id belongs first. Both are recreated WITH (security_invoker = true)
-- explicitly — the 0046→0047 lesson (B-GAE-006) is that reloptions do not
-- survive a replace, so they are stated here rather than assumed.
--
-- Verified after applying: reloptions = {security_invoker=true} on both;
-- grants inherited unchanged (anon/authenticated/postgres/service_role);
-- get_advisors reports no new finding; 1 owner, 921 gap rows, 908 missing.
BEGIN;

DROP VIEW IF EXISTS public.v_skill_gap;
DROP VIEW IF EXISTS public.v_skill_demand;

CREATE VIEW public.v_skill_demand WITH (security_invoker = true) AS
SELECT q.owner_id,
       COALESCE(ss.canonical_norm, rs.skill_norm)        AS skill_norm,
       max(COALESCE(ss.canonical_label, rs.skill_asked)) AS skill,
       max(rs.skill_type)                                AS skill_type,
       count(DISTINCT rs.role_id)                        AS demand
  FROM role_skills rs
  JOIN v_apply_queue q ON q.role_id = rs.role_id
  LEFT JOIN skill_synonyms ss ON ss.raw_norm = rs.skill_norm
 GROUP BY q.owner_id, COALESCE(ss.canonical_norm, rs.skill_norm);

CREATE VIEW public.v_skill_gap WITH (security_invoker = true) AS
SELECT d.owner_id,
       d.skill,
       d.skill_type,
       d.demand,
       (m.skill_norm IS NOT NULL) AS i_have_it,
       m.level                    AS my_level
  FROM v_skill_demand d
  LEFT JOIN my_skills m
         ON m.owner_id  = d.owner_id
        AND m.skill_norm = d.skill_norm
        AND m.status = ANY (ARRAY['active'::text, 'in_progress'::text]);

COMMENT ON VIEW public.v_skill_demand IS
  'Per-owner skill demand over that owner''s apply queue, canonicalised through skill_synonyms.';
COMMENT ON VIEW public.v_skill_gap IS
  'Per-owner skill demand vs that owner''s my_skills: gaps (i_have_it=false) ranked by demand. Callers MUST filter on owner_id.';

COMMIT;
