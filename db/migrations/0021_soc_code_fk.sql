-- 0021 · Phase 2 Task 4 (link) — soc_code is now a real foreign key.
--
-- After 0020's hygiene + the resolver backfill, every non-null soc_code is an
-- official code, so the FK to the occupation reference table validates.
-- Applied via Supabase MCP 2026-07-10.

alter table public.role_listings
  add constraint role_listings_soc_code_fkey
  foreign key (soc_code) references public.skilled_worker_occupations (occupation_code);
