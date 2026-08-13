-- 0011 · GA-012 — clean non-UK residue + add a UK guard to the apply queue.
--
-- Reality check vs the tracker: the audit said "25 non-UK test fixtures". On
-- inspection, 23 of those are LEGITIMATE multi-region postings that include the
-- UK (e.g. "Amsterdam, Netherlands; London, United Kingdom; Paris, France") —
-- real UK-eligible roles the code filter correctly kept. The genuine residue is
-- 2 rows: "Cambridge, MA" (Cambridge, Massachusetts) biotech roles that slip
-- through because is_uk()'s regex matches the word "cambridge". Those are the
-- only rows deleted here. role_skills children cascade (ON DELETE CASCADE).
--
-- NOTE (root cause, not fixed here — code, out of this DB task's scope):
-- src/fetch/feeds.py UK_RE matches bare city names, so "Cambridge, MA" /
-- "Reading, PA" style US locations false-match. Harden is_uk() in a code task.

BEGIN;

-- Delete genuine non-UK residue: a UK city name sitting in a US state, with no
-- explicit UK country token. (Multi-region UK postings always carry
-- "United Kingdom"/"UK"/"GB"/nation name and are preserved.)
DELETE FROM role_listings r
WHERE r.location ~ '\y(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|MA|MD|ME|MI|MN|MO|MS|MT|NC|ND|NE|NH|NJ|NM|NV|NY|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VA|VT|WA|WI|WV|WY)\y'
  AND r.location !~* '\y(united kingdom|u\.?k\.?|gbr?|england|scotland|wales|northern ireland)\y';

-- Recreate the apply queue with a UK-location backstop (mirrors is_uk()'s
-- positive markers). Identical to 0008/0009 otherwise; security_invoker kept.
CREATE OR REPLACE VIEW v_apply_queue
WITH (security_invoker = true) AS
SELECT r.role_id,
    c.company_name,
    c.fit_rank,
    CASE
        WHEN c.sponsor_confidence ~~* '%sponsors%' THEN 'confirmed'
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
    c.lane
FROM role_listings r
JOIN target_companies c ON c.company_id = r.company_id
WHERE r.role_status = 'open'
  AND r.location ~* '\y(united kingdom|u\.?k\.?|gbr?|england|scotland|wales|northern ireland|london|manchester|edinburgh|cambridge|oxford|bristol|leeds|glasgow|birmingham|cardiff|belfast|newcastle|sheffield|nottingham|brighton|reading)\y'
  AND r.role_title ~* '(solutions? (engineer|architect)|forward[- ]deployed|applied ai|ai engineer|machine learning engineer|ml engineer|llm engineer|ai/ml|generative ai|gen ?ai|customer engineer|deployment engineer|developer advocate|sales engineer|technical consultant|ai consultant|implementation engineer|integration engineer|onboarding engineer|ai product|technical product manager)'
ORDER BY
    CASE c.fit_rank WHEN 'High' THEN 1 WHEN 'Med' THEN 2 WHEN 'Low' THEN 3 ELSE 4 END,
    CASE WHEN c.sponsor_confidence ~~* '%sponsors%' THEN 1
         WHEN c.sponsor_confidence ~~* '%register-only%' THEN 2 ELSE 3 END,
    r.created_at DESC;

COMMIT;
