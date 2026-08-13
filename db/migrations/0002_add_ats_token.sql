-- 0002_add_ats_token.sql
-- Applied via Supabase MCP (apply_migration: v2_add_ats_token).
-- Stores the ATS board slug so fetchers can build feed URLs without parsing careers_url.

alter table public.target_companies add column if not exists ats_token text;
comment on column public.target_companies.ats_token is 'ATS board slug used to build feed URLs (set by the classifier).';
