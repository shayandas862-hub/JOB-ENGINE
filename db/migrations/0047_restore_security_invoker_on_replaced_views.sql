-- 0047: restore security_invoker on the four views 0046 replaced.
-- CREATE OR REPLACE VIEW does not preserve reloptions; the house rule is
-- security_invoker=true on every view (caught by get_advisors immediately
-- after 0046 — ERROR level, fixed in the same session).
-- Applied via Supabase MCP as `restore_security_invoker_on_replaced_views`
-- on 2026-08-10.
alter view public.v_apply_queue set (security_invoker = true);
alter view public.v_today set (security_invoker = true);
alter view public.v_scorecard set (security_invoker = true);
alter view public.v_sponsor_browse set (security_invoker = true);
