-- 0049: cv_blocks gains the retire stamp + write provenance (U8b, the
-- founder's 2026-08-10 amendment: writer tools ship WITH task 0). Retire is
-- a STAMP, never a delete (keep-all); source records who wrote the draft
-- (the owner's own conversation vs a client AI's proposal), the
-- learned_at-style provenance add_skill already carries.
-- Applied via Supabase MCP as `cv_blocks_retire_stamp_and_source` on 2026-08-10.
alter table public.cv_blocks add column if not exists retired_at timestamptz;
comment on column public.cv_blocks.retired_at is
  'The owner retired this fact (U8b). A stamped block never serves again (load_cv_blocks excludes it); the row itself is kept, as everything is.';
alter table public.cv_blocks add column if not exists source text;
comment on column public.cv_blocks.source is
  'Who wrote this block: mcp (a client AI drafting via add_cv_block) or operator seeding. Confirmation is always the owner''s, whatever the source.';
