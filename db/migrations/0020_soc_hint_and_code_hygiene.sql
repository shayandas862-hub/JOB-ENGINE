-- 0020 · Phase 2 Task 4 (schema) — soc_hint evidence column; soc_code becomes codes-only.
--
-- Audit found role_listings.soc_code holding free-text names ("Software
-- Engineer") from earlier reads — names are evidence, not codes. soc_hint
-- keeps the raw reader hint; soc_code holds ONLY official SOC 2020 codes
-- (resolved deterministically by src/analysis/occupations.py; never guessed).
-- Applied via Supabase MCP 2026-07-10. Backfill (via the tested resolver):
-- 580 legacy hints examined, 34 resolved to official codes, 546 left NULL.

begin;

alter table public.role_listings
  add column if not exists soc_hint text;
comment on column public.role_listings.soc_hint is
  'Raw occupation-name hint from the JD reader. Evidence only — resolution to soc_code is deterministic and never guesses.';
comment on column public.role_listings.soc_code is
  'Official SOC 2020 occupation code, resolver-confirmed. NULL = unresolved (wall falls back to flat threshold).';

create unique index if not exists skilled_worker_occupations_code_unique
  on public.skilled_worker_occupations (occupation_code);

update public.role_listings
   set soc_hint = coalesce(soc_hint, soc_code),
       soc_code = null
 where soc_code is not null;

commit;
