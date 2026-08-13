-- 0016 · Phase 1 Task 8 — read-once keyed on the listing, not on skill rows.
--
-- The old guard ("role_id not in (select role_id from role_skills)") re-sent
-- any zero-skill role to the paid API on every run, forever. extracted_at
-- stamps a successful read regardless of skill count.
-- Applied via Supabase MCP 2026-07-10. Backfill result: 733/754 rows stamped;
-- 11 open roles with JD text remained genuinely unread (NULL -> read next run).

alter table public.role_listings
  add column if not exists extracted_at timestamptz;

comment on column public.role_listings.extracted_at is
  'When the JD was successfully read (Gemini or keyword). Read-once keys on this — set even for zero-skill readings. NULL = not yet read.';

-- Backfill: mirror the old rule exactly — roles that already have skill rows
-- were "done" under the old guard and must not be re-read (re-billed).
update public.role_listings r
   set extracted_at = coalesce(r.updated_at, now())
 where r.extracted_at is null
   and exists (select 1 from public.role_skills rs where rs.role_id = r.role_id);
