-- 0059 · Infra sitting 2026-08-11 — mirror the three view bodies 0046 recorded
-- as PROSE, so the log can rebuild what production actually runs (B-GAE-025).
--
-- 0046 said so in its own words: "Full definitions live in the database; this
-- mirror records the CHANGES". It then recorded them as English comments —
-- lines 31-36 for v_apply_queue, 53-58 for v_today, 60-62 for v_scorecard —
-- which psql cannot execute. Found by the new CI database lane: applying
-- ops/ci/01-genesis.sql plus all 58 migrations to a blank Postgres and diffing
-- against live produced three mismatched view bodies and five missing columns,
-- with everything else (67 constraints, 75 indexes, 32 policies, 7 triggers)
-- identical.
--
-- What the log was rebuilding instead:
--   * v_apply_queue with the HARDCODED FOUNDER TITLE REGEX that 8.5 removed
--     ('solutions? (engineer|architect)|forward[- ]deployed|applied ai|...').
--     Live reads target_roles; the log still filtered on one person's job
--     titles. A rebuild would silently reinstate a personal hardcode inside a
--     view, which is exactly where the 0013 audit missed it the first time.
--   * v_today without is_new_today, skill_have, skill_asked.
--   * v_scorecard without new_today, sponsors_total.
--     All five are read by src/dashboard/page.py, so a rebuilt dashboard would
--     have broken on a missing column.
--
-- This migration changes NOTHING on live: the bodies below are live's own
-- pg_get_viewdef output, so applying it is a verified no-op replace. It is the
-- log catching up with the database, not the database changing.
--
-- CREATE OR REPLACE VIEW is safe here (all three keep their existing columns in
-- order and only v_today/v_scorecard append), but it DROPS reloptions — the
-- 0046/0047 lesson and B-GAE-006 — so security_invoker is re-asserted at the
-- bottom. Measured before writing: all three carry security_invoker=true today.
BEGIN;

CREATE OR REPLACE VIEW public.v_apply_queue AS
 SELECT r.role_id,
    c.company_name,
    c.fit_rank,
        CASE
            WHEN r.sponsors_this_role = 'no_sponsor'::text THEN 'role-excluded'::text
            WHEN r.sponsors_this_role = 'sponsors'::text THEN 'role-confirmed'::text
            WHEN c.sponsor_confidence ~~* '%sponsors%'::text THEN 'company-confirmed'::text
            WHEN c.sponsor_confidence ~~* '%register-only%'::text THEN 'register-only'::text
            ELSE 'weak'::text
        END AS sponsor_signal,
    r.role_title,
    r.location,
    r.salary_text,
    r.salary_min,
    r.salary_max,
        CASE
            WHEN r.salary_max IS NULL THEN 'unknown'::text
            WHEN g.going_rate_annual IS NOT NULL THEN
            CASE
                WHEN r.salary_max >= GREATEST(g.going_rate_annual, COALESCE(( SELECT mc.numeric_value
                   FROM my_constraints mc
                  WHERE mc.kind = 'salary_threshold_standard'::text AND mc.owner_id = c.owner_id), 0::numeric)) THEN 'clears'::text
                WHEN r.salary_max >= GREATEST(0.7 * g.going_rate_annual, COALESCE(( SELECT mc.numeric_value
                   FROM my_constraints mc
                  WHERE mc.kind = 'salary_threshold_new_entrant'::text AND mc.owner_id = c.owner_id), 0::numeric)) THEN 'clears_new_entrant'::text
                ELSE 'below'::text
            END
            WHEN r.salary_max >= (( SELECT mc.numeric_value
               FROM my_constraints mc
              WHERE mc.kind = 'salary_threshold_standard'::text AND mc.owner_id = c.owner_id)) THEN 'clears'::text
            WHEN r.salary_max >= (( SELECT mc.numeric_value
               FROM my_constraints mc
              WHERE mc.kind = 'salary_threshold_new_entrant'::text AND mc.owner_id = c.owner_id)) THEN 'clears_new_entrant'::text
            ELSE 'below'::text
        END AS salary_wall,
    r.role_url,
    r.created_at::date AS first_seen,
    c.sponsor_confidence,
    c.lane,
    r.sponsors_this_role,
    r.soc_code,
        CASE
            WHEN r.salary_max IS NULL THEN 'no_salary'::text
            WHEN g.going_rate_annual IS NOT NULL THEN 'going_rate:'::text || r.soc_code
            ELSE 'flat_fallback'::text
        END AS wall_basis,
    c.owner_id,
    r.deadline,
    r.deadline_source,
    CURRENT_DATE - r.created_at::date AS age_days,
    ev.last_changed_at
   FROM role_listings r
     JOIN target_companies c ON c.company_id = r.company_id
     LEFT JOIN soc_going_rates g ON g.occupation_code = r.soc_code
     LEFT JOIN LATERAL ( SELECT max(e.occurred_at) AS last_changed_at
           FROM listing_events e
          WHERE e.role_id = r.role_id AND (e.event_type = ANY (ARRAY['changed'::text, 'reopened'::text]))) ev ON true
  WHERE r.role_status = 'open'::text AND (r.location ~* '\y(united kingdom|u\.?k\.?|gbr?|england|scotland|wales|northern ireland)\y'::text OR r.location ~* '\y(london|manchester|edinburgh|cambridge|oxford|bristol|leeds|glasgow|birmingham|cardiff|belfast|newcastle|sheffield|nottingham|brighton|reading)\y'::text AND r.location !~* '\y(united states|u\.?s\.?a\.?|america|canada|ontario|australia|new zealand|south africa)\y'::text AND r.location !~ ',\s*(AL|AK|AZ|AR|AB|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|MB|NE|NV|NH|NJ|NM|NY|NC|ND|NB|NL|NT|NS|NU|OH|OK|OR|ON|PA|PE|QC|RI|SC|SD|SK|TN|TX|UT|VT|VA|VI|VIC|WA|WV|WI|WY|YT|NSW|QLD|TAS|ACT)\y'::text) AND (EXISTS ( SELECT 1
           FROM target_roles t
          WHERE t.owner_id = c.owner_id AND regexp_replace(lower(r.role_title), '[-\s]+'::text, ' '::text, 'g'::text) ~~ (('%'::text || regexp_replace(lower(t.search_title), '[-\s]+'::text, ' '::text, 'g'::text)) || '%'::text)))
  ORDER BY (
        CASE c.fit_rank
            WHEN 'High'::text THEN 1
            WHEN 'Med'::text THEN 2
            WHEN 'Low'::text THEN 3
            ELSE 4
        END), (
        CASE
            WHEN r.sponsors_this_role = 'sponsors'::text THEN 1
            WHEN c.sponsor_confidence ~~* '%sponsors%'::text THEN 2
            WHEN c.sponsor_confidence ~~* '%register-only%'::text THEN 3
            WHEN r.sponsors_this_role = 'no_sponsor'::text THEN 5
            ELSE 4
        END), r.created_at DESC;

CREATE OR REPLACE VIEW public.v_today AS
 SELECT q.role_id,
    q.owner_id,
    q.company_name,
    q.role_title,
    q.location,
    q.salary_text,
    q.salary_wall,
    q.wall_basis,
    q.sponsor_signal,
    q.fit_rank,
    q.role_url,
    q.deadline,
    q.deadline_source,
    q.age_days,
    r.source,
    r.read_quality,
    r.staged_at IS NOT NULL AS in_reading_tray,
    COALESCE(r.jd_full, ''::text) <> ''::text AS has_jd,
    r.extracted_at IS NOT NULL AS has_reading,
        CASE
            WHEN q.sponsor_signal = 'role-excluded'::text THEN 'needs'::text
            WHEN COALESCE(r.jd_full, ''::text) = ''::text THEN 'needs'::text
            WHEN r.extracted_at IS NULL THEN 'needs'::text
            WHEN q.salary_wall = 'below'::text THEN 'needs'::text
            ELSE 'ready'::text
        END AS bucket,
        CASE
            WHEN q.sponsor_signal = 'role-excluded'::text THEN 'listing says no sponsorship'::text
            WHEN COALESCE(r.jd_full, ''::text) = ''::text THEN 'no JD yet — arrives when its board is fetched or a reader supplies one'::text
            WHEN r.extracted_at IS NULL THEN 'waiting for tonight''s read'::text
            WHEN q.salary_wall = 'below'::text THEN ('salary below the visa wall ('::text || q.wall_basis) || ')'::text
            ELSE NULL::text
        END AS needs_what,
    q.first_seen = CURRENT_DATE AS is_new_today,
    COALESCE(sk.have, 0::bigint)::integer AS skill_have,
    COALESCE(sk.asked, 0::bigint)::integer AS skill_asked
   FROM v_apply_queue q
     JOIN role_listings r ON r.role_id = q.role_id
     LEFT JOIN LATERAL ( SELECT count(*) FILTER (WHERE ms.skill_norm IS NOT NULL) AS have,
            count(*) AS asked
           FROM role_skills rs
             LEFT JOIN skill_synonyms ss ON ss.raw_norm = rs.skill_norm
             LEFT JOIN my_skills ms ON ms.skill_norm = COALESCE(ss.canonical_norm, rs.skill_norm) AND ms.owner_id = q.owner_id AND (ms.status = ANY (ARRAY['active'::text, 'in_progress'::text]))
          WHERE rs.role_id = q.role_id) sk ON true;

CREATE OR REPLACE VIEW public.v_scorecard AS
 SELECT ( SELECT count(*) AS count
           FROM role_listings
          WHERE role_listings.application_status = 'applied'::text) AS applications_total,
    ( SELECT count(*) AS count
           FROM role_listings
          WHERE role_listings.applied_date = CURRENT_DATE) AS applications_today,
    ( SELECT count(*) AS count
           FROM v_today) AS queue_rows,
    ( SELECT count(*) AS count
           FROM v_today
          WHERE v_today.bucket = 'ready'::text) AS ready_rows,
    ( SELECT count(*) AS count
           FROM v_today
          WHERE v_today.bucket = 'needs'::text) AS needs_rows,
    ( SELECT count(*) AS count
           FROM role_listings
          WHERE role_listings.role_status = 'open'::text AND role_listings.is_local AND role_listings.read_quality = 'ai'::text) AS read_ai,
    ( SELECT count(*) AS count
           FROM role_listings
          WHERE role_listings.role_status = 'open'::text AND role_listings.is_local AND role_listings.read_quality = 'keywords'::text) AS read_keywords,
    ( SELECT count(*) AS count
           FROM role_listings
          WHERE role_listings.role_status = 'open'::text AND role_listings.is_local AND role_listings.extracted_at IS NOT NULL AND role_listings.read_quality IS NULL) AS read_unlabelled,
    ( SELECT count(*) AS count
           FROM role_listings
          WHERE role_listings.role_status = 'open'::text AND role_listings.is_local AND COALESCE(role_listings.jd_full, ''::text) <> ''::text AND role_listings.extracted_at IS NULL) AS unread_with_jd,
    ( SELECT count(*) AS count
           FROM role_listings
          WHERE role_listings.staged_at IS NOT NULL) AS staged_now,
    ( SELECT count(*) AS count
           FROM role_listings
          WHERE role_listings.claimed_at IS NOT NULL) AS claimed_now,
    ( SELECT count(*) AS count
           FROM review_items
          WHERE review_items.status = 'open'::text) AS reviews_open,
    ( SELECT count(*) AS count
           FROM target_companies) AS companies_tracked,
    ( SELECT count(*) AS count
           FROM target_companies
          WHERE target_companies.ats_token IS NOT NULL) AS companies_with_boards,
    ( SELECT count(*) AS count
           FROM aggregator_ads
          WHERE aggregator_ads.merge_outcome = 'merged'::text) AS ads_merged,
    ( SELECT count(*) AS count
           FROM aggregator_ads
          WHERE aggregator_ads.matched_org_norm IS NOT NULL AND aggregator_ads.merged_at IS NULL) AS ads_awaiting_merge,
    ( SELECT max(pipeline_runs.finished_at) AS max
           FROM pipeline_runs) AS last_run_at,
    ( SELECT pipeline_runs.status
           FROM pipeline_runs
          ORDER BY pipeline_runs.run_id DESC
         LIMIT 1) AS last_run_status,
    ( SELECT count(*) AS count
           FROM licensed_sponsors) AS register_rows,
    ( SELECT CURRENT_DATE - max(licensed_sponsors.created_at)::date
           FROM licensed_sponsors) AS register_age_days,
    ( SELECT count(*) AS count
           FROM v_today
          WHERE v_today.is_new_today) AS new_today,
    ( SELECT count(*) AS count
           FROM v_sponsor_browse) AS sponsors_total;


-- CREATE OR REPLACE VIEW does not preserve reloptions (B-GAE-006). Without
-- these three lines this migration would silently convert all three views to
-- definer semantics and undo 0047.
ALTER VIEW public.v_apply_queue SET (security_invoker = true);
ALTER VIEW public.v_today SET (security_invoker = true);
ALTER VIEW public.v_scorecard SET (security_invoker = true);

COMMIT;
