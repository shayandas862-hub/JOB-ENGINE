-- 0046: the view layer goes universal (Phase 8.5 / U6 + the E2E blocker).
-- (a) v_apply_queue's hardcoded founder title regex — a personal hardcode
--     the 0013 audit missed because it lives in a VIEW, not code — becomes
--     a data-driven gate over the owner's target_roles (normalised
--     substring match, hyphen/space-insensitive like build_role_matcher).
--     10 patterns seeded into the founder's target_roles first so his
--     queue keeps every row the regex admitted (verified: 272 -> 272,
--     0 lost, after applying).
-- (b) v_today gains is_new_today + skill_have/skill_asked (the fit
--     column's receipts, role_skills x my_skills via synonyms).
-- (c) v_scorecard gains new_today + sponsors_total.
-- (d) v_sponsor_browse: the Sponsors tab's curated view (plain-English
--     industries; never ats_token).
-- Applied via Supabase MCP as `universal_queue_and_sponsor_browse` on
-- 2026-08-10. Full definitions live in the database; this mirror records
-- the CHANGES (the unchanged clauses of the replaced views are verbatim
-- copies of their 0040/0043-era definitions).

insert into public.target_roles (search_title, canonical_role, notes, owner_id)
select v.title, v.title,
       'Seeded by 0046: preserves the pre-U6 queue regex coverage',
       (select profile_id from public.profiles order by created_at limit 1)
from (values ('ML Engineer'), ('AI/ML'), ('Applied AI'), ('Generative AI'),
             ('GenAI'), ('Gen AI'), ('AI Product'), ('Forward Deployed'),
             ('Solution Engineer'), ('Solution Architect')) as v(title)
where not exists (
  select 1 from public.target_roles t
  where regexp_replace(lower(t.search_title), '[-\s]+', ' ', 'g')
      = regexp_replace(lower(v.title), '[-\s]+', ' ', 'g'));

-- v_apply_queue: WHERE title gate replaced by
--   EXISTS (select 1 from target_roles t
--           where t.owner_id = c.owner_id
--             and regexp_replace(lower(r.role_title), '[-\s]+', ' ', 'g')
--                 like '%' || regexp_replace(lower(t.search_title), '[-\s]+', ' ', 'g') || '%')
-- (location gates, columns, ordering unchanged).

create view public.v_sponsor_browse as
 SELECT v.org_name_norm,
    v.organisation_name,
    v.town_city,
    v.registry_status,
    v.industry_descriptions,
    sc.probe_outcome,
    sc.careers_url,
    sc.local_jobs_seen,
    sc.total_jobs_seen
   FROM v_sponsor_industry v
     JOIN sponsor_census sc USING (org_name_norm);
comment on view public.v_sponsor_browse is
  'The dashboard Sponsors tab''s entire read surface (U6): registry-matched sponsors with plain-English industry descriptions + board facts. Never carries ats_token.';

-- v_today: appended columns
--   q.first_seen = CURRENT_DATE AS is_new_today,
--   COALESCE(sk.have, 0)::int AS skill_have,
--   COALESCE(sk.asked, 0)::int AS skill_asked
-- via LEFT JOIN LATERAL over role_skills / skill_synonyms / my_skills
-- (owner-scoped, status active|in_progress).

-- v_scorecard: appended counts
--   (select count(*) from v_today where is_new_today) AS new_today,
--   (select count(*) from v_sponsor_browse)           AS sponsors_total
