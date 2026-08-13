-- 0033_sic_rls_hardening.sql
-- Clears the two security-advisor ERRORs introduced by 0031/0032:
--  * enable RLS on the sic_codes reference table (matches every sibling table's
--    posture: RLS on, no policy; the engine reaches it via the direct owner
--    connection, which bypasses RLS).
--  * make v_sponsor_industry run with the querying user's rights (security
--    invoker) instead of the creator's, so it can't bypass RLS via PostgREST.
alter table sic_codes enable row level security;
alter view v_sponsor_industry set (security_invoker = true);
