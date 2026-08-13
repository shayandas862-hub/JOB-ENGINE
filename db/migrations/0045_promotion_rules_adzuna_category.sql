-- 0045: promotion_rules gains adzuna_category (Phase 8.5 / U1).
-- The rule row IS the owner's lens: industry codes now drive the Pass-2
-- probe pick AND nightly promotion, and this column drives which Adzuna
-- category the ads sweep walks ('all' = whole-inventory walk; NULL = unset,
-- the sweep falls back to the it-jobs bootstrap). Seed the founder's row to
-- it-jobs so his sweep behaviour is byte-identical before and after U1.
-- Applied via Supabase MCP as `promotion_rules_adzuna_category` on 2026-08-10.
alter table public.promotion_rules add column if not exists adzuna_category text;
comment on column public.promotion_rules.adzuna_category is
  'The Adzuna category slice this owner''s ads sweep walks (e.g. it-jobs, social-work-jobs); ''all'' walks the whole inventory; NULL falls back to the it-jobs bootstrap.';
update public.promotion_rules set adzuna_category = 'it-jobs'
 where adzuna_category is null;
