-- 0006_skill_views.sql
-- Applied via Supabase MCP (apply_migration: v2_skill_views).
-- Skill demand across the fit queue, and the gap vs my_skills.

create or replace view v_skill_demand as
select rs.skill_norm,
       max(rs.skill_asked) as skill,
       max(rs.skill_type) as skill_type,
       count(distinct rs.role_id) as demand
from role_skills rs
join v_apply_queue q on q.role_id = rs.role_id
group by rs.skill_norm;

create or replace view v_skill_gap as
select d.skill, d.skill_type, d.demand,
       (m.skill_norm is not null) as i_have_it,
       m.level as my_level
from v_skill_demand d
left join my_skills m on m.skill_norm = d.skill_norm and m.status in ('active','in_progress')
order by (m.skill_norm is not null), d.demand desc;

comment on view v_skill_demand is 'Skill demand across the fit apply queue: distinct fit roles requesting each skill.';
comment on view v_skill_gap is 'Skill demand vs my_skills: gaps (i_have_it=false) ranked by demand = what to learn first.';
