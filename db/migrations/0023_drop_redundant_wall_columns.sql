-- 0023 · Phase 2 Task 7 — drop the redundant clears_wall / soc_tier columns.
--
-- Both 0/754 filled (verified before drop). The wall verdict is computed by
-- v_apply_queue (per-SOC since 0022); a stored copy could only ever go stale.
-- Applied via Supabase MCP 2026-07-10.

alter table public.role_listings
  drop column if exists clears_wall,
  drop column if exists soc_tier;
