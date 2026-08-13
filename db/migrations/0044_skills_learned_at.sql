-- 0044: my_skills gains learned_at + a duplicate guard (Phase 8.5 / U2).
-- The skills-entry tool is the FIRST writer of my_skills; the spec pins
-- learned_at + evidence from day one so the future learning-curve model
-- (plan 0010 item 16) has data the day it is built. The unique index makes
-- "one row per owner per normalised skill" a database guarantee, not a
-- writer convention (measured before applying: 22 rows, 0 dupes, 0 null norms).
-- Applied via Supabase MCP as `skills_learned_at` on 2026-08-10.
alter table public.my_skills add column if not exists learned_at date;
comment on column public.my_skills.learned_at is
  'When the owner learned this skill (their own account, date precision). Feeds the learning-curve model; nullable because pre-U2 rows never recorded it.';
create unique index if not exists my_skills_owner_skill_norm_key
  on public.my_skills (owner_id, skill_norm);
