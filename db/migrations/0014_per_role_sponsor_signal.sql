-- 0014 · GA-008 — per-role sponsor signal (JD hint outranks company register).
-- Rule: being on the sponsor register != will sponsor THIS role. The JD's own
-- hint (sponsors_this_role, from Gemini) is the stronger, role-specific signal:
--   - 'sponsors'   -> role-confirmed   (strongest positive)
--   - 'no_sponsor' -> role-excluded    (JD says you must already have the right
--                                        to work; hard negative, ranked last)
--   - else fall back to the weaker company-level register signal.
-- The raw hint is also surfaced as a column. UK guard (0011) preserved.

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
        WHEN r.salary_max >= (SELECT my_constraints.numeric_value FROM my_constraints
                              WHERE my_constraints.kind = 'salary_threshold_standard') THEN 'clears'
        WHEN r.salary_max >= (SELECT my_constraints.numeric_value FROM my_constraints
                              WHERE my_constraints.kind = 'salary_threshold_new_entrant') THEN 'clears_new_entrant'
        ELSE 'below'
    END AS salary_wall,
    r.role_url,
    r.created_at::date AS first_seen,
    c.sponsor_confidence,
    c.lane,
    r.sponsors_this_role   -- appended last (CREATE OR REPLACE can't reorder columns)
FROM role_listings r
JOIN target_companies c ON c.company_id = r.company_id
WHERE r.role_status = 'open'
  AND r.location ~* '\y(united kingdom|u\.?k\.?|gbr?|england|scotland|wales|northern ireland|london|manchester|edinburgh|cambridge|oxford|bristol|leeds|glasgow|birmingham|cardiff|belfast|newcastle|sheffield|nottingham|brighton|reading)\y'
  AND r.role_title ~* '(solutions? (engineer|architect)|forward[- ]deployed|applied ai|ai engineer|machine learning engineer|ml engineer|llm engineer|ai/ml|generative ai|gen ?ai|customer engineer|deployment engineer|developer advocate|sales engineer|technical consultant|ai consultant|implementation engineer|integration engineer|onboarding engineer|ai product|technical product manager)'
ORDER BY
    CASE c.fit_rank WHEN 'High' THEN 1 WHEN 'Med' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END,
    -- per-role sponsor hint dominates the ranking, then company register
    CASE
        WHEN r.sponsors_this_role = 'sponsors'          THEN 1
        WHEN c.sponsor_confidence ~~* '%sponsors%'      THEN 2
        WHEN c.sponsor_confidence ~~* '%register-only%' THEN 3
        WHEN r.sponsors_this_role = 'no_sponsor'        THEN 5
        ELSE 4
    END,
    r.created_at DESC;

COMMIT;
