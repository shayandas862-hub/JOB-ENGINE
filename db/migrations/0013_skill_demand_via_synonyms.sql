-- 0013 · GA-004 — route the skill-gap through the synonym map.
-- v_skill_demand now groups by the canonical name (coalesce(synonym, raw)), so
-- variants collapse and v_skill_gap's join (demand.skill_norm = my_skills.skill_norm)
-- finally matches my skills. v_skill_gap itself is unchanged — it just receives
-- canonical names now. security_invoker preserved.

BEGIN;

CREATE OR REPLACE VIEW v_skill_demand
WITH (security_invoker = true) AS
SELECT
    coalesce(ss.canonical_norm, rs.skill_norm)        AS skill_norm,
    max(coalesce(ss.canonical_label, rs.skill_asked)) AS skill,
    max(rs.skill_type)                                AS skill_type,
    count(DISTINCT rs.role_id)                        AS demand
FROM role_skills rs
JOIN v_apply_queue q ON q.role_id = rs.role_id
LEFT JOIN skill_synonyms ss ON ss.raw_norm = rs.skill_norm
GROUP BY coalesce(ss.canonical_norm, rs.skill_norm);

COMMIT;
