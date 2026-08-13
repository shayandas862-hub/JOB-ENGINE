-- 0003_extend_my_skills.sql
-- Applied via Supabase MCP (apply_migration: v2_extend_my_skills).
-- Makes my_skills categorisable, status-aware, and provenance-tracked, and indexes
-- skill_norm so it joins cleanly to role_skills.skill_norm for future gap analysis.

alter table public.my_skills
  add column if not exists category text,
  add column if not exists status text not null default 'active',
  add column if not exists source text;

comment on column public.my_skills.category is 'technical | cognitive | domain | tool — lets gap analysis target JD-matchable (technical/tool) skills vs narrative ones.';
comment on column public.my_skills.status is 'active | dormant | in_progress — filter for what counts in job matching.';
comment on column public.my_skills.source is 'Provenance of the skill record, e.g. spec_sheet_v1.';

create index if not exists my_skills_norm_idx on public.my_skills (skill_norm);
