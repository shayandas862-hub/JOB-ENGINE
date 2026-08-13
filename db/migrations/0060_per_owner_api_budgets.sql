-- 0060 · Phase 9 task 5 — per-owner budgets and per-source caps.
--
-- The drip's shared 950/day Reed ledger, generalised to two scopes:
--   * the WORLD cap  — api_quota_ledger (source, day), already here since
--                      0036 and already written every night. Kept as-is:
--                      the provider's quota belongs to everybody, and the
--                      nightly world half is the only thing that should be
--                      able to spend it down on nobody's behalf.
--   * the OWNER budget — api_owner_spend (owner_id, source, day), new. A
--                      user-triggered call debits BOTH, so one key holder
--                      can never eat the shared quota.
--
-- Caps live in a table rather than in code so raising one is a decision the
-- founder can make without a deploy — and so a source with NO cap row is
-- refused rather than granted infinity (the conditional upsert in
-- budget.ledger returns no row when the subselect is NULL: fail closed).
BEGIN;

CREATE TABLE IF NOT EXISTS public.api_budget_caps (
  source       text PRIMARY KEY,
  world_daily  int  NOT NULL CHECK (world_daily >= 0),
  owner_daily  int  NOT NULL CHECK (owner_daily >= 0),
  note         text,
  CONSTRAINT owner_never_exceeds_world CHECK (owner_daily <= world_daily)
);

COMMENT ON TABLE public.api_budget_caps IS
  'Daily call caps per external API: world_daily is the shared provider quota, owner_daily is what any single owner may take of it. A source with no row here has no budget at all — the gate fails closed.';

CREATE TABLE IF NOT EXISTS public.api_owner_spend (
  owner_id uuid NOT NULL REFERENCES public.profiles(profile_id) ON DELETE CASCADE,
  source   text NOT NULL REFERENCES public.api_budget_caps(source),
  day      date NOT NULL,
  calls    int  NOT NULL DEFAULT 0,
  PRIMARY KEY (owner_id, source, day)
);

COMMENT ON TABLE public.api_owner_spend IS
  'One owner''s API calls per source per UTC day. Written only by the engine role at the HTTP choke point; every attempted call is spent, including a retry and including a failed one, because the provider counts it too.';

-- The nightly world half debits api_quota_ledger and nothing else, so it
-- never appears here — the founder's single-owner night is unchanged.

INSERT INTO public.api_budget_caps (source, world_daily, owner_daily, note) VALUES
  ('adzuna', 250, 100,
   'Free tier is 250 calls/day. The broad sweep already defaults to --adzuna-cap 240 and has peaked at 240 across 9 ledgered days, so 250 is a backstop above real use, not a throttle.'),
  ('reed', 950, 300,
   'The provider free day the sweep and the JD drip already share; peaked at exactly 950 across 11 ledgered days. Unchanged on purpose — this migration must not narrow tonight.'),
  ('companies_house', 20000, 2000,
   'No published daily limit (600 req/5 min is the rate limit); this is our own runaway backstop. The nightly classify batch of 2,000 organisations costs up to 4,000 calls, so 20,000 leaves the night four times its headroom.')
ON CONFLICT (source) DO NOTHING;

-- RLS ---------------------------------------------------------------------
-- Through the door: an owner reads their OWN budget rows, everybody reads
-- the caps and the world ledger, and NOBODY writes any of the three. The
-- policies alone would not achieve the last part: 0052 granted
-- SELECT/INSERT/UPDATE on all tables (and on future ones by default) to
-- goal_a_app, and an UPDATE with no visible row is 0 rows and no error —
-- silent, which is the wrong shape for a refusal. So the write privilege is
-- revoked outright and a forged spend raises 42501 instead.
ALTER TABLE public.api_budget_caps  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.api_owner_spend  ENABLE ROW LEVEL SECURITY;

CREATE POLICY app_reads_caps ON public.api_budget_caps
  FOR SELECT TO goal_a_app USING (true);

CREATE POLICY app_reads_own_spend ON public.api_owner_spend
  FOR SELECT TO goal_a_app USING (owner_id = public.app_owner());

GRANT SELECT ON public.api_budget_caps, public.api_owner_spend TO goal_a_app;
REVOKE INSERT, UPDATE, DELETE ON public.api_budget_caps  FROM goal_a_app;
REVOKE INSERT, UPDATE, DELETE ON public.api_owner_spend  FROM goal_a_app;

-- The world ledger was 'app_world_rows' FOR ALL USING(true) WITH CHECK(true)
-- from 0053, which let any key holder write the shared quota counter — and
-- therefore zero it. Nothing through the door ever wrote it (the sweep and
-- the drip run as the engine role, detached), so this narrows to SELECT.
DROP POLICY IF EXISTS app_world_rows ON public.api_quota_ledger;
CREATE POLICY app_reads_world_ledger ON public.api_quota_ledger
  FOR SELECT TO goal_a_app USING (true);
REVOKE INSERT, UPDATE, DELETE ON public.api_quota_ledger FROM goal_a_app;

COMMIT;
