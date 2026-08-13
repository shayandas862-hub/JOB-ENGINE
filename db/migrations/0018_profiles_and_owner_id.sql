-- 0018 · Phase 2 Task 1 — profiles + owner_id: all personal data belongs to a profile.
--
-- Person-agnostic provision: the engine reads WHO from the database, never from
-- code. Single-user convenience: owner_id gets a DEFAULT of the founder's
-- profile so existing insert paths keep working — the DEFAULT is removed in
-- Phase 9 (multi-tenant). Tokens/secrets are NEVER stored here: notion_token_ref
-- names an environment variable, nothing more.
-- Applied via Supabase MCP 2026-07-10. Backfill verified: 1 profile;
-- my_skills 22/22, my_constraints 14/14, target_roles 39/39,
-- target_companies 79/79 rows owned. Views become owner-aware in the Task 5
-- view rebuild (one recreate instead of two).

begin;

create table if not exists public.profiles (
  profile_id           uuid primary key default gen_random_uuid(),
  name                 text not null,
  contact_email        text,
  notification_channel text,   -- e.g. 'ntfy:<topic>' (used from Phase 4)
  notion_token_ref     text,   -- env-var NAME holding the Notion token (Phase 7); never the token itself
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);
comment on table public.profiles is
  'One row per person the engine runs for. Personal tables hang off owner_id. Secrets are never stored here — *_ref columns name environment variables.';
alter table public.profiles enable row level security;

-- The founder's profile (fixed UUID so the single-user DEFAULT is stable and
-- the Phase 9 migration can find it deterministically).
insert into public.profiles (profile_id, name, contact_email)
-- Public mirror note: the seed row below carries placeholders; the live DB
-- holds the real owner profile (personal data never ships in the repo).
values ('00000000-0000-4000-a000-000000000001', 'Owner Name', 'owner@example.com')
on conflict (profile_id) do nothing;

-- owner_id on every personal table: FK + backfill + NOT NULL + single-user DEFAULT.
alter table public.my_skills
  add column if not exists owner_id uuid references public.profiles(profile_id);
update public.my_skills set owner_id = '00000000-0000-4000-a000-000000000001' where owner_id is null;
alter table public.my_skills
  alter column owner_id set not null,
  alter column owner_id set default '00000000-0000-4000-a000-000000000001';

alter table public.my_constraints
  add column if not exists owner_id uuid references public.profiles(profile_id);
update public.my_constraints set owner_id = '00000000-0000-4000-a000-000000000001' where owner_id is null;
alter table public.my_constraints
  alter column owner_id set not null,
  alter column owner_id set default '00000000-0000-4000-a000-000000000001';

alter table public.target_roles
  add column if not exists owner_id uuid references public.profiles(profile_id);
update public.target_roles set owner_id = '00000000-0000-4000-a000-000000000001' where owner_id is null;
alter table public.target_roles
  alter column owner_id set not null,
  alter column owner_id set default '00000000-0000-4000-a000-000000000001';

alter table public.target_companies
  add column if not exists owner_id uuid references public.profiles(profile_id);
update public.target_companies set owner_id = '00000000-0000-4000-a000-000000000001' where owner_id is null;
alter table public.target_companies
  alter column owner_id set not null,
  alter column owner_id set default '00000000-0000-4000-a000-000000000001';

-- The singleton-threshold protection (0017) must now be per-owner.
drop index if exists public.my_constraints_singleton_kinds;
create unique index if not exists my_constraints_singleton_kinds
  on public.my_constraints (owner_id, kind)
  where kind in ('salary_threshold_standard', 'salary_threshold_new_entrant', 'salary_floor');

commit;
