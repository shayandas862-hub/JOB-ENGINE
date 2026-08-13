-- 0027 · Phase 5 Task 4 — the review queue: ambiguities the code couldn't decide.
--
-- Built now, filled mainly by Phase 6 discovery; seeded today from low-confidence
-- skill_synonyms so the review tools (list_review_flags / resolve_review_flag)
-- act on real data. Additive; RLS enabled with no policy, matching the engine's
-- posture (service-role access — real per-owner policies land in Phase 9).
-- Applied via Supabase MCP 2026-07-11.

create table if not exists public.review_items (
  review_id   bigint generated always as identity primary key,
  kind        text not null,                 -- what needs review, e.g. 'skill_synonym'
  ref         text,                          -- pointer to the underlying row (evidence key)
  summary     text not null,                 -- human-readable one-liner
  evidence    jsonb,                         -- structured context for the decision
  status      text not null default 'open'
              check (status in ('open','resolved','dismissed')),
  resolution  jsonb,                         -- the decision recorded on resolve
  created_at  timestamptz not null default now(),
  resolved_at timestamptz
);
comment on table public.review_items is
  'Ambiguities the deterministic engine flagged for a human/Claude to settle. Built Phase 5, filled mainly by Phase 6 discovery; seeded from low-confidence skill_synonyms.';
create index if not exists review_items_status_idx
  on public.review_items (status, created_at);
alter table public.review_items enable row level security;

-- Seed (data, applied separately via execute_sql; idempotent by ref):
--   insert into review_items (kind, ref, summary, evidence)
--   select 'skill_synonym', s.raw_norm,
--          'Low-confidence synonym: "'||s.raw_norm||'" -> "'||s.canonical_label||'"',
--          jsonb_build_object('raw_norm', s.raw_norm, 'canonical_label', s.canonical_label,
--                             'canonical_norm', s.canonical_norm, 'confidence', s.confidence,
--                             'source', s.source)
--   from skill_synonyms s
--   where s.confidence = 'low'
--     and not exists (select 1 from review_items ri
--                     where ri.kind='skill_synonym' and ri.ref = s.raw_norm);
-- 2026-07-11: seeded 740 rows (all confidence='low' synonyms).