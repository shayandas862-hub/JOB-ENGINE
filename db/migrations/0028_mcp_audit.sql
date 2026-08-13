-- 0028 · Phase 5 Task 5 — the MCP audit trail: one row per action a tool took.
--
-- Provisional-until-confirmed extends to Claude's actions: every action/review
-- write tool records what it did. Stores an arg summary and a result summary —
-- NEVER a raw secret (the tools pass non-secret args and secret-free results).
-- Additive; RLS enabled with no policy (service-role access; Phase 9 adds real
-- per-owner policies). Applied via Supabase MCP 2026-07-11.

create table if not exists public.mcp_audit (
  audit_id    bigint generated always as identity primary key,
  tool        text not null,          -- the tool name that acted
  args        jsonb,                  -- arg summary (never a secret)
  result      jsonb,                  -- result summary (never a secret)
  occurred_at timestamptz not null default now()
);
comment on table public.mcp_audit is
  'One row per action an MCP tool took on the founder''s behalf (provisional-until-confirmed for Claude). Stores an arg/result summary, never a secret.';
create index if not exists mcp_audit_occurred_idx
  on public.mcp_audit (occurred_at desc);
alter table public.mcp_audit enable row level security;