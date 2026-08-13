# Bug Log — goal-a-engine

Every bug this project has hit, what caused it, how it was fixed, and — the
field that makes this log worth keeping — **whether it can come back in the
next build, and where it would come back**.

This is a separate log book from the others on purpose:

| Log | Answers |
|---|---|
| `docs/decision-log.md` | why a choice was made |
| `docs/progress-log.md` | what shipped, when, with measured numbers |
| **`docs/bug-log.md`** | **what broke, why it broke, and whether it will break again** |

A bug appears here whether it reached production or died in a test, whether it
was found by a human, a test, a review, or a live run. A bug that was fixed
before anyone noticed still teaches the same lesson.

**Rules for this file**
- **One entry per bug, numbered `B-GAE-NNN`, allocated on first sight and
  never renumbered or recycled.** Cite the id from the test that closes it, so
  the guard and the record point at each other.
- **Every entry states whether it can return.** "Fixed" is not the end of the
  story; "nothing stops it happening again" is a finding, not an omission.
- **Guards are named, not implied.** If the only thing preventing a repeat is
  a sentence in a document, say so — a doc line is a weaker guard than a test
  and the log should not flatter it.
- **This file ships in the public repository.** No secrets, no project ref, no
  personal data, no token values — the snapshot's scrub checks would fail the
  release, and rightly.
- **Updated at every phase close**, as a step in the phase relay, and
  immediately whenever a bug is found mid-phase.

**Entry shape** — the labels are fixed so they can be checked mechanically
(`tests/test_bug_log.py`):

```
### B-GAE-NNN · one line: what broke
- **Phase:** where in the build it happened, and the date
- **Found by:** what caught it — a test, a live run, a review, a person
- **Cause:** the mechanism, not the symptom
- **Fix:** what changed
- **Guard:** what now makes this fail loudly (name the test, or admit there
  isn't one)
- **Could it return?** LOW | MEDIUM | HIGH — and where it would show up next
```

---

## Open

### B-GAE-050 · A database test measured the founder's laptop instead of the query, so it was green on live and red on any rebuilt database
- **Phase:** 9.5 — task 4's test, found 2026-08-13 while chasing [[B-GAE-049]].
  **The instance is FIXED; the entry stays open only for the sweep it asks for
  at the end.**
- **Found by:** reproducing the public `database` job locally in Docker —
  postgres:17, `ops/ci/apply-schema.sh`, `RUN_DB_TESTS=1` — after the public
  repository went red and the Actions logs returned 403 without a token.
  `tests/test_learning_curve.py::test_the_curve_runs_against_the_real_views_and_real_column_types`
  failed on `assert basis["skills_held"] > 0` with `0 > 0`. **Confirmed not to
  be a regression** by running the same test from a worktree at `070447b` —
  the commit whose snapshot CI had passed — where it failed identically.
- **Cause:** the test asserted on whatever the database happened to contain,
  and its own comment said so out loud: *"The measured shape of the founder's
  own base"*, with `assert ... "no 'prove it' rows — 9 were measured on
  2026-08-12"`. On live that is 21 held skills and it passes. A database built
  the way CI builds one — genesis, the 64 committed migrations, then
  `ops/ci/02-seed.sql` — seeds `role_skills` (so demand exists, and
  `skills_in_demand > 0` passed) and **no `my_skills` at all**, so nothing is
  held and the next line fails. It was a measurement of the developer's laptop
  wearing the shape of a test of a query.
- **The part still not explained, stated rather than smoothed over:** the same
  test passed CI at `8f1f3c4` — the `database` job for that run really is
  `success` on the API — and it fails deterministically on a database rebuilt
  by the same script at the same commit. Ambient-state tests are
  order-dependent by nature, so the likeliest reading is that something
  earlier in that run left committed rows behind, which is the same family of
  defect as [[B-GAE-041]]. It is NOT confirmed, the logs need a token this
  session did not have, and the fix does not depend on the answer.
- **Fix:** the test now CREATES what it needs — it reads a real `skill_asked`
  out of `role_skills`, writes it as a held skill for the owner through the
  canonical `criteria.writer.add_skill`, exercises the ranking, and rolls
  back. The assertions became properties instead of counts: a held,
  in-demand, unevidenced skill must rank "prove it", and `skills_held > 0` now
  fails with "a skill was just written and the query cannot see it — the join,
  not the data, is wrong", which is a sentence about the code under test.
- **Guard:** the test itself, now environment-independent and **verified in
  both directions rather than assumed** — green against the live database
  (12 passed) and against a Docker-built CI-identical fixture (12 passed), and
  the full suite green against that fixture (1,163 passed). The class was
  swept: `select profile_id from profiles order by created_at limit 1` appears
  in one other live test, `tests/test_rls_policies.py`, which uses it for
  IDENTITY and not to assert on row counts, and which passes against the
  fixture. **What is still owed is the wider sweep** — no scan asserts that a
  DB test never depends on ambient rows, and that sweep is written down here
  rather than claimed as done.
- **Could it return?** **MEDIUM.** The instance is closed and the two-database
  check is now a thing that has actually been run once, which it never had
  been. The class returns the moment a DB test is written against live and
  never tried on a rebuilt database — cheap to do now that the Docker recipe
  is in this entry, and nothing forces it.

### B-GAE-049 · The pre-push ritual runs two lanes that both SKIP the database tests, so a DB-only breakage reaches the public repo red
- **Phase:** 9.5 — 2026-08-13, on the founder's instruction to push both repos.
  **The instance is fixed; the ritual gap that let it out is OPEN.**
- **Found by:** the public repository's own CI going **red on the pushed
  commit** (`2e0875c`), minutes after a push that every local check had
  blessed. Four tests in `tests/test_signin_identity.py` failed against a real
  Postgres.
- **Cause:** two mistakes, and only the second one is interesting.
  1. [[B-GAE-048]]'s gate made profile CREATION conditional, and four existing
     tests create a JWT-born owner in order to prove something else about it
     (that RLS scopes them, that the budget ledger meters them). They needed
     to open the gate explicitly and did not.
  2. **The ritual could not see it.** The phase relay's pre-push sequence is
     "run the suite" then "run the suite INSIDE the snapshot" — and BOTH of
     those lanes skip every `RUN_DB_TESTS` test. Locally those four tests
     printed as `s`. In the snapshot they printed as `s`. The public
     `database` job creates a real Postgres on the runner and runs them, so
     the FIRST execution of the affected tests anywhere was in public, on a
     repository whose whole purpose is to be looked at. The verification
     ritual was structurally incapable of catching a DB-only regression, and
     nothing said so.
- **Blast radius, measured:** the private push (`07bbb36`) and the public push
  (`2e0875c`) both carried it; the public run failed both times it could. The
  offline lane reported **1,099 passed / 64 skipped** and the snapshot lane
  **1,092 passed / 71 skipped** — two green results either side of a broken
  change. Run with `RUN_DB_TESTS=1` afterwards: **1,163 passed, 0 skipped**,
  which is the number that would have refused the push.
- **Fix:** the four tests now pass `env=OPEN` (they are testing what a
  JWT-born owner *is*, which requires creating one), and the full lane was run
  with `RUN_DB_TESTS=1` before re-pushing — 1,163 passed, 0 skipped. The
  ritual gap itself is NOT fixed: the relay still does not name the DB lane as
  a pre-push step.
- **Guard:** **none mechanical — nothing stops a push whose DB lane was never
  run.** The public CI is what caught it, and it caught it one step too late
  by construction: it runs after publication. The honest statement is that the
  only thing standing between a DB-only regression and a red public
  repository today is remembering to type `RUN_DB_TESTS=1` first. A skip is
  not a pass, and this suite prints 64 of them.
- **Could it return?** **HIGH.** Every future change to a gate, a policy or a
  writer is disproportionately likely to break exactly the tests that only run
  with a database — and the two lanes anybody actually runs before pushing
  will keep printing green. The next surface is any phase close: step 4 of the
  relay explicitly says "run the suite INSIDE the snapshot" and stops there.

### B-GAE-048 · The stranger gate is held by the Google switch, but EMAIL sign-up is on — so the self-serve door is ajar, not shut
- **Phase:** 9.5 — 2026-08-13, found on the founder asking a direct question:
  "is the Google auth and the user onboarding something any user can do?"
  **OPEN — the config half is a security setting on the founder's account and
  the code half is a decision he has not yet made.**
- **Found by:** reading the door instead of the note. `CLAUDE.md` and
  `plans/0014` both state the stranger tier is "built and switched OFF at the
  founder's gate", and the evidence offered for that is always the **Google
  provider**. Measured against the live project 2026-08-13:

  | link in the chain | measured | assumed by the standing gate |
  |---|---|---|
  | `external.google` | **false** | false ✓ |
  | `external.email` | **true** | never considered |
  | `disable_signup` | **false** | true ✗ |
  | `mailer_autoconfirm` | false | — |
  | `SUPABASE_URL` on the MCP service | **set** (`ops/cloud/env.sh:65`) | set ✓ |
  | Cloud Run ingress | `--allow-unauthenticated` (`ops/cloud/setup.sh:116`) | deliberate ✓ |

  A `POST /auth/v1/signup` carrying a deliberately invalid body was refused
  with `error_code: weak_password` — **input validation, not policy**. A
  policy-shut instance answers `signup_disabled` before it looks at the
  password at all. The probe created nothing.
- **Cause:** the gate was reasoned about as "is Google enabled?" when the
  property that decides it is **"can a member of the public obtain a
  Supabase-signed JWT for this project?"** Google is one way to get one; email
  sign-up is another, it is on by default, and it was never part of the
  decision. `mcp_server/transport.py`'s JWT path then does exactly what it was
  built to do — verifies signature, issuer and audience, every one of which a
  real email-signup token passes, because it genuinely IS this project's token
  — and `auth/signin.py::owner_for_auth_user` **creates a profile on first
  sight**. That auto-create is correct for the stranger tier and is precisely
  what makes the tier self-serve; it is only wrong because the tier is
  supposed to be off. The switch and the mechanism disagree, and the switch
  lives in somebody else's dashboard where no test can see it.
- **What it does and does NOT mean, measured rather than feared:** it is
  **not** a data breach. RLS holds — 30 policies over 30 tables, proven in
  Phase 9 by ATTEMPTING cross-user reads and being refused, and the MCP door
  runs as `goal_a_app`, which cannot bypass them. A self-registered owner gets
  their OWN empty lens, queue, tray and CV and cannot read one row of the
  founder's. Notion filing already refuses for owners the single credential
  does not belong to; nudges only reach a channel that owner sets. The real
  exposures are (1) **a standing ⛔ founder gate is not held by the mechanism
  he believes holds it**, and (2) **cost and noise** — a registered owner can
  reach `run_sweep`, `run_classification` and `start_pipeline`, which spend
  the shared Adzuna/Reed/Companies House quotas, and every new owner earns a
  personal pass in the 06:30 job. The per-owner budget ledger (Phase 9 task 5)
  is what caps the money meanwhile, and it is quietly doing the job the
  provider switch was assumed to be doing.
- **The barrier that does exist, stated so it is not overrated:**
  `mailer_autoconfirm` is **false**, so a sign-up returns no session until the
  address is confirmed. That stops a bot with no mailbox. It does not stop a
  person: anyone who owns an email address passes it in two steps. It is a
  speed bump, and calling it a gate would repeat the exact mistake this entry
  is about.
- **Fix — the code half is DONE 2026-08-13; the live half is not, and the gap
  between those two sentences is the important part of this entry.**
  1. **Code, shipped: the gate moved out of the dashboard and into the repo.**
     `auth/signin.py` gains `RegistrationClosed` and `self_serve_open()`, and
     `owner_for_auth_user` now REFUSES to create a profile for an unknown
     identity unless `SELF_SERVE_SIGNUP` is explicitly a yes. Creation is
     gated; **resolution never is** — an already-known `auth_user_id` still
     resolves whether the gate is open or shut, because closing the door on
     strangers must not close it on the people already inside. The default is
     SHUT, and the yeses are an ALLOWLIST (`1/true/yes/on`) rather than a
     truthiness check, so `SELF_SERVE_SIGNUP=2` or `=disabled` — what a
     hurried deployment edit actually looks like — fails shut instead of
     opening the engine. `mcp_server/transport.py` turns the refusal into the
     same `None` an unknown credential gets, so "we are closed" cannot be
     distinguished from "who are you": a door that answers those differently
     tells a stranger they have found a live system worth pushing on.
  2. **⚠️ Still exposed in production until the service is REDEPLOYED.** The
     running Cloud Run revision carries the old code. The repository is shut;
     the live door is not. Until then the immediate mitigation is the config
     switch, which needs no deploy: Authentication → Sign In / Providers →
     Email → *Allow new users to sign up* off. **Deliberately not done from
     here — it is a security setting on the founder's own account.**
- **Guard:** `tests/test_self_serve_registration_gate.py` (24 tests) and two
  new cases in `tests/test_signin_door.py`. The gate tests pin the properties
  that actually decide it: that an absent setting means SHUT (the state live
  tonight), that an unrecognised value fails shut, that an existing owner
  still gets in while it is shut, that a refusal touches neither `insert` nor
  `savepoint` — a gate that writes and rolls back has still touched the table
  it exists to protect — and that the tier genuinely still WORKS when the
  founder opens it, which is the failure where a gate reads as closed because
  the feature behind it was quietly broken. The door tests prove a
  cryptographically perfect stranger is refused, and that being closed is
  byte-identical to being unknown. **What is still unguarded, stated plainly:
  nothing here reads the live auth configuration, so no test can tell you
  which providers are enabled** — the fix is that it no longer matters, not
  that the dashboard became visible.
- **Could it return?** **LOW once deployed; the present exposure is live until
  then.** After the deploy the class is genuinely closed rather than the
  instance: every future provider (Apple, GitHub, magic link, phone) mints a
  token this door still verifies correctly, and every one of them now hits a
  gate that lives in the code and defaults to shut. The remaining way back in
  is someone setting `SELF_SERVE_SIGNUP=1` without meaning it, which is one
  grep away instead of invisible.

### B-GAE-046 · The phase brief sent a task to build a model over a column no row has ever carried
- **Phase:** 9.5 — task 4, 2026-08-12. **OPEN as a record-accuracy finding;
  the code consequence is closed** (task 4 was built on data that exists).
- **Found by:** measuring before building, because the project's own rule says
  numbers are measured and not recalled. `CLAUDE.md` and `plans/0014` item 4
  both say the learning-curve model can now be built because
  "`my_skills.learned_at` + evidence **has been collecting since 2026-08-10**,
  pinned from day one for exactly this. **With weeks of data**". Measured on
  live: **22 skills, 0 with `learned_at`**, every row written **2026-06-28**
  from `source = 'spec_sheet_v1'`, and **not one skill added since**. The
  column arrived with migration 0044 on 2026-08-10 and nothing has written to
  it in the two days of its existence.
- **Cause:** two claims that were true about the *schema* restated as claims
  about the *data*. 0044 did pin `learned_at` on day one, and `add_skill` has
  accepted it ever since — so "pinned from day one for exactly this" is
  accurate. "Has been collecting" and "weeks of data" are not: collecting
  requires a writer, the only writer is `add_skill`, and the sole population
  of `my_skills` predates the column by six weeks. The same sentence also
  contradicts itself on time — a column created two days before the brief
  cannot have weeks of anything — and nobody read it closely enough to notice,
  including at the Phase 9 close audit.
- **Blast radius:** none in production, and that is luck rather than design.
  Had the ranking been built as briefed, it would have sorted on a column
  where every value is NULL: an empty list forever, from code that runs
  without error and reviews as correct. The failure would have surfaced as
  "the curve never has anything in it", months later, with nothing pointing
  here — the same silent shape as [[B-GAE-004]].
- **Fix:** the brief's claim is not repairable retroactively, so task 4 was
  built on what the data supports instead — demand × what the owner holds ×
  what a confirmed fact proves — and `learned_at` is carried as a **stated
  absence with a trigger** rather than silently ranked on. The next
  `CLAUDE.md` says so.
- **Guard:** `tests/test_learning_curve.py::test_the_basis_reports_how_much_recency_data_exists`
  — the curve reports `learned_at_known` in its own basis and does not rank on
  recency while that is zero, so the absence is visible in every answer
  instead of being invisible in an empty one. What is NOT guarded is the
  original defect: **no test reads a phase brief and checks its claims against
  the database**, and none reasonably could.
- **Could it return?** **MEDIUM, and the class is the project's oldest.** A
  brief is prose, prose rots, and this one rotted between being written
  (2026-08-10, when the column was new and the intention fresh) and being read
  (2026-08-12). It returns wherever a future card says "we have been
  collecting X" — the defence is the standing rule that a number is measured
  in the session or not stated, which caught it this time.

### B-GAE-034 · A discovery stage holds one transaction open across every network fetch, so a migration run during it dies
- **Phase:** 9 — task 6, 2026-08-12. **OPEN and deliberately not fixed here:**
  changing a stage's transaction shape is an engine change under the 06:30
  lane rule, and this task's rule is to log what is found elsewhere rather
  than fix it. Nothing was corrupted; the migration was simply refused.
- **Found by:** migration 0062 failing with `57014: canceling statement due
  to statement timeout` on an `ALTER TABLE profiles ADD COLUMN` — against a
  one-row table, which is the part that made it worth chasing rather than
  retrying. Enumerating `pg_locks` × `pg_stat_activity` found one backend
  `idle in transaction` for **10 minutes 37 seconds**, holding
  `AccessShareLock` on both `profiles` and `licensed_sponsors`, its last
  statement `lookup_register_verdict`'s register query.
- **Cause:** `scripts/discover_companies.py` opens ONE
  `with get_conn() as conn, conn.cursor() as cur:` around the whole
  discovery pass, and the pass interleaves database statements with HTTP
  fetches. Between fetches the connection sits idle *inside* a transaction,
  holding an AccessShareLock on every table it has touched, for as long as
  the stage runs. DDL needs ACCESS EXCLUSIVE, so it queues behind that lock
  and dies on the statement timeout — and, worse than the failure itself, a
  queued ACCESS EXCLUSIVE request blocks every NEW reader behind it too. The
  census sweep is shaped better by accident (`commit` per organisation), so
  its window is one organisation rather than one stage.
- **Fix:** none yet. The shape that fixes it is the sweep's: commit between
  units of work, and never hold a transaction across a network call. Also
  worth having, and cheaper: an `idle_in_transaction_session_timeout` on the
  engine role, so a stuck stage cannot hold locks indefinitely.
- **Guard:** **none — a paragraph in this log and the query that found it.**
  No test can catch it: it is a runtime interleaving, not a shape a scan can
  see. What makes it *diagnosable* rather than mysterious is written down
  here, which is not the same as prevented:
  `select l.pid, a.state, age(now(), a.xact_start), left(a.query,60) from
  pg_locks l join pg_class c on c.oid = l.relation join pg_stat_activity a
  on a.pid = l.pid where c.relname = '<table>' and l.pid <> pg_backend_pid();`
- **Could it return?** **HIGH — it is not even fixed, and it is certain.** It
  returns the next time any migration is applied while discovery or the
  nightly job is running, which is most of the way through every 06:30 run.
  The failure is loud (the migration refuses) rather than silent, which is
  the only mercy in it.

### B-GAE-037 · The read stage labels a row by which key is set, not by what actually read it — and the laptop still holds the key the invariant says is never set
- **Phase:** 9 — the phase-close doc pass, 2026-08-12. **OPEN and deliberately
  not fixed here:** the code half is an engine change under the 06:30 lane
  rule, and the config half is the founder's own `.env`, which this pass does
  not edit.
- **Found by:** rewriting `docs/dev.md`'s stale `GEMINI_API_KEY` line for
  [[B-GAE-033]] and checking the claim before restating it, rather than
  copying the standing invariant across. `CLAUDE.md` says the engine "calls NO
  AI AT ALL (GEMINI_API_KEY is never set)". Measured: the local `.env` carries
  a **non-empty, 53-character** value for it. (Not printed, not committed, and
  not AIza-shaped — characterised by length and pattern only.)
- **Cause:** two things that only look like one.
  1. **The invariant is a sentence, not a mechanism.** Nothing asserts the key
     is unset anywhere the engine can run. The cloud half *is* mechanised —
     `GEMINI` is banned by name from every cloud script and is not among the
     eight secrets the deployment mounts — so the 06:30 job is AI-free by
     construction. The laptop is not, and a local `scripts/run.py`,
     `preview_pipeline` or `start_pipeline` reads the same `.env`.
  2. **The provenance label is chosen before any call happens.**
     `scripts/extract_skills.py` line 43 computes
     `quality, provenance = ("ai", "gemini") if api_key else ("keywords",
     "keywords")` from the key's PRESENCE, then loops calling
     `read_jd_or_fallback`, whose whole purpose is to fall back to the keyword
     extractor when the call fails. So a run with a dead key would stamp every
     row `read_quality='ai', read_provenance='gemini'` while the keyword
     extractor did the work — a receipt that names a reader that never read.
     That is a "every score ships its receipts" violation, and it is
     independent of whether the key is set: it is wrong whenever the AI path
     is configured and fails.
- **Blast radius, measured rather than feared:** `select read_provenance,
  read_quality, count(*) from role_listings group by 1,2` (2026-08-12) returns
  **2,378 keywords · 122 user-ai · 10,549 unread · ZERO gemini**. So no local
  read stage has ever run with the key present, no row is mislabelled today,
  and no money has been spent. The invariant has held in the data while being
  false in the configuration, which is the only reason this is a finding and
  not an incident.
- **Fix:** one of the two halves is DONE. **The key half: the founder deleted
  the `GEMINI_API_KEY` line (and its comment) from `.env` on 2026-08-12
  ~19:10 BST — measured gone, zero gemini mentions left in the file** — so the
  laptop now matches the invariant for the first time since it was written.
  The old comment recorded that a key pasted in chat was compromised; killing
  the credential at its source (Google AI Studio) is the founder's remaining
  minute. The label half is still open: provenance must be decided by what
  `read_jd_or_fallback` actually did (it already knows), not by what was
  configured — an engine change scheduled inside Phase 9.5.
- **Guard:** **the cloud half only.**
  `tests/test_cloud_setup.py::test_retired_and_deferred_keys_never_reach_the_cloud`
  makes the deployed engine AI-free mechanically. Nothing guards the laptop
  against the key returning, and nothing guards the label. The test this
  field deferred on purpose — assert `GEMINI_API_KEY` is blank wherever a
  `.env` exists — was unwritable while it would sit red on the founder's
  machine; **that day ended 2026-08-12 when the founder cleared the key**, so
  it is writable now (it would pass today) and belongs with the label fix
  this phase.
- **Could it return?** **It has not gone.** **MEDIUM** for a mislabelled row
  (it needs a local run of the `read` or `synonyms` stage, which is rare now
  that the nightly job is in the cloud) and **HIGH** for the class — a
  configured-versus-actual label. The next place the same shape can bite is
  any stage that records HOW something was produced from a setting rather than
  from the outcome. It surfaces first the next time anybody runs
  `scripts/run.py` on the laptop.

### B-GAE-024 · The mirrored migration log cannot rebuild the schema it mirrors
- **Phase:** 9 — infra sitting, 2026-08-11. **OPEN as a documented property,
  not a pending repair:** the CI lane now works around it correctly and the
  workaround is proven, but `db/migrations/` alone still cannot build the
  database and that is worth keeping visible.
- **Found by:** building the A1 CI database lane — applying
  `db/migrations/*.sql` in filename order to a blank Postgres 17 and reading the
  first error instead of assuming the log was replayable. `0001` failed with
  `relation "public.role_listings" does not exist`, and 47 of 58 migrations then
  failed as a cascade of that one cause.
- **Cause:** the log opens at `0001` with `alter table public.role_listings`.
  Eight tables were created in Phase 1 through the Supabase dashboard *before*
  `db/migrations/` existed, so they are in no migration: `role_listings`,
  `role_skills`, `target_companies`, `target_roles`, `licensed_sponsors`,
  `skilled_worker_occupations` (the engine's) plus `decisions` and
  `cowork_findings` (other projects sharing the database). Measured: the log
  creates **20 of 28** live tables. The gap is not only tables — **2 trigger
  functions** (`set_updated_at`, `set_skill_norm`), **7 triggers** and **4 RLS
  policies** (`occ_`/`sponsors_` anon+authenticated) are also genesis. The
  mirroring rule in `CLAUDE.md` has been followed faithfully since 0001; it was
  simply never retroactive, and nothing ever tried to replay the log.
- **Where the genesis DDL actually lives (measured 2026-08-11, after applying
  0059):** `list_migrations` on the Supabase project returns **57** entries
  against the repo's **59** files, and the two sets differ in BOTH directions.
  Supabase holds seven entries with no repo counterpart —
  `create_licensed_sponsors`, `create_skilled_worker_occupations`,
  `create_target_roles_simple`, `create_decisions`, `create_gap_analysis_schema`,
  `enable_rls_gap_analysis_tables`, `create_cowork_findings` — and those ARE the
  genesis tables. So **the Phase 1 DDL was never lost, only never mirrored**, and
  closing this properly is a copy job rather than a reconstruction. Going the
  other way, **nine repo migrations are absent from Supabase's history**
  (`0006`, `0008`–`0015`), because they were applied through the SQL editor or
  `execute_sql` rather than `apply_migration`. Neither record is complete on its
  own, which is the sharpest argument for the derived baseline: it is checked
  against the live database, and the live database is the only complete source.
- **Fix:** not a repair to the log — no migration is edited, deleted or skipped.
  A derived pre-0001 baseline, `ops/ci/01-genesis.sql`, is applied before the
  log. It is **generated, never hand-written** (`ops/ci/generate-genesis.py`):
  types, defaults, generated expressions and identity clauses come from
  `pg_dump` against live verbatim, and what to subtract is parsed out of the
  migrations themselves, so a new `add column` lands in the subtraction with no
  edit here. A hand-maintained genesis file would have been [[B-GAE-015]] at
  schema scale, which is the reason for every design choice in that script.
- **Guard:** `ops/ci/verify-genesis.py` — it builds the schema exactly as CI
  does and diffs it against live across nine dimensions: every column with type,
  nullability, default and generated flag, plus constraints, indexes, policies,
  view names, **view bodies**, view reloptions, RLS flags and triggers.
  Measured identical (482 columns, 67 constraints, 75 indexes, 32 policies, 12
  view bodies, 28 RLS tables, 7 triggers). It **cannot run in CI** — CI has no
  database credential and must not gain one — so it is a laptop tool, and that
  is the honest weakness of this guard: the CI lane proves the log *applies*,
  and only a human running `verify-genesis.py` proves it applies to the *right
  schema*.
- **Could it return?** **MEDIUM.** Not as a surprise — the lane fails loudly the
  moment a migration stops applying. It returns as *silent drift*: if a future
  DDL is applied to live via Supabase MCP and mirrored imperfectly, the CI lane
  stays green (it never sees live) while the log quietly stops describing
  reality. That is exactly [[B-GAE-025]], found in the same hour. The genesis
  file also cannot represent anything the log *removed* — four pre-0053
  policies could not be dumped because live no longer has them, harmless only
  because their `DROP POLICY` statements are `IF EXISTS`.

### B-GAE-016 · Thirteen of twenty-two database writers have never met a real table
- **Phase:** 9 — 2026-08-11. **Deliberately OPEN**: logged unfixed on the
  founder's word ("log the bug and mark the status unfixed, we will fix it
  later") rather than fixed in the session that found it. It is a decision,
  not an oversight.
- **Found by:** asking what class [[B-GAE-013]] and [[B-GAE-014]] belong to,
  after the same defect shipped twice in two days in sibling writers — then
  measuring the repo instead of estimating. **22 modules issue an INSERT or
  UPDATE. 32 test files use the FakeCursor; only 9 can reach a real database.
  Thirteen writer modules are named in no real-database test at all**:
  `discover.agg_partition`, `discover.agg_store`, `discover.merge`,
  `discover.onboarding`, `discover.promote_rule`, `discover.register_refresh`,
  `fetch.jd_drip`, `persist.extract_rules`, `persist.fetch_rules`,
  `pipeline.report`, `reading.accept`, `reading.serve`, `reading.stage`.
- **Cause:** the FakeCursor records the SQL string and asserts on it, so it can
  prove a query *reads* correctly and nothing else. Column types, generated
  columns, constraints and uuid handling do not exist inside it — which is
  exactly where both shipped bugs lived (a generated column in 013, an untyped
  `coalesce` in 014). Red-first does not compensate and this is the part worth
  keeping: a fake-cursor test goes red because the function is missing and
  green because it exists, so **both states are about the string and neither
  is ever about the database**. The discipline was followed and the defect
  still shipped.
- **Where it bites, and where it does not:** most of the thirteen run nightly
  in the 06:30 pipeline (`register_refresh`, `merge`, `jd_drip`,
  `stage_reading`, `report`, the `persist.*` rules) — a parse-time error there
  fails a stage loudly within one morning, so **the run is itself the
  integration test**. The real exposure is the modules **nothing runs except a
  person**: `reading.accept` and `reading.serve` (the tray),
  `discover.promote_rule`, `discover.onboarding`. Both bugs so far were this
  exact shape, and both were found by a human trying to use a tool, not by the
  suite.
- **Guard:** `tests/test_writer_coverage.py` — the test over the tests this
  entry called for, built in the 2026-08-11 infra sitting. It scans `src/` for
  every module issuing INSERT/UPDATE/DELETE, asserts each is named in at least
  one `RUN_DB_TESTS` test, and fails the build otherwise. Three assertions make
  it a ratchet rather than a snapshot: a new blind writer fails by name; an
  allowlist entry that has gained coverage must be deleted (so the list cannot
  keep stale names); and `MAX_BLIND_WRITERS` is pinned at 13, so a new writer
  can never be waved through by adding it to the list. All three seen red under
  deliberate mutation, plus a control asserting the scan still finds the 22
  writers rather than passing on an empty set.
  **This entry stays OPEN, and the reason is the point:** the guard stops the
  blind set GROWING; it does not make the 13 covered. **The allowlist was
  measured fresh rather than copied from the list above, and the two are not the
  same thirteen** — `discover.merge` and `discover.onboarding` gained real
  coverage later in Phase 9 (via [[B-GAE-018]]'s and [[B-GAE-020]]'s fixes),
  while `audit` and `discover.agg_match` were never named here at all. The
  measured blind set is now: `audit`, `discover.agg_match`,
  `discover.agg_partition`, `discover.agg_store`, `discover.promote_rule`,
  `discover.register_refresh`, `fetch.jd_drip`, `persist.extract_rules`,
  `persist.fetch_rules`, `pipeline.report`, `reading.accept`, `reading.serve`,
  `reading.stage`. This closes when that list is empty.
- **Could it return?** **HIGH — it has not left.** The next surface is the
  reading tray: `submit_reading` writes through `reading.accept`, which has no
  real-table coverage and almost no live exercise (staging measured 0 of 1,083
  for weeks), so if it carries the same defect the first person to read a real
  job is the one who finds it. After that, **task 4's onboarding writes**
  (`create_profile`, `target_roles`) — a brand-new user's very first action,
  on a path that today has fake coverage only, which is how 013's blast radius
  went from zero for the founder to total for user number two.

---

## Resolved

### B-GAE-047 · A committed plan described a ratchet that was neither in the repository nor passing
- **Phase:** 9.5 — task 7, 2026-08-12. Found and fixed on resuming the task
  after the session that started it ran out of quota mid-trim.
- **Found by:** measurement on resuming, before writing any code: `git status`
  showed `tests/test_tool_description_budget.py` UNTRACKED, and running it gave
  `22766 <= 19000` — **red**. Meanwhile `plans/0014`, committed at `2f27dc4`,
  already described that file as "a ratchet that measures what every client
  pays per turn and refuses to let it grow". `git log --all -- <path>` returns
  empty: the file had never been in a single commit.
- **Cause:** two halves that only look like one, and the second is the real one.
  1. The pin was written **before** the work it measured. `MAX_DESCRIPTION_CHARS
     = 19_000` was a target someone hoped a trim would reach, and the comment
     beside it stated "The trim pass that followed brought it to the number
     below" — a claim about a pass that had not run. The honest number, measured
     after a full quality-preserving trim of all 51 descriptions, is **20,151**.
  2. **Nothing checks that a document naming a guard is telling the truth.** The
     carry-forward sweep wrote the claim into a plan at the phase boundary,
     which is exactly when such claims are written and exactly when nobody
     re-runs them. This is the [[B-GAE-004]] shape one level up: not a test that
     cannot fail, but a *record of a test* that cannot fail.
- **Blast radius, measured rather than feared:** 38 distinct `tests/…py` paths
  are cited across `plans/` and `docs/` (34 in the public snapshot, which
  deletes `docs/handoffs` and `docs/claude-md-archive`). Exactly **one** was
  missing — this one. `docs/bug-log.md` is the heaviest citer, because its entry
  format REQUIRES a named guard, and `tests/test_bug_log_guard_ratchet.py`
  cannot catch a false citation: it scans the Guard field for *admissions* of
  absence, so a confident citation of a file that does not exist reads to it as
  a guard that does.
- **Fix:** the trim was finished honestly (23,087 → **20,151** characters across
  51 tools, −12.7%, while the toolset GREW by four), the pin set to the measured
  number, and the misleading comment replaced with what actually happened rather
  than quietly corrected. Then the missing guard was written.
- **Guard:** `tests/test_plan_cited_tests_exist.py` — every `tests/…py` path
  named anywhere in `plans/` or `docs/` must exist as a file. Proven red twice
  the way it would really break: deleting the cited file makes
  `test_every_test_file_the_logs_and_plans_name_actually_exists` fail naming
  that exact path. It carries its own control
  (`test_the_scan_is_actually_reading_the_logs_and_plans`, floor 25 against a
  measured 38/34) because a scan that silently stops matching would read as a
  clean result — which is the defect this entry is about. It deliberately does
  NOT assert the cited test *passes*: the suite being green proves that, and a
  test asserting other tests pass is a loop nobody can debug.
- **Could it return?** **LOW for the instance, MEDIUM for the class.** A missing
  file is now caught mechanically. What is still unguarded is a citation that
  exists but does not do what the prose says it does — the guard checks
  presence, not truthfulness, and it says so rather than implying more. The
  narrower risk that produced this entry is real and named: a number written
  into a test as a target before the work, which reads as measured forever
  after. Next surface is any future ratchet whose pin is chosen at design time
  rather than after the pass it measures.

### B-GAE-025 · Migration 0046 mirrored three view bodies as English prose, so the log rebuilds the founder's deleted hardcode
- **Phase:** 9 — infra sitting, 2026-08-11. Fixed the same sitting by migration
  **0059**.
- **Found by:** the new A1 lane's schema comparison, on its second attempt. The
  first version of that comparison checked view **column lists** and reported
  "views match" — so it had to be caught twice: once as five missing columns,
  and then, after the check was widened to compare view **bodies**, as three
  mismatched definitions. The first check was the [[B-GAE-004]] shape exactly:
  it could not fail for the reason that mattered.
- **Cause:** `0046` says so in its own header — *"Full definitions live in the
  database; this mirror records the CHANGES"* — and then records those changes
  as **comments**, not SQL: lines 31–36 for `v_apply_queue`, 53–58 for
  `v_today`, 60–62 for `v_scorecard`. `psql` cannot execute prose. So the
  committed log rebuilt the *pre-8.5* versions of all three views. The
  consequence is worse than a stale view: **`v_apply_queue` came back with the
  hardcoded founder title regex** (`solutions? (engineer|architect)|forward[-
  ]deployed|applied ai|…`) that Phase 8.5 deliberately replaced with a
  data-driven gate over the owner's `target_roles`. `CLAUDE.md` states that
  regex "is GONE"; it is gone from live and it was still in the repository.
  `v_today` lost `is_new_today`, `skill_have`, `skill_asked` and `v_scorecard`
  lost `new_today`, `sponsors_total` — all five read by
  `src/dashboard/page.py`, so a rebuilt dashboard would have died on a missing
  column.
- **Fix:** migration **0059** carries the three real bodies, taken from live's
  own `pg_get_viewdef`, and re-asserts `security_invoker = true` on all three
  because `CREATE OR REPLACE VIEW` drops reloptions ([[B-GAE-006]]).
  **Applied to live 2026-08-12 18:37 BST on the founder's word**, and proven a
  no-op by measurement: the md5 of all three view bodies is byte-identical
  before and after, and all three still carry `security_invoker=true`;
  `get_advisors` shows nothing new. **What the apply itself uncovered:** this
  entry used to say the migration was "deliberately not applied to live" — but
  Supabase's own history shows the same SQL was already applied
  **2026-08-11 22:20**, unprefixed (`mirror_view_bodies_0046_left_as_prose`),
  the very evening it was written. So the paper was wrong about its own
  no-op from that evening on, the close audit repeated the claim without
  checking the history list, and today's second run is what finally made
  every record agree. The history now carries the SQL twice, both no-ops,
  both named — untidy, stated, and harmless.
- **Guard:** `ops/ci/verify-genesis.py`'s `view_bodies` comparison — an md5 of
  every view definition, live against rebuilt-from-log. Seen red naming exactly
  `v_apply_queue`, `v_today`, `v_scorecard` before 0059 and green after. Its
  `view_reloptions` check covers the B-GAE-006 half. **The weakness is the same
  one as [[B-GAE-024]]:** this runs on a laptop, not in CI, because it needs the
  live credential. Nothing automatic will notice the next prose mirror.
- **Could it return?** **HIGH.** The practice that caused it is still available
  and was deliberate: a migration that describes its DDL instead of containing
  it looks tidy and reads well. Nothing forbids it, no test parses migrations
  for executability, and the next `CREATE OR REPLACE VIEW` mirrored by hand can
  do it again. It returns wherever a view is edited through Supabase MCP and
  summarised into the log rather than copied — and it stays invisible until
  someone rebuilds from scratch, which before this sitting nobody had ever
  done.

### B-GAE-045 · The snapshot verifier can print CLEAN it has not earned: a scanner error reports ok, and a missing LICENSE fails nothing
- **Phase:** 9 — independent close audit, 2026-08-12. **RESOLVED 2026-08-12,
  Phase 9.5 task 0.** It was latent rather than an incident — the current
  snapshot IS clean, proven independently by value against every `.env`
  secret and by shape — which is exactly why it was worth closing before the
  phase's own refresh leaned on the verdict again.
- **Found by:** asking the audit brief's question "can it produce a CLEAN
  verdict it has not earned?" and demonstrating it in a sandbox: with a
  shape-matching ref planted, the healthy `check()` grep finds 1 file (FAIL,
  correct); the same pipeline with a broken grep invocation — its error
  hidden by `2>/dev/null` and its exit status by `|| true` — counts 0 and
  prints "ok". A false clean, from the construction the project's own gotcha
  list forbids ("a broken check must not look like a clean result").
- **Cause:** `ops/flip/prepare-snapshot.sh::check()` needed `|| true` so that
  grep's finds-nothing exit (1) would not kill the script under `set -e` —
  the comment explains that honestly — but `|| true` cannot tell exit 1
  (clean) from exit 2 (the scanner itself broke), and `2>/dev/null` hides the
  complaint. Separately, line 91 prints `LICENSE present: NO` without setting
  `fail=1`, so a snapshot missing its licence still ends `SNAPSHOT CLEAN`.
- **Fix:** `check()` captures grep's exit status and treats **only 0 and 1 as
  answers** — anything higher is reported as "the scanner itself failed …
  this snapshot has NOT been checked for it" and sets `fail=1`. `2>/dev/null`
  is gone, so grep's own explanation reaches the person who needs it. The
  match count is now computed in shell rather than by piping to `grep -c`:
  having just decided grep may be broken, asking it how many lines it
  produced would be trusting the same tool twice. A missing LICENSE sets
  `fail=1` like every other check — a public repository with no licence
  grants no rights to anyone reading it, which is a publishing failure and
  not a remark.
- **Guard:** `tests/test_snapshot_verifier.py`, and it tests the script by
  **running it**, not by reading it — grepping the source for words would only
  prove the file contains them. Each test builds a miniature sandbox
  repository and runs the real script inside it:
  `test_a_scanner_that_breaks_fails_shut_instead_of_reporting_ok` shims a
  `grep` that exits 2 onto PATH and requires a refusal;
  `test_a_snapshot_missing_its_licence_is_not_clean` omits the LICENSE;
  `test_the_scrub_patterns_actually_catch_a_planted_leak` plants a
  project-ref-shaped string and requires the scrub to find it — closing the
  other half of this entry's original finding, since the four patterns had
  never once been fired at something they are meant to catch. The control,
  `test_a_healthy_sandbox_still_verifies_clean`, comes first deliberately:
  every other assertion is "the script refused", and all of them would pass
  if the sandbox were broken in some unrelated way. **Seen red for the right
  reason:** the two defect tests failed against the old script while the
  control and the planted-leak test passed. The planted string is assembled at
  runtime and never appears as a literal — writing a real-shaped ref into a
  tracked file is the very leak these checks exist to catch, and this project
  has done it once already, in the test that was checking for it.
- **Verified end to end, not only in the sandbox:** the fixed script was run
  against the real repository and still reports four `ok` lines, `LICENSE
  present: yes`, one commit, and `SNAPSHOT CLEAN`; the suite was then run
  INSIDE that snapshot — **959 passed / 67 skipped, exit 0**, the seven
  `private_only` guards skipping exactly as intended, which also confirms
  [[B-GAE-040]]'s new two-signal predicate behaves correctly where it matters
  most.
- **Could it return?** **LOW.** A broken scanner and a missing licence both
  fail shut now, and both are tested by execution. The honest residual: these
  tests prove the script refuses for the two reasons it was blind to, not that
  the four patterns describe every secret this repo could ever hold — a leak
  of a shape nobody thought to write a pattern for still passes, and no test
  can close that.

### B-GAE-043 · .dockerignore's `__pycache__/` never matched a nested path, so locally built images ship the laptop's bytecode
- **Phase:** 9 — independent close audit, 2026-08-12. **RESOLVED 2026-08-12,
  Phase 9.5 task 0**, proven by building the image both ways.
- **Found by:** running the suite inside a locally built image for the
  claim-3 re-measurement: skip locations printed with the founder's macOS
  home path baked in. `find /app/tests/__pycache__ -name "*.pyc"` inside the
  image then listed the laptop's bytecode files shipped wholesale.
- **Cause:** `.dockerignore` lists `__pycache__/` and `*.pyc`, but dockerignore
  patterns anchor at the CONTEXT ROOT — they match only a top-level
  `__pycache__`, never `tests/__pycache__` (the recursive forms are
  `**/__pycache__` and `**/*.pyc`). So `COPY src/ scripts/ tests/ db/` carries
  every nested cache along, and the Dockerfile's own comment ("a tree copy
  could smuggle local state or credentials into a layer") claims a protection
  the belt does not deliver. CI images are clean by luck alone — a fresh
  runner checkout has no caches; every image built on the laptop
  (`ops/cloud/build-push.sh`, and so plausibly the deployed one) is not.
- **Blast radius, measured rather than feared:** a locally built image
  contained **246 `.pyc` files, every one of them foreign** — each carrying
  the author's absolute macOS home path inside it, read out of the marshalled
  code object rather than guessed at. After the fix, the same build ships
  **0 `.pyc` files and 0 `__pycache__` directories**.
  A detail the guard turned up on its first honest run, worth keeping because
  it makes the smuggling concrete: **9 of the working copy's cached files were
  compiled at a path that no longer exists** —
  `…/Desktop/GOAL/goal-a-engine/`, this repository's location before it was
  moved under `MY CODES`. So the images were not merely carrying a copy of the
  current tree; they were carrying bytecode for source files at an address
  that had not been valid for weeks. Not a separate defect — nothing in the
  project is wrong because a directory was renamed — but it is the sharpest
  available statement of what "the laptop's state rides into the layer" means.
  Those 9 files were deleted (caches regenerate; nothing was lost).
- **Fix:** the recursive forms — `**/__pycache__`, `**/*.pyc`, and the same
  correction applied to the other classes that occur at any depth
  (`**/.pytest_cache`, `**/.DS_Store`, `**/.env`), since the entry's own
  prediction was that the next flat pattern would repeat this. The top-level
  directories (`docs/`, `plans/`, `ops/`, `data/`) stay flat, which is right
  for them. Container lane re-verified after the rebuild: **904 passed / 122
  skipped** (1,026 collected — the close's 900/118 plus this task's 8 new
  tests, which reconciles exactly).
- **Guard:** `tests/test_image_hygiene.py`, three tests, and the important one
  is not a shape check.
  `test_no_bytecode_in_this_tree_was_compiled_somewhere_else` reads the source
  path recorded inside every `.pyc` under the trees the Dockerfile copies (the
  COPY list is parsed from the Dockerfile, not copied) and fails if any was
  compiled outside this checkout. It is deliberately NOT "no .pyc exists" —
  running pytest creates bytecode as it imports, so that test would be red
  everywhere, forever, which is how a suite starts being ignored. This one
  passes on a laptop, passes in a correct image, and **fails by name in a
  smuggling one** — verified in both directions: red in the pre-fix image
  listing all 246, green in the rebuilt one.
  `test_the_dockerignore_excludes_every_at_any_depth_class_recursively`
  guards the cause itself, and
  `test_the_dockerfile_still_copies_by_allowlist_not_by_tree` is its control:
  the recursive patterns only matter while the copy stays an allowlist, and
  `COPY . .` would make `.dockerignore` the only protection — the arrangement
  that just proved unreliable.
- **Could it return?** **LOW for bytecode, MEDIUM for the class.** Foreign
  bytecode now fails the container lane on every push. A *different* smuggled
  class — a stray `.log`, a lock file, a data dump — would still ride in if it
  were added to `.dockerignore` flat, and only the named list above is
  checked. What is genuinely closed is the blind spot's invisibility: it was
  undetectable in CI by construction, and the check that would have caught it
  now runs there.

### B-GAE-042 · The README dead-link guard only sees a link to the deleted directory itself, not to anything inside it
- **Phase:** 9 — independent close audit, 2026-08-12. **RESOLVED 2026-08-12,
  Phase 9.5 task 0.**
- **Found by:** mutation. Appending `[gone](docs/handoffs)` to the README
  makes `test_the_readme_never_links_to_a_path_the_snapshot_deletes` fail
  (correct); appending `[gone](docs/handoffs/phase-9p5-relay-2026-08-12.md)`
  — a file INSIDE a directory the scrub deletes — stays green, and that link
  would 404 in public exactly like [[B-GAE-039]] did. Both re-reproduced
  before the fix.
- **Cause:** the test compares `link.strip("/") == gone.strip("/")` — exact
  equality against the scrub list's four paths — so a path one segment deeper
  never matches. [[B-GAE-039]]'s actual instance was a link to the directory
  itself, and the guard was written to that instance rather than to its
  class.
- **Fix:** the comparison is now "equal to, **or inside**" —
  `link == gone or link.startswith(gone + "/")`, with the trailing-slash
  normalisation done once on each side rather than twice in the condition.
  The scrub list is still read out of `prepare-snapshot.sh` rather than
  copied, so this covers whatever the list says tomorrow.
- **Guard:** the same test, `tests/test_public_workflow.py::test_the_readme_never_links_to_a_path_the_snapshot_deletes`,
  now covering the class instead of the instance. **Seen red for the right
  reason, and checked in three directions** rather than one, because a
  widened matcher is exactly the kind that starts catching things it should
  not: the child link now FAILS (it did not before), the directory link still
  FAILS (the original instance is not lost), and a legitimate
  `docs/decision-log.md` link still PASSES (`docs/` is not scrubbed — only
  `docs/handoffs` and `docs/claude-md-archive` are, and a prefix match that
  swallowed all of `docs/` would have been a worse bug than the one fixed).
- **Could it return?** **LOW for this class.** Equal-or-inside is the whole
  space for a path link. The residual edge is a link written in a form the
  regex does not read as a link at all — a bare URL, an HTML `<a href>`, or a
  reference-style `[x]: path` definition — none of which the README uses
  today, and none of which this guard would see.

### B-GAE-041 · The per-owner window probe schema survives every DB run — its cleanup drops it and then rolls the drop back
- **Phase:** 9 — independent close audit, 2026-08-12. **RESOLVED 2026-08-12,
  Phase 9.5 task 0**, and the live database is clean: `pg_namespace` now
  returns **zero** non-system schemas.
- **Found by:** querying `information_schema` without a schema filter during
  the audit's claim-8 re-measurement: `target_companies` came back doubled.
  `pg_namespace` on the live database then showed schema
  `per_owner_window_probe` present AFTER two green `RUN_DB_TESTS=1` runs the
  same day (the close's 1,018/0 and the audit's). Re-measured before the fix:
  still present, with its 3 tables.
- **Cause:** `tests/test_per_owner_isolation.py::test_each_owner_gets_their_own_apply_window`
  must `conn.commit()` mid-test (it spawns `scripts/enrich_deadlines.py` as a
  subprocess, which needs to SEE the probe rows), so its schema creation is
  durable. Its `finally` then runs `drop schema … cascade` followed by
  `conn.rollback()` — and DDL is transactional in Postgres, so the rollback
  UNDOES the drop, every run, deterministically. The two sibling probes
  (`per_owner_nudge_probe`, `per_owner_report_probe`) never commit, so their
  final rollback erases schema and all — same finally, opposite outcome,
  which is why only one schema lingers and nobody noticed.
- **Fix:** the `finally` blocks now **commit the drop**, in all three probe
  tests rather than only the one that leaked — the sibling probes were correct
  by accident (they never commit), and the entry's own warning was that the
  next probe needing a mid-test commit would copy the broken shape. The live
  schema was removed **by running the repaired test**, not by a hand-typed
  `DROP`: the cleanest available proof that the fix does what it claims, since
  the residue disappearing IS the fix executing.
- **Guard:** `tests/test_db_residue.py::test_no_schema_a_test_invented_survives_on_the_live_database`
  — it reads the probe names out of the test sources with a regex over
  `schema = "…"` rather than keeping a copied list, so a probe added next
  month is covered without anyone remembering to add it. Two supporting
  tests stop it passing vacuously, which is the failure mode that let this
  bug live: `test_the_residue_scan_can_see_a_schema_that_is_really_there`
  plants a schema, proves the scan finds it, and proves a committed drop
  sticks (checked from a second connection); and
  `test_the_scan_finds_the_probe_names_the_suite_actually_uses` pins the name
  that caused this bug, so a broken parser fails loudly instead of reporting
  a clean database. **Seen red for the right reason:** the residue test failed
  against live naming `per_owner_window_probe` while both controls passed.
- **Could it return?** **LOW.** The drop is committed, and a leak of this
  class now fails the next `RUN_DB_TESTS=1` run by name rather than sitting
  invisible. Two honest residual edges: the check only runs when someone runs
  the DB lane (CI does, on every push to main), and it only knows names that
  match the `schema = "…"` convention — a probe built some other way would be
  invisible to it, which is why the convention is now worth keeping.

### B-GAE-040 · A byte-equal copy of the public workflow over the private one makes every deploy guard stand down silently
- **Phase:** 9 — independent close audit, 2026-08-12. **RESOLVED 2026-08-12,
  Phase 9.5 task 0.** Found after the close was written and before anything
  was pushed; fixed before any other work in the phase it endangered.
- **Found by:** mutation, on the audit brief's instruction to attack
  `private_only` first. `cp ops/flip/public-ci.yml .github/workflows/ci.yml`
  in the PRIVATE repo — the exact "bad fix" for the red X that [[B-GAE-036]]
  documents as nearly made — then the full suite: **953 passed / 65 skipped,
  exit 0, fully green**, indistinguishable from a healthy snapshot, while
  deploy-on-green, the WIF auth and the container lane were all destroyed.
  The same copy with ONE extra comment line (not byte-equal) correctly fails
  five tests, so the blind spot is exactly byte-equality — the one state a
  straight `cp` produces. **Re-reproduced before the fix** (2026-08-12, Phase
  9.5): 953 / 65, exit 0 — the audit's numbers to the test.
- **Cause:** `tests/conftest.py::_is_snapshot()` answers "am I the snapshot?"
  from a single signal: `.github/workflows/ci.yml` byte-equal to
  `ops/flip/public-ci.yml`. That signal is the very file the seven
  `private_only` guards exist to protect, so corrupting the subject flips the
  predicate and dismisses its own guards — including
  `test_the_scanner_still_bites_the_workflow_that_actually_deploys`, the
  anti-[[B-GAE-004]] control. [[D-GAE-074]] weighed guard-loss in the PUBLIC
  checkout and chose the mark per test to avoid it; the misfire in the
  PRIVATE checkout was not weighed.
- **Fix:** a SECOND independent signal, and both must agree.
  `_is_snapshot()` now requires the workflow to match **and** `CLAUDE.md` — a
  file only the scrub deletes — to be absent. One `cp` moves the first signal
  and cannot move the second, so the corrupted private repo is no longer
  mistaken for a snapshot and all seven guards run and fail. The two signals
  are independent by construction: one is a fact about the workflow, the
  other a fact about the scrub.
- **Guard:** `tests/test_public_workflow.py::test_the_snapshot_signals_never_disagree`
  — deliberately **UNMARKED**, because a guard skippable by the predicate it
  checks is the bug rather than the fix. It names the corruption in one
  sentence instead of leaving six unrelated-looking failures to be decoded,
  and it passes in both real checkouts (in the snapshot both signals are
  true; in the private repo both are false).
  `test_the_two_snapshot_signals_are_read_from_the_real_scrub_list` keeps the
  second signal honest by reading the scrub list out of
  `prepare-snapshot.sh`: if the list stops deleting `CLAUDE.md`, that test
  fails rather than `_is_snapshot()` silently returning False in the real
  snapshot and failing every `private_only` test in public.
  **Seen red for the right reason** before being trusted: with the mutation
  applied the suite goes **7 failed / 955 passed**, the new test among them
  with its own message; restored, **962 passed / 58 skipped** (1020 collected).
- **Could it return?** **LOW for this instance, MEDIUM for the class.** The
  copy no longer buys silence, and the second signal cannot be moved by the
  same command. The class — a predicate that reads its own guards' subject —
  is not closed in general: any future "am I environment X?" test that keys
  off one file can repeat it. What is closed is the specific inversion, and
  the phase-close snapshot refresh (which this entry warned would invite it)
  now runs against a suite that would say so.

### B-GAE-035 · The public snapshot ships the private CI workflow, so the portfolio repo shows a red X to every visitor
- **Phase:** 9 — 2026-08-12, while the private repo's CI was going green on
  the largest push of the phase. **RESOLVED 2026-08-12 18:33 BST, seen green:**
  the snapshot refresh shipped the two-lane allowlist workflow, the founder
  gave the push order, and the public repository's first Actions run on it —
  run 31623076331 — completed **success on both jobs** (offline suite, and the
  database lane against a runner-local Postgres built from the committed
  migration log). That green was this entry's closing condition, and it was
  watched, not assumed. **And then seen by the founder himself, ~18:55 BST,
  in the same Actions tab where this bug was found:** CI #3 (`034bf7b`,
  1m 32s) and CI #4 (`8f1f3c4`, the mirror refresh, 1m 17s) both green;
  the two 2026-08-10 reds still visible above them — 1m 36s and 1m 49s,
  exactly the "under two minutes each" this entry opened with, now
  history rather than the front page — and `CI` the ONLY workflow the
  tab lists, which is the allowlist holding.
- **Found by:** the founder, reading his own public repository's Actions tab
  — both runs on JOB-ENGINE- (2026-08-10, the Phase 8.5 snapshot) red at
  under two minutes each.
- **Cause:** the snapshot ships `.github/workflows/ci.yml` verbatim, and
  GitHub runs whatever workflow a pushed repository carries. The workflow's
  image and deploy jobs authenticate to Google Cloud via WIF credentials
  that deliberately do not exist in the public repository — so every public
  push fails those jobs by construction. The snapshot ritual verifies the
  suite green INSIDE the snapshot and scrubs its content, but never asked
  what GitHub would DO with the shipped workflow. The result inverts the
  repo's purpose: a portfolio that exists to demonstrate CI discipline
  greets every visitor with a failing badge.
- **Fix:** scheduled for the phase-close refresh, three rules pinned in the
  decision (2026-08-12 chat, founder + advisor): (1) the snapshot ships a
  public-tuned workflow containing ONLY the secret-free lanes — the offline
  suite and the database lane, which run a runner-local Postgres with a
  deliberately worthless credential; (2) the trimmed workflow is proven
  green in the PRIVATE repo once before it ships — a never-run workflow
  failing its first public run would put a day-one red on the fresh
  snapshot in front of exactly the audience the refresh is for; (3) the fix
  lives in the snapshot preparation in the private repo, never hand-edited
  into the public one — the mirror is one-way and a hand edit dies at the
  next force-push (the [[B-GAE-025]] lesson, applied to workflows).
- **Guard:** shipped at the close (wording corrected by the close audit —
  this field said "none yet" after the guard existed): `tests/test_public_workflow.py`
  holds the allowlist shut — exactly two jobs, no secret/WIF/deploy/write
  permission by raw-text scan, a control proving the scanner still bites the
  private deploy workflow, and a build test reading what `.github/workflows`
  actually ships. The entry stays OPEN only for the verification the fix
  exists to produce: the public repository's own Actions run going green.
- **Could it return?** **MEDIUM.** The class is "the snapshot ships a file
  whose behaviour differs where credentials differ", and workflows are just
  its loudest member. Without the allowlist guard, the next private job
  with cloud credentials rides straight back into the snapshot. It surfaces
  next at the first snapshot refresh after any CI change.

### B-GAE-044 · The close's own record states times and numbers its commits contradict
- **Phase:** 9 — independent close audit, 2026-08-12. Fixed the same day, at
  the founder's push order.
- **Found by:** reading timestamps against `git log` instead of accepting
  them. All 12 close commits landed **15:56–17:22 BST on 2026-08-12**, and the
  audit began at 17:33 the same day. Yet the decision log's close entry says
  "Built 20:00–23:30 BST" with per-decision times up to 22:50; the progress
  log's close line is stamped "2026-08-12 23:30 BST" in a commit made at
  16:23; and CLAUDE.md says "Applications so far: 0 (measured 2026-08-12
  23:30)" in a commit made at 16:33. D-GAE-072's stated decision time (20:20)
  postdates the commit implementing it (15:56) by four and a half hours. The
  relay adds two stale numbers: "946 passed / 65 skipped" for the snapshot
  lane, superseded by the close verification's own 953 / 65 thirty-six
  minutes after the relay shipped, and "8 commits ahead" written in what
  landed as the tenth commit.
- **Cause:** clock-time decoration written as if measured, and mid-close
  measurements shipped in the relay without a final re-measure — in a project
  whose standing rule is "any number you state about a repo is measured in
  that session or not stated". Either the prose times or the commit stamps
  are false; they cannot both be true, and the log ships publicly while the
  private history that contradicts it does not.
- **Fix:** done at push time, same session: the decision-log window now carries
  the commits' own times with the correction stated in place, the seven
  per-decision clock stamps are removed, the progress-log close line is
  restamped 17:10 with a correction note, CLAUDE.md's banner is restamped,
  and the relay's 946/65 and gate wording are refreshed. The correction is
  visible, not silent — each file says it was corrected and cites this id.
- **Guard:** **none — only a human reading prose times against the commits
  can see this**, and nothing re-measures a handoff's numbers at ship time.
- **Could it return?** **HIGH.** Every phase close writes a dated entry, a
  relay table and a CLAUDE.md banner by hand, and nothing compares any of
  them to the clock or to each other. It surfaces next at the Phase 9.5
  close, in the same three files.

### B-GAE-039 · The public README's "how I work" list links to a directory the snapshot deletes
- **Phase:** 9 — the phase-close snapshot refresh, 2026-08-12. Found and fixed
  the same sitting. **It is live in the public repository right now**, and has
  been since the archive left the snapshot on 2026-08-11 (`2da5fdd`).
- **Found by:** re-reading the README as the public repo's first page while
  writing [[B-GAE-036]]'s entry, having just learned that "what the snapshot
  REMOVES" is a class of breakage nobody was checking. Its reviewer-facing list
  offers `docs/claude-md-archive/` as *"the exact build instructions each phase
  ran under"* — a link the scrub deletes on the way out.
- **Cause:** the scrub list and the README are two files edited by different
  hands at different times, and nothing joins them. The archive was removed
  from the snapshot as a deliberate decision (public content is public BY
  DECISION, never by omission — founder call 2026-08-11) and the README line
  advertising it was simply never revisited. The defect exists **only in the
  public copy**: in the private repo the path is there and the link works
  perfectly, which is precisely why a year of looking at it would never find
  it. Same family as [[B-GAE-035]] and [[B-GAE-036]] — a file whose behaviour
  differs where the surrounding tree differs — arriving through the mildest
  possible symptom, a 404 on a portfolio page.
- **Fix:** the line is replaced rather than deleted: the list now offers
  `docs/bug-log.md` (which does ship and is arguably the better exhibit), and a
  sentence says the phase instructions are kept private and why. A dangling
  promise is worse than a stated absence.
- **Guard:** `tests/test_public_workflow.py::test_the_readme_never_links_to_a_path_the_snapshot_deletes`
  — it **parses the scrub list out of `prepare-snapshot.sh`** rather than
  restating it, so adding a fifth scrubbed path automatically starts checking
  the README against it. Seen red naming exactly `docs/claude-md-archive/`
  before the fix. It runs in both checkouts and carries a sanity assertion that
  the parsed list is not empty, since an unparsed list would silently check the
  README against nothing.
- **Could it return?** **LOW for the README** (the guard reads the real list
  and fails loudly) and **MEDIUM for the class**: only the README is checked.
  `docs/dev.md`, `docs/runbook.md`, `plans/*.md` and the logs all ship publicly
  too, and any of them may link to a scrubbed path with nothing noticing. The
  same test widened to every shipped markdown file would close that, and the
  reason it was not widened today is honest rather than principled — the
  README is the file a visitor actually reads first.

### B-GAE-038 · Writing one decision entry deleted the heading of the entry below it, so seven decisions changed owner
- **Phase:** 9 — introduced 2026-08-12 by commit `44431c4` (the task 5 entry),
  found and fixed at the phase close the same day.
- **Found by:** the phase-close pass over the decision log, reading the file
  end to end for the step-1 sweep rather than appending to it. Task 4's seven
  decisions — `create_profile` operator-only, `adopt_owner` as the one
  sanctioned re-scope, intake-v1, the never-echoing channel, M4 stopping at
  six, the Notion deferral, M5 note-only — were sitting under the heading
  **"Task 5: one ledger, two scopes"**, with no date and no title of their own.
- **Cause:** the log is newest-first, so every entry is written by inserting a
  block at the top of the file, above the previous one. The task 5 insertion
  overwrote one line: task 4's `## 2026-08-12 — Task 4: onboarding by
  conversation…` heading. Confirmed by history rather than guessed —
  `git show f107a12:docs/decision-log.md` contains the heading and
  `git show 44431c4:…` does not, so the deletion is pinned to one commit.
  Nothing noticed, because **the decision log had no shape test at all**: the
  bug log has had two since the day it was created, and the older, larger,
  equally public log next to it had none.
- **Fix:** the heading is restored verbatim from `f107a12`, so the ids and
  wording of the seven decisions are untouched — only their title came back.
- **Guard:** `tests/test_decision_log.py::test_no_section_has_swallowed_another_entrys_heading`
  — entries from Phase 9 onward open with a `Built HH:MM–HH:MM` line, so a
  section containing TWO openers is a section that has eaten another entry.
  Seen red naming exactly the task 5 heading before the fix, green after,
  paired with a control asserting the scan can still see the openers at all.
  The file also gained the checks the log should always have had: decision ids
  unique and inside the registry's high-water mark, and the log tracked so it
  ships and stays inside the public-safety scans.
  **The limit, stated rather than glossed:** only three sections carry that
  opener today, so 57 older sections are unprotected. This guard grows as
  entries adopt the convention; it does not cover the log's past.
- **Could it return?** **MEDIUM.** For a Phase 9-style entry, LOW — the test
  fails the moment it happens. For anything written without the opener line,
  unchanged and invisible, which is most of the file. It surfaces next wherever
  someone inserts an entry at the top of a log by hand, which is every log this
  project keeps: `progress-log.md` has no shape test either, and its entries
  are single lines with no opener at all, so nothing there would ever notice.

### B-GAE-036 · The fix for the red X would have re-created it: four tests assert on the deploy workflow the snapshot replaces
- **Phase:** 9 — the phase-close snapshot refresh, 2026-08-12. Found and fixed
  in the same sitting, before anything was pushed.
- **Found by:** building a **trial snapshot into a scratch directory and
  running the suite inside it** — the ritual's own step, done early and for
  practice rather than at the end for ceremony. Not by reading the diff, which
  looked complete: the new workflow was written, its eight guards were green,
  and the private repo's suite passed 953/58. Inside the snapshot: **4 failed**.
- **Cause:** [[B-GAE-035]]'s fix makes `prepare-snapshot.sh` replace
  `.github/workflows/ci.yml` with the two credential-free lanes. Four tests in
  `tests/test_cloud_setup.py` read that exact path and assert on the DEPLOY
  jobs — `google-github-actions/auth@v2`, `needs: [test, changes]`, the
  `deploy:` block's own `cancel-in-progress: false`. In the snapshot those
  strings are gone by design, so the tests fail there. They had been correct
  and stable for a phase; what changed underneath them was the file, not the
  assertion. The class is exactly the one B-GAE-035's could-it-return names —
  *"the snapshot ships a file whose behaviour differs where credentials
  differ"* — arriving from the opposite direction: not a shipped file that
  misbehaves, but a shipped TEST whose subject was taken away. **The public
  repository's first Actions run would have been red again, in the same push
  that was meant to end the red**, and the cause would have looked nothing
  like the original.
- **Fix:** a `private_only` mark, defined once in `tests/conftest.py`, applied
  to the four. The predicate is structural, never a flag or an environment
  variable: *if the workflow this checkout carries already IS the file the
  snapshot installs, this checkout is a snapshot.* Nothing has to be set or
  remembered, and it answers correctly in all three places the suite runs
  (private repo, snapshot, container). One definition, because two copies of
  one predicate is how a mirror starts drifting ([[B-GAE-025]]).
  `test_no_service_account_key_is_ever_exported_anywhere` deliberately keeps
  running in both: it asserts an ABSENCE, which stays true and worth checking
  whichever workflow the file holds.
- **Guard:** `tests/test_public_workflow.py::test_the_snapshot_ships_the_public_workflow_and_nothing_else`
  builds a real snapshot and reads what `.github/workflows` actually contains,
  so the *wiring* cannot silently stop happening — but it does **not** run the
  suite inside the result, and that is the honest gap. What caught this was a
  person running the suite in a trial snapshot, and the only thing making that
  happen next time is the ritual step in `CLAUDE.md` that says to. **A
  documented ritual step is a weaker guard than a test and this entry does not
  flatter it.**
- **Could it return?** **HIGH, and specifically at the next snapshot refresh.**
  Any test that reads a file the snapshot rewrites, or one of the four paths
  the scrub list deletes (`CLAUDE.md`, `PROJECT-MEMORY.md`, `docs/handoffs`,
  `docs/claude-md-archive`), lands in the snapshot as a failure nobody sees
  until the suite is run inside it. Nothing enumerates that set; the scrub list
  and the tests are written in different files by different hands. The cheap
  close, if this recurs: have the guard above run `pytest` inside the snapshot
  it builds, which turns the ritual step into an assertion.

### B-GAE-033 · docs/dev.md is frozen at Phase 7.5 and states the tool count twice, one copy stale
- **Phase:** 9 — task 7, 2026-08-12, found by the runbook builder reading
  dev.md for the operator flows and cross-checking its numbers against
  reality. **RESOLVED 2026-08-12 at the phase close**, which is where its own
  entry said the prose rewrite belonged.
- **Found by:** reading, not a test — which is the whole point. dev.md's
  "### The 45 tools" heading (correct, set in task 4) sits eleven lines under
  "exposes the engine to Claude as **30 tools**" (stale). The "Status
  (honest)" section still reads "Phases 1–7 and 7.5 built and green (351
  offline tests + 10 DB-gated; migrations through 0030; 19 MCP tools); Phase
  8 is the next card. Nothing is committed yet (founder hold)" — every number
  and both claims wrong as of Phase 9 (965 tests, 60 migrations, 45 tools,
  live and deployed). The setup section still calls `GEMINI_API_KEY` "needed
  for JD reading", contradicting the standing invariant that the engine makes
  no AI calls and that key is never set. The Layout section still describes a
  `src/read/` Gemini reader and a Gemini synonym map.
- **Cause:** no test scans dev.md's prose, so its numbers and claims drift
  every phase while the guarded surfaces (README, the tool-count assertions)
  stay honest. It is the same shape as [[B-GAE-029]] — a number stated in two
  places, one copy going stale — but in an internal dev doc rather than the
  public README, which is why the blast radius is smaller and the fix is not
  urgent.
- **Fix:** the "30 tools" line was corrected to "45 tools" on sight at find
  time. The rest was done at the close, taking the **stronger** of the two
  options the entry itself offered — **the counts are deleted, not
  corrected**:
  * "Status (honest)" is **gone**. It restated the phase, the test count, the
    migration number and the tool count, all four wrong, all four owned by
    another file. What replaced it is a table of which file answers which
    question — pointers, which cannot go stale the way numbers do.
  * The two "47 tools" mentions lost their numerals (`### The tool set`), with
    one line saying explicitly that counts live in the README's numbers table
    because a test measures that table against reality.
  * The `GEMINI_API_KEY` line now says *leave it blank*, with the reason and a
    pointer to [[B-GAE-037]] — which is the bug that line's rewrite uncovered.
  * "Layout" was rewritten against a measured `src/` tree (every path in it
    checked to exist): `read/` leads with the deterministic extractor and
    names `gemini.py` as retired-but-present, and the eleven packages added
    since Phase 7.5 — `reading/`, `match/`, `cv/`, `criteria/`, `auth/`,
    `budget/`, `pipeline/`, `mcp_server/`, `status/`, `dashboard/`, `history/`
    — exist in it at last.
  * The dashboard's "three curated views" became four; `v_sponsor_browse`
    joined the allowed set in Phase 8.5 and dev.md never heard.
- **Guard:** two, of different strengths, and the difference is the lesson.
  * **The numbers: structural.** dev.md now contains no build-state count at
    all, so there is no longer a number in it that CAN rot. Deleting the thing
    is a stronger guard than correcting this instance of it.
  * **The Layout: a real test at last.**
    `tests/test_dev_doc_paths.py::test_every_repository_path_dev_md_names_still_exists`
    scans every backticked `src/`, `scripts/`, `db/`, `ops/` or `tests/` path
    the file names — **28 of them, all present** — and fails on any that has
    gone. Seen red for exactly that, against a deliberately inserted
    `src/telepathy/`, and paired with a control asserting the scan still finds
    the Layout at all (a pattern that quietly stops matching would read
    exactly like a clean file). This is the test the entry's own could-it-return
    asked for, written here rather than promised again.
  * **What is still unguarded, stated plainly:** the test checks that a path
    exists, never that the sentence describing it is true. `src/read/` could be
    described as anything and still pass. No test reads prose, and none is
    proposed — the honest limit of a mechanical guard over documentation.
- **Could it return?** **LOW for a stale count** (none are left, and adding one
  would be a deliberate act) and **LOW for a dead path** (the new test fails
  loudly). **MEDIUM for a stale DESCRIPTION** — the rewritten Layout can still
  become wrong about what a module *does* while every path it names continues
  to exist, and that is the half nothing catches. It surfaces next wherever a
  package keeps its name and changes its job.

### B-GAE-032 · The day sign-in goes live, any signed-in stranger can rewrite the sponsor register
- **Phase:** 9 — found in the overnight security sweep, 2026-08-12; **fixed
  2026-08-12 as the first step of task 6**, before a single line of sign-in
  was written. It was never exploitable — sign-in was off and `auth.users`
  held 0 rows, measured — and that is precisely why it had to close first:
  the flip is what makes "authenticated" mean a stranger.
- **Found by:** enumerating `pg_policies` × `has_table_privilege` for every
  role the door and the FUTURE sign-in path can reach, after [[B-GAE-030]]'s
  could-it-return named the class. Measured: `authenticated` holds INSERT,
  UPDATE **and DELETE** on `licensed_sponsors` and UPDATE on
  `skilled_worker_occupations`, AND the genesis-era policies
  (`sponsors_authenticated_all`, `occ_authenticated_all` — `FOR ALL USING
  (true) WITH CHECK (true)`) that let those privileges through RLS. Wider
  still: Supabase's default grants give `anon`+`authenticated` **252**
  INSERT/UPDATE/DELETE table grants across `public` — inert on every other
  table only because no anon/authenticated policy exists there. Re-measured
  at fix time and wider again: the same two roles also held TRUNCATE,
  REFERENCES and TRIGGER on all 42 relations, so the real figure was **504
  write grants**, and TRUNCATE alone would empty a keep-all table without
  touching a policy.
- **Cause:** the four genesis policies predate migration 0001 (created via
  the dashboard when "authenticated" meant nobody, because Auth had no
  users), and Supabase's default privilege grants were never revoked. Task
  2a's RLS work sorted `goal_a_app` policies table by table and never
  revisited the Supabase-native roles — the door that was being secured was
  the MCP one, and the auto REST API's door was out of frame.
- **Fix:** migration **0061**, after verifying three ways that the data API
  serves nothing: no file in the repo names PostgREST, supabase-js or the
  publishable key; `goal-a-mcp` carries only DATABASE_URL and MCP_TOKEN;
  `goal-a-status` carries only DATABASE_URL. It (a) drops
  `sponsors_authenticated_all` and `occ_authenticated_all`, (b) drops the
  two `anon` SELECT policies as a decision rather than as tidying
  (decision-log 2026-08-12 — publishing the register would be defensible;
  publishing it by leftover is not), (c) revokes INSERT/UPDATE/DELETE/
  TRUNCATE/REFERENCES/TRIGGER from `anon`, `authenticated` and PUBLIC on
  every relation in `public`, and (d) sets `ALTER DEFAULT PRIVILEGES` so the
  next table created does not hand them straight back. SELECT grants are
  deliberately left: with RLS on and no policy admitting either role they
  are inert, and the guard below pins the "RLS on" half.
- **Guard:** `tests/test_data_api_lockdown.py` (RUN_DB_TESTS=1), four
  assertions, all three of the first ones seen **red** against the live
  database before 0061 ran — 42 relations × 6 privileges × 2 roles, and both
  FOR ALL policies named. It asserts over classes, never lists:
  `::test_no_supabase_native_role_can_write_any_relation_in_public`,
  `::test_no_policy_admits_a_native_role_to_a_write`,
  `::test_a_table_created_tomorrow_does_not_re_grant_writes_to_them` (the
  default-privileges half — the could-it-return, closed mechanically), and
  `::test_every_table_in_public_still_has_row_level_security_on`, which is
  what makes leaving the SELECT grants honest. Every one carries a control,
  because a probe that returns nothing reads exactly like a locked database.
- **Could it return?** **LOW by our own hand, MEDIUM by Supabase's.** The
  default-privileges revoke covers `postgres`, the grantor for every path
  that creates a table here (MCP migrations, SQL editor, the engine). It
  does **not** cover `supabase_admin`'s own default ACL: `postgres` is
  neither superuser nor a member of that role, so it cannot be altered with
  the credentials this project has — a stated limit, not an oversight. If a
  relation ever appears with native write grants by that route, the live
  all-relations assertion catches it the moment it exists, but only when the
  DB lane is run. It would surface next at any new table created outside our
  migration path, or on a project restore that replays Supabase's defaults.

### B-GAE-031 · The registry was the biggest spender in the system and the only one nobody counted
- **Phase:** 9 — task 5, 2026-08-12. Fixed the same sitting, by the gate this
  task exists to build.
- **Found by:** measuring the ledger before choosing cap numbers rather than
  after. `select source, max(calls), count(*) from api_quota_ledger group by
  source` returned exactly two sources — reed (peak 950 over 11 days) and
  adzuna (peak 240 over 9). Companies House, which the nightly `classify`
  stage calls up to 4,000 times a night, had **zero rows** and always had.
- **Cause:** the ledger arrived in migration 0036 with the *aggregator* raw
  layer, so it was wired into the two clients that layer owned. The registry
  client predates it (Phase 6) and was simply never joined up. Nothing failed,
  which is why nobody looked: `PAUSE = 0.6` keeps the pass under the 600-per-5-
  minute rate limit, so the spend was polite and invisible at the same time.
  The consequence was not overspending, it was **blindness** — had Companies
  House started refusing, `run_classify`'s per-item `except Exception` would
  have written an 'error' card for every remaining organisation in the batch,
  and the run would have reported all-stages-ok with up to 2,000 fabricated
  errors and no clue as to the cause.
- **Fix:** the debit moved to the one place any of the three APIs is actually
  called, so a client cannot be forgotten — it is metered by where it points,
  not by who remembered to wire it. `companies_house` now carries a cap row
  (world 20,000/day, owner 2,000) and every attempt is ledgered.
- **Guard:** `tests/test_budget_gate.py::test_every_ledger_source_is_reachable_from_some_url`
  (a cap with no URL mapping is a budget nobody can spend) and
  `::test_the_registry_client_charges_before_it_calls_out`, plus
  `tests/test_budget_ledger.py::test_the_three_sources_are_seeded_with_caps`.
  The `except Exception` half is closed by
  `::test_the_registry_batch_stops_instead_of_stamping_every_org_an_error`
  and `::test_the_census_sweep_stops_instead_of_carding_every_org_an_error`.
  The second of those was found by re-reading every caller of `enrich_org`
  **after** believing the fix was finished: `discover.sweep.run_sweep` has the
  same per-item `except Exception` and would have carded every remaining
  organisation 'error' — worse than the classify case, because a probe card is
  what stops an organisation being picked again, so the damage would have
  outlived the day that caused it. Four runners needed the same catch, and
  three of them were found only by walking the call graph a second time.
- **Could it return?** **LOW for a new client, MEDIUM for a new source.** A new
  helper pointed at an existing base URL is metered automatically. A genuinely
  new *provider* would not be — `source_for_url` returns None for an unknown
  host and the call passes through free. That is deliberate (board feeds must
  not draw down an aggregator budget) and it is the exact hole this bug came
  through. It would next surface the first time a fourth paid API is added.

### B-GAE-030 · Any key holder could zero the shared quota counter through the door
- **Phase:** 9 — task 5, 2026-08-12, found while deciding the RLS shape for
  the new budget tables. Present in production since migration 0053 (task 2a).
- **Found by:** asking what `app_world_rows` actually grants on the one world
  table that is not reference data. It is `FOR ALL ... USING (true) WITH CHECK
  (true)`, and 0052 had already granted `SELECT, INSERT, UPDATE` on every
  table to `goal_a_app` — so the policy was permissive over a privilege that
  was already there.
- **Cause:** 0053 sorted tables into owner-scoped, derived and *world*, and
  world meant "not anybody's, so readable by every caller". `api_quota_ledger`
  was filed there because it is nobody's — which is true of who it belongs to
  and false of who may write it. It is not reference data, it is a **control
  surface**: `update api_quota_ledger set calls = 0` resets the shared spend,
  and with the cap read from that same counter, a key holder could hand
  themselves an unlimited day, every day. No tool offered it; a key holder
  with a database connection is not the threat model, but a key holder is
  precisely who this policy was written for.
- **Fix:** migration 0060 narrows it to `FOR SELECT` and revokes INSERT/UPDATE/
  DELETE from `goal_a_app` outright. The same shape is applied to the two new
  budget tables from the start. The revoke matters as much as the policy: an
  UPDATE that matches no visible row is **0 rows and no error**, so a policy
  alone would have made the refusal silent instead of loud.
- **Guard:** `tests/test_budget_ledger.py::test_the_door_reads_the_world_ledger_and_can_never_write_it`
  and `::test_an_owner_cannot_forge_their_own_budget_through_the_door` — both
  carry a paired control that writes the same row as the engine role first, so
  what refuses is provably the role and not a broken statement.
- **Could it return?** **MEDIUM.** 0052 grants `SELECT, INSERT, UPDATE` on
  **future** tables to `goal_a_app` by default, so the next control-surface
  table is writable through the door on the day it is created unless somebody
  remembers to revoke. Nothing tests for that class — `test_rls_cutover.py`
  checks the engine has the privileges it needs, which is the opposite
  question. It would next surface in task 6, where sign-in makes the set of
  key holders open-ended.

### B-GAE-029 · The public README advertises a test count that is two tasks stale, and its guard cannot see it
- **Phase:** 9 — task 5, 2026-08-12, found in the step-0 verification of task 4
  (the builder was not the verifier), before any of task 5 was written.
- **Found by:** grepping the README for every number rather than trusting the
  one the test checks. The numbers table says **934**; the Quick start block
  eleven lines lower says **913**. Both are in the file that ships to the
  public repository.
- **Cause:** the README states the test count in **two** places, and
  `test_the_readme_test_count_matches_reality` asserts
  `f"**{collected}**" in readme or f"{collected} tests" in readme` — an **OR
  over presence**. Presence of the right number anywhere satisfies it, so the
  second, wrong number is invisible to the guard. `913` entered at Task 3
  (commit `0c759ec`) and survived Task 4's update of the table because only
  the table was updated. This is the "tests that cannot fail" shape from a new
  angle: the assertion is not weak about *its* claim, it is weak about
  **absence** — it can prove a number is present and can never prove a stale
  one is gone.
- **Fix:** the Quick start line stops carrying a number at all (one place in
  the file owns the count — the numbers table), and the guard gains a second
  assertion: every `NNN tests` string in the README must equal the collected
  count.
- **Guard:** `tests/test_public_safety.py::test_the_readme_states_one_test_count_and_it_is_the_real_one`
  — scans **every** `\d+ tests?` occurrence and fails on any that is not the
  measured number. Seen red against the 913 line before the line was changed.
- **Could it return?** **LOW** for the test count specifically — the new
  assertion is over all occurrences, so a second stale copy fails loudly.
  **MEDIUM** for the two neighbouring numbers: migrations (**59**) and tools
  (**45**) are still checked only by the retired-claim blocklist, which lists
  the *old* wrong values ("34 migrations", "24 tools") and so can only catch
  the drift that already happened once. The next place this surfaces is the
  public snapshot at any phase close where migrations or tools change and only
  one of the two mentions is updated.

### B-GAE-028 · One owner's apply-window silently sets every owner's deadlines
- **Phase:** 9 — task 3, 2026-08-12, found in the same read as [[B-GAE-027]].
- **Found by:** reading `scripts/enrich_deadlines.py` line by line for owner
  dependence, on the assumption that a stage with no `--owner` flag might
  still contain a per-owner read. It did.
- **Cause:** `select apply_window_days from profiles order by created_at
  limit 1` — the `default_profile_id` pattern open-coded, so it is invisible
  to any search for that helper's name. `apply_window_days` is a per-owner
  column (`profiles`, default 21); the flat fallback deadline it feeds is
  written to `role_listings.deadline`, which every owner's queue reads. A
  second owner with a 7-day window would silently get owner A's 21-day
  estimates on their own listings — wrong dates, presented with the same
  confidence as the stated ones, on the field the nudge prints as "apply by".
  No leak, no error: just quietly wrong advice, which is the harder kind to
  notice.
- **Fix:** the stage takes `--owner` and reads that profile's window, and
  scopes the rows it updates to that owner's listings through the
  `role_listings → target_companies.owner_id` seam. Measured before relying on
  the seam: 894 companies, **0 with a null owner**, and 0 of 12,923 listings
  unreachable by it (2026-08-12) — so for one owner the scoped set is the
  whole set and tonight's output is unchanged.
- **Guard:** two, because the bug and its class are different things.
  `tests/test_per_owner_isolation.py::test_each_owner_gets_their_own_apply_window`
  runs the real stage per owner against a two-owner scratch schema and asserts
  the deadlines land 21 and 7 days out respectively — the bug itself. The
  class guard is
  `test_no_stage_script_open_codes_the_first_profile_lookup`, which scans every
  file in `src/` and `scripts/` for `from profiles order by created_at limit 1`
  and allows it only in `criteria/loader.py`, where it belongs. That scan reads
  **code with docstrings and comments stripped**, because its first run flagged
  the paragraph in `pipeline/owners.py` explaining this very bug; string
  literals are kept, since the pattern lives inside SQL. It carries its own
  control — `test_the_first_profile_scan_still_catches_the_code_it_was_written_for`
  — so a scan that quietly stops matching fails instead of passing.
  **How the red was obtained:** measured against unmodified HEAD (397c596) by
  the same probe as [[B-GAE-027]] — it reported the stage using **window=21
  (owner A's) for every listing while owner B's own window was 7**, i.e. B's
  advertised "apply by" dates 14 days late.
- **Could it return?** **HIGH for the class, and the class is the finding.**
  This one hid from `grep default_profile_id` because it was open-coded, and
  nothing currently searches for the *pattern* rather than the helper name.
  `order by created_at limit 1` over `profiles` is the real signature, and it
  appears in `criteria.loader.default_profile_id` legitimately. Until a test
  scans `src/` and `scripts/` for that shape outside the one place it belongs,
  the next open-coded copy lands the same way — and it will look like a
  three-line convenience, not a defect.

### B-GAE-027 · The nightly personal pass would have nudged one owner's phone with another owner's queue
- **Phase:** 9 — task 3, 2026-08-12, found while reading the seven personal
  stages before splitting them. **Logged at find-time; being fixed in the same
  sitting** — this is the defect task 3 exists to remove.
- **Found by:** reading `ELIGIBLE_SQL` against the column list of the view it
  queries, rather than trusting the stage that consumes it. `v_apply_queue`
  carries `owner_id`; `ELIGIBLE_SQL` names no owner at all.
- **Cause:** the whole personal half of the loop was written when one profile
  was the only possibility, so it resolves its owner **once, blind**, and
  selects its work **unscoped**. Two independent halves of the same mistake:
  * `notify.nudges.nudge_stage` selects every eligible row in the table via
    the ownerless `ELIGIBLE_SQL`, then sends the digest to
    `load_channel(default_profile_id(cur))` — the *first* profile by
    `created_at`. With a second owner this pushes owner B's companies, titles
    and salaries to owner A's phone, and then `mark_nudged` stamps every one
    of those rows, so **owner B is never nudged for them at all**. The stamp
    makes it silent as well as wrong.
  * `cv.filing.run_filing_stage` reuses the same `ELIGIBLE_SQL` and the same
    blind `default_profile_id`, so owner B's listings are filed as cards on
    owner A's Notion board — with CVs built from owner A's `cv_blocks`. The
    per-owner column `profiles.notion_token_ref` already exists and was never
    read; the stage uses the single global `settings.notion_database_id`.
  Neither is reachable today: `select count(*) from profiles` = 1 (measured
  2026-08-12), which is exactly why it survived task 1b's sweep — that sweep
  scoped the tools a key holder can call, and **the nightly job calls none of
  them**. It is the same shape as [[B-GAE-017]] in a place nobody thought to
  look: a per-owner value read blind, in code no MCP tool touches.
- **Fix:** the personal pass takes its owner as an argument instead of
  discovering one. `nudge_stage(cur, send, owner_id=…)` and
  `run_filing_stage(cur, settings, owner_id=…)` are required-owner calls;
  `ELIGIBLE_SQL` gains `where q.owner_id = %s`; `scripts/run.py` supplies the
  owner per iteration of the per-owner loop. `default_profile_id` stays only
  as the stdio/local fallback it was demoted to in task 1.
  **The filing half is fixed only as far as it honestly can be.** Scoping the
  row selection stops the stage mixing owners, but it cannot make a shared
  board private: there is one Notion credential in the environment and it
  opens one person's board. So filing now RUNS for the owner that credential
  belongs to and **refuses, with a reason, for everyone else** — rather than
  writing their cards somewhere they can never read them. Per-owner Notion
  (`profiles.notion_token_ref`, a column that exists and is read by nothing —
  measured 2026-08-12) is task 4's onboarding work.
- **Guard:** `tests/test_per_owner_isolation.py::test_owner_bs_roles_never_reach_owner_as_nudge`
  — two owners with their own companies and listings in a scratch schema,
  asserting A's digest contains none of B's roles and that B's rows are left
  unstamped for B's own pass. Paired with offline guards that fail if either
  stage is called the old ownerless way, and with
  `tests/test_two_owner_night.py`, which drives the real stage table through a
  two-owner night.
  **How the red was obtained, since the fix makes the honest red impossible:**
  adding a required `owner_id` means the old code cannot be called the new
  way, so the guard against the pre-fix source would have failed with a
  `TypeError` — which proves nothing about leaking. Instead the defect was
  *measured*: a probe ran the unmodified HEAD (397c596) `nudge_stage` the way
  `scripts/run.py` called it, against a two-owner scratch schema. It reported
  **owner B's role delivered to owner A's channel, and owner B's listing
  stamped `nudged_at` by owner A's pass**. Both halves reproduced; the guard
  asserts their absence.
- **Could it return?** **MEDIUM.** The class guard is weak in one direction:
  `ELIGIBLE_SQL` is a shared constant read by two stages, so a third consumer
  would inherit the scoping for free — but a *new* stage that writes its own
  query gets nothing from this fix. Where it shows up next is any stage added
  to the personal half that resolves an owner itself instead of accepting one,
  and the only thing standing against that today is the required-argument
  signature: a stage that calls `default_profile_id` directly still compiles.
  The filing refusal is the weaker half and should be treated as a **deferral,
  not a fix** — it is one `if` and the day task 4 gives each owner their own
  Notion token, that `if` has to be replaced rather than deleted, or the second
  owner's cards go to the first owner's board the moment the guard comes out.

### B-GAE-026 · Two database tests passed because their hand-written tables invented a schema the database does not have
- **Phase:** 9 — infra sitting, 2026-08-11. Found and fixed in the same sitting,
  while converting the last ten hand-written scaffolds for the A3 guard.
- **Found by:** converting `create table x (...)` to
  `create table x (like public.x including all)` and running the result. Not by
  reading either test — both read perfectly well, and both had been green for
  months. This is the [[B-GAE-022]] lesson repeating: the conversion is what
  surfaces the defect, and each fix uncovered the next one underneath it.
- **Cause:** two instances of one mechanism — a scaffold that is not a copy but
  an *invention*, so the test asserts against a shape production does not have.
  1. `tests/test_discover_register.py` declared `licensed_sponsors` with
     `rating text, org_name_norm text, is_skilled_worker boolean` as plain
     columns and inserted values into all three. On the real table **all three
     are GENERATED ALWAYS**, and the column they are generated FROM —
     `type_rating`, which is NOT NULL — did not exist in the scaffold at all.
     `id` was declared a plain `bigint` where the real column is
     `GENERATED ALWAYS AS IDENTITY`. So the one test covering
     `find_candidate_sponsors` could never have caught a B-GAE-013-style write
     to a generated column on that path, and would still have passed if the
     function had been changed to read `type_rating`.
  2. `tests/test_queue_views_db.py` declared `role_listings.role_status` with
     `default 'open'`. **The real table has no default for it.** The view's very
     first condition is `r.role_status = 'open'`, so that invented default was
     the entire reason those six queue tests ever saw a row — against the real
     table every seeded row arrived NULL and `v_apply_queue` came back empty.
     Its seed also used positional `insert ... values`, which is what made the
     scaffold unconvertible without rewriting it.
- **Fix:** both files copy the real tables with `LIKE ... INCLUDING ALL`. The
  register seed inserts raw facts only and lets the database derive the three
  generated columns — which required using a REAL register phrasing
  (`'Worker (A rating)'`), because `rating` is generated by a LIKE over
  `'%(A %'`/`'%(A)%'`/`'%A rating%'` and a tidy-looking `'A (Premium)'`
  generates NULL. Every insert now names its columns, with
  `OVERRIDING SYSTEM VALUE` where a real primary key is an identity column and
  the assertions are about which id came back. `role_status` is stated per row,
  as production code states it.
- **Guard:** `tests/test_scratch_schema_scaffolds.py` — the A3 class guard, and
  the reason this was found at all. Four assertions: no test hand-writes a table
  that exists in `public`; a LIKE names the same table it imitates; `INCLUDING
  ALL` is not quietly downgraded to a bare `LIKE` (which copies types but no
  defaults, generated expressions or checks — exactly the blind spot); and a
  control that the scan still sees the 28 real tables and 20 copies, so it
  cannot pass by finding nothing. Each seen red under a deliberate mutation.
  **Also caught in its own writing:** the first version failed on itself,
  because it quotes the forbidden spelling as documentation and a text scan
  cannot tell an example from an offence — the [[B-GAE-009]] shape.
- **Could it return?** **LOW for a hand-written table, MEDIUM for the class.**
  The guard makes a new hand-written scaffold fail immediately, and it is a test
  rather than a sentence. What it does **not** check is whether a LIKE copy's
  *seed* is realistic: nothing stops a future fixture inserting
  `type_rating = 'A (Premium)'` and quietly getting `rating = NULL`, or omitting
  a column that has no default and reading the resulting NULL as data. That is
  the same family and it needs a real assertion about the rows, not the schema.

### B-GAE-018 · One tenant silently swallows another's job listings — `dedupe_key` was global
- **Phase:** 9 — found 2026-08-11 in task 2a's security review, fixed
  2026-08-11 at the top of task 3, which is where its entry said the repair
  belonged.
- **Found by:** the `security-review` skill, run adversarially against the RLS
  migrations, asking what a second tenant's merge would actually do.
- **Cause:** `_ensure_company` is correctly owner-scoped — each owner gets
  their own `target_companies` row — but `dedupe_key(company_name, title, url)`
  contains no owner and no company_id, and its unique index was global. So
  `on conflict (dedupe_key) do nothing` meant whichever owner merged an ad
  FIRST created the listing; the second owner's identical ad fell through to
  the `select role_id ... where dedupe_key = %s` fallback and was handed **the
  first owner's role_id**, stamped into their `aggregator_ads.merged_role_id`.
  The second owner never received the job at all. After the 2b cutover the same
  fallback would have run as `goal_a_app` with the other owner's
  `app.owner_id`, found nothing, and killed the nightly `merge` stage on a
  `None` subscript.
- **Fix:** migration **0058** replaces the global unique index with
  `UNIQUE (company_id, dedupe_key)`, and **all three** callers were scoped in
  the same change — `discover/merge.py` (conflict target and the fallback
  lookup), `persist/fetch_rules.py` (conflict target), and `history/events.py`,
  whose `dedupe_key -> role_id` map could otherwise attach one owner's event to
  another owner's listing. `record_events` takes `company_id` as a REQUIRED
  argument: a default would have let every existing caller keep the old wrong
  behaviour silently.
- **Guard:** `test_two_owners_merging_the_same_advert_each_get_their_own_listing`
  (`RUN_DB_TESTS=1`) — two real owners, one advert, against the real table.
  Seen red for exactly the documented symptom ("the second owner was handed the
  first owner's role_id") before the fix. Paired with
  `test_one_owner_still_cannot_hold_the_same_advert_twice`, because scoping the
  key must not stop it deduping within a company, which is the reason it
  exists. **No fake could ever have caught this** — a `FakeCursor` has no unique
  index, which is why all eleven offline merge tests passed throughout.
- **Could it return?** **LOW for this table, MEDIUM for the pattern.** The
  paired tests fail if either half regresses. But `dedupe_key` is also used by
  `census_jobs`, whose unique index is still global — harmless today because
  the census is world data owned by nobody, and it becomes a bug the moment
  anything per-owner is keyed off it. Nothing checks that.

### B-GAE-023 · The task-2b cutover killed `submit_reading` — the app role holds no DELETE, and the reading tray needs one
- **Phase:** 9, task 2b — 2026-08-11. Found and fixed inside the cutover
  sitting, before the change was committed: it never reached production.
- **Found by:** grepping `src/` for `DELETE` while asking what the new role
  cannot do — **not** by the suite, which was fully green (868 collected) with
  this break present. No offline fake enforces a privilege, and no test drives
  a write tool against a real table, so nothing in the repo could see it. A
  read-only live smoke of all 19 read tools passed too; only the write path
  was affected.
- **Cause:** `goal_a_app` was created with `SELECT, INSERT, UPDATE` and
  deliberately **no DELETE, ever** (0052), so that "keep-all tables never lose
  rows" is a privilege rather than prose. But `src/reading/accept.py:105` runs
  `delete from role_skills where role_id = %s` — a *replace* of derived rows;
  its own comment calls it "the upgrade, not an accumulation" — and
  `submit_reading` reaches it through `loop_tools`. Under the app role this
  raises `InsufficientPrivilege: permission denied for table role_skills`,
  confirmed by running the statement as the role in a rolled-back transaction.
- **Fix:** migration **0057** grants DELETE on `role_skills` and on nothing
  else — the founder's call, asked because it edits a security property he
  set in 2a. `role_skills` is derived and rebuilt from the job description on
  every read, so this narrows the rule to the keep-all tables it was written
  for rather than loosening it. Deliberately NOT added to 0052's
  `ALTER DEFAULT PRIVILEGES`: a table created tomorrow must not inherit a
  delete grant by accident. The rejected alternative — a `SECURITY DEFINER`
  function making the delete owner-checked — is tighter and is worth
  revisiting if a second table ever needs this.
- **Guard:** `test_the_app_role_holds_every_privilege_the_engine_actually_uses`
  scans `src/` for every `INSERT`/`UPDATE`/`DELETE` and asserts
  `has_table_privilege` for each real table, so the NEXT missing privilege
  fails loudly instead of shipping. Seen red naming exactly
  `['DELETE on role_skills']` before 0057. Paired with
  `test_the_reading_tray_can_replace_its_derived_skill_rows`, which runs the
  precise statement `accept.py` issues, as the role, and rolls back.
- **Could it return?** **MEDIUM** — the class guard covers table privileges,
  which is the shape that bit here. It does **not** cover sequences, functions
  or anything reached through dynamic SQL the regex cannot see, and it still
  proves nothing about whether a write tool WORKS end to end — that gap is
  [[B-GAE-016]], still open. It would return as a green suite and a dead tool,
  which remains this project's worst pairing.

### B-GAE-022 · The census scaffold was two migrations stale, and the second defect was hiding behind the first
- **Phase:** 9 — 2026-08-11, found while fixing [[B-GAE-019]] at the task-2b
  sitting's open.
- **Found by:** reading the live schema before applying 019's named one-line
  fix, instead of applying it and trusting the green tick — a column-by-column
  comparison of `public.census_jobs` against the test's hand-written
  `CREATE TABLE`.
- **Cause:** the same scaffold drift as [[B-GAE-015]] and [[B-GAE-020]], but
  **masked by another bug**. `insert_census_jobs` writes `is_local`, a column
  Phase 8.5 added and the scratch table never had; 019's `TypeError` aborted
  the call before any SQL was sent, so the missing column could not surface.
  Applying 019's fix exactly as its entry described would have converted a
  `TypeError` into an `UndefinedColumn` — a second red, from a defect that had
  been sitting underneath the first the whole time. The sibling
  `target_companies` scaffold in `tests/test_discover_onboarding.py` was found
  eight columns stale in the same sweep, latent only because that test happens
  to write none of them.
- **Fix:** both census tables converted to
  `create table … (like public.… including all)`. `LIKE` does not copy foreign
  keys, so `census_jobs`' FK to `sponsor_census` is re-added explicitly —
  without that, the test's `ForeignKeyViolation` assertion would have silently
  stopped asserting anything, which is its own [[B-GAE-004]].
- **Guard:** the LIKE itself, for these tables. **Nothing generic.** The honest
  answer is that this was found only because a human read the schema rather
  than trusting a green tick, and no test enforces that. The A3 rule
  (LIKE-only test tables) would close the class; it is still a sentence in a
  document, which is a weaker guard than a test and this log should not
  flatter it.
- **Could it return?** **HIGH** — fixing one error can uncover a second, and
  nothing here checks that a scaffold still matches the table it imitates. It
  returns at the next migration that adds a column to any table a test still
  hand-writes, and stays invisible until someone runs the opt-in lane.

### B-GAE-021 · The mint script demanded a database before it read its arguments — so its refusal test failed only where there is no `.env`
- **Phase:** 9 — found 2026-08-11 by the independent verifier's container gate;
  fixed 2026-08-11 at the task-2b sitting's open. **This also solved the CI
  mystery:** run #28 for `3786a79` DID run, and failed in 60s on its
  offline-suite step with exit 1 — this same test. CI checks out the repo with
  no `.env`, exactly like the container. The overnight "CI never woke" reading
  was wrong: the watchers polled for the *deploy*, which a red suite correctly
  never produced, and so could not see a fast failure. One bug, three
  environments; the laptop alone was masked by its `.env`.
- **Found by:** the independent verifier running CI's own command by hand —
  `docker run --entrypoint python <image> -m pytest`. On the laptop the suite
  passed (837/28); inside the image
  `test_minting_without_a_label_is_refused` failed.
- **Cause:** `main()` entered `get_conn()` — which loads config, and config
  raises `RuntimeError: DATABASE_URL is not set` — BEFORE the `--label` check
  nested inside that `with` block. The image carries no `.env` **by design**,
  so the container never reached the label-refusal path the test asserts. The
  same environment-blindness family as [[B-GAE-004]]'s container-fatal `.venv`
  paths.
- **Fix:** the ordering, not the test. The usage check moved above
  `get_conn()`, so a malformed command is refused before any environment is
  read — an operator should not need a database to be told the command is
  malformed. A monkeypatched `DATABASE_URL` in the test would also have gone
  green, and would have papered over exactly this.
- **Guard:** `test_a_usage_error_is_refused_before_any_environment_is_read`
  monkeypatches `get_conn` to raise, so it fails the instant anything reaches
  the database first — **and it fails on the laptop**, which is precisely what
  the older test could not do. Seen red for that reason before the fix. Behind
  it: CI's "suite must be green INSIDE the container" step, and the no-`.env`
  clean-copy lane, which was re-run with the fix reverted and reproduced both
  failures.
- **Could it return?** **MEDIUM** — the guard covers this one script. Any other
  operator script that loads config before parsing its arguments repeats it,
  and nothing scans `scripts/` for config loads that precede validation.

### B-GAE-020 · The onboarding DB test hand-wrote `review_items` — without the `owner_id` the new code writes
- **Phase:** 9 — found 2026-08-11 in the pre-push verification of tasks 1b/2a;
  fixed 2026-08-11 at the task-2b sitting's open.
- **Found by:** the independent verifier running the FULL suite with
  `RUN_DB_TESTS=1` before pushing — the lane CI does not run.
- **Cause:** `tests/test_discover_onboarding.py` built its scratch
  `review_items` from a hand-written column list predating migration 0056;
  `src/review.py` writes `owner_id` (the [[B-GAE-017]] fix), so the insert died
  with `UndefinedColumn`. **The live table was correct** — verified by query —
  the defect was the scaffold. Exactly the leftover [[B-GAE-015]] named: "one
  `CREATE TABLE` in a test remains hand-written elsewhere in the suite."
- **Fix:** `create table review_items (like public.review_items including all)`,
  the 015 shape. Its two siblings in the same statement, `target_companies` and
  `mcp_audit`, were converted in the same pass rather than left to become the
  next instance — see [[B-GAE-022]] for what that sweep turned up.
- **Guard:** the fix is its own guard for these three tables: a LIKE cannot
  drift. Seen red for the exact `UndefinedColumn` before the fix, green after.
- **Could it return?** **MEDIUM** — not in this file, but the class is closed
  only where LIKE has actually been applied. The A3 rule and the A1 CI
  real-database lane remain the class guards, and both are still queued.

### B-GAE-019 · The census DB test called `insert_census_jobs` with its pre-8.5 signature
- **Phase:** 9 — found 2026-08-11 in the same verification run; fixed
  2026-08-11 at the task-2b sitting's open.
- **Found by:** the same independent-verifier `RUN_DB_TESTS=1` run.
- **Cause:** `insert_census_jobs` gained a `local_matcher` argument in Phase
  8.5's owner-lens work; `test_census_tables_constrain_and_dedupe` still called
  the old shape and died with `TypeError` before touching a row. CI runs
  offline-only, so the opt-in test drifted silently — [[B-GAE-015]]'s mechanism
  in a different file. Red since 8.5 task 2 landed.
- **Fix:** pass the matcher the call was missing —
  `lambda title: True, lambda location: True`. On its own this was **not**
  enough to make the test pass; the drift underneath it is [[B-GAE-022]].
- **Guard:** the test itself, now that it can actually run — seen red for the
  `TypeError`, red again for [[B-GAE-022]], then green. Nothing stops the next
  signature change doing this again: the caller is a test, and no CI lane runs
  it.
- **Could it return?** **HIGH for the class until the A1 CI database lane
  lands** — "the suite is green" and "every test passes" are still not the same
  sentence in this repo. It returns wherever an opt-in DB test calls a function
  whose signature moves.

### B-GAE-017 · `promotion_review` flags leaked one owner's private lens, and anyone could dismiss them
- **Phase:** 9 — 2026-08-11, found by the security review and fixed the same
  sitting rather than deferred to task 3, because the task-1b fuse is out and
  this was reachable the moment a friend key existed
- **Found by:** the `security-review` skill, adversarially — it checked the
  premise behind a recorded decision instead of accepting it
- **Cause:** task 1b recorded, deliberately, that `review_items` is world data
  because all four kinds are "ambiguities about PUBLIC facts". True of
  `skill_synonym`, `sponsor_match` and `company_onboard`. **False of
  `promotion_review`**, whose evidence is built from the owner's own lens:
  `matched_industry_codes` is the intersection with THEIR
  `promotion_rules.industry_codes`, `min_local_jobs` is THEIR threshold, and
  `matched_titles` are census titles matched against THEIR `target_roles`.
  All 20 rows carried both. `list_flags`/`resolve_flag` took no owner, and
  0053 had put the table on the `USING (true)` world list, so RLS would not
  have caught it after cutover either.
- **Fix:** migration **0056** gives `review_items` a NULLABLE `owner_id` —
  NULL meaning "about a public fact, shared by everyone", a value meaning
  "derived from one person's lens" — backfills the promotion_review rows,
  and replaces the open policy with owner-or-world on read AND write.
  `add_flag`/`list_flags`/`resolve_flag` take an owner; the promotion-review
  **cap is now per-owner too**, since a shared cap let one person's unresolved
  flags hold everyone else's promote pass shut. The idempotency key gained the
  owner as well, or the first person to flag an organisation would silently
  suppress everybody else's flag for it.
- **Guard:** `tests/test_review.py::test_owner_b_cannot_read_or_dismiss_owner_as_promotion_flags`
  — two owners in a scratch schema, proving B is refused A's flag on read and
  on dismissal, and that A's flag does not suppress B's for the same
  organisation. Seen red for the dismissal case against the unscoped source.
  Plus offline guards that fail if either function is called the old
  ownerless way.
- **Could it return?** **MEDIUM**, and the lesson outlives the bug: **the
  decision was recorded honestly and its premise was still wrong.** "Measured,
  then decided" protects against forgetting, not against measuring the wrong
  thing — the four kinds were counted, and what their evidence CONTAINED was
  never looked at. The next place that shape bites is any other table declared
  "world data" by kind rather than by content; `mcp_audit` and `pipeline_runs`
  are both on that list today and both are named for task 3.

### B-GAE-014 · `add_cv_block` could never write a block — an untyped `coalesce` against `'{}'`
- **Phase:** 9 — 2026-08-11, while the founder was using the tool for real
  (adding his daily-study fact and eight facts extracted from the CalmLine
  repo). Shipped in Phase 8.5's U8b the day before and **live-broken from its
  first commit**: the tool has never written a single row.
- **Found by:** the founder's own use over the hosted MCP. Four `add_cv_block`
  calls returned `DatatypeMismatch`. A rolled-back probe then proved it fails
  with `skill_norms=None` too — so it was not a skills bug, it was total.
- **Cause:** the insert wrote `coalesce(%s,'{}')`. Both operands are untyped —
  the parameter carries no cast and `'{}'` is an untyped literal — so Postgres
  resolves the whole expression as `text`, and `cv_blocks.skill_norms` is
  `text[]`. It fails at **parse** time, which is why the value passed made no
  difference: no list, no string, and no `NULL` could ever have worked.
- **Fix:** `coalesce(%s::text[],'{}')`. One cast, in `src/cv/blocks.py`.
- **Guard:** `test_add_cv_block_actually_lands_a_row_in_a_real_cv_blocks`
  (RUN_DB_TESTS=1) — runs the real function against `create table (like
  public.cv_blocks including all)` and asserts a row exists with its skills
  intact. Seen red for exactly this `DatatypeMismatch` before the fix. The
  offline test could not have caught it and **no rewrite of it could**: a
  `FakeCursor` has no column types, so it asserts the SQL *string* and is
  blind to what Postgres would do with it.
- **Could it return?** **HIGH** for the class. This is [[B-GAE-013]] again,
  one day later, in the sibling writer — `add_skill` written by the same hand
  in the same phase, both fully covered offline, both dead on arrival, both
  found only when a human tried to use them. **Two of the four U8b writer
  tools were broken and the suite was green.** Nothing scans for SQL that
  never meets a real table. The next places it surfaces are the remaining
  never-executed writers — `confirm_cv_block` and `retire_cv_block` are
  simple `UPDATE`s and were exercised live here, but **task 4's onboarding
  writes (`create_profile`, `target_roles`) are the same shape and have the
  same offline-only coverage today**.

### B-GAE-015 · A hand-written test table drifted from the schema, and only the opt-in suite could see it
- **Phase:** 9 — 2026-08-11, found while proving [[B-GAE-014]]'s fix
- **Found by:** running `tests/test_cv_blocks.py` with `RUN_DB_TESTS=1`.
  Verified against clean `HEAD` (`git stash`) — the failure predates this
  session's changes.
- **Cause:** `test_load_cv_blocks_against_a_seeded_slice` built its scratch
  table with a hand-written `CREATE TABLE` listing ten columns. Migration
  **0049** added `retired_at` and `source`, and `load_cv_blocks` began
  filtering on `retired_at is null` — so the query hit a column the test's
  table had never had. It has been failing since 0049 landed.
- **Why nobody saw it:** the test is opt-in (`RUN_DB_TESTS=1`) and CI runs
  offline, so the phase closed green with this red underneath it. **"The suite
  is green" and "every test passes" were not the same sentence** and no one
  had reason to notice.
- **Fix:** `create table cv_blocks (like public.cv_blocks including all)` —
  the same shape [[B-GAE-014]]'s new guard uses. A LIKE cannot drift.
- **Guard:** the fix is its own guard for this table. Nothing automatic covers
  the general case: **any other hand-written test table can drift the same way
  and stay invisible while CI is offline-only.** Honest answer — the only
  thing preventing a repeat elsewhere is this log entry.
- **Could it return?** **MEDIUM.** One `CREATE TABLE` in a test remains
  hand-written elsewhere in the suite, and the opt-in DB lane is not run by
  CI, so a drift there is silent by construction. It surfaces the next time
  someone runs `RUN_DB_TESTS=1` after a migration — i.e. rarely, and long
  after the migration that caused it.

### B-GAE-013 · `add_skill` could never add a skill — it wrote to a GENERATED column
- **Phase:** 9, task 2's opening audit — 2026-08-11. Shipped in Phase 8.5 and
  live-broken ever since
- **Found by:** auditing every INSERT into the owner-scoped tables before
  dropping their `owner_id` DEFAULTs — the column list named `skill_norm`,
  which the schema generates
- **Cause:** `my_skills.skill_norm` has been `GENERATED ALWAYS AS (lower(…))
  STORED` since migration **0001**, so naming it in an INSERT raises
  `GeneratedAlways` outright. `criteria.writer.add_skill` computes the norm in
  Python — correctly, for the UPDATE's `WHERE` and for its return value — and
  then also passed it as an insert parameter. The update-then-insert shape hid
  it perfectly: updating an EXISTING skill never reaches the insert, so the
  founder's own use never failed. Only a genuinely new skill did.
- **Fix:** the insert writes raw facts only and lets the database compute
  `skill_norm`, the same rule `licensed_sponsors` already follows.
- **Guard:** two, at different levels.
  `test_add_skill_leaves_the_generated_column_to_the_database` (offline)
  forbids the column name; `test_add_skill_actually_lands_a_row_in_a_real_my_skills`
  (RUN_DB_TESTS=1) runs the real function against a real copy of the table and
  asserts a row exists and that the database's normalisation equals `norm()`'s.
  The offline one alone would not have caught this and no rewrite of it could.
- **Could it return?** **MEDIUM** for this class, and it is the sharpest
  illustration in the log of why: **three offline tests covered `add_skill`
  and one of them actively pinned the bug in place** by asserting the
  normalised value appeared among the insert parameters — coverage that could
  only pass while the defect existed (the B-GAE-004 shape, again). Seven
  generated columns exist across four tables; nothing scans for code writing
  to one. The next place it surfaces is **task 4**, where onboarding a new
  user means EVERY skill is new, so `add_skill` fails 100% of the time — the
  bug's blast radius was zero for a single established user and total for the
  second one.

### B-GAE-012 · A tool promised `channel_set` and returned `channel_configured`
- **Phase:** 9, task 1b — 2026-08-11
- **Found by:** reading `send_test_nudge` while giving it an owner; no test
  covered it, because every test asserted against the implementation's key
- **Cause:** the tool's docstring — which IS the contract a client AI reads,
  since these tools are described in prose and nothing else — named a return
  key the engine has never produced. A client following the description would
  look for `channel_set`, find nothing, and have no way to tell whether the
  nudge was configured. The docstring and the code were written at different
  times and nothing compares them.
- **Fix:** the docstring now names the keys the tool actually returns.
- **Guard:** none that is automatic. `test_send_test_nudge_*` pins the real
  keys, so the CODE cannot drift; nothing checks that the PROSE agrees with
  it. The existing `test_every_next_hint_names_a_tool_that_actually_exists` is
  the shape such a check would take, one level down.
- **Could it return?** **HIGH** — 41 tools describe their returns in prose and
  not one of those descriptions is checked against a real result. This is the
  cheapest unclosed gap in the log: the next place it surfaces is task 6's M4
  typed output schemas on the loop tools, which would make the promise
  machine-checkable for six of them and leave the other 35 exactly as they are.

### B-GAE-011 · A scratch-schema fixture silently read production's tables instead of its own
- **Phase:** 9, task 1b — 2026-08-11, caught before the commit
- **Found by:** the paired control assertion inside the new isolation test —
  "owner A's queue is not empty" — which failed while the refusal assertions
  it guards would all have passed
- **Cause:** the fixture copies the real views by reading
  `pg_get_viewdef(...)` and re-creating them in a scratch schema.
  `pg_get_viewdef` qualifies any name not reachable under the **current**
  `search_path`, and the definitions were read *after* switching to the scratch
  schema — so they came back naming `public.role_listings`, and the copied
  views read production's rows. The scratch queue was therefore empty, and
  every "owner B sees nothing" assertion would have passed for the wrong
  reason.
- **Fix:** the definitions are read while `search_path` is still `public`, and
  each one is asserted to contain no schema qualifier before it is used.
- **Guard:** that assertion, inside
  `tests/test_owner_scoping.py::_build_scratch_schema` — plus the design rule
  that made this visible at all: **every refusal is paired with the same call
  succeeding for the owner who owns the row.** A one-sided isolation test
  cannot distinguish "refused" from "nothing there".
- **Could it return?** **HIGH**, and specifically in **task 2**: RLS policies
  must be proven the same way, in a schema built the same way, and the failure
  mode is identical — a policy test against an empty fixture passes. The
  pairing rule is the guard that generalises; the assertion only guards this
  one fixture.

### B-GAE-010 · Two users cannot want the same job title — `target_roles.search_title` is globally unique
- **Phase:** 9, task 1b — 2026-08-11
- **Found by:** seeding a second owner in the new isolation test; the insert
  raised `UniqueViolation` on `target_roles_search_title_key`
- **Cause:** a single-user artefact of the same family as the `owner_id`
  DEFAULTs. The constraint is `UNIQUE (search_title)` with no owner in the key,
  so "AI Engineer" can exist for exactly one person in the whole database.
  `my_skills` and `my_constraints` were both measured at the same time and are
  correctly per-owner — this is the only owner-blind uniqueness left.
- **Fix:** **migration 0055** (task 2's security-review close, 2026-08-11)
  drops `target_roles_search_title_key` and adds
  `target_roles_owner_search_title_key UNIQUE (owner_id, search_title)`.
  Verified on the live schema at the phase close (`pg_constraint` on
  `public.target_roles` returns exactly that definition, 2026-08-12).
  **This entry said "Fix: none yet" for a day and a half after it was
  fixed** — the repair landed inside a migration that closed three findings
  at once and nobody came back to the entry it closed. Found in the
  phase-close sweep, which is what that step is for.
- **Guard:** **the constraint itself, and nothing else — no test.** A
  regression would need a migration to drop the owner from that key, which is
  loud, but no test inserts two owners' identical target roles, so nothing in
  the suite would notice. `tests/test_owner_scoping.py`'s fixture still gives
  its two owners differently-worded search titles; that workaround is now
  unnecessary rather than wrong, and its comment has been corrected to say so.
  The test worth having is named here so it is not left to memory: two owners,
  the same `search_title`, both inserts succeeding — paired with a control
  against a scratch copy carrying the OLD single-column key, so it can be seen
  red for the right reason. Carried into the next phase.
- **Could it return?** **LOW.** The key is right on live and mirrored in the
  log, and the shape that caused it — a single-user unique constraint — was
  swept for at the same time (`my_skills` and `my_constraints` were both
  measured correct). **MEDIUM for the class**: any NEW table given a unique
  key that forgets the owner repeats it exactly, and nothing scans for unique
  constraints on owner-scoped tables that omit `owner_id`. That scan is a
  handful of lines against `pg_constraint` and would close the class rather
  than this instance.

### B-GAE-009 · This log's own test leaked the Supabase project ref into a tracked file
- **Phase:** 9 — 2026-08-10, while building this log book
- **Found by:** `tests/test_public_safety.py::test_no_supabase_project_ref_in_tracked_files`, on the first full suite run **after** the commit — and, awkwardly, after the push
- **Cause:** `tests/test_bug_log.py` re-implemented a public-safety scan over
  this file, using the project ref **hardcoded as the needle**. The existing
  suite already scans every *tracked* file for exactly that, so the new check
  was redundant — and while the test file was untracked it was also invisible
  to the real scan, so the suite stayed green right up to the commit that
  tracked it. A duplicated safety check became the thing it was checking for.
- **Fix:** the duplicate scan is gone. What replaced it asserts only what is
  not covered elsewhere — that `docs/bug-log.md` is tracked, which is what
  makes it both ship publicly and fall inside the existing scans.
- **Guard:** the pre-existing `test_no_supabase_project_ref_in_tracked_files`,
  which matches by SHAPE (20 lowercase letters near a supabase mention) and
  therefore never has to contain a ref itself — the pattern the new test
  should have copied.
- **Could it return?** **MEDIUM** — whenever a new check is written by
  restating a rule instead of calling the existing check. The tell is a
  literal secret appearing in a test as a needle: if a scan needs to name the
  thing it forbids, it belongs with the scan that already matches by shape.
  Note the exposure is bounded and was NOT rewritten out of history: the ref
  names the database but is not a credential on its own, the public snapshot
  is a fresh squashed export of the working tree (so history never reaches
  it), and rewriting a pushed branch would cost more than it saves.

### B-GAE-008 · A test asserted a secret was printed "once" but counted indented lines, so a second print passed
- **Phase:** 9, task 1a — 2026-08-10
- **Found by:** a deliberate mutation probe, run because the test had passed
  the moment it was written
- **Cause:** the assertion counted lines starting with two spaces rather than
  occurrences of the key itself. A second, unindented `print` of the same
  secret was invisible to it.
- **Fix:** the key is pinned to a sentinel value and counted across the whole
  captured stdout (`out.count(SENTINEL) == 1`).
- **Guard:** `tests/test_mint_access_key_script.py::test_the_minted_key_is_printed_once_and_the_digest_never`, re-probed against a mutated script until it failed.
- **Could it return?** **HIGH** — this is the project's most persistent defect
  class, not a one-off. Any assertion phrased over a *proxy* for the thing
  (line shape, call count, a substring) instead of the thing itself can pass
  while the defect exists. The only reliable counter is the standing rule:
  mutate the source until the new test goes red, then revert.

### B-GAE-007 · `profile_id` is a `uuid.UUID`, not a `str` — every hosted request on the bootstrap path would have returned 500
- **Phase:** 9, task 1a — 2026-08-10, caught before the deploy
- **Found by:** the `security-review` skill, run adversarially before pushing
- **Cause:** `profiles.profile_id` is a `uuid` column, so psycopg returns a
  `uuid.UUID` object regardless of `default_profile_id`'s `-> str` annotation.
  `AccessToken` declares `client_id: str` and pydantic rejects the object, so
  `verify_token` raised instead of authenticating. The same mismatch made
  `scripts/mint_access_key.py`'s fuse compare a `str` against a `UUID` — never
  equal, so it refused the founder too.
- **Fix:** normalise with `str()` at each boundary (`mcp_server/transport.py`,
  `mcp_server/identity.py`, `scripts/mint_access_key.py`); `current_owner`
  now always returns a plain string.
- **Guard:** the test fakes return `uuid.UUID(...)` like psycopg does — see
  `tests/test_mcp_identity.py` (`LOCAL_PROFILE`), `tests/test_mcp_transport.py`,
  `tests/test_mint_access_key_script.py`. Verified afterwards against the live
  database.
- **Could it return?** **MEDIUM** — wherever a database value crosses into a
  typed API. The next two candidates are named: **task 2** (RLS policies
  comparing owner ids in SQL and Python) and **task 6** (Supabase JWT claims,
  where `sub` arrives as a string and must match a `uuid` column). Nothing
  scans for the mismatch generally; only the discipline of faking the real
  type stands in the way. Note the root enabler was B-GAE-004's defect class:
  every existing test faked the value as a string because a string was
  convenient.

### B-GAE-006 · `CREATE OR REPLACE VIEW` silently dropped `security_invoker` from four views
- **Phase:** 8.5 — 2026-08-10 (migration 0046, fixed by 0047 the same session)
- **Found by:** `get_advisors`, immediately after the DDL, at ERROR level
- **Cause:** `CREATE OR REPLACE VIEW` does not preserve reloptions, so
  replacing `v_apply_queue`, `v_today`, `v_scorecard` and `v_sponsor_browse`
  reverted them to definer semantics against the house rule.
- **Fix:** `0047_restore_security_invoker_on_replaced_views.sql` re-asserts
  `security_invoker = true` on all four.
- **Guard:** `get_advisors` after every DDL — mandated in `CLAUDE.md` and in
  the phase relay. The advisor is a real detector, but it only fires **if
  someone runs it**.
- **Could it return?** **HIGH** — it will recur on the next `CREATE OR REPLACE
  VIEW`, which task 1b already needs for `v_skill_gap` (migration 0051), and
  again for any view touched during the RLS work. This is the clearest
  candidate in the log for an automated check rather than a habit: a test that
  asserts every view carries `security_invoker=true` would close it for good.

### B-GAE-005 · A monitor reported the exact opposite of the truth
- **Phase:** 8 — 2026-08-09
- **Found by:** the founder, comparing the monitor's claim against the job
  that was visibly running
- **Cause:** two faults compounding. The poll ran `gcloud … $P` with flags
  held in a variable, but **this shell is zsh, which does not word-split
  unquoted expansions**, so gcloud received one mangled argument and failed
  with "You must specify a region"; `2>/dev/null` then swallowed that error,
  and the empty result was read as "no execution appeared".
- **Fix:** the flags are passed as a real array, and the error stream is no
  longer discarded.
- **Guard:** the standing rule in `CLAUDE.md` — never `2>/dev/null` in a
  watcher — plus the design principle that a check must fail loudly and
  *differently* from "all clear". No test enforces it.
- **Could it return?** **MEDIUM** — in any new ops script or watcher. The
  lesson outranks the bug: an instrument that can report success when it has
  actually failed is worse than no instrument, because it is trusted.

### B-GAE-004 · Three tests produced a green tick without exercising what they named
- **Phase:** 8, Stage C — 2026-08-09
- **Found by:** the work of fixing four unrelated defects; each fix surfaced a
  test that could not have failed
- **Cause:** three distinct shapes of the same mistake. (1) `test_trigger.py`
  and `test_mcp_census_tools.py` asserted `".venv" in cmd[0]` — true on the
  laptop and *necessarily* true of the very hardcoding that was the bug, so
  the assertion could only pass while the defect existed. (2) A regression
  test written with `responses` passed against the unfixed code, because
  `responses` mocks the adapter and the latin-1 header encoding that actually
  raises never happens. (3) A no-channel test guarded with a throwing lambda
  that was never reached.
- **Fix:** all three rewritten to exercise the real path; the container-fatal
  case is now asserted against the image's actual layout.
- **Guard:** the standing question in `CLAUDE.md` — *has this test been seen
  red for the right reason?* — and, in practice, mutation probing before a
  guard is trusted.
- **Could it return?** **HIGH.** It already has: B-GAE-008 and the enabler of
  B-GAE-007 are the same defect in new clothes. Treat this as a permanent
  condition of the codebase rather than a closed item.

### B-GAE-003 · A non-latin-1 push title raised an exception that escaped the error handler entirely
- **Phase:** 8, Stage C — 2026-08-09
- **Found by:** RUNNING the code — an audit's static pass had missed it
- **Cause:** `send_push` set `headers={"Title": title}`; a non-latin-1 title
  raises `UnicodeEncodeError`, which is **not** a `requests.RequestException`,
  so it escaped the `except` clause. `send_test`'s hardcoded em-dash title
  therefore crashed every time.
- **Fix:** the title is UTF-8 encoded (`title.encode("utf-8")` round-trips;
  ntfy accepts UTF-8).
- **Guard:** a regression test that exercises the real encoding path rather
  than a mocked adapter — the fix for one third of B-GAE-004.
- **Could it return?** **LOW** for this call site. **MEDIUM** for the class:
  catching a library's own exception type says nothing about the exceptions
  raised *before* the library is reached. Blast radius was chased at the time
  and the 06:30 path proven safe — a digest carrying accented company names
  delivered fine, because the body is UTF-8 encoded.

### B-GAE-002 · Board lookups missed every company whose register name carries a legal suffix
- **Phase:** 7.5 — 2026-07-11
- **Found by:** a live smoke run against real register names
- **Cause:** every UK register name legally ends in Ltd / Limited / PLC, while
  job-board slugs use the bare brand, so `candidate_tokens` generated
  candidates that could never match.
- **Fix:** `candidate_tokens` now also tries legal-suffix-stripped variants.
- **Guard:** the census's own token tests.
- **Could it return?** **MEDIUM**, and specifically **when the country
  changes.** The suffix list is UK-shaped (Ltd/Limited/PLC); the machine is
  built country-agnostic, so the first non-UK register will reintroduce this
  bug in a new alphabet of suffixes.

### B-GAE-001 · `scripts/discover.py` shadowed the `src/discover` package
- **Phase:** 7.5 — 2026-07-11
- **Found by:** a live run
- **Cause:** Python puts a script's own directory first on `sys.path`, so
  `scripts/discover.py` hid the `src/discover` package from every import
  inside it.
- **Fix:** renamed to `scripts/discover_companies.py`.
- **Guard:** **a documentation line only** — the `CLAUDE.md` gotcha "a
  `scripts/*.py` name must never equal a `src/` package name". Measured
  2026-08-10: **no test enforces this.**
- **Could it return?** **MEDIUM** — it needs only one new script named after a
  package, and the failure appears at import time in whichever door runs that
  script, not in the suite. The guard is the weakest in this log; a test
  comparing `scripts/*.py` stems against `src/` package names would be a few
  lines and would close it permanently.

---

## What this log says about the codebase

Measured 2026-08-12 at the Phase 9 close: **39 entries — 6 open, 33 resolved.**
Read together rather than one at a time, they point at four recurring shapes,
and the counts are the argument. Every number below is counted from the entries
above on that date; if you are reading this later, count again rather than
trusting it — a restated number with nothing checking it is [[B-GAE-033]].

0. **The blind spot, and it is still open.** [[B-GAE-016]]: **13 of 22
   database-writing modules have never been run against a real table.** Around
   it sit the bugs that blind spot let through — 013 and 014 (two sibling
   writers, dead on arrival, fully covered offline, both found by a human
   trying to use them), 015, 019, 020, 022, 023 and 026 (real-database tests
   that were failing, or passing against a schema the database does not have,
   while CI ran offline only). **"The suite is green" and "every test passes"
   were not the same sentence in this repo from migration 0049 until the CI
   database lane landed on 2026-08-11.** They are now — for the schema. They
   still are not for the thirteen.

1. **Tests that cannot fail** — 004, 008, 011, 013, 014, 022, 025, 026, 029,
   and the reason 007 survived review: **ten of thirty-nine**, the most common
   defect here by some distance and the only one that has recurred in every
   phase since it was first named. 013 is the strongest case: a test did not
   merely fail to catch the bug, it *asserted the bug was correct*, and had
   done so since the feature shipped. 029 is the subtlest: an assertion that
   was not weak about its claim but weak about **absence** — it could prove the
   right number was present and could never prove a stale one was gone. The
   common root of most is a fake that does not behave like the database (no
   generated columns, no uuid types, no constraints), which makes *"does this
   test need a real database to mean anything?"* worth asking of every new
   offline test. The counter that actually works is the paired control: 011 was
   caught by one, and 026's, 032's and 036's guards each carry theirs.

2. **Silence where there should be noise** — 003, 005, 027, 028, 030, 031:
   **six**. A swallowed error, a mis-typed exception, a stamp that marks work
   as done for the wrong owner, a policy that would have made a refusal silent
   instead of loud, a quota nobody counted because spending it politely looked
   like not spending it. The through-line: an instrument that can report
   success while failing is worse than no instrument, because it is trusted.

3. **Guards that are documents, not code** — 001, 005, 006, 012, 022, 024, 034
   and 037 name, in their own Guard field, something that is not a test: a
   sentence in `CLAUDE.md`, a habit ("run `get_advisors` after DDL" — a real
   detector that only fires if someone runs it), a tool that needs the live
   credential and therefore cannot run in CI, or nothing at all. This category
   was the largest at the last count and is no longer growing fastest, because
   Phase 9 converted several of its members into real assertions — but it has
   never been emptied, and two of its members (012, 034) are not fixed at all,
   only written down.

4. **Mirrors that stop describing what they mirror** — 024, 025, 035, 036, all
   four found in Phase 9 and none of them possible earlier, because a mirror
   needs two copies before it can drift. The migration log against the live
   schema (024: the log could not rebuild the database it mirrors; 025: three
   view bodies mirrored as English prose, so a rebuild resurrected a hardcode
   the founder had deleted). The private repo against its public snapshot (035:
   the snapshot shipped a workflow that could only fail where the credentials
   are absent; 036: the fix then left four tests asserting on a file the
   snapshot replaces). **This is the newest shape in the log and the one to
   watch**, because every instance of it was invisible until somebody rebuilt
   from the copy instead of trusting it — which, before this phase, nobody had
   ever done.

The four cheap closes named in their own entries are still worth doing: a
`scripts/*.py`-vs-package-name check (001), a `security_invoker = true`
assertion over every view (006), typed outputs making a tool's promised keys
machine-checkable (012 — M4 typed six of the loop tools in Phase 9 task 4 and
deliberately stopped there, so the other tools still describe their returns in
prose that nothing checks), and a `pg_constraint` scan for unique keys on
owner-scoped tables that omit the owner (010's class).
