-- 0009_security_invoker_views.sql
-- Applied via Supabase MCP (apply_migration: v2_security_invoker_views).
-- Hardening: recreate the views with security_invoker=true so they respect the
-- querying role's RLS instead of the creator's (fixes the security_definer_view
-- advisor). The engine connects as `postgres` (bypasses RLS) so this is transparent
-- to it, while closing any anon-API bypass.

drop view if exists v_skill_gap;
drop view if exists v_skill_demand;
drop view if exists v_apply_queue;

create view v_apply_queue with (security_invoker = true) as
select
  r.role_id, c.company_name, c.fit_rank,
  case when c.sponsor_confidence ilike '%sponsors%' then 'confirmed'
       when c.sponsor_confidence ilike '%register-only%' then 'register-only'
       else 'weak' end as sponsor_signal,
  r.role_title, r.location, r.salary_text, r.salary_min, r.salary_max,
  case when r.salary_max is null then 'unknown'
       when r.salary_max >= (select numeric_value from my_constraints where kind='salary_threshold_standard') then 'clears'
       when r.salary_max >= (select numeric_value from my_constraints where kind='salary_threshold_new_entrant') then 'clears_new_entrant'
       else 'below' end as salary_wall,
  r.role_url, r.created_at::date as first_seen, c.sponsor_confidence, c.lane
from role_listings r
join target_companies c on c.company_id = r.company_id
where r.role_status = 'open'
  and r.role_title ~* '(solutions? (engineer|architect)|forward[- ]deployed|applied ai|ai engineer|machine learning engineer|ml engineer|llm engineer|ai/ml|generative ai|gen ?ai|customer engineer|deployment engineer|developer advocate|sales engineer|technical consultant|ai consultant|implementation engineer|integration engineer|onboarding engineer|ai product|technical product manager)'
order by
  case c.fit_rank when 'High' then 1 when 'Med' then 2 when 'Low' then 3 else 4 end,
  case when c.sponsor_confidence ilike '%sponsors%' then 1 when c.sponsor_confidence ilike '%register-only%' then 2 else 3 end,
  r.created_at desc;

create view v_skill_demand with (security_invoker = true) as
select rs.skill_norm, max(rs.skill_asked) as skill, max(rs.skill_type) as skill_type,
       count(distinct rs.role_id) as demand
from role_skills rs join v_apply_queue q on q.role_id = rs.role_id
group by rs.skill_norm;

create view v_skill_gap with (security_invoker = true) as
select d.skill, d.skill_type, d.demand,
       (m.skill_norm is not null) as i_have_it, m.level as my_level
from v_skill_demand d
left join my_skills m on m.skill_norm = d.skill_norm and m.status in ('active','in_progress');
