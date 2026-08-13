-- 0015 · GA-010 — make feed coverage visible.
-- Distinguish "no feed" (can't see this company at all) from "feed works but no
-- UK roles right now" — previously both looked like silence. feed_status states:
--   no_feed  : ats_type unknown / no token — no usable feed (needs Workday/custom)
--   ok       : feed fetched and has >=1 open UK role
--   empty    : feed fetched fine but 0 open UK roles right now
--   error    : last fetch errored (set live; not inferable here)
--   not_checked (null) : never attempted
-- Backfills from current data (no re-fetch) + a coverage view.

BEGIN;

-- No usable feed.
UPDATE target_companies
   SET feed_status = 'no_feed'
 WHERE ats_type IS NULL OR ats_type = 'unknown' OR ats_token IS NULL;

-- Has a feed: ok if it currently shows open roles, else empty.
UPDATE target_companies c
   SET feed_status = CASE
       WHEN EXISTS (SELECT 1 FROM role_listings r
                     WHERE r.company_id = c.company_id AND r.role_status = 'open')
       THEN 'ok' ELSE 'empty' END
 WHERE ats_type IS NOT NULL AND ats_type <> 'unknown' AND ats_token IS NOT NULL;

CREATE OR REPLACE VIEW v_feed_coverage
WITH (security_invoker = true) AS
SELECT
    c.company_id,
    c.company_name,
    c.ats_type,
    c.feed_status,
    c.last_fetched_at,
    count(r.role_id) FILTER (WHERE r.role_status = 'open') AS open_roles
FROM target_companies c
LEFT JOIN role_listings r ON r.company_id = c.company_id
GROUP BY c.company_id, c.company_name, c.ats_type, c.feed_status, c.last_fetched_at
ORDER BY c.feed_status, open_roles DESC;

COMMIT;
