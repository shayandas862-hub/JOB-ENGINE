-- 0025 · Phase 3 Task 6 — the queue tells each listing's story.
--
-- Appends (CREATE OR REPLACE can only append): apply-by deadline + its source
-- (stated vs estimated — always advisory), listing age in days, and when the
-- listing last changed/reopened (from listing_events). Identical to 0022
-- otherwise. Applied via Supabase MCP 2026-07-10.

BEGIN;

CREATE OR REPLACE VIEW v_apply_queue
WITH (security_invoker = true) AS
SELECT r.role_id,
    c.company_name,
    c.fit_rank,
    CASE
        WHEN r.sponsors_this_role = 'no_sponsor'        THEN 'role-excluded'
        WHEN r.sponsors_this_role = 'sponsors'          THEN 'role-confirmed'
        WHEN c.sponsor_confidence ~~* '%sponsors%'      THEN 'company-confirmed'
        WHEN c.sponsor_confidence ~~* '%register-only%' THEN 'register-only'
        ELSE 'weak'
    END AS sponsor_signal,
    r.role_title,
    r.location,
    r.salary_text,
    r.salary_min,
    r.salary_max,
    CASE
        WHEN r.salary_max IS NULL THEN 'unknown'
        WHEN g.going_rate_annual IS NOT NULL THEN
            CASE
                WHEN r.salary_max >= greatest(g.going_rate_annual,
                        coalesce((SELECT mc.numeric_value FROM my_constraints mc
                                  WHERE mc.kind = 'salary_threshold_standard'
                                    AND mc.owner_id = c.owner_id), 0))
                    THEN 'clears'
                WHEN r.salary_max >= greatest(0.7 * g.going_rate_annual,
                        coalesce((SELECT mc.numeric_value FROM my_constraints mc
                                  WHERE mc.kind = 'salary_threshold_new_entrant'
                                    AND mc.owner_id = c.owner_id), 0))
                    THEN 'clears_new_entrant'
                ELSE 'below'
            END
        WHEN r.salary_max >= (SELECT mc.numeric_value FROM my_constraints mc
                              WHERE mc.kind = 'salary_threshold_standard'
                                AND mc.owner_id = c.owner_id) THEN 'clears'
        WHEN r.salary_max >= (SELECT mc.numeric_value FROM my_constraints mc
                              WHERE mc.kind = 'salary_threshold_new_entrant'
                                AND mc.owner_id = c.owner_id) THEN 'clears_new_entrant'
        ELSE 'below'
    END AS salary_wall,
    r.role_url,
    r.created_at::date AS first_seen,
    c.sponsor_confidence,
    c.lane,
    r.sponsors_this_role,
    r.soc_code,
    CASE
        WHEN r.salary_max IS NULL THEN 'no_salary'
        WHEN g.going_rate_annual IS NOT NULL THEN 'going_rate:' || r.soc_code
        ELSE 'flat_fallback'
    END AS wall_basis,
    c.owner_id,
    r.deadline,
    r.deadline_source,
    (current_date - r.created_at::date) AS age_days,
    ev.last_changed_at
FROM role_listings r
JOIN target_companies c ON c.company_id = r.company_id
LEFT JOIN soc_going_rates g ON g.occupation_code = r.soc_code
LEFT JOIN LATERAL (
    SELECT max(e.occurred_at) AS last_changed_at
    FROM listing_events e
    WHERE e.role_id = r.role_id AND e.event_type IN ('changed', 'reopened')
) ev ON true
WHERE r.role_status = 'open'
  AND (
    r.location ~* '\y(united kingdom|u\.?k\.?|gbr?|england|scotland|wales|northern ireland)\y'
    OR (
      r.location ~* '\y(london|manchester|edinburgh|cambridge|oxford|bristol|leeds|glasgow|birmingham|cardiff|belfast|newcastle|sheffield|nottingham|brighton|reading)\y'
      AND r.location !~* '\y(united states|u\.?s\.?a\.?|america|canada|ontario|australia|new zealand|south africa)\y'
      AND r.location !~ ',\s*(AL|AK|AZ|AR|AB|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|MB|NE|NV|NH|NJ|NM|NY|NC|ND|NB|NL|NT|NS|NU|OH|OK|OR|ON|PA|PE|QC|RI|SC|SD|SK|TN|TX|UT|VT|VA|VI|VIC|WA|WV|WI|WY|YT|NSW|QLD|TAS|ACT)\y'
    )
  )
  AND r.role_title ~* '(solutions? (engineer|architect)|forward[- ]deployed|applied ai|ai engineer|machine learning engineer|ml engineer|llm engineer|ai/ml|generative ai|gen ?ai|customer engineer|deployment engineer|developer advocate|sales engineer|technical consultant|ai consultant|implementation engineer|integration engineer|onboarding engineer|ai product|technical product manager)'
ORDER BY
    CASE c.fit_rank WHEN 'High' THEN 1 WHEN 'Med' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END,
    CASE
        WHEN r.sponsors_this_role = 'sponsors'          THEN 1
        WHEN c.sponsor_confidence ~~* '%sponsors%'      THEN 2
        WHEN c.sponsor_confidence ~~* '%register-only%' THEN 3
        WHEN r.sponsors_this_role = 'no_sponsor'        THEN 5
        ELSE 4
    END,
    r.created_at DESC;

COMMIT;
