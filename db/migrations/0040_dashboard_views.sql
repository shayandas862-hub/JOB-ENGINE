-- 0040: the dashboard's three curated views (Phase 7.8 task 8).
-- Complexity-hiding is the contract: the dashboard package reads ONLY these
-- (pinned by test). All bucket/reason logic lives HERE so the page renders
-- decisions instead of making them. security_invoker per house rule (0009).
-- Applied via Supabase MCP as `dashboard_views` on 2026-08-02.

-- One row per queue listing, bucketed ready/needs with the reason and every
-- receipt the page shows. Builds ON v_apply_queue (extend, never rename).
create or replace view public.v_today with (security_invoker = true) as
select q.role_id, q.owner_id, q.company_name, q.role_title, q.location,
       q.salary_text, q.salary_wall, q.wall_basis, q.sponsor_signal,
       q.fit_rank, q.role_url, q.deadline, q.deadline_source, q.age_days,
       r.source, r.read_quality,
       (r.staged_at is not null)          as in_reading_tray,
       (coalesce(r.jd_full, '') <> '')    as has_jd,
       (r.extracted_at is not null)       as has_reading,
       case
         when q.sponsor_signal = 'role-excluded' then 'needs'
         when coalesce(r.jd_full, '') = ''       then 'needs'
         when r.extracted_at is null             then 'needs'
         when q.salary_wall = 'below'            then 'needs'
         else 'ready'
       end as bucket,
       case
         when q.sponsor_signal = 'role-excluded'
           then 'listing says no sponsorship'
         when coalesce(r.jd_full, '') = ''
           then 'no JD yet — arrives when its board is fetched or a reader supplies one'
         when r.extracted_at is null
           then 'waiting for tonight''s read'
         when q.salary_wall = 'below'
           then 'salary below the visa wall (' || q.wall_basis || ')'
         else null
       end as needs_what
  from public.v_apply_queue q
  join public.role_listings r on r.role_id = q.role_id;
comment on view public.v_today is
  'The Today screen: every queue row bucketed ready/needs with its reason and receipts. The dashboard reads this, never the tables behind it.';

-- One row of labelled counts: the honesty panel.
create or replace view public.v_scorecard with (security_invoker = true) as
select
  (select count(*) from public.role_listings where application_status = 'applied')            as applications_total,
  (select count(*) from public.role_listings where applied_date = current_date)               as applications_today,
  (select count(*) from public.v_today)                                                       as queue_rows,
  (select count(*) from public.v_today where bucket = 'ready')                                as ready_rows,
  (select count(*) from public.v_today where bucket = 'needs')                                as needs_rows,
  (select count(*) from public.role_listings where role_status='open' and is_local
                                               and read_quality = 'ai')                       as read_ai,
  (select count(*) from public.role_listings where role_status='open' and is_local
                                               and read_quality = 'keywords')                 as read_keywords,
  (select count(*) from public.role_listings where role_status='open' and is_local
                                               and extracted_at is not null
                                               and read_quality is null)                      as read_unlabelled,
  (select count(*) from public.role_listings where role_status='open' and is_local
                                               and coalesce(jd_full,'') <> ''
                                               and extracted_at is null)                      as unread_with_jd,
  (select count(*) from public.role_listings where staged_at is not null)                     as staged_now,
  (select count(*) from public.role_listings where claimed_at is not null)                    as claimed_now,
  (select count(*) from public.review_items where status = 'open')                            as reviews_open,
  (select count(*) from public.target_companies)                                              as companies_tracked,
  (select count(*) from public.target_companies where ats_token is not null)                  as companies_with_boards,
  (select count(*) from public.aggregator_ads where merge_outcome = 'merged')                 as ads_merged,
  (select count(*) from public.aggregator_ads where matched_org_norm is not null
                                                and merged_at is null)                        as ads_awaiting_merge,
  (select max(finished_at) from public.pipeline_runs)                                         as last_run_at,
  (select status from public.pipeline_runs order by run_id desc limit 1)                      as last_run_status,
  (select count(*) from public.licensed_sponsors)                                             as register_rows,
  (select current_date - max(created_at)::date from public.licensed_sponsors)                 as register_age_days;
comment on view public.v_scorecard is
  'The honesty panel: applications, queue mix, read-quality mix, tray depth, coverage, last run, register age — every number labelled.';

-- One row per tracked company: the company watch (problems sort first in
-- the page). Exposes has_board as a boolean — never the token itself.
create or replace view public.v_health with (security_invoker = true) as
select c.company_id, c.owner_id, c.company_name,
       (c.ats_token is not null) as has_board,
       c.ats_type, c.feed_status, c.last_fetched_at,
       count(r.role_id) filter (where r.role_status = 'open')            as open_roles,
       count(r.role_id) filter (where r.application_status = 'applied')  as applied_roles,
       max(r.updated_at)                                                 as last_listing_change
  from public.target_companies c
  left join public.role_listings r on r.company_id = c.company_id
 group by c.company_id, c.owner_id, c.company_name, c.ats_token, c.ats_type,
          c.feed_status, c.last_fetched_at;
comment on view public.v_health is
  'Company watch: per tracked company — board known, feed state, last fetch, open/applied roles. No token value ever leaves the table.';
