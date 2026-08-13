-- 0029 · Phase 7 Task 1 — cv_blocks: verified career facts as structured blocks.
--
-- The truthful source for tailored CVs. Each block is one confirmed fact; the CV
-- maker selects/orders blocks by skill evidence (assemble.py), rephrases only the
-- fact_text (Gemini, caged), and a truth gate rejects any output line that can't
-- trace back here. skill_norms use the shared norm() so they match role_skills.
-- Owner-scoped with the single-user DEFAULT (removed Phase 9); RLS enabled with
-- no policy (service-role access, matching the engine's posture). Additive.
-- Applied via Supabase MCP 2026-07-11; get_advisors after: only the expected
-- INFO rls_enabled_no_policy on cv_blocks (same as every engine table).

create table if not exists public.cv_blocks (
  block_id     bigint generated always as identity primary key,
  owner_id     uuid not null default '00000000-0000-4000-a000-000000000001'
               references public.profiles(profile_id),
  kind         text not null
               check (kind in ('role','achievement','skill_evidence','education')),
  title        text,                          -- short label (role title / degree)
  organisation text,                          -- employer / institution
  date_range   text,                          -- e.g. '2021-2023' (CVs render prose)
  fact_text    text not null,                 -- the verified, human-confirmed statement (grounding source)
  skill_norms  text[] not null default '{}',  -- normalised skills this block evidences (matches role_skills.skill_norm)
  sort_hint    int not null default 0,        -- stable base ordering / priority tiebreak
  confirmed    boolean not null default false,-- only human-confirmed facts feed a CV
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
comment on table public.cv_blocks is
  'Verified career facts (roles/achievements/skill evidence/education) for the CV maker. Every CV line must trace to a confirmed fact_text here; skill_norms match role_skills via the shared norm(). Owner-scoped; RLS with no policy (Phase 9 adds per-owner policies).';
create index if not exists cv_blocks_owner_confirmed_idx
  on public.cv_blocks (owner_id, confirmed);
alter table public.cv_blocks enable row level security;
