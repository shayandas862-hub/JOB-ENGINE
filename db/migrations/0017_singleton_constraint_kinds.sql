-- 0017 · Phase 1 Task 11 — protect the queue from duplicate threshold rows.
--
-- v_apply_queue (and the skill views above it) read salary thresholds via
-- scalar subqueries on my_constraints.kind. A second row for a threshold kind
-- makes every query on those views fail at runtime ("more than one row
-- returned by a subquery"). Partial index: kill_keyword etc. legitimately
-- have many rows; only the singleton kinds are constrained.
-- Applied via Supabase MCP 2026-07-10.

create unique index if not exists my_constraints_singleton_kinds
  on public.my_constraints (kind)
  where kind in ('salary_threshold_standard', 'salary_threshold_new_entrant', 'salary_floor');
