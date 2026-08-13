-- 0007_constraints_and_salary.sql
-- Applied via Supabase MCP (apply_migration: v2_constraints_and_salary).
-- Hard filters/preferences table + parsed salary range on listings.

create table if not exists public.my_constraints (
  id bigint generated always as identity primary key,
  kind text not null,            -- salary_floor | salary_threshold_standard | salary_threshold_new_entrant | visa | geo | kill_keyword | target_role | note
  value text,
  numeric_value numeric,
  hard boolean not null default true,
  source text,
  created_at timestamptz not null default now()
);
comment on table public.my_constraints is 'Hard filters & preferences for the search (salary, visa, geo, kill-list). Connectable to the queue.';
alter table public.my_constraints enable row level security;

alter table public.role_listings
  add column if not exists salary_min numeric,
  add column if not exists salary_max numeric;
