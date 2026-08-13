-- 0005_apply_queue_view.sql
-- Applied via Supabase MCP (apply_migration: v2_apply_queue_view).
-- v1 ranked apply queue: open + title-in-cluster roles, ranked by fit_rank,
-- sponsor confidence, then recency. Gemini skill/salary enrichment and the
-- SOC going-rate salary wall are layered on later.

create or replace view v_apply_queue as
select
  r.role_id,
  c.company_name,
  c.fit_rank,
  case
    when c.sponsor_confidence ilike '%sponsors%' then 'confirmed'
    when c.sponsor_confidence ilike '%register-only%' then 'register-only'
    else 'weak'
  end as sponsor_signal,
  r.role_title,
  r.location,
  r.salary_text,
  r.role_url,
  r.created_at::date as first_seen,
  c.sponsor_confidence,
  c.lane
from role_listings r
join target_companies c on c.company_id = r.company_id
where r.role_status = 'open'
  and r.role_title ~* '(solutions? (engineer|architect)|forward[- ]deployed|applied ai|ai engineer|machine learning engineer|ml engineer|llm engineer|ai/ml|generative ai|gen ?ai|customer engineer|deployment engineer|developer advocate|sales engineer|technical consultant|ai consultant|implementation engineer|integration engineer|onboarding engineer|ai product|technical product manager)'
order by
  case c.fit_rank when 'High' then 1 when 'Med' then 2 when 'Low' then 3 else 4 end,
  case when c.sponsor_confidence ilike '%sponsors%' then 1
       when c.sponsor_confidence ilike '%register-only%' then 2 else 3 end,
  r.created_at desc;

comment on view v_apply_queue is 'Ranked apply queue (v1): open + title-in-cluster roles, ranked by fit_rank, sponsor confidence, recency. Salary-wall + Gemini skill enrichment added later.';
