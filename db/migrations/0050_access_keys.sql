-- 0050 · Phase 9 task 1 — friend-tier access keys: a key knows its owner.
--
-- Until now the hosted door held ONE static bearer token and stamped every
-- request client_id="founder". That is the single-user assumption living in
-- the transport layer, and it has to go before a second person can hold a
-- key. This table is the whole replacement: a key resolves to the owner it
-- was minted for, and to nobody else.
--
-- Three decisions worth reading:
--   * The key itself is never stored. Only its SHA-256 is, and the check
--     constraint makes storing anything else impossible — so a leaked dump
--     is a set of digests, not a set of working keys. A random 256-bit key
--     needs no KDF; it is not a password and cannot be guessed.
--   * Revocation is a STAMP (revoked_at), never a delete — keep-all, so who
--     held a key and when it was pulled survives the revocation.
--   * NO owner_id DEFAULT. The single-user DEFAULTs from 0018 are exactly
--     the debt Phase 9 task 2 clears; this table starts without one, so an
--     unstamped key fails loudly instead of quietly becoming the founder's.
--
-- RLS is enabled with no policies, like every other table: the engine role
-- bypasses it, and anon/authenticated see nothing at all. Task 2 replaces
-- that blanket denial with policies proven by a REFUSED cross-user read.
--
-- Applied via Supabase MCP as `access_keys` on 2026-08-10.
-- get_advisors after apply: one INFO rls_enabled_no_policy (as every table
-- has today), no ERROR, no new WARN.

create table if not exists public.access_keys (
  key_id       bigint generated always as identity primary key,
  owner_id     uuid not null references public.profiles(profile_id),
  token_sha256 text not null unique,
  label        text not null,
  created_at   timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at   timestamptz,
  constraint access_keys_digest_shape check (token_sha256 ~ '^[0-9a-f]{64}$')
);

create index if not exists access_keys_live_owner_idx
  on public.access_keys (owner_id) where revoked_at is null;

alter table public.access_keys enable row level security;

comment on table public.access_keys is
  'Friend-tier access keys (Phase 9 task 1): one row per key a person holds, and the owner whose data that key opens. Revocation is a STAMP (revoked_at) — the row is kept, so who held a key and when it was pulled survives. No owner_id DEFAULT on purpose: an unstamped key must fail loudly rather than quietly become the founder''s.';
comment on column public.access_keys.token_sha256 is
  'SHA-256 hex of the key. The key itself is shown ONCE at mint and is never stored — a leaked dump is a set of digests, not a set of working keys. The check constraint makes storing a plaintext key impossible.';
comment on column public.access_keys.last_used_at is
  'Stamped on every successful resolution — the operator signal for a key that has gone quiet (runbook, task 7).';
