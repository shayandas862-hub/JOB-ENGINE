-- 0010 · GA-009 — drop the 3 dead columns on role_skills.
-- i_have_it / my_level / gap were 0% filled (0/2817); the skill views already
-- compute these by joining role_skills.skill_norm -> my_skills.skill_norm.
-- Keeping the stored columns is a second source of truth waiting to go stale.
--
-- v_full read those columns directly, so it is recreated to compute them by
-- LEFT JOIN to my_skills (same logic as v_skill_gap). It was also missing
-- security_invoker=true (the other views have it) — set it here.

BEGIN;

DROP VIEW IF EXISTS v_full;

ALTER TABLE role_skills
  DROP COLUMN IF EXISTS i_have_it,
  DROP COLUMN IF EXISTS my_level,
  DROP COLUMN IF EXISTS gap;

CREATE VIEW v_full
WITH (security_invoker = true) AS
SELECT
  c.company_name,
  c.lane,
  c.fit_rank,
  r.role_title,
  r.role_status,
  r.application_status,
  s.skill_asked,
  s.skill_norm,
  (m.skill_norm IS NOT NULL) AS i_have_it,
  m.level             AS my_level,
  (m.skill_norm IS NULL)  AS gap
FROM role_skills s
JOIN role_listings r  ON s.role_id = r.role_id
JOIN target_companies c ON r.company_id = c.company_id
LEFT JOIN my_skills m
  ON m.skill_norm = s.skill_norm
 AND m.status = ANY (ARRAY['active', 'in_progress']);

COMMIT;
