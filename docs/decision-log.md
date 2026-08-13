# Decision Log — goal-a-engine

Phase-level decisions, scope shifts, and gate confirmations. Every entry dated with clock time (HH:MM TZ); backfilled entries are marked [backfilled]. Newest first.

---

## 2026-08-12 — Phase 9.5 tasks 2, 3, 4, 6, 9, 10: two prompt bumps, a brief that was wrong, and a retention decision that is the founder's

Built 20:10–22:30 BST. The through-line is that three of these tasks changed
what they were briefed to be, because measuring first said so.

- **D-GAE-087 · An amendment inserts BEFORE it retires, and validates before
  either.** If the insert fails, the old fact is still serving; the reverse
  order can leave an owner with no fact at all, and retire-then-validate loses
  the original to a typo. **Rejected:** an in-place `UPDATE` of `fact_text` —
  it would rewrite history, since bullets traced last week against the old
  sentence would afterwards appear to have been traced against words the owner
  never approved. The superseded row keeps its wording AND its confirmed
  state: it *was* a confirmed fact, and it remains true that it was one.
- **D-GAE-088 · `amended_from` points backwards only.** A `superseded_by`
  written onto the old row would mean modifying a retired row, which is the
  mutation the stamp chain exists to avoid. **Trade-off:** walking a chain
  forwards costs a scan rather than a follow; with one arrow per amendment
  and no volume, that is not worth a second column that can disagree.
- **D-GAE-089 · M7 is a server-side write, not a sentence in the prompt.**
  The plan offered both. The prompt option was not hypothetical — it shipped
  in Phase 9 and `intake-v1` has said "record skills via add_skill as you go"
  ever since. Measured on the founder's own base: **21 live skills, 4
  evidenced, 17 with no fact behind them**, and **6 role blocks evidencing
  "teamwork", "call handling", "cinematography" — none matching any
  `my_skills` row**. Every norm was correctly normalised, so it was never a
  normalisation bug; the sessions that wrote facts and the sessions that wrote
  skills chose different words months apart. A sentence in a prompt cannot
  make two independent writes agree on a vocabulary. `record_experience`
  takes the block's `skill_norms` from what `add_skill` returns, so the two
  join by construction, and a test proves the norms came from the writer
  rather than being recomputed — a second normalisation would bring the drift
  back wearing the fix's clothes.
- **D-GAE-090 · Two prompt versions were bumped rather than edited in place.**
  `intake-v1 → v2` (one call now records a fact and its skills together) and
  `extract-v1 → v2` (the salary gate's subject changed). Both pinned
  assertions were edited deliberately. The rule being applied: a client that
  reads a version label is entitled to the behaviour that label described, and
  a prompt describing a gate that no longer exists is worse than no prompt —
  the client writes to the stricter rule, drops a real salary, and nothing
  reports it.
- **D-GAE-091 · The salary gate reads the advert; the skills gate reads the
  bytes.** Salary is grounded against `clean_html`-stripped text using the ONE
  shared stripper, aliased. Measured before the change: **of 212 salary ranges
  in 334 HTML adverts, 63 (30%) were readable to a human and ungroundable in
  the raw text** — including role 7090, the listing the original finding
  named. Skills keep the strict raw-text gate **deliberately**, because they
  feed the match engine and a looser gate there changes which jobs the owner
  is shown; a test pins the asymmetry so removing it must be deliberate.
  **Rejected:** widening both for consistency.
- **D-GAE-092 · A rejected salary holds the listing in the tray instead of
  releasing it.** The old path un-staged on the way out whatever happened, so
  the client was told "salary_rejected" about a row it could no longer reach.
  **Trade-off considered and closed:** a held row could in principle sit in
  the tray forever, so the escape hatch is explicit — resubmitting with a
  groundable salary *or with none at all* releases it, and an abandoned claim
  frees itself on the ordinary 60-minute reclaim.
- **D-GAE-093 · The learning curve ranks on effort, not on `learned_at`.**
  The brief said that column had been "collecting since 2026-08-10" with
  "weeks of data". Measured: **22 skills, 0 with `learned_at`**, every row
  written 2026-06-28, six weeks before the column existed ([[B-GAE-046]]).
  Ranking on it would have returned an empty list forever from code that runs
  cleanly. **Chosen instead:** demand × held × proven, in three effort tiers —
  and tier outranks demand, which is the whole argument, because a skill 55
  roles ask for that takes months is not closer to closing than one 3 roles
  ask for that needs a sentence. `learned_at` is not silently dropped: every
  answer reports `learned_at_known` and `ranks_on_recency`, so its emptiness
  is visible in the response rather than invisible in an absent one.
- **D-GAE-094 · M5 (`prompts`/`resources` MCP primitives) stays note-only, for
  the third phase running — restated as a decision so it cannot decay into an
  oversight.** `plans/0013` §6's own instruction is to build it when a real
  client's UI pulls for it. **Trigger unchanged and still unmet:** a client
  whose interface lists MCP prompts or resources natively. Nothing in this
  phase changed that; the three server-side prompts remain DATA served through
  ordinary tools, which every client can already reach.
- **D-GAE-095 · The database retention decision is NOT taken, and the reason
  is measurement rather than deferral.** Measured 2026-08-12: **323 MB of the
  500 MB free tier** (316 MB on 2026-08-10), **`profiles` = 1**. Neither
  trigger — ~450 MB, or user #2 — has fired. More usefully, two of the three
  options the plan lists are now known to be worth almost nothing today:
  **trimming JD text on closed roles frees 6 MB** (847 closed listings; it
  buys about two days), and **pruning long-closed ads at never-sponsor
  employers has zero candidates** — 91% of `aggregator_ads` (95,565 of
  104,761) never matched a sponsor, but **not one row is older than 60 days**;
  the oldest `last_seen` is 2026-07-22. `aggregator_ads` is 127 MB accumulated
  in two harvest weeks (2026-07-20 and 2026-07-27, ~52k rows each) with no new
  ads by `first_seen` since 2026-08-03, so it is not the part that is growing.
  **So the only lever that changes anything today is Supabase Pro at $25/mo,
  which is billable and therefore a ⛔ founder gate — and it is not needed
  yet.** Recommendation, for the founder to accept or reject: do nothing now;
  revisit at 450 MB, by which point the 60-day prune will have real candidates
  and will be the large lever (91% of the biggest table). **Keep-all remains
  an OWNER-data principle; whether world data shares it is still his call, and
  this entry is the basis for making it, not the making of it.**

**Measured, not recalled** (2026-08-12): 51 MCP tools; migrations through
0064; DB lane 1,086 passed / 0 skipped; database 323/500 MB; `profiles` = 1.

---

## 2026-08-12 — Phase 9.5 task 0 + task 1: five audit repairs, then the machine starts describing the person

Built 18:40–20:10 BST. Task 0 closed five of the close audit's six defects
with executing tests — the guardless ratchet fell **19 → 14**, its first fall
since the audit raised it. Task 1 then shipped the mirror. The two halves are
related more than the ordering suggests: every task-0 repair was a check that
could not fail, and the mirror is the first surface whose whole job is to
report an uncomfortable number honestly.

- **D-GAE-079 · The snapshot predicate demands TWO signals that agree, and
  its consistency test is deliberately unmarked.** `_is_snapshot()` asked one
  question — is `.github/workflows/ci.yml` byte-equal to the public workflow —
  and that file is the very thing the seven `private_only` guards protect, so
  one `cp` dismissed its own guards and left a green suite over a repo that
  could no longer deploy ([[B-GAE-040]]). It now also requires `CLAUDE.md`,
  which only the scrub deletes, to be absent: one command can move the first
  signal and cannot move the second. **Rejected:** marking the new consistency
  test `private_only` for symmetry with its neighbours — a guard the predicate
  it checks can skip is the bug restated, not the fix. **Trade-off:** the
  second signal is a hardcoded path, so a scrub that stopped deleting
  `CLAUDE.md` would silently make the predicate always-false in the real
  snapshot; a second test reads the scrub list out of `prepare-snapshot.sh` to
  make that a loud failure instead.
- **D-GAE-080 · Test residue is checked against the live database, from a
  list read out of the test sources.** [[B-GAE-041]] committed a probe schema
  to production on every green run for a week. **Rejected:** asserting the one
  known probe is gone (the instance, not the class) and keeping a hand-written
  list of probe names (a second copy, which is how mirrors drift). The scan
  parses `schema = "…"` out of `tests/*.py`, so next month's probe is covered
  by the convention rather than by memory. **Trade-off:** a probe built some
  other way is invisible to it — which is now a reason to keep the convention.
- **D-GAE-081 · Foreign bytecode is detected by the path recorded inside it,
  not by a shape rule about `.dockerignore`.** [[B-GAE-043]] shipped 246 of
  the laptop's `.pyc` files into every locally built image. The obvious test —
  "no `.pyc` under the copied trees" — would be red everywhere forever, since
  pytest makes bytecode as it imports, and a permanently red test is how a
  suite starts being ignored. So the assertion is that every compiled file in
  this tree was compiled FROM this tree, which passes on a laptop, passes in a
  correct image, and fails by name in a smuggling one. **Trade-off:** it
  guards bytecode specifically; a different smuggled class still needs its own
  pattern, and only the named at-any-depth list is shape-checked.
- **D-GAE-082 · The snapshot verifier treats only grep exit 0 and 1 as
  answers.** Anything higher means the scanner broke and the snapshot has NOT
  been checked, so it fails shut ([[B-GAE-045]]). Its match count is computed
  in shell rather than by piping to `grep -c`: having just decided grep may be
  broken, asking it how many lines it produced would trust the same tool
  twice. **Rejected:** testing the script by grepping its source, which would
  prove only that it contains certain words — each test builds a sandbox repo
  and runs the real script, one of them with a `grep` that exits 2 shimmed
  onto PATH.
- **D-GAE-083 · The mirror stores no opinion of the person; understanding is
  re-formed from the rows on every read.** **Rejected:** a summary table
  refreshed nightly (cheaper per read, and wrong the moment the owner adds a
  fact — the machine would go on confidently describing who they were in
  August). The cost is two queries over a few dozen rows, which is nothing,
  and it cannot be wrong about the present.
  `test_the_mirror_writes_nothing_at_all` makes that a mechanism rather than a
  stated intention.
- **D-GAE-084 · The mirror's headline number is the uncomfortable one.** A
  read-back that counts what it has is flattery; the number that predicts a
  thin CV is how many recorded skills have NO confirmed fact behind them,
  because `cv.truth`'s gate will decline exactly those. Measured on the
  founder's own base the day it shipped: **38 facts, 21 live skills, 4
  evidenced, 17 not — 19% coverage.** The 17 are **named**, not counted, since
  a count is something nobody can act on. **Trade-off:** the first thing the
  founder's own dashboard now tells him is bad news, on purpose.
- **D-GAE-085 · Evidence means confirmed and never retired — the mirror is
  never more generous than the truth gate.** A draft is a proposal nobody
  approved and a retired block was withdrawn; if either could evidence a
  skill, the mirror would promise a CV line `cv.generate` then refused to
  write, which is worse than silence. Related: a skill proven by a job counts
  as proven by the job, so only a skill with NO paid-work evidence counts as
  "evidenced outside paid work" — otherwise the honest number inflates with
  the ordinary case.
- **D-GAE-086 · The dashboard card reads a new view, and the two
  implementations are held together by a test.** The dashboard may read only
  curated views, so `v_owner_mirror` (migration 0063) carries the counts while
  `src/cv/mirror.py` keeps the receipts a view cannot hold. That is two
  implementations of one idea — the [[B-GAE-025]] shape — so the DB test runs
  the **shipped migration SQL** against probe tables and asserts every count
  matches the Python fold. **Rejected:** having the dashboard import
  `build_mirror` (it would pass the source scan, since the scan reads only
  `src/dashboard/`, while breaking the rule the scan exists to enforce);
  extending `v_scorecard` instead (a global row cannot hold a per-owner fact,
  and `CREATE OR REPLACE VIEW` drops `security_invoker`). `cv_blocks` and
  `profiles` were added to the scan's `RAW_TABLES` in the same commit — the
  rule had been enforced only for the tables someone happened to list in 2026.

**Measured, not recalled** (2026-08-12): suite 1,047 collected — offline 986
passed / 61 skipped, DB lane **1,047 passed / 0 skipped**, container 904 /
126; 48 MCP tools; migrations through 0063; guardless ratchet 14.

---

## 2026-08-12 — The Phase 9 close: the portfolio's red X, and three logs that were describing something else

Built 15:56–17:22 BST — the times are the twelve close commits' own; this entry first shipped saying "20:00–23:30" with per-decision clock times no instrument recorded, corrected at the close audit ([[B-GAE-044]]). Seven decisions, all of them about
the same thing from different sides: **a copy that stopped describing what it
copies.** [[B-GAE-035]] is the private CI workflow shipped into a public repo
that cannot run it; [[B-GAE-036]] is the fix leaving four tests asserting on a
file the snapshot replaces; [[B-GAE-038]] is a log entry losing its heading to
the entry written above it. Same shape, three surfaces, one afternoon.

- **D-GAE-072 · The snapshot ships an ALLOWLIST of two jobs, not a filtered
  copy of the private workflow.** `ops/flip/public-ci.yml` contains the
  offline suite and the database lane — the two that read no credential — and
  `prepare-snapshot.sh` empties `.github/workflows` before installing it.
  Emptying first is what makes it an allowlist rather than a blocklist: a
  credentialled job added to the private workflow tomorrow stays out by
  default, with nobody needing to remember. **Rejected:** stripping the deploy
  jobs out of a copied `ci.yml` (a blocklist of today's jobs, which is exactly
  how this bug arrived), and shipping no workflow at all (a portfolio that
  demonstrates CI discipline should demonstrate it running).
- **D-GAE-073 · The public workflow is proven in the PRIVATE repo before it
  ships, as a dispatch-only twin.** `.github/workflows/public-ci-proof.yml`
  is the same file with one difference — it runs only when a human presses the
  button — and the two are held byte-equal by test on their parsed `jobs`. A
  workflow that has never run cannot be trusted to go green on its first public
  run, and a first-run failure would put a day-one red on a fresh snapshot in
  front of exactly the audience the refresh is for. It stays after the first
  proof rather than being deleted: the next change to the public workflow gets
  the same treatment for free, and dispatch-only costs nothing until pressed.
  **Rejected:** editing the public repo by hand (the mirror is one-way and a
  hand edit dies at the next force-push — the [[B-GAE-025]] lesson applied to
  workflows), and giving the shipped file `workflow_dispatch` alongside `push`
  so one file serves both (it would then run the database lane twice on every
  private push, for no proof).
- **D-GAE-074 · "Am I the snapshot?" is answered structurally, never by a
  flag.** [[B-GAE-036]]'s fix needed the suite to know which repository
  it is in. The predicate is: *if the workflow this checkout carries already IS
  the file the snapshot installs, this checkout is a snapshot.* Nothing has to
  be set, exported or remembered, and it answers correctly in all three places
  the suite runs — private repo, snapshot, container. It lives once, in
  `tests/conftest.py`, because two copies of one predicate is how a mirror
  starts drifting. **Rejected:** an environment variable (a guard that depends
  on being switched on is off by default), and marking the whole affected
  module private-only (it would take the public repository's working guards
  away with it).
- **D-GAE-075 · dev.md's counts are DELETED, not corrected.**
  [[B-GAE-033]] offered two repairs and the stronger one was taken: the file
  now states no build-state count at all, and one line says why — the README's
  numbers table owns them and a test measures that table against reality. The
  "Status (honest)" section, which restated the phase, the test count, the
  migration number and the tool count (all four wrong), is replaced by a table
  of *which file answers which question*. Pointers do not go stale the way
  numbers do. **Rejected:** correcting the four numbers, which is what let them
  rot for a phase and a half in the first place.
- **D-GAE-076 · A guard was written for dev.md's prose instead of another
  admission.** The entry's own could-it-return asked for a test that
  every `src/…` path the file names still exists; it was written rather than
  promised again (`tests/test_dev_doc_paths.py`, 28 paths, seen red against a
  planted `src/telepathy/`). This matters beyond the file: the guard ratchet
  counts entries held shut by prose, and the honest alternative was to raise
  that number a third time in one session. **What the test does NOT do is
  stated in the entry** — it checks a path exists, never that the sentence
  describing it is true.
- **D-GAE-077 · "Open" in the bug log means NOT FIXED, not RECENTLY WRITTEN.** Six entries whose own text recorded a completed fix and a named
  guard were sitting under `## Open`, because entries are written at the top of
  the file and nobody moved them afterwards. Refiled: Open is now exactly
  [[B-GAE-035]], [[B-GAE-034]], [[B-GAE-037]], [[B-GAE-024]], [[B-GAE-025]] and
  [[B-GAE-016]] — which is the founder's own list, arrived at independently.
  The same pass found [[B-GAE-010]] still saying "Fix: none yet" a day and a
  half after migration 0055 fixed it, verified against the live constraint.
  **A log that ships publicly and misstates its own open set is worse than no
  section headings at all**, because the headings are believed.
- **D-GAE-078 · The ratchet's phrase list is widened rather than the entries
  reworded.** Two entries written this same afternoon admitted an
  unguarded half in wording the scan did not know, and so ducked the ratchet
  without anyone intending to. The wording was not the problem; a phrase list
  shorter than the language people write in was. Two phrases added verbatim
  from real Guard fields, and `MAX_GUARDLESS_ENTRIES` raised 12 → 13 with every
  move stated in the file (−1 for 010, now held by a database constraint; +2
  for 036 and 037). **Rejected:** rewording the two entries to match the
  existing phrases, which would have made the count right and the scan no
  better.

## 2026-08-12 — Task 6: the stranger tier — the data API shut first, then a Google identity becomes an owner

Built 17:30–19:40 BST. The task's own instruction put [[B-GAE-032]] before any
line of sign-in, and that ordering is the decision the rest of these hang off:
the hole was only harmless while "authenticated" meant nobody.

- **D-GAE-062 · The data API is shut, not narrowed, 17:55.** Supabase publishes
  a PostgREST API over the same database; `anon` and `authenticated` held
  INSERT/UPDATE/DELETE **and** TRUNCATE/REFERENCES/TRIGGER on all 42 relations
  in `public` — 504 write grants, not the 252 the bug counted, because the bug
  counted only the three privileges it went looking for. Migration 0061 revokes
  all six from both roles and from PUBLIC. Wider than the bug named, on
  purpose: TRUNCATE empties a keep-all table without touching a policy, and
  TRIGGER lets a role attach code to somebody else's writes. Verified safe
  three ways first — no file in the repo names PostgREST, supabase-js or the
  publishable key; `goal-a-mcp` carries only DATABASE_URL and MCP_TOKEN;
  `goal-a-status` only DATABASE_URL. **Rejected:** revoking on the two tables
  that had policies (the grants are the class; the policies were the accident).
- **D-GAE-063 · The two anon SELECT policies are DROPPED, and that is a
  decision, 18:00.** The register is public government data, so serving it to
  `anon` would be defensible — but publishing is an act, not a leftover, and
  nothing reads these. An unused read path on the table this product's truth
  depends on is a liability with no user. **Rejected:** keeping them "because
  it is public anyway". If a public sponsor lookup is ever wanted, it comes
  back as its own migration with its own reason.
- **D-GAE-064 · SELECT *grants* stay, and a new test is what makes that
  honest, 18:05.** With RLS on and no policy admitting either role, a SELECT
  grant is inert — but only while RLS stays on. So
  `test_every_table_in_public_still_has_row_level_security_on` pins the
  condition the decision rests on, rather than the decision resting on memory.
  **Rejected:** revoking SELECT too (strictly stronger, and it would silently
  break a future supabase-js dashboard the founder has not decided against).
- **D-GAE-065 · The could-it-return is `ALTER DEFAULT PRIVILEGES`, with a
  limit stated out loud, 18:10.** Supabase re-grants everything to both roles
  on every NEW relation, so a revoke alone lasts until the next CREATE TABLE.
  The default ACL is fixed for grantor `postgres`, which is every path that
  creates a table here. It CANNOT be fixed for `supabase_admin`: `postgres` is
  neither superuser nor a member of it — measured, not assumed. Named in the
  migration and in the test rather than left as a silent gap.
- **D-GAE-066 · The provider's `sub` is never our owner id, 18:35.**
  `profiles.auth_user_id` (0062) is nullable and unique: nullable because the
  founder and every friend-tier profile has no auth user and never will,
  unique because an identity maps to exactly one owner. **Rejected:** using
  `sub` as `profile_id` (every downstream row would then depend on the
  identity provider's choices), and a foreign key to `auth.users` (it would
  either cascade — deleting a person's whole record, which the keep-all rule
  forbids — or block the auth deletion outright).
- **D-GAE-067 · First sign-in creates the profile at the door, 18:40.** No
  "register" tool: a verified token IS the registration, and a separate step
  would be one more thing to fail between a stranger and their first brief.
  The unique index decides a race, not the read before it — the loser rolls
  back to a savepoint and re-reads, because without the savepoint a failed
  insert aborts the whole transaction and the request dies on a race it should
  absorb.
- **D-GAE-068 · Order at the door: minted key, then JWT, then bootstrap —
  and a failed JWT still falls through, 19:00.** A minted key always wins, so
  neither of the other two can override a stored owner. A credential that
  merely LOOKS like a JWT and fails verification continues to the bootstrap
  comparison rather than being refused early: the shape test decides which
  verifier to try, never who is refused, so the founder's own token cannot be
  locked out by happening to contain two dots. Issuer, audience and ES256 are
  pinned from the project's live JWKS (one ES256 P-256 key, measured today);
  without the issuer pin, a genuine token from ANY Supabase project would open
  this door. A verified stranger gets `["owner", "signed-in"]` and never the
  bootstrap scope.
- **D-GAE-069 · `SUPABASE_URL` joins the secret allowlist (seven → eight)
  though it is not confidential, 19:15.** It is a public URL; it rides through
  Secret Manager because it carries the project ref, which never enters the
  public repository, and that is this project's only path for a value that
  must stay out of git. The count test was renamed with it, deliberately, and
  the old blanket ban on the `SUPABASE_` prefix in cloud scripts became a ban
  by NAME — the three data-API credentials stay banned, which is the ban that
  now means something. **Rejected:** a new `SUPABASE_PROJECT_URL` (a
  near-duplicate of a name already in `.env`), and `--set-env-vars` at deploy
  time (the value would then live in a script, which is where the ref must
  never be).
- **D-GAE-070 · Self-serve keys are JWT-only, and the mint invariant is
  narrowed rather than deleted, 19:25.** `issue_my_key`/`revoke_my_key` refuse
  a minted key (one leaked key would otherwise become an unrevokable supply of
  them), the bootstrap token and stdio. Neither takes an owner argument at
  all. The old test said "minting is unreachable from the skin"; its stated
  fear was "a client could issue itself a key for somebody else's data", and
  sign-in makes the second half preventable — so the test now checks the fear
  directly (mint reachable from exactly one module, the unscoped `revoke_key`
  reachable from none, neither tool taking an owner-shaped argument) and was
  seen red against a mutated import before being trusted.
- **D-GAE-071 · The connector's OAuth flow is NOT built, and the reason is on
  Supabase's side, 19:35.** Measured today: the project answers
  `/auth/v1/.well-known/oauth-authorization-server` with **404
  "OAuth server is disabled"**, and its OpenID discovery advertises no client
  registration endpoint — so the 2026-08-10 13:20 assumption that Supabase's
  OAuth 2.1 server would serve the connector's authorize page does not hold on
  this project today. Token verification is done and works regardless. When
  that feature is enabled, the wiring is a composition, not a rewrite:
  FastMCP's `SupabaseProvider` serves both `.well-known` documents and accepts
  our existing verifier through its `token_verifier` parameter. Not improvised
  now — it needs a new public endpoint and a deploy, both founder gates.

---

## 2026-08-12 — Task 5: one ledger, two scopes — and the cap moves into the client

Built 02:55–03:40 BST. Six decisions and one deliberate acceptance of a known
debt, written down with its trigger rather than left as silence.

- **D-GAE-058 · The cap is enforced in the HTTP client, not per tool, 03:00.**
  There are exactly two functions in the codebase that reach a metered API —
  `discover.aggregators._get_json` and `discover.companies_house._get_json` —
  so the gate goes there. Every tool that spends today inherits it and so does
  every tool written later, because `budget.gate.source_for_url` meters a call
  by **where it points**, not by who remembered to wire it. That is the exact
  hole [[B-GAE-031]] came through: Companies House was the largest spender in
  the system and the only client nobody had joined to the ledger, for a year,
  silently. Rejected: a per-tool check (five tools today, and the sixth is a
  bug), and a metered `session` object (a client that falls back to
  `requests.Session()` would slip the gate without anyone noticing).
- **D-GAE-059 · The world ledger keeps its table; the owner budget gets a new
  one, 03:05.** `api_quota_ledger (source, day)` is already written every
  night and already correct, so the world cap needed nothing but a cap value.
  `api_owner_spend (owner_id, source, day)` is the new half. A user-triggered
  call debits **both**; the nightly world half passes no owner and debits only
  the world — which is what keeps the founder's night byte-identical, and is
  tested as such rather than asserted. Rejected: one table with a sentinel
  owner for world rows (a nil-uuid that means "everybody" is a value that will
  eventually be read as an owner).
- **D-GAE-060 · Caps live in a table, and an unknown source is refused, 03:10.**
  `api_budget_caps` so the founder can raise a limit without a deploy, and so
  the fail-closed direction is free: a source with no cap row makes both
  subselects NULL, `calls < NULL` is NULL, no row is returned, and the call is
  **refused** rather than granted infinity. Seeds are measured, not guessed —
  adzuna world 250 (the sweep already defaults to `--adzuna-cap 240`; peak 240
  across 9 ledgered days), reed world 950 (peak exactly 950 across 11 days),
  companies_house world 20,000 (no published daily limit; the nightly 2,000-org
  classify batch costs up to 4,000 calls, so this is a runaway backstop with
  four times the headroom). A `CHECK (owner_daily <= world_daily)` refuses a
  per-owner budget larger than the shared quota — it caught a test that tried
  to configure exactly that.
- **D-GAE-061 · Who pays travels as an environment variable, 03:15.** Every
  user-triggered spend is **detached**: the tool spawns `sweep.py`, or spawns
  `run.py` which spawns `jd_drip.py`, and the Reed call happens two processes
  down. Environment crosses both hops with no plumbing; a `--owner` flag would
  have to be threaded through every stage and would be forgotten at the first
  one. `GOAL_A_BUDGET_OWNER` unset means the nightly world half, which owes
  nobody — so the scheduler's own 06:30 run is unchanged by construction.
- **The refusal is a stop, never an item error, 03:20.** Three runners caught
  a budget refusal in a per-item `except Exception` and would have turned one
  exhausted day into a flood of fake failures — the drip into 200 "broken
  jobs", `run_classify` into up to 2,000 fabricated census 'error' cards. Each
  now catches `BudgetExhausted` **above** the catch-all and stops with
  receipts. The sweep reuses its existing `quota_exhausted` outcome rather
  than inventing a word, so the wrapper already knows not to retry.
- **The ledger has one writer now, 03:25.** `quota_add` is gone from
  `discover.agg_store`: with the debit in the client, a second writer in the
  runners would double-count every call. One real consequence, measured rather
  than estimated: the nightly `discover` stage was **never** ledgered, and it
  makes one call per role pattern per source — **49 patterns today**, so up to
  49 adzuna and 49 reed calls a night that nobody was counting.
  * **The nightly job is not narrowed.** Reed's night is discover (≤49) then
    the drip, which already takes `min(200, 950 − spent)` and simply takes 49
    fewer — ~249 against a 950 cap. `agg_sweep` is not one of the 15 stages,
    so its 950 does not land on the same run.
  * **Adzuna needs the founder's eye.** A day on which `agg_sweep` is also run
    now totals 240 (its own `--adzuna-cap`) + 49 = **289 against a 250 free
    tier** — which means the machine has probably been over that tier on those
    days already, invisibly, and the ledger's 240 peak was the sweep's own cap
    binding rather than the truth. The cap stays at the documented 250 rather
    than being raised to hide it: the sweep's tail stops with
    `quota_exhausted` and resumes tomorrow, which is the designed behaviour.
    The choice — lower `--adzuna-cap` to ~200, or confirm the account's real
    tier and raise the cap row — is the founder's, and it is a one-row UPDATE
    either way.
- **S-8 accepted, not fixed — with a written trigger, 03:35.** The MCP rate
  limiter is `RateLimitingMiddleware`, in-process, and the service runs
  `--max-instances 2`, so the effective limit is already **twice** what it
  says — this is a live 2× overshoot, not a hypothetical one. Deliberately
  left as is for now: the friend tier is a handful of founder-minted keys, and
  the thing that actually protects the shared money is the budget ledger built
  today, which is per-owner, DB-backed and therefore correct across any number
  of containers. The rate limiter only shapes request burst. **The trigger to
  replace it with a DB-backed request ledger or a gateway limit is task 6** —
  the moment sign-in makes the key-holder set open-ended — **or any change
  that raises `--max-instances` on the MCP service before then.** Rejected:
  building it now (it would be the third scarce-resource ledger in one night,
  guarding the cheapest of the three).



## 2026-08-12 — Task 4: onboarding by conversation — the interview, the profile door, the setters, the typed six

Built 02:15–02:50 BST. Six decisions, one explicit deferral, one boundary.

- **create_profile is operator-only until sign-in lands (task 6), 02:20.**
  Whoever can create identities decides who the machine answers to, so the
  gate is the bootstrap scope (the founder's operator token) or the local
  stdio door — a minted friend key is refused, and the refusal is tested
  adversarially. Rejected: letting any key holder create profiles (identity
  minting stays with the person who answers for the machine until Google
  sign-in gives strangers their own identity path).
- **adopt_owner is the one sanctioned re-scope, and it lives in
  mcp_server.session, 02:25.** The app role's own policy (WITH CHECK
  `profile_id = app_owner()`) means a new profile row can only be written
  AS the owner it belongs to — so the tool adopts the new id for the
  insert and scopes straight back for its audit row. A scan now pins
  `set_config` to session.py alone: anywhere else it would be a tool
  smuggling identity past the door — the B-GAE-027 shape at the MCP layer.
  Proven on the real policy both ways: refused without adoption, created
  with it, rolled back after.
- **intake-v1 is served data, and its standard is a referee's, 02:15.**
  The third versioned prompt closes 0013 §6 M1: one fact per block, dates
  and numbers asked for, honest tool levels, unpaid experience on the same
  footing, drafts only — the owner confirms, never the interviewer. The
  shape is test-pinned in lockstep with cv.blocks.BLOCK_KINDS so the
  interview and the writer quartet can never drift apart.
- **The channel never echoes, 02:40.** set_notification_channel stores the
  one secret an owner brings (the ntfy topic IS the capability to reach
  their phone) and returns `{updated}` — the audit row records that a
  change happened, never the value. set_notion_token_ref stores a pointer
  and refuses token-shaped values (ntn_/secret_) outright.
- **M4 stops at six, 02:50.** Typed envelopes on daily_brief,
  get_reading_batch, submit_reading, serve_cv, submit_cv, get_apply_queue
  — and the boundary is itself a test, so a 46th typed tool is a decision
  rather than drift. Noted so nobody logs it as a bug later: declaring an
  output schema changes fastmcp's *Python client convenience* (`.data`
  hands back a generated model), while the wire format is unchanged; the
  tool tests read `structured_content`, the raw envelope a real client
  validates.
- **Per-owner Notion filing is DEFERRED, explicitly, 02:55.** One
  credential opens one board. Onboarding now STORES each owner's ref, but
  nothing reads it, and the filing stage keeps its B-GAE-027 refusal for
  non-credential owners. Trigger to build: the first real second owner who
  wants a board — then a resolver (Secret Manager read, by ref, engine
  side) REPLACES the refusal `if`; the B-GAE-027 entry already pins that
  it must never simply be deleted. Until then a second owner's product
  runs whole minus Notion cards: nudges, queue, tray and engine-rendered
  CVs all work.
- **M5 stays note-only** (0013 §6's own instruction): the prompts/resources
  primitives are listed, not built, until a real client wants them.

## 2026-08-12 — Task 3: the night splits in two, and the run report folds back into one

The nightly job now runs world work once and a personal pass per owner. Four
choices in it were not obvious, and one of them is a security decision.

- **World stages are the first eight, personal the last seven, and the pinned
  order did not move.** `STAGE_CMDS` is untouched — the split is derived from
  it by a name set (`pipeline.owners.PERSONAL_STAGES`) rather than by
  restructuring the table, so the stage order stays a single readable list and
  the existing test that asserts `register < classify < discover` keeps
  working on the same object.
- **`salary` and `eval` are in the personal half even though neither reads a
  profile.** A salary parse and a grounding score are the same answer whoever
  asks. They are per-owner because the ROWS are: `role_listings` reaches an
  owner through `target_companies.owner_id`, so scoping partitions the work
  instead of duplicating it — measured before relying on it, 894 companies
  with **0** null owners and **0** of 12,923 listings unreachable by that
  seam. `eval` gains something real from it: a shared average lets one owner's
  broken extraction hide inside everyone else's good numbers, and the stage
  that fails should belong to the person it failed for.
- **Per-owner detail rides as a FIELD on the run report, never as extra array
  elements.** `v_status_stages` counts `jsonb_array_elements(stages)` and the
  public status page renders that as "15 of 15 stages". Appending per-owner
  rows would have turned it into 29 of 29 on a page the founder points other
  people at. So `finish_run` folds N owners back into one object per stage
  name and adds an `owners` list; the four existing fields keep their names
  and meanings, and for a single owner the summary is that owner's verbatim.
- **The owners in that report are NUMBERED, not named — this is the security
  decision.** `pipeline_runs` is world-readable: every key holder can call
  `get_run_report`, and the mint-key operator note has always described that
  table as machine-health-only. A `profile_id` in there would hand out the
  exact value a cross-owner read attempt needs, so per-owner lines carry a
  per-run `seq` and nothing else. The seq → owner map is printed to the run's
  own stderr, which is the operator's log and nobody else's. Chosen over
  hashing the id (still a stable cross-run identifier) and over omitting the
  detail entirely (which would have made a failed owner invisible).
- **Fan-out shape now, fan-out deployment later.** `task_shard()` reads Cloud
  Run's `CLOUD_RUN_TASK_INDEX` / `CLOUD_RUN_TASK_COUNT` and falls back to 0 of
  1, so tonight is one task, every owner, serially — identical to before.
  Owners are sorted by `profile_id`, not `created_at`: the shard has to agree
  across tasks that never talk to each other, and creation order stops being
  stable the first time a profile is deleted. Raising `taskCount` fans it out
  with no code change, which is the whole reason the loop was not written as a
  plain serial `for`.
- **Filing REFUSES for other owners rather than misfiling.** There is one
  Notion credential and it opens one person's board. Scoping the selection
  stops the stage mixing owners but cannot make a shared board private, so
  filing runs for the credential's owner and returns a stated skip for anyone
  else. This is a deferral to task 4, recorded as one in the bug log, not a
  fix — and the `if` that implements it must be replaced rather than removed
  when per-owner Notion lands.

Two defects came out of writing this, both the same shape — a per-owner value
read blind, in code no MCP tool touches and so untouched by task 1b's sweep:
[[B-GAE-027]] (one owner's queue to another owner's phone, and their rows
stamped so they were never nudged for them) and [[B-GAE-028]] (one owner's
apply window applied to everyone's deadlines). Both were **measured against
unmodified HEAD** with a probe rather than asserted, because the fixes add a
required argument and a `TypeError` proves nothing about leaking.

`pipeline.report` came off `BLIND_WRITERS` (13 → 12): the fold writes a nested
structure into a `jsonb` column, precisely the shape a `FakeCursor` cannot say
anything true about.

---

## 2026-08-11 19:40 BST — Task 2b: the MCP door runs as `goal_a_app`, and the proof had to remove the application filter to mean anything

The cutover task 2a deliberately split off. Since 2a, RLS policies existed on
all 28 tables and refused nothing in production, because every door connected
as `postgres`, which carries `rolbypassrls`.

- **Seven lines, not thirty-one.** `src/mcp_server/session.py` wraps
  `get_conn()`: resolve the owner FIRST on the engine role, THEN
  `SET LOCAL ROLE goal_a_app`, THEN publish `app.owner_id`, THEN yield. The
  ordering is load-bearing — `access_keys` and `profiles` both carry policies
  keyed on the owner, so assuming the role first would make the door resolve
  every caller to nobody. The 26 tool call sites are untouched: each module
  imports `scoped_conn as get_conn`.
- **That convenience is also the trap, and it was named in the relay before it
  was hit.** Because the tests' fakes still patch `<module>.get_conn`, the
  whole offline suite passes without ever exercising the role switch. A green
  suite says nothing about this change, so the proof is
  `tests/test_rls_cutover.py`: a real tool, over a real `Client`, on a real
  connection, **with `fetch_queue`'s `where owner_id = %s` removed**. With the
  filter in place owner B reads nothing whether or not RLS is live — the test
  would have restated task 1b and worn a security badge. Seen red first: owner
  B read 20 of owner A's queue rows, and the tool body ran as `postgres`.
- **Scope, decided rather than drifted.** Cut over: the MCP door only. Left on
  `postgres`: `transport.py` (it resolves the key — step 1's problem), the
  nightly job (world work spanning owners until task 3; B-GAE-018 would crash
  its `merge` under this role), and the dashboard and status page (the
  founder's own surfaces, curated views, no stranger reaches them). The rule
  that falls out and is written into the module: **anything a key holder can
  reach runs as `goal_a_app`; everything the founder alone reaches does not.**
- **The cutover broke one tool, and the suite could not see it (B-GAE-023).**
  `submit_reading` → `accept_reading` runs `delete from role_skills`, and the
  role holds no DELETE by design. Found by grepping `src/` for DELETE while
  asking what the role cannot do — not by 868 green tests. **The founder chose
  the narrow grant** (0057, asked because it edits a property he set in 2a):
  `role_skills` is derived and rebuilt from the JD on every read, so this
  narrows "no DELETE, ever" to the keep-all tables it was written for. The
  rejected alternative, a `SECURITY DEFINER` owner-checked delete, is tighter
  and is the shape to revisit if a second table ever needs this.
- **A pinned test was rewritten, not relaxed.**
  `test_the_app_role_cannot_delete_anything` became
  `test_the_app_role_can_delete_from_exactly_one_derived_table`, asserting the
  grant set EQUALS `{role_skills}` — so both widening it and revoking it fail.
  The class guard added alongside scans `src/` for every INSERT/UPDATE/DELETE
  and checks `has_table_privilege`, which is what would have caught B-GAE-023
  before the cutover instead of during it.
- **Measured:** suite 870 passed / 0 skipped with `RUN_DB_TESTS=1`, 838 / 32
  offline, no-`.env` lane green, container green (798 / 72), entrypoint exit 2.
  All 19 read tools byte-identical under the app role against live data —
  the founder's product is unchanged.

## 2026-08-11 03:30 BST — B-GAE-017 fixed ahead of task 3, and the cutover deliberately NOT started at the end of a long session

Two sequencing calls, both worth the record.

**The cutover was not started.** Task 2b turns out to be a **31 cursor-site
refactor across seven tool modules**, every one of which changes a tool's
security context — measured, not estimated. Beginning that at the end of a
session that had already shipped three commits is how the security boundary
acquires a quiet mistake, and the relay's own rule says to stop at a green
commit and say so. The design is settled and written down for the next
sitting: resolve the owner FIRST on the engine role (the `access_keys`
bootstrap solves itself, because the verifier already runs on its own
connection), THEN `SET LOCAL ROLE goal_a_app` and `set_config('app.owner_id')`
for the tool body. Two things gate it — B-GAE-018 crashes the nightly `merge`
stage under the app role, and the nightly job genuinely needs to span owners
until task 3 gives it a per-owner loop. So the MCP door cuts over first; the
job follows task 3.

**B-GAE-017 was fixed instead, out of task order.** It was assigned to task 3,
but the task-1b fuse is out: the day a friend key exists, a key holder can read
the founder's lens and dismiss his flags. A live hole outranks a deferred
defence-in-depth, and the founder's own rule is that security ordering wins.

- **Migration 0056** gives `review_items` a **nullable** `owner_id`, and the
  nullability is the design: NULL means "an ambiguity about a public fact,
  shared by everyone" — two people settling one sponsor ambiguity once is
  still correct — and a value means "derived from one person's lens". The
  policy becomes owner-or-world on read AND write.
- **The idempotency key gained the owner**, or the first person to flag an
  organisation would silently suppress everybody else's flag for it — the same
  shape as B-GAE-018's global dedupe key, which is now two instances of one
  pattern rather than a one-off.
- **The promotion-review cap is per-owner too.** A shared cap let one person's
  unresolved flags hold everyone else's promote pass shut, which matters
  because it is currently full at 20/20.
- Proven by attempting it: two owners in a scratch schema, B refused A's flag
  on read and on dismissal, and A's flag no longer suppressing B's for the same
  organisation. The dismissal case was watched going red against the unscoped
  source before it was trusted.

The lesson is the part to carry: **task 1b's decision was recorded honestly and
its premise was still wrong.** "Measured, then decided" protects against
forgetting, not against measuring the wrong thing — the four review kinds were
counted, and what their evidence CONTAINED was never looked at. `mcp_audit`
and `pipeline_runs` are on the same "world data by kind" list today.

## 2026-08-11 02:40 BST — Task 2a: RLS was enforcing nothing, so the policies were written against a role that cannot bypass them — cutover deliberately split off

The measurement that decided the whole task: **every door — engine, MCP
server, dashboard, status page — connects through one `get_conn()` as
`postgres`, and `postgres` carries `rolbypassrls`.** RLS was on across 28
tables and refusing nothing, and policies alone would not have changed that by
one row. `FORCE ROW LEVEL SECURITY` would not have either — FORCE removes the
table-OWNER exemption, not the role attribute. Writing policies for
`anon`/`authenticated` was considered and rejected: nothing in the codebase
uses those roles, so an isolation test against them would have passed while
proving nothing, which is this project's documented recurring defect wearing a
security badge.

- **`goal_a_app` (0052)** — NOLOGIN, NOBYPASSRLS, owns no table.
  `SELECT/INSERT/UPDATE` only: **no DELETE, ever**, so "keep-all tables never
  lose rows" stops being prose and becomes a privilege. Proof needs no new
  credential — `SET ROLE` drops the bypass because RLS is evaluated against
  `current_user`.
- **Policies on all 28 tables (0053)**, in three shapes: owner-scoped by
  `owner_id`, derived via `EXISTS` on `target_companies` (the seam task 1b
  proved in the application layer), and world data readable. Getting the world
  half wrong is the quiet failure — RLS on with no policy denies everything,
  so the nightly run would report all-stages-ok having seen an empty census.
  The caller is a per-request setting, not a JWT claim, because friend keys
  are database rows; `app_owner()` **fails closed** (unset → NULL → no match).
- **The DEFAULTs are gone (0054).** Every INSERT into the five tables was read
  first: all pass `owner_id` explicitly, so the default protected nothing and
  only stood ready to hide a mistake. Now an unstamped write raises.
- **The founder chose the split** (asked, because it touches the 06:30 lane):
  policies and proof now, engine cutover its own sitting. So **these policies
  protect nothing in production yet** — the application-layer scoping from
  task 1b is still the only boundary, and the mint script says so to anyone
  holding a key.
- **Proven by refusal, then re-proven by mutation.** A loosened policy and an
  *uncorrelated* `EXISTS` were each installed deliberately and watched turning
  the tests red. The second probe mattered: it showed the four stranger-based
  tests all PASSED while owner B read all 12,584 listings — so a second real
  owner was added, and that is what catches the likeliest regression.

## 2026-08-11 02:40 BST — The security review earned its place: three holes closed (0055), two logged open

Run adversarially against task 2a, as the phase card requires. It confirmed
the parts that matter were sound — all 12 views carry `security_invoker=true`
(a definer view would have defeated RLS entirely), no `SECURITY DEFINER`
functions, and `app.owner_id` is unreachable from the tool surface — and then
found six real things.

Closed in **0055**: `decisions` was left open to `anon`/`authenticated` on a
premise I got wrong — I called it "public reference data" and it is the
founder's private strategic log with live Notion URLs, readable by a key
Supabase treats as public and that **task 6 will ship into a browser**;
`mcp_audit` sat on the world list holding every owner's verbatim tool
arguments, now append-only for the app role; and `target_roles`' global
`UNIQUE (search_title)` (B-GAE-010) became `UNIQUE (owner_id, search_title)`,
because under RLS a duplicate-key error reports the existence of a row the
policy says is invisible — an enumeration channel, not just a collision.

Also corrected: **my own test file's docstring claimed write proofs that did
not exist.** The `WITH CHECK` half of eleven policies had zero coverage behind
prose asserting the opposite. Written properly now, including the derived-table
smuggle case.

Left OPEN with entries rather than silently fixed: **B-GAE-017** —
`promotion_review` flags carry the owner's own lens, so task 1b's "review_items
is world data" decision was honestly recorded and its premise was still wrong;
and **B-GAE-018** — `role_listings.dedupe_key` is globally unique, so a second
owner's identical advert is swallowed and they silently never receive the job.
Both belong to task 3 and both are named there.

## 2026-08-11 01:05 BST — Task 1b: the owner is an ARGUMENT, never a default — and the fuse comes out on a refusal, not on a review

Task 1a answered *who is calling*; the reads it left ownerless meant a
friend's key would have opened the founder's queue, so
`scripts/mint_access_key.py` refused to mint for anyone else. This is the
sitting that scopes them and removes that fuse.

- **Required positional `owner_id`, no default, on all eight**
  (`fetch_queue`, `fetch_skill_gaps`, `fetch_job`, `fetch_job_gap`,
  `history_for_role`, `mark_applied`, `snooze_listing`, `load_channel`). A
  default owner is right for user one and silently wrong for user two with
  nothing failing in between — the same shape as the `owner_id` column
  DEFAULTs task 2 drops. Pinned by tests that call each function *exactly as
  Phase 8.5 called it* and require a `TypeError`; those assertions fail
  against the pre-1b source, which is what makes them guards.
- **`role_listings` keeps NO owner column** — the seam is proven, not
  replaced. Every listing-level query walks `role_listings.company_id →
  target_companies.owner_id`, the same seam `v_apply_queue.owner_id` is built
  from, and a test fails the day a second source of truth appears. The writes
  take that join too: a role_id is guessable, and stamping another owner's
  listing is as damaging as reading it.
- **`fetch_job` returns None for "not yours" and "no such listing" alike.**
  Distinguishing them would confirm that a given role_id exists for somebody.
- **`send_test_nudge` was taken here, not deferred to task 3.** It was the
  only unscoped call whose effect leaves the database — it read the first
  profile's channel whoever asked, so a friend's key would have fired a push
  at the founder's phone. Deferring it would have meant un-fusing on "B
  cannot read A's rows, but B can reach A's phone". `load_channel` now takes
  a required owner; `nudge_stage` and `notify_failure` resolve
  `default_profile_id` and pass it. That is the SAME row the blind query
  picked (`order by created_at limit 1`), so nightly behaviour is unchanged
  and `scripts/run.py` is untouched — but the owner is now a value the stage
  holds, which is what task 3's per-owner loop needs. ⚠ It is still an engine
  stage change: the sacred-lane ritual (rebuild → manual
  `gcloud run jobs execute --wait` → verify stages ok → only then cron)
  applies whenever this is deployed.
- **Two surfaces stay unscoped, decided rather than missed**, and the mint
  script now says so to whoever holds a key: `review_items` are ambiguities
  about PUBLIC facts (world data, like the census — two people resolving one
  sponsor ambiguity once is correct; the `promotion_review` kind gets its
  owner in task 3), and `pipeline_runs` carries machine health only, the same
  class the public status page publishes on purpose.
- **Proven by refusal, in a scratch schema, both ways.**
  `tests/test_owner_scoping.py` seeds two owners into tables copied from
  production's shapes with `like … including all` and views created from
  production's own `pg_get_viewdef` output — so the logic under test is the
  real logic. Every refusal is PAIRED with owner A making the same call
  successfully; without that pairing an empty fixture passes. Both a read
  (`fetch_job`) and a write (`mark_applied`) were mutated back to their
  pre-1b SQL and the test was watched going red before being trusted.
- **The fuse is deleted in this commit**, as instructed — not before, and not
  to unblock anything. What it does NOT buy: RLS is still task 2, so the
  database itself refuses nothing and the engine connects as the owner role.
  A key is a door lock, not a vault; the script says that too.

## 2026-08-11 01:05 BST — Migration 0051 drops and recreates rather than replacing, because owner_id belongs first

`v_skill_gap` was the one read in the 1b map with no owner column at all —
demand came from everyone's queue and `i_have_it` matched anyone's skills.
`CREATE OR REPLACE VIEW` can only append columns, so both it and
`v_skill_demand` were dropped and recreated with `owner_id` leading, and
`my_skills` now joins on the same owner rather than on `skill_norm` alone.
`security_invoker = true` is stated explicitly on both (B-GAE-006: reloptions
do not survive a replace) and verified afterwards along with the grants;
`get_advisors` reported no new finding. Measured after: 1 owner, 921 gap rows,
908 missing. Three bugs were found and logged during the sitting — B-GAE-010
(`target_roles.search_title` is globally unique, so two users cannot want the
same job title — deferred to task 2 deliberately, and it WILL bite task 4's
onboarding), B-GAE-011 (a scratch fixture that read production's tables),
B-GAE-012 (a tool promising a return key it never returns).

## 2026-08-10 17:59 BST — U8b (the founder's mid-session amendment, found in the log): the fact base gets its own door — drafts only, owner confirms, retire is a stamp

Caught at phase close: `git log` showed a parallel-session commit
(`f1a5908`, 17:15) amending plan 0013 with **U8b** — cv_blocks writer tools
"ship WITH task 0". The tool-count check (37 measured = 37 pinned) proved no
code had landed with it; it was unbuilt spec belonging to this phase, so the
phase re-opened rather than closing over it.

- **Four tools, one trust model** (migration **0049**: `retired_at` +
  `source`): `add_cv_block` ALWAYS writes `confirmed=false` — a client AI
  proposes, only the owner confirms (the reading tray's "propose, don't
  decide", applied to the fact base; the confirmed-only CV path can never
  see an unapproved draft). `list_cv_blocks` serves both states so drafts
  can be shown for approval. `confirm_cv_block` records the OWNER'S yes.
  `retire_cv_block` stamps — keep-all, never a delete — and
  **load_cv_blocks now excludes retired rows**, so a retired fact stops
  serving in drafts, lists and CVs alike.
- Kind whitelist mirrors the render sections (role / achievement /
  skill_evidence / education) — writer-side, the criteria.writer style.
  Tools 37 → **41**; the Phase 9 CLAUDE.md, relay, README and dev.md were
  re-measured and corrected, and the public snapshot rebuilt so the phase
  close ships what the phase actually contains.

## 2026-08-10 17:47 BST — Task 0 (U8) ungated mid-session and built: serve-all CV — AI decides relevance, code decides truth, the engine renders

The cv_blocks gate opened DURING the phase (0 at session start → 22 rows,
all confirmed: 8 achievement · 6 role · 6 skill_evidence · 2 education —
the founder's parallel session, exactly as the relay predicted), so the
task-order rule "build task 1 first and return" resolved to: return now.

- **The serve-all correction implemented as decided** (2026-08-10 founder
  call, commit 1b3994b): `serve_cv` hands the client AI the job + **every**
  confirmed block — the anti-filter is PINNED by test (listing skills that
  match one block still serve all of them); the engine's literal skill
  match rides as `skill_hint`, a hint never a limit. `cv-v1` is server-side
  versioned DATA like extract-v1 — a client can never override the
  ATS-safe/invent-nothing rules.
- **The gate is the EXISTING one, reused not rebuilt:** submit_cv traces
  every bullet against ITS block's fact_text via cv.truth.trace_bullet
  (numbers must all appear; ≥75% content-word grounding) — an untraceable
  bullet is replaced by the verbatim fact (same fallback contract as the
  engine-side path), unknown block ids are dropped and REPORTED, and
  rendering reuses cv.render (single-column ATS-safe .docx) + cv.filing's
  save. The docx bytes never ride the MCP wire — the path does.
- **The old engine-side generate_cv stays** (the no-AI fallback the daily
  filing stage uses — plain facts when no client AI is present). The two
  paths share blocks/truth/render/save; only selection+phrasing differ, and
  that difference IS the U8 design. Tools 35 → **37**.

## 2026-08-10 17:40 BST — Task 6 acceptance: proven as an integration walk + a read-only live twin — the founder's live lens is NOT flipped for a demo

Phase 8.5's acceptance ("a care-home test lens set up by conversation alone
produces a correct queue with receipts — no code edit anywhere").

- **Chose: a 5-step integration test over the REAL in-process MCP server**
  (tests/test_lens_e2e.py: words→codes over MCP; codes→rule row + auto-knock;
  the same picker picks care cards; the tray matches care titles under care
  patterns; a source scan proving no universal-chain module bakes an industry)
  **plus a read-only live walkthrough** on the real database. **Rejected:
  flipping the founder's single live profile to a care lens** — it would
  hijack tomorrow's 06:30 queue, fire a real care sweep against his lens, and
  race his parallel sessions, all for a demo; and a second live profile
  cannot be driven "by conversation" until Phase 9 binds identity to the
  tools (client_id from the token — already decided, not built here).
- **The live twin, measured 17:39 BST, all read-only:** care doors
  **49 / 5,087 knocked (0.96%)** — one auto-knock batch (2,000×4 workers)
  reaches ~40%, the second run crosses the U4 >50% target; **313 open care
  listings ALREADY sit at register sponsors** (the all-industry ads layer
  merged them — a care queue is non-empty on day 1, receipts riding);
  **0 of 313 have JDs** — exactly U5's gap — with **413 care-titled Reed
  ads** at sponsors ready for the drip (~2 nights at cap 200); the tray
  serves them as JDs land (U7 matches care titles under care patterns).
  Every brick built this phase is precisely the missing link the
  measurements show. The lens is rows; the machine does not care whose.

## 2026-08-10 17:37 BST — U7 the tray un-starves: a labelled near-miss tier the client AI may accept or SKIP — and a skip is a stamp

Phase 8.5 task 5b, migration **0048**.

- **Chose the near-miss tier over widening the patterns.** Widening
  target_roles patterns would fix the founder once and starve the next
  narrow user the same way; a labelled tier is the universal fix — the
  machine stays deterministic (it labels, never judges) and the client AI
  supplies the judgement, which is exactly the code/AI split the product is
  built on. Non-matching-but-stageable rows stage as `staged_tier =
  'near_miss'`, CAPPED at 25/run (a drip to triage, not a 1,083-row flood);
  matches stay uncapped and always serve FIRST (batch ordering pinned).
  Kill keywords exclude BOTH tiers — an explicit no is a no.
- **A skip is a STAMP** (`reading_skipped_at`, new `skip_reading` tool —
  audited, 35th tool): plain unstaging would re-stage the same row every
  night forever; keep-all's "removals are stamps" already had the answer.
  accept_reading and skip_reading both clear `staged_tier` on the way out.
- The extraction prompt (`extract-v1`) is deliberately UNCHANGED — the
  near-miss judgement lives in the get_reading_batch/skip_reading tool
  contract, not in the extraction instructions; extraction quality and
  relevance judgement are different jobs.
- Pairs with U5: drip-fetched ad JDs whose titles miss the patterns now
  reach the tray labelled instead of vanishing — supply and serving fixed
  together.

## 2026-08-10 17:31 BST — U5 Reed JD drip: a new 06:30 stage (deliberate pin change), budget-honest by construction, proven live before the lane meets it

Phase 8.5 task 5. The stage order gains **jd_drip between merge and promote**
— a deliberate contract change, pin test updated in the same commit.

- **Why that position:** merge creates tonight's ad rows; the drip
  immediately gives them full JDs, so salary/deadlines/eval/stage_reading
  enrich them the SAME run. The tray (U7's supply side) gains real text the
  night a job arrives, not a day later.
- **Reed-only, and honestly so:** Adzuna exposes no details endpoint — its
  1,833 JD-less rows wait on board discovery. Reed's pool measured at
  **3,707** open JD-less listings. At cap 200/night the backlog drains in
  ~19 nights while new merges stay current (queue rows jump the line:
  in-queue first, then newest).
- **Budget honesty is structural:** the drip reads the SHARED
  api_quota_ledger before picking (never exceeds Reed's 950/day even after
  the broad sweep spent it), ledgers every attempted call (failures stay
  spent), per-item commit, per-item error isolation. clean_html is the ONE
  existing stripper (fetch/feeds), aliased — never a second copy;
  reed_job_details joined aggregators.py, the one Reed HTTP home.
- **Proven live before the lane meets it:** a --cap 2 local run fetched 2
  real JDs (5.2k chars each, zero HTML tags, both in-queue rows —
  queue-first ordering visible), ledgered 2 calls. **Standing obligation at
  push time (⛔): this touches scripts/run.py, so rebuild → `gcloud run
  jobs execute goal-a-daily --wait` → only then may the 06:30 cron meet
  it.**

## 2026-08-10 17:24 BST — U6 + a hardcode the audit missed: the QUEUE VIEW carried the founder's title regex; it now reads target_roles — and the dashboard browses all 98,638 sponsors

Phase 8.5 task 4, migrations **0046** + **0047**.

- **Found: `v_apply_queue` hardcoded the founder's role-title regex** (~20
  software title stems in the WHERE clause). Plan 0013's audit listed four
  hardcode spots but scanned CODE — this one lives in a VIEW, and it made
  the phase's acceptance ("a care lens produces a correct queue, no code
  edits") impossible: care titles could never enter the queue. **Chose: the
  gate becomes an EXISTS over the owner's target_roles** (normalised
  substring, hyphen/space-insensitive — the SQL twin of
  build_role_matcher). 10 behaviour-preserving patterns were seeded into
  the founder's rows first (ML Engineer, AI/ML, Applied AI, Generative AI,
  GenAI, Gen AI, AI Product, Forward Deployed, Solution Engineer, Solution
  Architect — the stems the regex had that his 39 rows lacked), then
  **verified: 272 rows before, 272 after, 0 lost**. Seeding target_roles is
  behaviour-preservation of an existing stored behaviour (the regex),
  exactly like 0045's it-jobs seed — NOT invention of personal facts (the
  cv_blocks rule is untouched).
- **Caught by get_advisors right after 0046: CREATE OR REPLACE VIEW drops
  reloptions**, so the four replaced views lost `security_invoker=true`
  (ERROR-level lint; every other view carries it). 0047 restores it same
  session. Standing lesson for every future view migration: replace, then
  re-assert security_invoker, then advisors.
- **v_today** gained `is_new_today` + `skill_have`/`skill_asked` (the fit
  column's receipts, role_skills × my_skills via synonyms, owner-scoped) —
  rendered as a "skills 3/7" chip only when a reading exists (0/0 hides).
  **v_scorecard** gained new_today + sponsors_total. **v_sponsor_browse**
  (new): the Sponsors tab's entire read surface; plain-English industries;
  never ats_token.
- **Dashboard stays zero-JS and view-only:** the Sponsors tab is a GET
  filter form (re-carries existing query params as hidden inputs) + a
  table; the FILTERED pager total rides each row via `count(*) over()` —
  one query, honouring "no extra counting queries". The complexity pin now
  requires v_sponsor_browse in the allowed set; raw tables stay banned.

## 2026-08-10 17:12 BST — U3 universal reads: one shared tokenisation, generalise-not-duplicate, and the searches carry their receipts

Phase 8.5 task 3.

- **One tokenisation for the whole layer:** `criteria.lens.word_patterns`
  (prefix-stemmed ILIKE patterns) now feeds the translator, search_sponsors,
  search_hiring and the words-path of get_skill_gaps — the same words mean
  the same match everywhere, and there is exactly one place to tune it.
- **`search_sponsors` filters on the VIEW'S descriptions**, not on re-derived
  codes, so every row's `industry_descriptions` IS the receipt for why it
  matched; join to sponsor_census only for board facts (probe_outcome,
  jobs seen — never ats_token). Empty/stopword-only words = no industry
  filter (a browse), not an empty answer. Boards-first ORDERING always
  stands; `with_boards_only` adds the FILTER.
- **`search_hiring` spans the two stored worlds** — tracked open listings
  first (a live board = apply-able today), census sightings fill the
  remainder (every census org is on the register by construction); defensive
  Python-side cap on top of SQL limits. **Rejected:** searching
  aggregator_ads here — ads are employer-level supply (the merge already
  lifts them into role_listings); a third source would double-serve the same
  jobs.
- **Skills-gap search extends `get_skill_gaps` in place** (optional
  `role_words` → per-lens gap over role_skills, owner-scoped i_have_it) —
  no new tool, honouring generalise-don't-duplicate; the full skills-lens
  moat stays Phase 9 (0010 item 5 is 🧠 P9). `list_software_companies`
  likewise stays as the founder convenience; search_sponsors is its
  universal version (0013 §2).
- Live Leeds check ran the exact SQL: care sponsors in Leeds answer with
  receipts — and almost all show probe_outcome null, the 0.7% truth U4's
  knock-on-demand exists to fix. Tools 32 → **34**.

## 2026-08-10 17:04 BST — U4 knock-on-demand: a lens CHANGE starts the door-knock itself; the brief carries the honest coverage line

Phase 8.5 task 2b. The census door-knock lives in its own lane (manual/MCP,
own lock) — it is NOT in the 06:30 run, so "the front of the probe queue"
alone would knock nothing for a new lens until someone remembered to sweep.

- **Chose: `set_promotion_rule` triggers the knock itself** — when
  industry_codes are passed AND actually change, the owner-lens sweep starts
  DETACHED (batch 2,000, workers 4, same script the run_sweep tool spawns;
  the sweep lock makes a double-start exit instantly). Reported in the
  payload (`knock: {started, log_path}`) and the next-hint flips to
  sweep_status. **Rejected:** relying on the client AI to follow a "now call
  run_sweep" hint (the spec says enqueue ON lens creation — build the
  trigger in, don't hope), and adding a probe stage to the 06:30 lane (the
  sacred-lane blast radius for something the on-demand trigger already
  covers).
- **The brief tells the truth about coverage** (the U4 expectation-setting):
  `assemble_brief` gains `lens_coverage` {knocked, total, pct} measured over
  the same slice the Pass-2 picker sees (registry-matched + lens codes), and
  daily_brief's state appends "your industry's doors are still being knocked
  — N/M done" while pct < 50. The founder at 98% never sees the line; a
  fresh care lens at 0.7% always does. Also fixed a near-trap: the tweak
  path (floor/auto/category only, or re-sending identical codes) must NOT
  knock — pinned by test.
- assemble_brief is called ONLY by the daily_brief skin (verified by grep) —
  nothing here touches scripts/run.py or the stage order.

## 2026-08-10 16:56 BST — U1 keystone: promotion_rules IS the owner's lens row — probe pick, ads category and nightly promotion all read the same rules

Phase 8.5 task 2, the audit's "one real blocker" removed.

- **Chose: `pick_owner_lens_batch` resolves the codes from the owner's
  promotion rule** (`owner_lens_codes`: rule codes, else the SOFTWARE_SIC
  bootstrap so a rule-less database behaves exactly as before). The picker
  seam `(cur, n)` is unchanged — hiring-first and injected pickers untouched.
  **Rejected:** passing codes through every runner signature (breaks the
  picker contract for zero gain) and defaulting a rule-less DB to an empty
  pick (honest-sounding, but it would silently kill the founder's sweep the
  day the rule row is deleted).
- **Renames follow the meaning:** `run_software_sweep[_parallel]` →
  `run_lens_sweep[_parallel]`; the script flag and MCP tool arg become
  `--owner-lens` / `owner_lens`. The script keeps `--software-only` as an
  alias (shell muscle-memory is free to support); the TOOL drops it cleanly —
  hosted clients re-list tools per session, and one flag with two names in a
  schema is worse than a clean rename.
- **The Adzuna category joins the lens row** (migration **0045**:
  `promotion_rules.adzuna_category`, founder seeded 'it-jobs' so his sweep is
  byte-identical). Resolution in the runner: explicit CLI wins → owner's rule
  → 'it-jobs' bootstrap; the literal 'all' means NO category narrowing (the
  whole-inventory walk Reed already does). **Rejected:** a my_constraints
  kind (scatters the lens across two tables when the point of U1 is ONE row a
  conversation can set).
- `TECH_NAME_PATTERN` untouched — ordering only, as the spec demands.
- The 06:30 lane is untouched: the daily run never imports probe_pick (the
  sweep is its own lock + lane), verified by grep before building.

## 2026-08-10 16:44 BST — U2 translator NEVER writes: words→codes serves candidates; the write stays with set_promotion_rule

Phase 8.5 task 1. The spec's sentence "matched codes written to THEIR
promotion_rules row" could read as one tool that searches AND writes. Split it.

- **Chose: `find_industry_codes` is a pure read** — deterministic token search
  over `sic_codes` (prefix-stems so "homes" matches home/homes and
  "activities" matches activity/activities; user words reach SQL only as
  bound parameters), ranked by tokens-matched then census sponsor count, each
  candidate carrying its receipts (`matched` names the OWNER'S words, not
  internal stems). The client AI confirms codes with the owner, then the
  EXISTING `set_promotion_rule` writes them. **Rejected:** a search-and-write
  tool — a fuzzy match silently becoming the owner's lens breaks
  provisional-until-confirmed, and live data showed why: "care homes" matches
  11 codes including "Farm animal boarding and care" (8 sponsors) — a
  candidate list is honest, an auto-write would be wrong.
- **`add_skill` upserts by `skill_norm`** (the ONE normaliser), coalescing
  absent fields and reviving retired rows; `learned_at` + `evidence` pinned
  from day one (the learning-curve model's data). Migration **0044** adds
  `learned_at` AND a unique index on `(owner_id, skill_norm)` — measured
  first: 22 rows, 0 dupes, 0 null norms — so one-row-per-skill is a database
  guarantee, not a writer convention. `my_skills` had never had a writer
  before; it does now, and the tool audits like every action.
- Tool count 30 → **32**; the pinned toolset test, README's test count
  (696 → 713 collected) and dev.md's table updated deliberately — assertions
  tightened, never loosened.

## 2026-08-10 13:50 BST — The flip is DONE, into a public repo nobody's tracking knew existed — and the public/private contract is now permanent

Founder's word given in plain terms ("push it to public job-engine and we can
keep working for the next phases in private"). What made the task interesting is
that the repo check he asked for first turned up an **unrecorded early flip**.

- **`JOB-ENGINE-` already existed** — public, one commit, authored by the
  founder 2026-08-03 19:19 BST, from the walkthrough evening. No phase record
  mentions it; task 7 was tracked as "prepared, awaiting word" throughout.
  Cloned and put through the full leak battery before anything else: **clean**
  (`.env.example` is bracketed placeholders; the founder's name appears only in
  LICENSE/pyproject/fixtures/deliberate docs — it predates the security pass and
  got lucky). But its README was **stale and partly false**: 592 tests (reality
  686), 41 migrations (43), and it advertised *"a hard spend cap"* — retired the
  very day it was pushed.
- **Chose: force-push today's verified snapshot over it** (`7d8cf62 → adbdf31`,
  single commit, history depth 1). **Rejected:** a second, new public repo (two
  shop windows drift apart and split the portfolio's identity — the earlier
  "create an empty repo" instruction is void); making the private repo public
  (its git history carries the Supabase project ref and the pre-fix leaks —
  permanent no, this is WHY the snapshot squashes).
- **A leak-in-waiting was found and destroyed on the way:** a July-20 local
  export sat at the snapshot script's default target path — containing
  `ops/apply-shortlist.md`, the exact file task 6 later identified as a real
  leak, with its own `.git` one push away from publishing it. **Proved it had
  no remote (never pushed, leak never left the laptop), then deleted with the
  founder's explicit authorisation.** The script refusing to overwrite an
  existing target had been accidentally protecting him. Lesson: stale export
  artefacts are leaks-in-waiting; build fresh, always, from the current tree.
- **The snapshot deliberately excludes two mid-flight commits.** `1b3994b`
  (CV serve-all decision) and `03270e4` (plan 0013) landed from the founder's
  parallel session at 13:07/13:41 — DURING the flip work. The pushed snapshot
  was built from `a2f8fe6`, exactly the artefact verified and approved; publish
  what was blessed, never silently more. The next refresh carries them.
- **The contract, now standing:** the private repo (GOAL-A) is the source of
  truth, the CI, and the only deploy authority (WIF pins deploys to its exact
  name — a fork of the public repo can never touch the cloud). The public repo
  is a **filtered promotion**, rebuilt by `prepare-snapshot.sh` and re-pushed
  at each phase close — now a standing step of the 5-step relay. Same one-way
  direction the project already uses for `*.local.md` → committed logs.
- **Verified beyond the script's own checks:** the full suite was run INSIDE
  the snapshot before pushing — **686 passed / 10 skipped, exit 0** — because
  the artefact's audience is a hiring manager whose first move is `pytest`.

## 2026-08-10 13:20 BST — Phase 9 identity: Google sign-in via Supabase OAuth 2.1 (magic links rejected on a measured limit the founder has already been burned by)

Decision recorded now, BUILT in Phase 9. Founder raised the constraint himself:
a previous project of his broke on Supabase free-tier email — the built-in
sender allows ~2 emails/hour, which suffocates magic links immediately.

- **Chose: Google social login.** Zero emails ever sent, 50k monthly active
  users on the free tier, and ONE button serves both doors — the hosted user
  dashboard and the MCP connector's OAuth authorize page. Setup is ~15 minutes
  inside the GCP project that already exists. **Rejected:** magic links
  (email-limited), custom SMTP (cost + moving parts for no gain today),
  building our own OAuth server (never — auth servers are not a two-person
  project's business).
- **The architecture:** Supabase Auth as the OAuth 2.1 authorization server —
  it now ships MCP-shaped discovery + dynamic client registration, i.e. the
  exact three `/.well-known` paths measured 404 when Claude's connector failed
  against our static-bearer door in task 3 become real. The MCP service adds
  protected-resource metadata and swaps "compare one static token" for
  "verify Supabase-signed JWTs" (FastMCP has the verifier built in). The
  `client_id="founder"` hardcode fills itself from the token, and RLS policies
  key off the same identity — security debts S-2 and S-3 fall in one stroke.
  This supersedes the "username+password, email confirmation OFF" shape in the
  Phase 9 card (2026-08-03); the card gets updated when Phase 9 is staged.
- **Caveat pinned:** connector OAuth has vendor quirks; the Phase 9 task is not
  done until a LIVE Claude-connector login is measured working end-to-end.

## 2026-08-10 12:20 BST — Run 8's silence diagnosed to the row: correct behaviour, and deliberately left unchanged

The first true unattended 06:30 run produced no phone push and the founder
asked why. Audited read-only rather than assumed: scheduler fired 05:30:00 UTC
exactly as `goal-a-invoker`, run 8 ok 14/14 on the digest-verified `c557a23`
image, and the nudge stage recorded **"nothing new to nudge"** — the only stamp
event in history is run 5's 64 listings at 18:58 UTC (the founder received this
morning's notification on Saturday evening, because the cron-move test claimed
the queue early), and `eligible_unnudged = 0` was verified by query.

- **Chose: change nothing.** A heartbeat push ("ran ok, 0 new") was considered
  and NOT built — the nudge philosophy is one digest, only when something
  deserves attention. The trio stands: **phone = new roles · status page = did
  it run · email alerts = it broke.** Silence + green status page = a healthy
  day with nothing new. Revisit only if the founder asks.
- Findings parked, not fixed (per plan 0013 §4): promotion review list FULL at
  20/20 open flags — `promote` has reported `cap_hit=True, promoted=0` four
  runs straight, so the discovery lane is throttled behind founder decisions,
  not code; 169 ready rows sit in the queue with applications at 0; Starling
  Bank's board 429'd and was tolerated per-company (self-heals next run).

---

## 2026-08-09 23:55 BST — Deploy-on-green stops rebuilding for prose (founder-initiated)

Founder asked whether running the cloud repeatedly costs money, and said his own
instinct was to fix the doc-rebuild properly now rather than "rebuild the whole
car because the owner's manual changed". He was right, and the measuring turned
up a cost neither of us had been looking at.

- **The money is not where it looked.** Measured: the daily job uses ~23,700
  CPU-seconds a month against Cloud Run's 180,000 free — about 13%, so Google
  is effectively free; both services scale to zero; Artifact Registry holds
  380MB across 20 images (layers are shared) and sits under the 0.5GB free tier.
  The real meter is **GitHub Actions on a PRIVATE repo**: 2,000 free minutes a
  month, and a full run (suite → container build → suite inside it → deploy) is
  8–12 of them. Roughly 16 pushes in one evening spent ~8% of the month, many of
  them for log entries. This project writes documents constantly, so the waste
  is systematic rather than occasional.

- **The correctness argument outranks the cost one.** The standing rule is that
  the 06:30 image gets hand-run before cron meets it. Rebuilding on every push
  makes that rule impossible to follow, and it silently was not followed
  tonight: image `0836977` was proven by hand, then two markdown edits swapped
  in `682def3` underneath it. Harmless — the pipeline diff between them was
  measured as zero files — but **a rule that quietly cannot hold is worse than
  no rule**, because everyone believes it is holding.

- **The gate asks about the IMAGE, not about "important" files.** A `changes`
  job checks whether anything shipped by the Dockerfile's COPY allowlist moved
  (`src/`, `scripts/`, `tests/`, `db/`, build files). Documents are not in the
  image at all, so a doc-only push cannot alter the artefact — that is a fact
  about the Dockerfile, not a judgement call about what matters.

- **The TEST job is deliberately NOT gated, which is the whole subtlety.**
  Skipping tests on doc pushes is the cheap version of this fix and it is wrong
  here: the suite reads the README and the git index on purpose
  (`test_the_readme_test_count_matches_reality`, the public-safety scans), so a
  document genuinely can turn the suite red. Only the expensive half — build
  and deploy — is skipped. Cost saved without buying it with coverage.

- **An unknown base sha assumes the program changed.** New branch or
  force-push reports an all-zero base; the safe default is to do the work, never
  to silently not deploy. A skipped deploy that nobody ordered is exactly the
  kind of quiet failure this phase kept finding.

---

## 2026-08-09 23:18 BST — Tasks 6, 5b and 7-prep: the audit found real leaks, and CI now deploys without a key

Founder's instruction was "do the rest" after asking why I had stopped. Fair
challenge, and half right: the ⛔ gates on a public URL and on publishing a repo
are real, but **task 6 was never gated** and stopping to ask before it was an
unnecessary halt. Recorded because the lesson is about gate DISCIPLINE, not gate
enthusiasm: a gate exists for irreversible or outward-facing acts, and treating
every task boundary as one is its own failure.

- **The security-review skill was NOT run, and the substitution is on the
  record.** It reviews the diff against `origin/HEAD`, and that diff is zero
  files — everything is merged and pushed. Running it would have reported clean
  after reviewing nothing, which is the precise failure mode this project has a
  standing rule about. Did the whole-repo audit the phase card actually asks for
  instead. Saying so rather than claiming the mandated tool ran.

- **Two real leaks, in tracked files, found by measuring rather than trusting.**
  (1) `ops/apply-shortlist.md` was tracked: 15 named roles the founder is
  targeting at Anthropic, Faculty and Palantir, with live application links,
  pulled from his own queue. Operational output about a PERSON, in a repo about
  to be published — untracked, local copy kept, `.gitignore` widened. (2)
  `PROJECT-MEMORY.md` carried the live Supabase project ref in a runbook line;
  scrubbed. Cleared and measured, not assumed: the two `AIza` strings are 6 and
  10 characters, i.e. truncated placeholders and not the 39-char real thing;
  `.env.example` holds bracketed templates; `docs/cv-intake-template.md` is an
  EMPTY form; no email, phone or founder company appears anywhere.

- **An audit is a moment, so it became a habit.** `tests/test_public_safety.py`
  asserts all of it against the git INDEX — what would actually be published.
  Each detector first proves it can BITE on a synthetic bad value before it is
  trusted, because the two written naively both cried wolf immediately
  (`.env.example`'s `[YOUR-PASSWORD]`, and a test fixture's invented
  `goala-secret-topic`). Tightening those without re-checking they still fired
  would have produced two scanners that pass forever.

- **The attribute condition is the WIF security control, not the pool.** Without
  it the provider trusts the ISSUER, so any repository on GitHub could present a
  valid token and be accepted. Verified live after creation:
  `assertion.repository=='shayandas862-hub/GOAL-A'`, and the only principal that
  may impersonate the deployer is that repo's principalSet. The deployer holds
  `run.developer` + `artifactregistry.writer` and pointedly NOT
  `secretmanager.secretAccessor` — CI names the secrets a service mounts, it
  never needs to read one. Tests assert both the roles present and the roles
  that must be absent.

- **CI updates the daily job but never executes it.** The 06:30 lane is sacred:
  a run takes ~13 minutes, sends real nudges and writes real rows. Firing it
  stays a deliberate act, never a side effect of merging. The two services do
  roll automatically, and the workflow then curls the public status page and
  fails the build unless it answers 200 — a deploy that silently breaks the one
  public surface is not a successful deploy.

- **Squash, never mirror, and verify the artefact rather than the intention.**
  The project ref is in history (3 commits, 5 files), so `--mirror` would
  publish it permanently; rewriting history here would break every commit id
  cited across the logs and phase cards. `ops/flip/prepare-snapshot.sh` exports
  the tracked tree, drops the build machinery (`CLAUDE.md`, `PROJECT-MEMORY.md`,
  `docs/handoffs`), commits once, then re-checks the RESULT for the project ref,
  a real connection string, an ntfy topic, the apply shortlist, a single commit
  and a LICENSE. It publishes nothing.

- **Three instrument failures in one sitting, all the same shape.** (1) Polling
  the GitHub Actions API on a PRIVATE repo returned `{"status":"404"}` and the
  poller read the error code as the run status — replaced by asking GCP what
  image the services actually run, which is the evidence that matters. (2) The
  README test SKIPPED because `addopts="-q"` plus a hand-passed `-q` makes `-qq`
  and silences the count line; a skip reads exactly like a pass. Same trap as
  earlier in the phase, now commented at the call site. (3) The snapshot
  verifier died mid-check because `grep` exits 1 on no-match, `pipefail`
  propagates it and `set -e` killed the script — so a CLEAN snapshot aborted the
  check meant to bless it, printing no verdict. A standalone test of the same
  pipeline had passed, because it ran without `pipefail`. **The instrument
  differed from the real conditions every time.**

- **The README was materially false and is now pinned.** It advertised 402
  tests, 34 migrations, 24 tools, "caged AI with Gemini" and "a hard spend cap"
  — an architecture the project no longer had. Rewritten from measured state,
  and two tests now guard it: one bans claims about RETIRED things (they can
  only be wrong), one compares the stated count against a real collection. The
  second failed on its first run, because writing the two tests moved the count
  from 692 to 694.

---

## 2026-08-09 22:39 BST — Tasks 3 and 4 live: two Cloud Run services, and the same flag meaning two opposite things

The first Cloud Run **services** this project has ever deployed (until tonight
there was only the Job). Both gates were opened by the founder, each with the
evidence in front of him.

- **Task 3's code was already built and nobody's documents knew.** `05ace84`
  (13:48 today) had shipped the token gate, rate limiter and
  `MCP_TRANSPORT=http` with 8 tests — yet `CLAUDE.md` and plan 0012 both listed
  task 3 as untouched, because both were only ever tracking the *deployment*
  half. Discovered by reading `server.py` rather than the plan. Recorded because
  the plan documents are trusted as a map of what exists, and here they were
  wrong in the safe direction (understating), which is the direction nobody
  checks.

- **`--allow-unauthenticated` is on BOTH services and means opposite things.**
  On the MCP it is not "no auth" at all: the bearer token is the door, and IAM
  authentication would demand an OAuth identity the founder's AI client cannot
  mint — locking out the only intended user. On the status page it means what it
  says, because migration 0043's views make personal data unreachable. Reading
  the second as if it were the first is the expensive mistake available here, so
  each `setup.sh` stanza states which claim it makes, the rejected alternative
  is written down, and a test pins that `MCP_TOKEN` never appears in the status
  stanza.

- **The secret allowlist SPLIT rather than grew.** One list was right while
  there was one runtime. With three, `SECRETS` is what Secret Manager holds
  while `JOB_SECRETS` / `MCP_SECRETS` / `STATUS_SECRETS` say what each surface
  mounts. The daily job never receives `MCP_TOKEN`; the MCP gets the database
  and its own token and no aggregator keys (its script-spawning tools are not
  durable in a Cloud Run service anyway — Stage C's finding — so those keys
  would be exposure without benefit); the public page carries `DATABASE_URL`
  alone. Least privilege per surface, each pinned by name.

- **On the public page the VIEW is the privacy boundary, not the page.** With no
  authentication the page cannot protect anyone, so protection moved into
  migration 0043: `src/status/` does not know the NAME of a single personal
  column, and a test greps its source for eighteen of them. What it cannot name
  it cannot leak. Stage SUMMARY text is dropped deliberately — "nudged 64
  listing(s)" reads well but names companies and describes the owner's
  activity. `applications_total` is absent although `v_scorecard` carries it:
  copying the dashboard's view here was the obvious, wrong move.

- **Verified against real data before the gate, not after.** Rendered from the
  live database and scanned: zero hits for the founder's name, the ntfy topic,
  the Supabase ref, "£", "applied", "token", "Bearer", "postgres" or an email.
  The only "salary" is the pipeline STAGE called salary; the only "@" is
  `@media`. The founder saw the rendered page before answering the gate, and
  first answered the gate with a QUESTION — whether it was read-only and what
  exactly it exposed — which is the gate working as intended rather than a
  rubber stamp.

- **Two instrument failures caught, both by the standing rule.** (1) The first
  MCP smoke reported 307 for no-token, wrong-token AND right-token: the endpoint
  is `/mcp`, not `/mcp/`, and a uniform redirect looks exactly like a uniform
  result. Fixed the probe, not the conclusion; the real answer was 401/401/200.
  (2) A `for name in ${MCP_SECRETS}` loop typed into this zsh shell did not
  word-split, so it tried to grant one secret literally named
  "DATABASE_URL MCP_TOKEN" — and the `echo` after it printed "granted" anyway.
  The scripts are `#!/usr/bin/env bash` and are correct; the lesson is to RUN
  them, never to retype their loops interactively.

- **Known, recorded rather than hidden:** `/healthz` returns 200 from the same
  image locally but 404 from Cloud Run's edge (Google's own error page, so the
  request never reaches the container). Harmless — it was a convenience
  endpoint and the page itself serves — but it is a local/live difference, and
  those get written down.

- **The rate limiter is GLOBAL, not per-token.** Proven by firing 40 concurrent
  requests: exactly 15 passed (the burst capacity) and 25 were refused. Correct
  for one user; wrong the moment there is a second, since one client could
  starve another. Carried to Phase 9 alongside the existing note that the
  limiter is in-process and becomes per-instance as soon as Cloud Run scales
  out.

- **Hosted MCP does not reach the founder's phone, and that is an auth-shape
  problem, not a hosting one.** Claude's custom connectors (available even on
  free plans, one connector) authenticate by OAuth; our door takes a static
  bearer token, advertises a bare `WWW-Authenticate: Bearer`, and returns 404 on
  all three OAuth discovery paths — measured, not assumed. So Claude Code works
  and Desktop/web/Cowork cannot. Founder's decision: ship task 4 first, then
  build OAuth as the next piece, since the same work also unlocks a hosted,
  properly-logged-in user dashboard for real users.

---

## 2026-08-09 21:03 BST — Stage C shipped: four audit fixes, and three tests that had been passing for the wrong reason

The deferred code fixes from the audit, done after run 5 proved the unattended
path green. All four landed in one commit (`b8dbab9`) with the plist retirement.
The fixes themselves were specified in plan 0012; what follows is what was *not*
obvious once the work started.

- **The recurring finding was not a bug — it was that three separate tests could
  not fail.** Stage C was meant to be four small fixes. In practice each one
  surfaced a test that produced a green tick without exercising the thing it
  named. (1) `test_trigger.py` and `test_mcp_census_tools.py` asserted `".venv"
  in cmd[0]` — true on the laptop, and *necessarily* true of the very hardcoding
  that was the bug, so the assertion could only pass while the defect existed.
  (2) The first C3 regression test, written with `responses` like every other
  push test, **passed against the unfixed code**: `responses` mocks the adapter,
  so the latin-1 header encoding that actually raises never happens. (3) The
  C4 no-channel test guarded with a throwing lambda, which the new
  `except Exception` would have swallowed — it would have kept passing after the
  behaviour it guarded was gone. This is the 2026-08-09 rule again, one layer
  further in: *a broken check is indistinguishable from a clean result*, and a
  test that cannot fail is worse than no test, because it also spends the
  credibility of the suite. Each was rewritten to be red first for the right
  reason before the fix went in — C3 against a session double that reproduces
  `http.client.putheader`, C4 against a call recorder that cannot be swallowed.

- **The interpreter fallback was already solved in this repo, and copied rather
  than invented.** `scripts/run.py` has carried `_python()` — repo venv when
  present, else `sys.executable` — precisely because the container has no venv.
  `python_executable()` mirrors it instead of introducing a second convention.
  The new tests exercise **both** branches; the fallback branch is the one that
  had never been tested, and it is the only one the container ever takes.
  Verified in the built image, not argued: `/app/.venv/bin/python` `exists=False`,
  resolved `/usr/local/bin/python` exists and is executable.

- **`start_pipeline` fixes the 504 but is NOT yet right for a hosted service,
  and that is recorded in the code.** Detaching solves the stated problem (a
  ~12-minute blocking call behind Cloud Run's 300s default). It does not survive
  the environment task 3 will put it in: a Cloud Run *service* throttles CPU once
  the response is sent and reclaims the instance on scale-to-zero, either of
  which kills a detached child mid-run. The correct hosted design is to invoke
  the existing `goal-a-daily` **Job** through the Jobs API. Not built now —
  that is task 3's decision and needs the service to exist — but written into
  `start_pipeline`'s docstring so task 3 inherits the finding rather than the
  trap. Shipping the fix as specified while naming what it does not fix.

- **A new invariant test, because C2 moved eight cross-references at once.**
  `next.call` is the machine-readable half of contract v2 — it is literally what
  a client AI calls next. Nothing checked that those targets exist, so a rename
  could half-land and the only symptom would be a client calling a tool that is
  not there. Added `test_every_next_hint_names_a_tool_that_actually_exists`. Two
  details make it honest rather than decorative: it distinguishes a *field* from
  a *tool* by whether the docstring documents the token inside `{...}` (this is
  what kept `jd_full` from being a false positive, instead of an allowlist that
  would rot), and it asserts its own scan found something, so it cannot pass by
  matching nothing.

- **Tool count 29 → 30 is a deliberate contract change**, not drift:
  `run_pipeline` no longer exists, replaced by `preview_pipeline` (waits) and
  `start_pipeline` (detaches). Every `call=` hint and every `Next:` line that
  pointed at the old name now points at `start_pipeline` — the "run it now"
  action — enforced by the test above rather than by having grepped carefully.

- **`docs/dev.md`'s schedule section was three separate lies and was rewritten
  from measured state.** It documented launchd at 08:00 pointing at a plist this
  commit deletes, and warned that loading it "starts real daily Gemini spend" —
  Gemini was retired 2026-08-03 and the engine now makes no AI calls at all. The
  live schedule was checked against Cloud Scheduler this session (`30 6 * * *`,
  Europe/London, ENABLED) rather than copied from another document. Its MCP
  section also said **24 tools**, stale since well before this session (it should
  already have read 29); corrected to 30 rather than leave two contradictory
  counts one line apart in the same file.

- **The plist was retired on evidence, with the founder watching.** Confirmed
  absent from `launchctl list` and `~/Library/LaunchAgents` before deletion — it
  had never been loaded, so nothing stopped running. Its gate was a confirmed
  clean unattended cloud run; run 5 satisfied it. Repo-only change, reversible.

---

## 2026-08-09 20:30 BST — The route to fully built ordered and written down (plan 0012)

Founder asked for one ordered plan across Phase 8 → 8.5 → 9. Written to
`plans/0012-road-to-fully-built.md`. The non-obvious calls:

- **Stage C goes first, ahead of the Phase 8 card order.** Not a re-ordering of
  the phase — Stage C is audit remediation that *blocks* task 3: four of the 29
  MCP tools (`run_pipeline`, `run_sweep`, `run_classification`,
  `send_test_nudge`) are dead inside a container. Hosting a door with 4 broken
  tools would be shipping a known defect. Its own gate ("wait for the first
  unattended run") expired when run 5 passed tonight.

- **Tasks 3 and 4 stay in card order but are flagged as sharing plumbing.**
  Both need the first Cloud Run **service** this project has ever deployed —
  a resource type that does not exist here yet. Whichever goes first pays that
  cost once; splitting them across sessions pays it twice. Task 6 must follow
  3/4/5 because it audits the surfaces those create.

- **Adding `MCP_TOKEN` is a deliberate contract change, not a config tweak.**
  `test_the_secret_allowlist_is_exactly_the_six` pins the secret count at six
  precisely so a seventh cannot appear by accident. Task 3 must update the test
  *and its name* — recorded so a future session does not read the failure as a
  bug and "fix" it by loosening the assertion.

- **A security-debt register replaces ad-hoc fixing** (8 items, §5 of the plan,
  each with a severity that is honest about *when* it bites). Two are already
  HIGH-at-flip or HIGH-at-multi-user rather than HIGH-today: the Supabase
  project ref in git history (blocks any full-history public push — this is
  *why* task 7 squashes) and RLS being on across 23 tables with **zero
  policies** while the engine bypasses it entirely as the owner role.

- **Scale shape assessed and deliberately NOT changed.** The expensive data is
  shared (register 144k · census 128k · ads 105k) and the per-user data is tiny
  (criteria, skills, rule, stamps) — one census serves every user. That is the
  correct economics; nothing about it needs redesigning for many users. What
  *does* break: the nightly job is O(1) for register/classify/discover/fetch but
  O(users) for match/promote/nudge, so **the scaling axis is per-owner fan-out**
  and Phase 9's per-owner pass should be written for Cloud Run `taskCount`
  rather than as a serial loop. External API quotas are per-account and shared —
  a hard ceiling, and the 8.5 Reed-drip pattern is the right thing to generalise.
  And **the MCP rate limiter lives in process memory**: correct at one instance,
  wrong the moment Cloud Run scales out (S-8). Also named as load-bearing: zero
  engine-side AI cost is the single best scale decision in the system and must
  not be undone by "helpfully" adding a model back.

- **"Fully built" redefined away from "perfect."** After tonight — green tests,
  reviewed code and accurate-sounding docs all coexisting with three real bugs —
  "verified perfect" is not a claim anyone can honestly make. Replaced with
  seven measurable criteria (§7), of which only one matters to Goal A:
  **applications sent > 0**, still 0.

- **Two blockers named that no amount of engineering clears.** `cv_blocks` is 0
  rows and gates Phase 8.5 task 0 — personal facts, human-confirmed, the
  founder's session (running in parallel). And the reading tray **starves**:
  150 rows waiting, 0 ever read, and tonight it staged 0 of 1,083 candidates
  because sieve 2 filters on the owner's title patterns. Logged as a *product*
  problem for 8.5 (supply side = the Reed drip, task 5), not a tuning nit.

---

## 2026-08-09 20:00 BST — Third-party audit acted on: the silence closed, CI landed, and the machine nudged the founder by itself for the first time

An independent read-only audit (no edits, everything measured) found three
critical risks before the first unattended 06:30 run. Acting on them produced
these decisions.

- **The audit's own triage was reordered before executing it.** Tracing the
  call graph showed only risk 1 is on the 06:30 path: `scripts/run.py` imports
  `pipeline.orchestrator/report/lock`, `db.connection`, `notify.*`, `config` —
  **never `pipeline.trigger`**, and `mcp_server.census_tools` is unreachable
  without a deployed MCP. So risks 2 and 3 cannot affect tomorrow. Risk 3 also
  **requires a container rebuild**, which would swap a known-good artefact for
  an untested one hours before the one event worth observing cleanly. Staged
  deliberately: **A** (notifications + alerting, tonight, zero deploy) · **B**
  (git hygiene + CI, tonight, repo-only) · **C** (the code fixes, only after
  tomorrow's run proves green). Founder approved the re-staging.

- **Two alert channels, and the second is independence — not redundancy.**
  `notify_failure` loads its channel from `profiles` and pushes over ntfy, so
  it structurally cannot report the database being unreachable or its own
  delivery path being down — and it never runs at all if `get_conn()` raises
  before it. Google Cloud Monitoring watches the *infrastructure* instead
  (OOM, timeout, crash on start, image pull failure, non-zero exit), on an
  email channel to the project owner. Neither channel can cover the other's
  blind spot; that is the whole point of having both.

- **The missed-run alert is a threshold, not a metric-absence condition.**
  GCP caps `conditionAbsent.duration` at **23h30m**, which is SHORTER than this
  job's 24h cycle — an absence policy would have emailed a false alarm every
  single morning in the gap before the next run landed. Rebuilt as a rolling
  24h `ALIGN_SUM` below 1 attempt, held 30 minutes so a slightly late run does
  not flap it, with `EVALUATION_MISSING_DATA_ACTIVE` to catch the series
  vanishing entirely. Tighter than the 26h originally planned.

- **That policy deliberately does NOT filter on `result`.** A job that runs and
  fails belongs to the *failure* policy; this one answers only "did it run at
  all" — the failure mode nobody watches, where Scheduler silently stops firing
  so no failure ever occurs and no failure alert ever triggers. First named it
  "NO successful run", which contradicted its own condition; renamed to "NO run
  at all in ~24h" before it could mislead anyone mid-incident.

- **Deploy-on-green is NOT wired into CI, on purpose.** It needs Workload
  Identity Federation; the shortcut is an exported service-account key in
  GitHub secrets, which `ops/cloud/NOTES.md` explicitly forbids ("No
  service-account keys are ever exported"). CI ships test + container-build
  only; the deploy half is a separate founder-gated PR. The `image` job (build,
  then run the suite INSIDE the container) exists because deployment is still a
  manual laptop ritual — it is the only automated thing between a broken
  Dockerfile and a broken 06:30 run.

- **Container contract tests skip; `ops/` does not enter the image.**
  `tests/test_cloud_setup.py` reads `ops/cloud/*.sh`, which the Dockerfile's
  named COPY allowlist and `.dockerignore` both exclude — so those 10 tests
  could never pass inside the artefact. Rejected copying `ops/cloud/` in:
  adding files to a runtime image to satisfy a test is backwards and erodes the
  allowlist principle that keeps local state and credentials out of every
  layer. Fixed with a module-level `skipif`, matching the precedent already set
  by `tests/test_record_ids.py` ("repo docs/plans not present (container
  image)"). These pin the shape of the DEPLOYMENT SCRIPTS in the repo, not the
  runtime: the scripts that BUILT the artefact are not shipped BY it.

- **Two bugs found by RUNNING code, not reading it — both missed by the audit's
  static pass.** (1) `send_push` sets `headers={"Title": title}`; a non-latin-1
  title raises `UnicodeEncodeError`, which is **not** a `requests.RequestException`
  and so escapes the `except` entirely. `send_test`'s hardcoded em-dash title
  therefore always crashed. Blast radius chased down: `digest()`'s title is
  always ASCII and `notify_failure`'s is a literal, so **the 06:30 path is
  safe** — proven live, and a digest carrying `Société Générale —— Ünicode Ltd`
  delivered fine because the body is UTF-8 encoded. Fix verified
  (`title.encode("utf-8")` round-trips; ntfy accepts UTF-8 — the fault was
  always ours), queued for Stage C with a regression test. (2) The container
  suite had been **red since 7fd4977** and nobody knew: task 1 verified it green
  at 604 tests BEFORE task 2 added `ops/cloud/` and its contract tests, and
  nobody re-ran it in the container afterwards. The new CI `image` job caught it
  on its first run.

- **The ntfy topic IS the access control** — 32 hex characters of entropy,
  because ntfy.sh is obscurity-only and the digest carries company names and
  role titles. It lives in exactly one place, `profiles.notification_channel`;
  it appears 0 times in the repo and is never printed by `send_test` (which
  reports booleans only). **Flagged for Phase 9:** obscurity is not access
  control — a self-hosted ntfy or an access-token-protected topic is the real
  fix, deliberately out of scope tonight.

- **BOTH remaining links proven live at 19:45 BST — the founder's test design
  was better than the one offered.** Two links had never been exercised:
  **Scheduler → Job** (configured correctly but never fired once; both
  executions to date were typed by hand) and **Cloud Run → ntfy.sh egress**
  (every push earlier tonight came from the founder's laptop via `.env`;
  run 4 bailed at "no notification channel configured" before ever reaching
  `send_push`, so the container had never sent one). A forced
  `gcloud scheduler jobs run` was offered; the founder rejected it and
  directed a better test — **move the live cron to `45 19 * * *` and watch
  the scheduler wake the job by itself.** That distinction is the whole
  point: a forced run bypasses the cron trigger, i.e. it skips the exact
  step under doubt. Recorded because the reasoning generalises: *test the
  real trigger, not a manual substitute for it.*
  **Result — everything passed.** Execution `goal-a-daily-pt99z` created
  `18:45:00 UTC` **to the second**, `RUN BY goal-a-invoker@…gserviceaccount.com`
  (a robot, not a human — the two prior executions name the founder);
  `pipeline_runs` run 5 opened 12s later and finished `18:58:16 UTC`,
  **status ok, 14/14 stages**; the `nudge` stage reported **"nudged 64
  listing(s)"** and `nudged_at` is stamped ONLY after a successful send
  (`nudges.py` raises on a failed push before stamping) — so the 64 stamps
  are themselves proof the container reached ntfy.sh. Confirmed three ways:
  the DB stage summary, the message on the ntfy server (`19:58:16`, title
  "64 roles ready to apply", Anthropic + 4 Palantir roles), and the founder's
  phone. The live cron was restored to `30 6 * * *` immediately after the
  trigger fired — the cron question was already answered, so there was no
  reason to hold the override; `ops/cloud/env.sh` was never edited.

- **A verification instrument reported the exact opposite of the truth, and
  the lesson outranks the bug.** The monitor armed to watch for the scheduler
  emitted "NO EXECUTION APPEARED — Scheduler did NOT invoke the Job" while
  the job was, in fact, running. Cause: the poll used `gcloud … $P` with the
  flags held in a variable — **this shell is zsh, which does not word-split
  unquoted expansions**, so gcloud received one mangled argument and failed
  with "You must specify a region"; `2>/dev/null` then discarded that error,
  leaving an empty list every poll, indistinguishable from "nothing fired".
  It was caught only because live state was checked directly rather than the
  instrument being believed. **This is the same failure mode as the night's
  other three findings** — an empty `notification_channel` that logged a note
  and moved on; a `send_push` whose `except` could not catch the error its
  own code raised; a container suite nobody re-ran. In every case **a broken
  check was indistinguishable from a clean result.** Standing rule taken from
  it: a check must fail LOUDLY and differently from "all clear" — never
  swallow stderr in a watcher, and never report an instrument's silence as a
  finding without confirming from a second source.

- **Deferred to Stage C, after tomorrow's run proves green** (all require a
  rebuild, none touch the 06:30 path): the hardcoded `.venv/bin/python` in
  `pipeline/trigger.py` and `mcp_server/census_tools.py` (no `sys.executable`
  fallback — 3 MCP tools are dead on arrival inside the image);
  `run_pipeline`'s ~12-minute blocking `subprocess.run` (a 504 the moment the
  hosted MCP deploys behind Cloud Run's 300s default), splitting into a
  synchronous `preview_pipeline` and a detached `start_pipeline`; and the
  `notify_failure` stderr shout so a swallowed failure is at least loud in
  Cloud Logging.

---

## 2026-08-03 (late evening) — Gemini retired to ZERO; the learning-curve model specced

- **Gemini is fully retired, by omission.** Founder directive: the engine
  exposes only raw deterministic data as MCP tools; ALL intelligence is
  user-side (Cowork for the founder; any MCP-capable AI for others). No code
  change needed — the engine was built pluggable (GA-003: optional key,
  keyword fallback, CV plain-facts fallback) — verified in config.py,
  read/gemini.py, cv/generate.py before deciding. Enforcement: GEMINI_API_KEY
  is simply never provisioned in any environment, including Secret Manager.
  Consequences accepted: engine reads are keyword-quality until the user's AI
  drains the tray; CV output is plain-facts (truth-gated, unphrased) until
  Phase 8.5 task 0 lands the user-side CV path. The Phase 8 monthly spend cap
  is retired with it (nothing engine-paid remains); rate limits stay. If a
  paid spot ever returns, the cap returns with it.
- **Skill-gap closure trajectory specced as plan 0010 item 16.** Timestamped
  learning events (skills-entry tool must carry learned_at + evidence from
  v1 — requirement pinned into P8.5 task 1 NOW so data accumulates from day
  one); closure rate as the discrete derivative; Δgap decomposed into user
  learning vs market drift (demand moves too — showing one number would
  lie); cumulative learning as the integral; forecasts honest (trailing
  trend + sample floor, never a promise).

## 2026-08-03 (late evening, 2) — CV serving is SERVE-ALL, not engine-filtered

Founder correction to Phase 8.5 task 0, accepted: the engine must hand the
client AI **every confirmed cv_block**, not an engine-selected subset.
Reasoning on the record: (a) the existing relevance match (assemble.py) is
literal skill-word overlap — it cannot see transferable evidence (film-crew
deadlines → "delivers under pressure"; 20–22 regulated calls/day → "handles
complex information"), so it would silently drop usable facts; (b) a filtered
fact is UNKNOWABLE to the client — recall failures are invisible and
permanent; (c) there is no scale argument — a career is ~40–60 blocks; (d)
safety does not depend on filtering: the truth gate is a CEILING (nothing
claimable that is not stored), so full freedom to SELECT costs nothing while
freedom to INVENT stays impossible. The skill match survives as an optional
hint in the payload, never a restriction. Division of labour, pinned: **AI
decides relevance, code decides truth.** Consequence for the fact base: store
every true fact including seemingly irrelevant history — breadth is now a
feature, not clutter.

## 2026-08-03 (evening) — Go-live directives: CV goes user-side, Notion deferred, day-one spine fixed

Founder directives before the cloud push, on the record:

- **The CV moves to the user's AI, tray-pattern.** New Phase 8.5 task 0: versioned server-side `cv-v1` prompt (ATS-safe rules baked in, non-overridable) + owner's cv_blocks facts served over MCP → client AI writes content → `submit_cv` truth gate (grounded in stored facts, reuses the existing CV gate) → the ENGINE renders the ATS-safe .docx (format never client-owned). Caged Gemini phrasing retires when it lands; spend-capped until then. cv_blocks seeding (the founder facts session) remains a prerequisite for ANY CV path — the gate needs true facts to check against; cv_blocks measured at 0 rows today.
- **Notion filing deferred by choice** — already optional in config (missing NOTION_* = quietly off); it joins the cloud later via two Secret Manager values, no laptop.
- **Day-one go-live spine = Phase 8 tasks 1→2→3 only** (container ✅ → Cloud Run Job + Scheduler + secrets → hosted MCP + bearer token + caps). Status page, CI, security pass, flip follow after. The ready queue is already DB-native (v_today, 96 ready at time of writing); MCP available from day one is the requirement, served by task 3. Phase 8's staged file needs NO edits — its order already matches.
- **Email reading via Cowork is user-side by design** — the founder connects his inbox to his own Cowork; the engine gains nothing and stores nothing about email. Reply-tracking stays outside the machine's walls.

## 2026-08-03 — Walkthrough day: the phase relay, Phase 8.5 inserted, the auth decision, classify shipped

The founder walked the whole machine step by step (register → census → doors) and made four decisions:

- **The phase relay is now the working protocol.** One phase = one Claude Code chat. Every phase ends with five steps (decision log → progress log → archive CLAUDE.md → write the next phase's CLAUDE.md from its SECTION 2 card → hand the founder a copy-paste prompt for the next chat). Everything feeds forward through files, never chat memory. Written into architecture-v2 SECTION 2 header and the CLAUDE.md end-of-phase ritual.
- **Phase 8.5 (Universal Product Layer) inserted between 8 and 9.** Why: the walkthrough exposed that the universal-lens bricks (words→codes translator, owner-lens sweep, universal search tools, skills-entry tool, Sponsors browse tab, Reed JD drip) are product work, not security work — building them BEFORE Phase 9 means the multi-user plumbing lands on finished surfaces. Sourced from plans/0010 (items 3–8, 10, 14). Principle pinned in the card: user words never edit code — they become rows.
- **The auth design, decided simple:** friend tier first — founder-minted per-user keys, no sign-in system at all (the MCP token IS the credential); stranger tier later — Supabase Auth in username+password shape with email confirmation switched OFF (no email flows; free plan covers 50k monthly users, verified 2026-08-03). Three locks: rented front door, per-user key → owner resolution, and row-level security on ALL tables (4/24 today — completing this is a hard Phase 9 gate). One rule above the locks: hold nothing worth stealing (no passports, no bank details, no passwords of our own).
- **Names vs codes, settled:** TECH_NAME_PATTERN was bootstrap ordering from the days before the census had industry codes — it sorts, never filters, and retires as lenses take over; the real lens is always SIC codes in the owner's rule row.

Also shipped same day (see progress log): the daily classify top-up (commit 5a59c4e) — built by a delegated Opus agent in a worktree from a written spec, inspected line-by-line and full-suite-verified (592 passed) before merging; the delegate-builder + inspector pattern worked and is now a precedent. Live census truth at time of writing: 128,006 cards · 126,342 asked · 97,127 matched · 11,726 software-lens · 290 boards found · 12,945 knocked (115,061 never knocked — knock-on-demand per lens is the design).

## 2026-08-02 20:04 BST — PHASE 7.8 BUILT in one session: the non-obvious choices, on the record

All nine tasks shipped same-day (suite 441 → 581; migrations 0037–0041; live smoke complete — see progress-log). The decisions that weren't in the staging spec:

- **The merge's "direct employer" test is the census's own industry codes, not a stored poster type.** The town×poster partition was a QUERY-time filter — ads never carried poster type. Stand-in chosen: an ad matched to a sponsor whose Companies House codes sit in SIC division 78 ("Employment activities") is recruiter-matched and stays out of the queue (`skipped_recruiter`). Measured before building: 2,804 of 9,193 local matched ads across 56 orgs. An org with NO census card is not a *known* agency and merges — exclusion is for measured facts, never guesses. Live result: 2,805 skipped.
- **The merge is a second audited crossing, and it creates BOARDLESS companies.** 763 matched orgs entered target_companies with register linkage and no ATS token — the fetch list ignores them (it selects on ats_token), so the census wall and the fetch lane are both untouched; their ads still rank in the queue. The crossing stays single-file: promote_rule may only reach target_companies through promote_from_census (pinned by test), and merge.py's own company insert is audited per org.
- **Duplicate threshold 0.93, deliberately between the twins.** An exact-title/same-town/overlapping-salary twin scores ~0.97 (absorbed — stamped `duplicate`, merged_role_id set); a Senior-variant near-title scores ~0.91 (its own row — seniority variants are different jobs). Pinned by test against prob.py itself. Known one-way boundary, accepted: an ad merged BEFORE its board twin is fetched will coexist with it until job-rot closes the ad row (fetch-time cross-source dedupe would touch the hot fetch path — deferred with the 0007 task-3 lineage).
- **Borderline promotion = exactly one condition missing.** Auto-promote needs all three (industry ∩ rule set, live title match vs target_roles, local-jobs floor); one miss → a capped promotion_review flag (cap 20, promotions never capped); two+ misses → silence. Titles re-match LIVE each night (stored census title_match reflects probe-time patterns); the rule stores no titles. Live: 25 promoted, 20 flagged with the cap holding, 103 silent.
- **Pre-0039 reads carry read_quality NULL — honestly unlabelled, and therefore re-stageable.** No backfill was invented (the reader identity was never recorded). The tray takes anything not 'ai', so the 721 unlabelled reads upgrade in place when a client connects. role_skills rows are REPLACED on upgrade (derived, re-derivable — keep-all protects evidence layers, not derivations). The engine's own Gemini reads now stamp 'ai' too, keeping them out of the tray.
- **The reading boundary imports no AI, pinned bluntly.** serve.py duplicates the reader's enums as served DATA and a test asserts equality with read.gemini's schema WITHOUT the tray importing it; the grounding gate is read.eval (one truth-gate, now three callers: CV, eval, accept). Salary must appear verbatim in the JD like every skill; rejects are audited; 'unknown' sponsor_hint is dropped as content-free.
- **Survival deadlines: first-appeared→first-closed, MIN_SAMPLE 5, receipts returned not stored.** Reopened listings measure their first lifetime only. Coarse title families (SOC first, 8 keyword buckets) so curves can actually fill. Receipts (family, n, median) ride the function return and the stage's stderr — no new column; the row's deadline_source='survival' is the queue-visible label. Refresh selection now includes 'survival' rows so estimates keep tracking the curves; 'stated' stays final.
- **Contract v2 is a breaking envelope, applied to ALL 29 tools at once.** {result, next:{state, call, why}} built in exactly one place (mcp_server/contract.py); every description rewritten What/When/Returns/Next and BOTH pinned by protocol-level tests. The next-block wording lives in the skin deliberately — it is orchestration presentation, not engine logic; every number in it comes from engine functions (brief.py assembles the agenda engine-side).
- **The dashboard's buckets are computed in v_today, not in Python.** ready vs needs (+ the needs_what sentence) is SQL in the view; the page renders and adds nothing — so the complexity-hiding pin (`dashboard reads ONLY v_today/v_scorecard/v_health`, raw table names absent from the package source) covers the logic too. Two design deviations from the reference, on purpose: secondary text lifted #6B6E7E → #8B8E9E (AA at 12px), and zero JS (meta-refresh 300s). Token: DASHBOARD_TOKEN in .env, constant-time compare, 127.0.0.1 bind pinned, no-token = no access, DB-down renders one calm line.
- **The register refresh diffs on (org_name_norm, route) and self-schedules inside the daily loop.** No cron: the `register` stage runs first with `--if-stale 7` and a register_refreshes bookkeeping table (0041 — a fifth migration beyond the four reserved; the alternative was stamping 143k rows weekly). Removals are STAMPED licence_removed_at, never deleted; reappearances clear the stamp. Live surprise, trusted over assumptions: licensed_sponsors derives org_name_norm/rating/is_skilled_worker as GENERATED columns (the DB's rating CASE even handles 'Provisional' — python aligned to it); the insert now carries only raw CSV facts. First automated refresh: +1,853 / −1,242 on 142,649 published rows — 45 days of drift the machine had been blind to. Sponsor matching does not yet filter on licence_removed_at (Phase 8+ decision, on the record).
- **The live merge was deferred from task 3 to task 9's smoke, consciously** — flooding role_listings mid-phase risked the founder's morning apply lane; measured after: the fit-title regex kept the queue at 200 rows (96 ready / 104 needs) while 5,549 ad rows landed labelled underneath.

## 2026-08-02 18:05 BST — PHASE 7.8 INSERTED (The Product Core) — architecture patched, CLAUDE.md staged; cloud (Phase 8) moves one step later

Founder order: "make a patch architecture and CLAUDE.md, fix all the things, then we go for cloud hosting." Executed via the architecture + builder-md skills. Nothing built yet — this entry records the staging decisions:

- **Why a phase before the cloud:** the cloud should lift a finished machine. Three of this session's designs change what the container must contain (the merge, rule-promotion, the staged-reading boundary + MCP contract v2, the dashboard as a fourth entrypoint) — shipping them first avoids deploying twice. Founder's sequencing, on record.
- **Numbering: 7.8** — follows the 7.5 insertion convention (decimal insert between built 7.5 and staged 8). The staged Phase 8 CLAUDE.md archived a second time (`archive-v2-phase8-build-instructions-staged-2.md`); Phase 8's card gains a 7.8 dependency line. Phase 8 re-stages from its card when 7.8 completes.
- **The math layer got module addresses** (the founder asked "where will the math be applied"): `src/match/score.py` = overlap × rarity with receipts · `stats.py` = percentiles + smoothed small-sample confidence · `decay.py` = half-life freshness · `prob.py` = name-match + same-job probability (powers the merge and orders every uncertain pile) · `history/survival.py` = open-duration curves replacing the flat 21-day deadline guess. Calibration/reply-probability deliberately EXCLUDED from 7.8 — it starves without application outcomes; it enters only when the founder's applied pile exists.
- **Complexity-hiding is now a pinned rule, not taste:** the dashboard may read ONLY curated views (`v_today`/`v_scorecard`/`v_health`) — a test enforces no raw-table access, mirroring the status-page no-leak pin planned for Phase 8. "No naked numbers" (every score ships its receipts) promoted to a phase rule.
- **MCP contract v2 pinned as the orchestration answer** (the founder's "how does a client AI know what to call"): every tool result carries a uniform `next` block (state · suggested call · why); prompts are server-side versioned data; `daily_brief` is the agenda tool. Client-side cleverness: none, by design — any vendor's model runs the loop.
- **Sieve-3 tray, rule-promotion, register-refresh** — as designed at 15:21; now tasks 4, 5, 9 with migrations 0037–0040 reserved.
- Standing rhythm written into the phase banner: the founder applies every morning while 7.8 builds; the build may never stale or block the apply lane. Applications remain 0 at staging time — the number the phase exists to move.

## 2026-08-02 15:21 BST — Design session (founder-directed, nothing built): user-side AI for the deep read; promotion becomes a rule; cloud heartbeat confirmed

Strategy/product session (same session as the 08-02 audit: 0 applications, queue frozen since 07-10). Founder constraint now pinned for the product: **the hosted engine runs NO AI on the founder's account** — all AI runs in each user's own client (Claude / ChatGPT / Gemini) connected over MCP; the engine stays deterministic and its daily run must complete with zero AI reachable.

- **The matching flow is named as three sieves:** sieve 1 = the register (legal), sieve 2 = profile facts (title words / town / salary floor) — both free, engine-side; sieve 3 = full-JD read → skills → score. Only sieve 3 needs AI.
- **Sieve 3 becomes a STAGED WORK QUEUE, not an engine AI call.** The daily run fetches full JDs for sieve-1/2 survivors and stages them unread. The user's AI, whenever it connects (its own scheduled task, their tokens), drains the tray: `get_reading_batch` returns JDs + extraction instructions + the required JSON shape — **prompts are server-side data, versioned**, so the engine controls extraction quality and any vendor's model just complies; `submit_reading` accepts results.
- **Verification is deterministic at the submission boundary** — the existing truth-gate/grounding pattern relocated: every claimed skill/number must appear verbatim in the stored JD text; enums validated; writes owner-scoped by token. A hallucinating (or malicious) client cannot poison rows; worst case is omission. Extracted job facts are world-facts shared across owners (one user's verified reading serves all); provenance recorded; re-reads may overwrite.
- **The engine never waits on AI:** the existing keyword fallback reads staged JDs crudely so the queue always ranks; rows carry read quality (`ai` vs `keywords`) and upgrade in place when a client submits. Degrade, never block — the house rule applied at the new boundary.
- **Client orchestration = self-describing tools, not client-side prompts:** every tool result ends with state + what to call next; a `daily_brief` tool returns the agenda (N to read, M to review, K CVs to phrase). The same stage → serve → accept → inspect → store pattern will carry CV phrasing and onboarding skill-parsing.
- **Manual promotion retired as product behaviour (button → rule):** the founder ruled per-company manual promotion is scaffolding, not product. Promotion becomes a per-owner rule (licensed + industry set + title match ⇒ auto-promote daily; ambiguous → a small review list). The census blast-radius wall survives — the rule is the audited crossing.
- **Cloud heartbeat confirmed as direction** (Phase 8 unchanged in substance): the daily run must not depend on the founder's laptop. **Gap found this session: the sponsor register itself is never re-downloaded** (loaded once, by hand) — a register-refresh job (weekly is sufficient) joins the schedule design.
- Nothing built; progress-log untouched by its own rule (completed tasks only). Next builds agreed in-chat: queue refresh run, rule-based promotion, ads→listings merge, then the cloud move.

## 2026-07-28 23:41 BST — Partition on facts, not on ranges: salary banding retired for location × poster type

Three days of engineering (bands 07-23, saturation guard 07-25, wall guard + split 07-28 morning) treated the symptoms of a strategy that could never work. The measurement that settled it: **a Reed band £25,155–£25,155 — zero pounds wide — reports 12,176 results.**

- **A range filter cannot partition an inventory.** Reed matches any job whose advertised salary range *overlaps* the band, so a job posted '£20k–£30k' answers all ~10,000 bands between. Every band is therefore the same ~12k superset behind the same 10k wall, and the only thing that ever ended one was the saturation guard — visible in the data as `ads_seen = 300` (exactly 3 pages) across most of the 324 bands. Splitting further was strictly self-defeating: more bands, same supersets, ~3 wasted calls each.
- **Partition on facts that are single-valued.** A job has exactly one location and exactly one poster type, so `(town, direct|recruiter)` is a true partition and each pair opens its OWN 10k-deep window. Confirmed live before committing to it: Birmingham·direct 1,081 · Birmingham·recruiter 4,956 · Manchester·direct 1,166 · Manchester·recruiter 6,046 · **London·direct 4,037** — all comfortably under the wall, where salary bands showed a uniform ~12,000. Marginal yield went from ~11 to **~35 new ads per call**.
- **The town list comes from the owner's own register, not a hardcoded UK city list** — `plan_location_slices` reads `sponsor_census.town_city`, so another owner's register produces another country's partition. Person-agnostic by construction (the standing third-party requirement). Case-folded: the register carries 'London' (33,021) and 'LONDON' (2,915) separately, and walking a town twice is pure waste.
- **Retire, don't walk, a proven-futile partition.** `retire_slices` closes unfinished cursors of a discredited kind in one statement; the 65 salary sub-bands created that morning would have cost ~195 calls to learn nothing. Kept as a general tool — every provider met so far has hidden a wall, and some partitions will keep turning out to be dead ends.
- **`split_band` and `ensure_bands` are kept, not deleted:** the salary machinery is now unused for Reed/Adzuna but remains correct and tested, and a future source may offer a genuinely exclusive numeric filter. The wall guard from this morning still backs everything up.
- **Known limitation, accepted:** a town × poster slice that itself exceeds 10k (London·recruiter is the candidate) will wall and lose its tail. The wall guard closes it safely and visibly; the next lever, if it bites, is a further exclusive split (contract type: permanent/contract/temp) rather than anything salary-shaped.

## 2026-07-28 08:09 BST — "A visible limp" is only useful if something acts on it: the depth wall becomes a first-class outcome

The 2026-07-22 band planner deliberately flushes oversized leaves rather than dropping ranges, and its docstring accepted that they "at worst hit the provider's wall and surface as source_error — a visible limp, not an invisible hole." Live, that limp cost a third of a quota-day: nothing downstream distinguished *permanent* failure from *transient* failure, so the wrapper retried a dead page 638 times.

- **A deep failure and an early failure are different events.** Reed 500s at `resultsToSkip=10,000`; a slice that has already banked ~10k rows and then fails has hit that wall, and no retry can ever succeed. `run_slice` now returns **`depth_wall`** past `wall_at=9,500` seen rows and closes the slice; below that threshold the same shape is still `source_error` and still retried, because a genuine outage usually kills page 1. One threshold, two meanings, both tested.
- **A walled band is finished, not broken.** `overall_verdict` maps `depth_wall` onto "keep working": it must not buy a 30-minute quota nap (nothing is capped) nor a 60-second error nap (nothing is broken).
- **Fix the coverage, not just the loop.** Closing the band would have silently abandoned ~19,500 reachable-in-principle ads. `agg_partition.split_band` re-splits ONLY the walled range — contiguous by construction, one persisted cursor per sub-band, no re-planning or re-walking of anything else. Live proof: £50,001–£100,000 became **65 sub-bands** on the first cycle after restart.
- **Why a threshold rather than reading the HTTP status:** the clients deliberately swallow transport detail (`_get_json` returns None on any failure) so that a down source can never crash a run. Rather than thread status codes back up through that seam, the wall is inferred from *depth already achieved* — provider-agnostic, and it works the same when Adzuna's clamp moves.
- **Residual risk, accepted and logged:** a real outage striking a slice that is already ~10k deep will be misread as the wall and close that band early. Cost is bounded — the band is re-split and re-walked on the next planning pass — and the alternative (retrying forever) is strictly worse.

## 2026-07-27 01:13 BST — The harvest was aimed at the wrong signal; two scheduling defects fixed (founder: fix the real defects)

Three defects diagnosed **before** any code changed, then fixed RED-first (suite 430). Progress-log same time has the shipping detail; the decisions worth keeping:

- **Following ad links can never work, and that is a property of the sources, not a bug in our parser.** Evidence: a live diagnostic followed 8 real ad URLs — Adzuna's `/jobs/details/{id}` *and* its `/jobs/land/ad/{id}` form both resolve to themselves (the hand-off to the employer is client-side, not an HTTP redirect), and Reed deliberately keeps applicants on reed.co.uk. No ATS token is ever exposed, so `parse_ats_url` had nothing to match: 3,458 links followed, **0 hints planted**. Deleting the module beat patching it — scraping landing-page HTML for a destination would be fragile, and Reed's `externalUrl` (detail API) costs one quota call per job for a signal we can get free another way. `aggregator_ads.harvest_checked_at` is kept (harmless, re-usable) but no longer written.
- **The signal we actually needed was already in the data: WHO is hiring.** Pass 2 probed only the software-SIC lot, so **433 licensed sponsors with 5,029 live ads carry no probe outcome at all**. An ad is proof a company is advertising *today*; finding its board is free (4 public ATS endpoints). So the learning loop inverted: aggregator ads → `pick_hiring_batch` → the existing, tested `probe_org`. Implemented as an **injectable `picker=`** on both runners rather than a new runner — one probe machinery, swappable batch source (`--software-only` vs `--hiring`), person-agnostic.
  - Deliberately NOT requiring `registry_outcome='matched'` in the hiring picker: a sponsor advertising right now is worth probing whether or not Companies House matched its legal name.
  - **Refinement found within minutes and left open:** ordering by ad-count puts recruitment agencies first (eFinancialCareers, Tradewind, Aspire People) — exactly the companies that use recruiter CRMs (Bullhorn/Vincere) rather than Greenhouse/Lever/Ashby/Workable. First 40 probed → 0 boards. Since the probe is free and fast (~40 orgs/2 min at 4 workers), the answer is to probe all 434 rather than build cleverness; if a future pass needs precision, order by software-SIC first or deprioritise agency SIC codes.
- **The drip may only sleep when nothing can progress.** The wrapper decided nap-vs-continue from "any source exhausted", so Adzuna hitting its 240 cap in 29 minutes idled Reed's remaining 850 calls for 30 minutes at a time. `overall_verdict()` is now a pure, tested function: all-complete → stop; any `page_budget_done` → continue immediately (it outranks another source's cap *and* another source's transient error); only an all-capped set naps.
- **A status view must read the same clock the writer uses.** `_print_status` read the ledger with Postgres `current_date` (UTC) while `run_slice` ledgers on the local date — so for the hour after midnight BST the status reported the *previous* day's calls, exactly when the founder checks a freshly-started run. Now parameterised on the runner's own date. Filed as cosmetic, fixed as correctness: the audit trail is only useful if two parts of the system agree what "today" means.

## 2026-07-25 02:25 BST — Adzuna clamps silently; walked ≠ banked; the saturation guard

- **Every provider hides a depth wall, each in its own dialect.** Reed said it honestly (HTTP 500 at skip 10,000). Adzuna lies by omission: past ~5k accessible results its pages keep returning HTTP 200 with ads — just never NEW ones. The error-shaped safety nets (source_error) cannot catch a wall that doesn't error. What caught it: the founder asking for progress **in percent**, which forced measuring *distinct rows banked* against provider totals — 5,253 distinct vs "34,000 walked" = 105 pages × 50 ≈ the clamp, exactly.
- **Rule pinned: progress is measured in DISTINCT ROWS BANKED, never in pages walked.** Cursor `ads_seen` is bookkeeping, not truth. The `--status` rollup keeps both, but any ETA or % must come from `stored_count` vs provider totals.
- **The saturation guard generalises the lesson** (`run_slice stale_limit=3`): three consecutive non-empty pages banking zero new rows = the slice is done. This one guard defends against silent clamps on any source AND stops Reed's overlap-saturated bands from burning quota — the two waste modes discovered this week, one mechanism.
- **Band machinery is now source-generic** (`ensure_bands(source, …, base_params)`): the third wall, whichever source hides it, is a config call away from the same medicine. Planning cost is paid once per source (persisted as cursor rows); Adzuna's 26 bands cost ~51 count calls of an already-degraded quota-day.

## 2026-07-23 00:01 BST — Reed's 10k wall and the coverage-is-sacred rule (two live lessons in one evening)

- **Reed hard-walls at resultsToSkip=10,000** (HTTP 500; paired-probe confirmed). Deep offsets can't walk a 93k inventory — partition instead. Dimension chosen: **salary bands** (probes: salary filters cover 92,842/92,907 = 99.93%; the 65-ad tail lands in the open >£200k band). Location/flag partitioning rejected: weaker coverage guarantees, combinatorial slices. Band overlaps at edges are absorbed by the ads dedupe key; the plan persists as cursor rows so planning (~2 calls/band, ledgered) happens once.
- **Coverage is sacred — a cap must limp, never lose.** The first live plan hit its 64-leaf cap inside the dense sub-£25k region and silently dropped £25,042–£200,000 — the professional range, invisible except to a contiguity check. Rule now pinned by test: when max_bands bites, remaining ranges are FLUSHED as oversized leaves. An oversized band at worst hits the wall and shows up as source_error — a visible limp — never an invisible hole. max_bands raised to 256.
- **Verification pattern that caught it:** after any partition/plan step, run the contiguity SQL (bands sorted, next.lo = hi+1, zero gaps, closed cover reaches the ceiling). Cheap, decisive, now part of the wrap ritual for partitioned sweeps.
- The safety stack earned its keep in sequence tonight: source_error guard (caught the wall) → contiguity check (caught the hole) → dedupe key (absorbs band overlaps and Reed's live page drift). None of these were speculative — each was pinned by a test written the same day it fired.

## 2026-07-22 22:22 BST — Maximum-coverage build: how the aggregator machine stores and decides (founder-ordered, run gated on founder)

Non-obvious choices made while building the 22:22 BST ship (see progress-log same time):

- **Raw layer over direct role_listings writes.** Aggregator ads land in their own keep-all table (`aggregator_ads`), NEVER directly in `role_listings` — merging into the pipeline's crown-jewel table needs the cross-source dedupe decision (0007 task 3, still open) and should be shaped by real data from the first pass. Mirrors the census/pipeline separation that already works. `content_fingerprint` (scrubbed employer|title|location) is the ready-made cross-source identity for that merge.
- **Unmatched ads are stored too.** Matching is a stamp (`matched_at` set, org NULL = confident no-match; `uncertain` = candidates exist, no silent guess). A better matcher later re-derives every label at zero API cost — quota is spent exactly once per ad, forever.
- **Locality for country-scoped sources**: Adzuna's `/gb` endpoint and Reed are UK-scoped by construction, so a bare UK town ("Basingstoke") is local unless an explicit foreign marker appears; `is_uk` remains the strong positive elsewhere. Found via the live smoke (47/150 under-labelled → rule fixed, 103 rows relabelled, 150/150 correct).
- **A dead source is not an empty inventory**: `([], total=None)` returns `source_error` and never flips `pass_complete` (the outage shape of the shared `_get_json`). Wrapper sleeps 60s and retries; quota exhaustion sleeps 30 min (ledger resets at midnight — the drip crosses days with no operator).
- **Token harvest plants hints, never verdicts**: it writes `ats_type/ats_token/careers_url` + `probe_outcome→NULL` (re-queue) and only onto cards with no known board; the normal, tested sweep path then verifies with `probe_token` (hint-first, one call) before any slug guessing. One write-path for boards/jobs stays intact; harvest write-set test-pinned to its two tables.
- **Reed full-inventory works** (keywords omitted): provider total ~92,925 — the whole Reed UK inventory fits inside ONE day's documented quota. Adzuna it-jobs ~44,562 ≈ 3–4 days at the free cap. Numbers now measured, not estimated.
- **Known limitation logged**: Reed's `jobUrl` points at Reed's own page, so harvest yield comes mostly from Adzuna redirects; Reed's job-detail API (`externalUrl`) is the future enhancement if harvest yield matters. First harvest smoke: 8 checked, 0 planted (expected — small matched set, Reed-heavy).
- **Not built, deliberately**: per-company aggregator queries (0007 task 2 — demoted: broad sweep is ~30× cheaper and covers more; reserve per-company for promoted orgs), the role_listings merge (0007 task 3 — after first-pass data), MCP switches for the aggregator (Claude drives via the script until the need is proven).

## 2026-07-22 21:26 BST — Pass 2 complete; aggregator lane designed jobs-first (no role-map fetching)

- **Pass 2 census COMPLETE** — self-stopped 20:40 BST on "0 picked" exactly as designed (evidence: `ops/sweep-logs/sweep-20260722T173825Z.log`). Software lot fully probed: **260 boards · 5,144 jobs (1,196 UK · 288 title-matched) · 0 errors**. Details in progress-log same time; plan 0003 flipped ✅ Done.
- **Aggregator-lane algorithm decided** (founder questioning session today — "role map → jobs, or jobs → companies?"): **jobs-first**. Broad category sweep (Reed = workhorse, documented ~1,000 req/day × 100 results/page; Adzuna = second opinion + salary layer, ~250/day × 50, exact quota confirmed on the dashboard at registration) → **employer-name match against the register is the filter** — NO role-keyword map as the fetch driver (a role map is a leaky filter and violates the founder's keep-all rule; titles are too creative to enumerate). Quota math: broad-sweep ≈30× cheaper in API calls than per-company door-knocking (11.7k calls vs ~400–800/full pass).
- **Token-harvest learning loop added as plan 0007 task 5:** census slug-guessing provably misses boards (legal names ≠ brand slugs — the M&S lesson). Aggregator ad apply-URLs leak real ATS tokens; feeding them through the existing `parse_ats_url` (`discover/company.py`) learns addresses the guesser missed → re-probe → those orgs get full ATS depth. Aggregators thereby GROW the board layer, not just supplement it.
- **Wiring truth for the founder's "will it work when keys land":** works day one — keyword discovery → register cross-check → onboarding (`aggregators.py` + `daily.py` + `sponsor_match.py`, tested, blank keys degrade cleanly). NOT built yet (in dependency order): cross-source dedupe (0007 task 3, MUST precede ad storage), ads-as-first-class-listings + explicit `source` column, per-company query mode (task 2), token harvesting (task 5), quota-budgeted drip wrapper (run-sweep.sh pattern). Sequencing unchanged: promotion → 1b → fetch → extraction stay the fast lane; aggregator lane is the parallel slow drip.

## 2026-07-21 23:37 BST — Third-party product direction captured as plan 0008 (friend demand; nothing built)

A friend asked for the engine for a **different profession**, still UK-sponsored jobs, with **email nudges** (open-jobs digest, applied confirmation, reply tracking — the founder wants these too). Founder directive: "make a plan, do not change anything." Logged as `plans/0008-third-party-product.md` (committed with this entry):

- **Key insight:** Pass 1's industry codes already cover every profession — the engine's software-first behaviour is one constant deep (`SOFTWARE_SIC`); generalising it is a per-profile data change, not a redesign. Sponsorship verification is profession-blind.
- **Two pathways:** LOCAL (friend self-hosts own instance/keys/data — ready after loader+SETUP+aggregators) vs HOSTED (second owner in one deployment — gated hard behind Phase 8 then Phase-9 isolation tests; no second person's data before those exist).
- **Reply tracking decision deferred, default recorded:** Claude-side via the user's own mail connector first (zero engine-held mail credentials); engine-side IMAP only ever with explicit consent + Phase-8-grade hardening.
- Non-tech professions make plan 0007's aggregator work PRIMARY coverage, not optional.

## 2026-07-20 19:43 BST — Pass 2 launched unattended; GitHub flip deferred behind it (founder order-change)

The public snapshot was staged first (fresh single-commit repo at `../goal-a-engine-public`, scrub verified) — then the founder re-ordered: run Pass 2 now, push after. Launch decisions:

- **NEW `ops/run-sweep.sh`** mirrors the proven Pass-1 wrapper: `sweep.py --software-only` in batches of 500 × 4 workers, auto-restart on transient death (per-org commits make resume exact), stops on "0 picked" (done) or the lock.
- **NEW graceful stop-file semantics** (the sweep had none): `touch .sweep-stop` stops cleanly after the current batch — founder-reachable by hand or via Claude; delete + relaunch = resume. Immediate stop stays `pkill -f run-sweep.sh; pkill -f scripts/sweep.py`. The file is gitignored.
- **Claude-independence** as Pass 1: `nohup … & disown` (PPID→launchd) + `caffeinate -i` pinned to the wrapper so the laptop naps nothing.
- **Smoke before launch:** a 5-org software batch ran clean end-to-end (5 no_board, 0 errors) — first live exercise of the post-0034 keep-all path.

## 2026-07-20 18:41 BST — Census keeps every job: is_local label replaces the UK filter (founder rule)

Pass 1 completed 2026-07-17 00:34 BST — **126,342/126,342 unique register orgs classified, 11,726 software companies, 0 errors**, wrapper self-stopped. Before Pass 2, the founder ruled (2026-07-16): "fetch all the jobs it finds — we filter later."

- **Label, not filter:** `census_jobs.is_local` (migration 0034; pre-0034 rows backfilled true — they passed the old filter by construction). `insert_census_jobs` takes a `local_matcher` beside `title_matcher`; both stamp labels, neither drops rows. Column named **is_local**, not is_uk, honouring the census schema's country-neutral principle (the `_is_local = is_uk` country seam stays the only UK-specific line).
- **Cap fairness:** when MAX_JOBS_PER_ORG (500) bites, local jobs are kept ahead of foreign; `local_jobs_seen` semantics unchanged (locals only; NULL = fetch failed vs 0 = none local still distinguishable).
- **Deliberately deferred (plan 0007, task 1b):** the pipeline layer (`fetch_jobs.py` still UK-filters before `role_listings`) and the Workday fetcher's internal non-UK skip (incl. the plain-"Remote" leak) — different blast radius, to be done together with narrowing the skill-extractor's picker so Gemini never bills foreign jobs by accident.
- **Timing discipline held:** census_store/sweep are hot files, so edits landed only after the classifier self-stopped. RED first (4 failing tests), then green; suite 402 collected, exit 0. Advisors after DDL: no new findings (the census_jobs RLS-no-policy INFO predates 0034). Local commit only.

## 2026-07-13/14 (committed 2026-07-14 21:28 BST) — Pipeline-vision insertion built additively, mid-census, with zero hot-file edits (founder-directed: "refine my vision, don't break anything, commit locally first")

The founder articulated his end-to-end flow (census → software lot → their jobs → profile tiers → skill fit → Notion or gap-closing → all Claude-driveable) and asked for it to be realised without breaking the running Pass-1 census. Mapping showed ~80% already existed; the gaps were Pass-2 software-first probing, the census→pipeline bridge, the per-job gap, and Pass-1 MCP switches. Full map: `docs/vision-pipeline.md`.

- **Commit hold lifted for LOCAL commits by the founder** ("commit this version first so we can go back"). Snapshot `dbb0e8f` = Phases 1–7.5 rollback point. No push, no publish — those still need the Phase-8 gates.
- **Hot-set discipline:** the census classifier's import chain (discover/sweep.py, census_store.py, classify.py, companies_house.py, config.py, db/connection.py, pipeline/lock.py, normalise/text.py, fetch/feeds.py, ops/run-classify.sh) was treated as READ-ONLY — a mid-run edit goes live at the next batch restart, so all new behaviour lives in NEW modules that import FROM the hot files: `discover/probe_pick.py` (Pass-2 picker + sequential/parallel runners re-using `probe_org` untouched), `discover/promote.py`, `discover/census_queries.py`, `analysis/job_gap.py`.
- **Pass-2 parallelism = one connection per worker** (psycopg connections are not shared across threads), per-org commit kept, politeness = workers/pause req-sec documented; `--workers` requires `--software-only` (argparse-enforced).
- **The bridge is founder-triggered, never automatic:** the census blast-radius wall stands (sweep never writes `target_companies`); `promote_company` is the deliberate, audited crossing — copies the census card's board, no re-probe, `register-only` confidence. Rejected alternative: letting the sweep auto-onboard (kills the wall the tests pin).
- **Gap-closing stays Claude-side by design** (AI only at caged spots): the engine provides `get_job_gap` data; the reasoning is a Claude skill, not engine logic.
- **Primary/secondary/tertiary tiering was NOT rebuilt** — it already exists as `target_roles` patterns + `fit_rank`/`lane` + `sponsor_signal` + the salary wall; renaming working concepts would churn tested code for vocabulary.
- MCP surface 19 → **24 tools** (`run_classification`, `classify_status`, `list_software_companies`, `get_job_gap`, `promote_company`; `run_sweep` gains `software_only`/`workers`). The exact-toolset pin test was updated consciously, as designed.

---

## 2026-07-12 14:22 BST — Notion filing moves OUT of the engine to Claude's own connector (founder-directed)

Founder's call (correct — it reverses part of Phase 7): the engine must not own a Notion integration. Claude already has a native, authenticated Notion connector that is faster and needs no engine-held secret. The engine's job is to produce **truth into its own database**; mirroring that into Notion for a human to read is a **presentation** concern that belongs to the client (Claude), not the engine. This also keeps the engine genuinely third-party-agnostic — a user on Slack / Sheets / email isn't forced into Notion.

- **New model:** engine → writes the ranked apply queue to its DB (source of truth, always current, works headless). Claude reads it via the existing `get_apply_queue` MCP tool **or** its own Supabase connector, and mirrors selected rows to Notion via **Claude's** connector — on demand ("sync my queue to Notion") or via a scheduled Claude routine. **No `NOTION_TOKEN` needed from the founder.**
- **Reverses Phase 7:** `src/notion/client.py` + `src/notion/tracker.py`, the Notion-upsert half of `src/cv/filing.py` (`run_filing_stage` / `file_application` / `regenerate_cv_card`), and the `NOTION_TOKEN` / `NOTION_DATABASE_ID` / `NOTION_PARENT_PAGE_ID` config get **retired** when the filing stage is next touched. **CV generation stays** engine-side (Gemini cage #3) — only decoupled from the Notion write.
- **Application STATUS source-of-truth moves to the DB** (was Notion). The old reverse-sync (`sync_applied`: Notion "Applied" checkbox → engine) is replaced by Claude calling the existing `mark_applied` MCP tool when the founder applies. No Notion→engine round-trip code.
- **Trade-off accepted (open-eyed):** a headless Cloud Run run keeps the **DB** current but does **not** touch Notion — Notion is synced whenever Claude runs. DB = 24/7 truth; Notion = human-facing mirror, refreshed on demand or on a Claude schedule. The engine's own ntfy nudge still fires headless. Matches the founder's framing: "pass the thing through to Notion for me to look into."
- **Not actioned yet** — the Pass-1 census is running and the only-touch-current-task rule holds. This folds into **Phase 8's** filing-stage work (the "file to Notion" step becomes "write to DB; Claude mirrors"). Recorded here so it isn't lost.
- **Aside (founder's efficiency question):** no API key speeds up the running census — Companies House is hard-capped at 600 req/5 min; a second CH key to parallelise was considered and **rejected** (one-app-one-key ToS, marginal gain, code not built for rotation). Gemini + Supabase keys are already set; the intelligence + data layers are covered.

---

## 2026-07-12 03:33 BST — Census re-architected into two passes: classify-first, then probe (founder-directed)

Founder's insight (correct): role-first aggregator search "searches and hopes" a sponsor comes back — it throws away the unfair advantage (the 141k sponsor list). The right shape is sponsor-first. But the register has NO occupation/industry column, so the original census probed all 141k blindly (weeks, ~1% board hit) with no way to narrow. **Companies House SIC codes are the missing narrowing signal** — official industry per company. So the census is now TWO passes:

- **Pass 1 — classify (built + running):** `src/discover/classify.py` walks the whole register and maps each company's Companies House SIC industry code + status + age onto its `sponsor_census` card — **no job-probing.** ~1 registry lookup per company, rate-limited by CH (600/5min) → whole register in ~1.5–2 days (vs weeks of blind probing). Live-verified: correctly tags 3Gi Technology/345 Technology as software (62020), but "3D Systems Europe" as wholesale (46690) and "360 Trading Networks" as financial (64999) — name-blind, fact-based. Runs `scripts/classify_sponsors.py` under its own `.classify.lock` (coexists with the probe sweep). Already-probed companies keep their cards and get SIC codes added (nothing wasted).
- **Pass 2 — probe (deferred until Pass 1 completes):** the existing `sweep.py` probe, but its picker will be changed to select ONLY `probe_outcome IS NULL AND registry_outcome='matched' AND industry_codes && SOFTWARE_SIC` — so the expensive job-probing runs on the ~10–15k genuine software/IT/data sponsors, not all 141k.

- **No schema change** — the `registry_*` columns from migration 0030 already exist; Pass 1 just fills them for everyone (a card can now be registry-classified with `probe_outcome` NULL = classified-but-not-probed; the CHECK passes on NULL). New code only: `classify.py`, `scripts/classify_sponsors.py`, `census_store.ensure_census_card` + `classify_status_counts`, `SOFTWARE_SIC` set. Reuses `companies_house.enrich_org` wholesale. 366 offline + 10 DB tests.
- **SOFTWARE_SIC set** (the Pass 2 target): 62011/62012/62020/62090/63110/63120/58210/58290/26200/72190. Stored raw codes per company; the set is only used to filter/count, so it can be widened later without re-classifying.
- **Pace honesty:** CH's 600/5min limit caps Pass 1 at ~3,600 companies/hour regardless of parallelism (we're rate-limited, not CPU-limited) — so ~1.5–2 days, and slower if the laptop sleeps (another reason for Phase 8 cloud hosting). The census's SLUG-PROBING recall ceiling (only catches boards whose slug ≈ name) is unchanged and still applies to Pass 2 — CH narrows *which* companies to probe, it doesn't fix *how* boards are found.

## 2026-07-11 21:37 BST — Phase 7.5 complete: The Census Sweep (founder-directed insertion), tests green, live-verified

Founder direction ("treat the register as a dataset — the actual analysis begins; country-agnostic machine") turned into an inserted phase between 7 and 8. Architecture v2 revised (Section 1 machine principle + PHASE 7.5 card); the staged-unbuilt Phase 8 CLAUDE.md archived as `archive-v2-phase8-build-instructions-staged.md`; Phase 7.5 CLAUDE.md built via /builder-md. **All 7 tasks done; 351 offline + 10 DB-gated tests, all 361 green under RUN_DB_TESTS=1 (was 296 + 9). Migration 0030 `sponsor_census` + `census_jobs`** (applied via Supabase MCP + mirrored; advisors after: only the expected INFO rls_enabled_no_policy on both). Commits still held.

- **The blast-radius rule is the phase's defining constraint, pinned by test AND verified live:** the sweep writes ONLY its two census tables. Never `target_companies` — the fetch stage (scripts/fetch_jobs.py:86) fetches every row with ats_type+token, so census boards would flood the daily loop. Never `review_items` — ~100k no-board flags would drown review (the register has 126,342 unique org names). Live smoke: 61 cards written; target_companies stayed 79, review_items stayed 740. Promotion census→tracked stays a deliberate act via `discover_company`/`add_target_company`; a `promote_census_company` tool was deliberately left out of v1.
- **Gemini is never called by the sweep** (cost decision at 126k-org scale). Census job titles are keyword-matched with the existing `build_role_matcher`; census_jobs stores NO JD body — promotion refetches with JD via the normal pipeline.
- **Country-agnostic by naming and seam, not by rewrite:** columns are `registry_*`, `industry_codes`, `local_jobs_seen`, `country` (default 'uk'); the sweep's local filter sits behind `_is_local = is_uk`; the national-registry client is imported as `from discover import companies_house as registry` — another country = one new plug-in module + register data. Engine-wide generalisation (visa/salary rules) stays Phase 9.
- **Per-org commit, not COMMIT_EVERY-batching:** sweep HTTP is free but slow (multi-hour batches) — exact crash-resume and milliseconds-short transactions beat commit amortisation (which exists to serve paid Gemini calls). Resumability = per-org commit + `NOT EXISTS` anti-join; verified live (25 → next 25, zero re-probes; a killed run lost only its uncommitted org).
- **Companies House contract verified live 2026-07-11** (developer-specs.company-information.service.gov.uk): Basic auth = key as username, blank password (the Reed shape); rate limit 600 req/5 min → module PAUSE 0.6 s per call + standard 429 backoff. Match rules mirror sponsor_match — exact norm, unique legal-suffix-stripped, plus ONE deliberate extension: among several exact-norm candidates, a single `active` one matches (dissolved namesakes are endemic in the registry; still deterministic — two actives stay `ambiguous`, never guessed). `ch_ready` gates the layer; blank key = probe-only automatically. FOUNDER ACTION: free key from developer.company-information.service.gov.uk → `COMPANIES_HOUSE_API_KEY` in .env.
- **MCP census switches (17 → 19 tools):** `run_sweep(batch_size)` spawns scripts/sweep.py **detached** (`start_new_session`, log under `ops/sweep-logs/`) because a sweep takes hours and must never block a chat call — the synchronous `run_pipeline` trigger pattern is right for minutes, wrong here. `sweep_status` is a pure read and does NOT audit (codebase convention: reads never audit). The sweep takes its own `.sweep.lock` so it can coexist with the daily pipeline; two sweeps cannot overlap.
- **LIVE BUG FOUND AND FIXED — `scripts/discover.py` shadowed the `src/discover` package:** Python puts the script's own directory first on sys.path, so `scripts/discover.py` (a module) hid `src/discover/` (the package) and broke its own `from discover.daily import ...` — the Phase 6 discover stage would have crashed on its first real run (offline tests mocked past it; it had never been executed live). Renamed to `scripts/discover_companies.py`; STAGE_CMDS updated with a comment pinning the reason. Lesson recorded: a scripts/*.py name must never equal a src package name.
- **LIVE RECALL GAP FOUND AND FIXED — `candidate_tokens` now tries legal-suffix-stripped variants:** every UK register name legally ends Ltd/Limited/PLC while board slugs use the bare brand, so the probe's guess list missed almost everything under its register name ('Synthesia Limited' never tried 'synthesia'). `_strip_legal` moved to its proper shared home as `normalise.text.strip_legal_suffixes` (sponsor_match keeps its old name as an alias); candidate_tokens appends stripped variants after the literal ones (original order preserved; existing tests untouched and green). Live effect: Synthesia Limited → board_found, 24 UK jobs; Quantexa Ltd → board_found, 8 UK jobs, real Ashby links, correct title_match flags. **Known remaining boundary (accepted, documented):** brands that differ beyond suffix-stripping (Monzo Bank Ltd → slug 'monzo'; Thought Machine Group Limited → 'thoughtmachine'; Improbable Worlds Ltd → 'improbable'; Wayve Technologies Ltd → 'wayve') still card as no_board — first-word guessing was rejected as a false-attribution risk (a collision would card the wrong company's jobs). Those are Claude URL-hunt territory (`classify_from_url`) on the interesting subset once registry industry codes identify it.
- **0-job board hits stay `no_board`** — classify_company's token-collision guard is load-bearing; the census under-reports parked-but-real boards rather than forking a second classifier.
- **Census scale facts:** 126,342 unique org names (dedupe by org_name_norm across 141,956 rows) — ~5.6 s/org measured live ⇒ default `--batch 2000` ≈ 3 h/night ≈ ~9 weeks to full probe coverage; registry enrichment adds ~1.2 s/org where matched. `local_jobs_seen` semantics: NULL = fetch failed, 0 = fetched and none local. Census job storage capped at 500/org (shared/agency boards).
- **Software-first ordering added 2026-07-11 22:40 (founder-directed):** `pick_batch` now sorts likely-software names first via `TECH_NAME_PATTERN` (a Postgres regex over `org_name_norm`), ahead of the skilled-worker/A-rated/id keys. This is the honest, correct use of the name signal that the 06:03 strategy session warned against as a *filter*: here it only ORDERS a census that still covers everyone — no org is excluded, tech sponsors just surface first (raising the early board-hit rate far above the ~2% seen in register-id order). Short tokens (ai/ml/data/io) are word-boundary-bounded to avoid 'email'/'retail' false hits; false positives/negatives are harmless because everyone is probed eventually. Bound as a param, never interpolated. Live-verified: the first 15 picks are all technology firms.
- **Noted for later (not built):** `--registry-backfill` picker (probe-only nights leave registry columns NULL on carded orgs — a three-line variant when needed); `promote_census_company`; a census recall pass via Claude URL-hunting; `load_tracked_orgs` can't see orgs tracked under a name that neither norms to the register row nor carries a sponsor_id link (harmless: worst case is duplicate census knowledge, never a duplicate row in target_companies).

---

## 2026-07-11 06:03 BST — Strategy session (no code changed): the register is a verifier, discovery is role-first, the MCP is optional

Founder-led conversation reviewing the built system before switching it on. No code, migrations, runs, or commits this session — direction + honest reality-check only. Key decisions and findings to carry forward:

- **The licensed-sponsor register (141,956 rows) is a VERIFIER, not a discovery source.** It has no industry column, so "filter by industry" can only match words in the org *name* — which surfaces ~5,990 generic IT/outsourcing shops (e.g. "COMPUTER DATA SHRED LTD") while MISSING the actually-wanted firms (Anthropic/Faculty/Monzo — no industry word in the name). Brute-forcing the whole register = ~6 days of probing + rate-limiting + mostly junk. **Decision: discovery must be role-first** — search by target role (aggregators, or a Claude-hybrid), then let the register *verify* the employer. Do NOT drive discovery by walking the register by name. (Sharpens the Phase 6 industry-hint note.)
- **Adopted mental model: "code is the memory/discipline/guardrails; Claude is the brain."** The genuinely code-only capabilities (things chat can't do): change-tracking across time (fingerprints/`listing_events`), unattended scheduled runs, read-once cost control (`extracted_at`), exact-every-time verification at scale (sponsor register via the shared `norm()`, the salary wall), and the truth gate policing the AI. Everything judgment-shaped (fit, prioritisation, CV wording, finding companies on the open web) is Claude's and is better left un-caged.
- **The 17-tool MCP is optional, and mainly for Claude *Desktop*.** In Claude Code the same hybrid workflow runs with zero new build: the deterministic scripts do the mechanical work, Claude reasons and reads via its own Supabase connector, and writes via its own Notion connector. Local stdio MCP can't be reached from Claude Cowork (cloud) — that needs the Phase 8 hosted MCP. The engine MCP is not registered in any client today (`ops/claude-mcp-config.json` ships the block to install; nothing installs it).
- **What "exposing tools via MCP" means — and why it's thin named tools, not raw SQL.** The engine MCP publishes **17 named, pre-written, tested actions** (`get_apply_queue`, `mark_applied`, `generate_cv`, …), NOT a generic `execute_sql`. So Claude **never writes a query through it** — it only *chooses which tool and fills a couple of typed args* (`role_id=8`); the SQL/logic was authored once, in tested code. Contrast with a **raw** connector (chat's own Supabase `execute_sql`): there Claude authors the SQL live — flexible, but blind to the engine's rules (sponsor logic, salary wall, truth gate) and able to write a wrong/destructive query. The thin-tool design is the guardrail: the *worst* Claude can do through the engine MCP is pick a wrong button, because there is no "run arbitrary SQL" button.
- **Tool determinism has two layers (recorded because it caused confusion).** The tool's *execution* is fully deterministic — the same tested code runs every time. Claude's *selection of which tool + arguments* is its reasoning (probabilistic). You do **not** teach Claude how to use them — each tool's **description** does that (a test asserts every tool has one). The price of the safety is boundedness: the engine MCP can only ever do those 17 things; new capability = a new tool (code), never runtime improvisation.
- **Two different "Notions" — do not conflate them (this confused the founder, so it's on record).** (a) **The engine's Notion** = a direct REST client using a `.env` integration token — the engine's own headless hands, filing cards on a schedule with no Claude present. **This is what the automation uses.** (b) **Claude's chat Notion connector** = Claude's own OAuth connection, works only while you're actively chatting, and powers nothing unattended. The MCP tools that write to Notion (`generate_cv`/`run_pipeline`) still reach for the engine's **`.env`** credentials — **the MCP is a trigger/button, not a second Notion connection.** So the `.env` setup is unavoidable for automation; the MCP is optional convenience on top (and in the pure hybrid, Claude could instead write cards via its *own* Notion connector, trading the engine's idempotency for chat-time flexibility).
- **Operational state confirmed (2026-07-11):** 39 fetchable companies, **0 unfetched** (all already run); 40 companies have no discoverable board (need a careers URL found first). 730 open listings, only **9 unread** by Gemini. **721/730 already carry real links** — sourced straight from the ATS JSON APIs, never from AI, so links are hallucination-proof by construction. `cv_blocks` still empty; nudges/Notion/aggregator keys still unset (founder actions).
- **Field-addition request assessed honestly:** (a) *application-open date* — real gap: the `date_opened` column exists but is 0/730 populated, and it IS sourceable from the ATS (Lever `createdAt`, etc.) → worth building when we resume. (b) *end date + time* — deadlines are all `estimated`; boards essentially never publish a stated closing *time* → cannot be filled truthfully, won't be faked. (c) *multiple links per role across portals* — premature: aggregators are off, so every listing is from one board and no cross-portal duplicates exist yet.
- **Candid strategic note (for the record):** measured purely against "apply to jobs fast," a lighter Claude-driven approach would have started applications sooner than a 7-phase build. The build earns its place on the durable axes (unattended operation, deterministic sponsor/salary verification, truthful CVs, and the artifact-as-portfolio for a UK tech role). The live gap now is *switching it on + applying to the 63 High-fit sponsor-cleared roles already in the queue*, not more building.

---

## 2026-07-11 04:27 BST — Phase 7 complete: CV Maker & Notion Filing (all 7 tasks), tests green

- **All 7 tasks done; 296 offline tests + 9 DB-gated = 305 (was 244 + 8). Nothing committed (founder hold). One migration: 0029 cv_blocks** (applied via Supabase MCP + mirrored; get_advisors after = only the expected INFO rls_enabled_no_policy, same posture as every engine table). New dep: `python-docx` (pyproject + requirements.lock).
- **cv_blocks is the fact base and the truth anchor.** Each row is one human-`confirmed` career fact; `fact_text` is the verbatim grounding source, `skill_norms text[]` uses the shared norm() so it matches `role_skills`. The loader returns only confirmed blocks by default. **FOUNDER ACTION — seed real facts:** the live table is empty; a CV can't be generated until the founder's current CV is turned into confirmed blocks (his to verify — no personal values in code).
- **assemble.py is pure and deterministic** — blocks ranked by skill overlap with the listing, ties broken on sort_hint then block_id. Same listing → same CV; different listings → different order (the "two visibly different CVs from one fact base" property, pinned by test).
- **AI spot #3 (phrase.py) is caged exactly like the other two** — reuses `read.gemini` client+retry at temperature 0 under "rephrase the supplied facts only, add nothing". Falls back to the verbatim fact on no key, any API error, or a block the model dropped. The cage's real enforcement is the truth gate, not the prompt.
- **The truth gate (truth.py) errs strict; the fallback is always safe.** Built on the `read.eval` grounding idea (verbatim containment): every number in a bullet must be present in its source fact, and ≥75% of its content words must trace back — else the bullet is replaced by the verbatim fact. This hard-catches invented metrics and fabricated employers/tools while tolerating light synonym rephrasing. Truth is the product.
- **render.py uses python-docx, NOT the docx skill's docx-js.** The skill recommends docx-js (npm) for interactive creation, but this is a headless Python engine module that must render in the daily loop without Node — the architecture card specifies python-docx, and that's correct here. Output is single-column, no tables/columns/images, real headings + real bullet lists (ATS-safe). The "golden test" is a golden **structure** (read-back paragraph sequence), because .docx bytes carry a zip timestamp and aren't byte-deterministic. Verified by read-back as a clean ATS-parseable CV.
- **Notion filing is a direct REST client, deliberately not the Claude Notion MCP** — the loop files headless. Pinned to Notion-Version `2022-06-28` (stable database/page endpoints; the 2025-09-03 "data sources" model is a later upgrade). Idempotent upsert keyed on a hidden `Role ID` number property (query → update, else create — never duplicates). `applied_role_ids` is the reverse read that syncs 'Applied' back. Token/database/parent-page in `.env`; blank token = filing skipped. **FOUNDER ACTION — Notion:** create an internal integration, share a page, set NOTION_TOKEN / NOTION_PARENT_PAGE_ID / NOTION_DATABASE_ID.
- **CV attachment vs. CV hosting — honest limitation.** The .docx IS generated and saved to `ops/cvs/`; the Notion "CV" property is a files property that takes an external URL, so the *attachment* only lights up once a public CV base URL exists (`cv_url_base`) — that hosting is Phase 8. Until then, cards carry all the data + the listing link, and the CV sits locally. Not faked.
- **Task 7 wiring:** `file` stage runs after `eval`, before the nudge, so today's cards exist when the digest sends; the nudge gains a Notion applications-board footer link; `sync_applied` marks applied in the engine from cards the human set to 'Applied'. `generate_cv(role_id, emphasis)` is the 17th MCP tool (thin wrapper; logic in `src/cv/filing.regenerate_cv_card`), letting Claude re-tailor on request. The filing stage skips cleanly without Notion and isolates a single failing listing.
- **Noted, not fixed (Rule 2):** (a) Gemini + Notion HTTP run inside the stage's/tool's DB transaction — fine for a daily batch / interactive tool, a later refinement could do network work outside the tx; (b) assemble's default `min_score=0` keeps low-relevance blocks (relevance-ordered) rather than dropping them — callers cap via `max_blocks` or `emphasis`; (c) the fetch/filing paths aren't owner-scoped beyond the default profile — Phase 9 RLS. Process: strict test-first RED→GREEN on every task.

---

## 2026-07-11 03:53 BST — Phase 6 complete: the Discovery Engine (all 7 tasks), tests green

- **All 7 tasks done; 244 offline tests + 8 DB-gated = 252 (was 186 + 6). Nothing committed (founder hold). No DDL this phase** — discovery rides existing tables; the new `review_items.kind` values (`company_onboard`, `sponsor_match`), `ats_type='workday'`, and `my_constraints.kind` hints (`region_hint`/`industry_hint`) are DATA, not schema. Migrations stayed at 0028; `get_advisors` not needed.
- **Register walk = A-rated Skilled Worker only** (`rating='A'` + `is_skilled_worker`; 122,084 of 141,956). Region/industry hints load from `my_constraints` (owner-scoped, never in code); empty hints = a broad walk. Verified `org_name_norm` == the shared `norm()` across all 141,956 rows (0 mismatches) → the name-based exclusion (and Task 6 matcher) are sound. **FOUNDER ACTION — seed `industry_hint` keywords:** with none set, the live walk returned 122k sponsors name-ordered (first candidates: a shipping firm, an ultrasound clinic) — irrelevant to the AI/data/tech lanes. Hints are what turn the register from noise into signal. Left to the founder (his criteria; no personal values in code); downstream onboarding + per-source caps bound the noise meanwhile.
- **Onboarding auto-joins the fetch list by construction:** it sets `ats_type` + `ats_token` — exactly the predicate `scripts/fetch_jobs.py` selects on — plus `sponsor_id` linkage, `web_checked=true`, `sponsor_confidence='register-only'` (the dominant existing value). Flagging is idempotent by `(kind, ref)` so daily re-runs never spam. Added `add_flag` to `review.py` so create/list/resolve all live on the one review surface (no second surface, per the gotcha).
- **Discovery MCP tools are a 2-tool skin (now 16 total, was 14):** `discover_company` + `classify_from_url`, logic in tested `src/discover/company.py`. Each attaches a sponsor-register verdict (exact-norm match); `classify_from_url` verifies a board has jobs before writing. The tool-set contract test was updated; the never-imports-the-skin invariant held (had to reword a `company.py` docstring that mentioned the package path — the invariant test is a blunt substring check).
- **Workday via the documented CXS API (not scraping).** Real shapes captured live 2026-07-11 from 3 tenants (NVIDIA/Adobe/Salesforce); trimmed real responses recorded in `tests/fixtures/workday/`. A company is onboarded from its careers URL (stored in `ats_token`); `fetch_company` dispatches `workday` via a lazy import (workday.py imports feeds, so a top-level import would cycle) → flows through the standard fetch→history→read pipeline unchanged. UK-filter on the cheap listing `locationsText`, then detail-fetch only survivors (bounds per-job calls: `max_jobs=100`, `max_pages=50`). **Known limit:** multi-location "N Locations" postings without a UK marker in the listing are skipped — a future pass can use Workday's location facet.
- **Adzuna + Reed via their official free APIs.** Adzuna auth = `app_id`/`app_key` query params; Reed auth = HTTP Basic with the key as username, empty password. Keys live in `.env` (Settings + `.env.example`); a blank key means that source is simply skipped — discovery degrades, never crashes (same posture as a blank Gemini key). Fixtures shaped from the providers' docs (no keys held to capture live). Results normalise into the standard `Job`; `salary_text` built from the structured salary range. **FOUNDER ACTION — the two free keys:** register at developer.adzuna.com and reed.co.uk/developers, paste into `.env`. I can't create the accounts.
- **Sponsor cross-check refuses to guess.** Confident only on an exact shared-`norm()` match OR a *unique* legal-suffix-normalised match (`'Acme AI'` == `'Acme AI Ltd'`). Ambiguous (several candidates) or merely partial → a `sponsor_match` review flag carrying the candidates; no register hit at all → a confident negative. Stripped suffixes are entity-forms only (ltd/limited/plc/llp/…), never geographic, so normalising can't over-merge distinct firms. **Tradeoff:** `'Monzo'` vs `'Monzo Bank Ltd'` flags for review rather than auto-matching (safe, but can add volume — a future enhancement can teach a synonym on resolve).
- **Discovery joined the schedule as the FIRST stage** (`discover` before `fetch`, so companies found today are fetched the same run and reach tonight's digest). Per-source caps (register 25, adzuna/reed 50 per query, onboard 15) and one per-source report line each into `pipeline_runs`. A failing source is isolated (`_safe`) so the stage degrades, never dies. Orchestration logic in tested `src/discover/daily.py`; `scripts/discover.py` is a thin runner.
- **Noted, not fixed (Rule 2):** (a) discovery HTTP (probes, aggregator calls) runs inside the stage's DB transaction — fine for an interactive tool / daily batch, a later refinement could probe outside the tx; (b) a company flagged-but-not-onboarded stays a register candidate and is re-probed on later runs (idempotent flagging prevents duplicate flags; caps bound it) — a clean future tweak is to exclude open-`company_onboard` companies from the walk; (c) the `scripts/fetch_jobs.py` fetch query is not owner-scoped (single-user era) — Phase 9's RLS work. **Process note:** Task 2 was coded before its tests (research-heavy); Tasks 1,3,4,5,6,7 followed strict test-first RED→GREEN. Every task ends green including DB integration.

---

## 2026-07-11 02:51 BST — Phase 5 complete: the MCP server (14 tools), DB-verified

- **All 7 tasks done; 186 offline tests + 6 DB-gated (was 122). Nothing committed (founder hold).** FastMCP 3.4.4 over stdio; the server is a *skin* — every tool wraps one tested `src/` function, zero logic in `src/mcp_server/`. A test proves no engine file imports the skin, so killing it cannot touch the daily loop.
- **`src/mcp` → `src/mcp_server` (founder-approved deviation from the CLAUDE.md).** With `pythonpath=["src"]`, a local package named `mcp` shadows the installed `mcp` SDK that fastmcp imports internally — proven to break `from fastmcp import FastMCP` at import time. Renamed to `mcp_server`; same class of bug the gotcha bans with a `queue.py` (stdlib shadow).
- **Tools call tested engine functions, never inline SQL.** New fns: `applyqueue.py` (queue/gaps/job reads + mark_applied/snooze), `review.py`, `audit.py`, `criteria/writer.py` (set_numeric_criterion/add_target_company; `default_profile_id` in loader), `pipeline/trigger.py` (shells the SAME `run.py`, injectable runner), `notify.push.send_test`, plus read fns on `history/events.py` + `pipeline/report.py`. `jobqueue.py` left untouched (Rule 2; its inline view query isn't logic-duplication — the ranking lives in the view).
- **No tool returns a secret** — curated column lists exclude `ats_token`/`notification_channel`/`notion_token_ref`; `send_test_nudge`/`get_criteria` return booleans/criteria only. Pinned by tests + a live scan.
- **snooze_listing = stamp `nudged_at`** (reuse the existing never-re-nudge mechanism; no schema change). It suppresses future nudges, not queue visibility — that's the Phase 5 meaning of "snooze."
- **review_items seed = 740, not 74.** The CLAUDE.md's "74 low-confidence synonyms" was stale; `skill_synonyms` grew to 1998 total / 740 at `confidence='low'`. Seeded all 740 (the operative rule is `confidence='low'`), idempotent by `ref`; flagged the 10× to the founder before applying.
- **mcp_audit:** every action + `resolve_review_flag` writes one row (tool, arg summary, result summary — never a secret) in the action's own transaction; a no-op `set_criteria` and a failed resolve write nothing. Live-verified: `run_pipeline(dry_run)` wrote `{tool:run_pipeline, args:{dry_run:true}, result:{dry_run:true,returncode:0}}`.
- **Schema (Supabase MCP, mirrored to `db/migrations/`):** 0027 `review_items`, 0028 `mcp_audit` — additive, RLS enabled with no policy (matching every engine table; real per-owner policies are Phase 9). `get_advisors` after each: only the expected INFO `rls_enabled_no_policy`, no new WARN/ERROR (the WARNs are all pre-existing).
- **Live verification was read-only / dry-run / safe only — no write tool mutated production during the build.** All 6 read tools on live data (0 secrets); `run_pipeline(dry_run)` previewed ~63 nudges; `list_review_flags` returned real seeded flags; the audit row landed. Write tools proven offline via FakeCursor, per the codebase convention.
- **Harness:** the in-process `fastmcp.Client` drives every tool, offline by default (DB/subprocess/push mocked), async via `asyncio.run` (no pytest-asyncio dependency). `fastmcp>=3.4,<4` pinned; `requirements.lock` 35→82 with no pre-existing pin moved.
- **Founder switches still pending:** commit go-ahead; ntfy topic on the profile (so `send_test_nudge`/nudges do anything); launchctl load. Also open for review: the 740 synonym flags; the Phase 2 fit-filter drift.

---

## 2026-07-11 00:02 BST — Doc system consolidated: handoff + PROJECT-MEMORY retired

- **Founder decision:** too many overlapping tracking files. Retired two:
  - **`docs/handoffs/`** — redundant: its phase map duplicated `architecture-v2.md`, its phase tracker duplicated `progress-log.md`, and its only unique piece (the end-of-phase checklist) now lives self-contained in each `CLAUDE.md`'s "End of Phase" section.
  - **`PROJECT-MEMORY.md`** — its standing-holds and review items are already carried in this decision-log, the `CLAUDE.md` banner, and `../SESSION-MEMORY.md` (now the single memory file).
- **Kept in `docs/`:** `architecture/` (the plan), `decision-log.md` (human-facing why), `claude-md-archive/` (past phase instructions), `progress-log.md` (task diary). Plus `PRD.md` (requirements; overlaps architecture — retire if desired) and `dev.md` (runbook: how to run + launchd — operational, not redundant).
- **CLAUDE.md End-of-Phase is now self-contained** (4 explicit steps: decision-log, progress-log, archive the CLAUDE.md, write the next from the next architecture card). No handoff needed.
- Note: `architecture-v2.md`'s folder-structure section still shows a `/docs/handoffs/` in its ideal layout — deliberately deviated; do not recreate it.
- **Git:** founder's view — committing internal build-scaffolding docs adds little value (Phase 8 publishes a fresh squashed public repo anyway). No commits made; the code commit go-ahead remains the founder's standing hold.

---

## 2026-07-10 22:45 BST — Phase 4 complete; FIRST FULL AUTOMATIC RUN: all stages ok, zero failures

- **pipeline_runs Run 1 = 'ok' (~12 min):** fetch 731 UK jobs / 39 companies, 187 stale closed (305s) → Gemini read 223 new roles, 2,060 skill rows, 193 enriched, 0 failed (356s) → 232 synonyms in 3 banked batches, 74 flagged low for review (26s) → salary on 91/730 open roles (12.5% — matches the ~13% expectation) → 729 estimated deadlines → grounding eval passed the 0.60 gate → nudge stage ok (no channel configured yet, reported honestly).
- **History went live:** 514 listing_events on first run — 164 appeared, 163 changed, 187 closed. Queue now 100 roles. 45 listings carry resolver-confirmed SOC codes (per-SOC wall verdicts appear as salaried+coded listings overlap grows).
- **Founder switches still pending:** ntfy topic on the profile; launchctl load (daily spend); commit go-ahead. Also for review: 74 low-confidence synonyms; the Phase 2 fit-filter drift.

---

## 2026-07-10 22:00 BST — GA-001 CLOSED: rotation confirmed by founder; keys live-verified

- Founder confirmed rotation of the Supabase DB password, Supabase secret key, and Gemini API key.
- **Verified live:** DB connection with the rotated credentials (754 listings visible); one minimal Gemini call returned correct structured output (skills/salary/sponsor/soc extracted as designed).
- **Commits remain held by founder instruction** ("don't commit now") — no longer gate-blocked; will be committed as a clean series on his word.

---

## 2026-07-10 21:52 BST — Phase 2 complete (rotation gate still carried); key decisions

- **All 7 Phase 2 tasks done; 86 tests (81 offline 0.79s + 5 DB integration).** Still nothing committed — gate open.
- **Going rates:** `skilled_worker_occupations` holds NO rate data (v1 assumption wrong). Seeded 17 tech-relevant codes directly from gov.uk Appendix Skilled Occupations Table 1 (page "Updated: 1 July 2026", fetched 2026-07-10; 2134=£54,700, 2133=£54,900, 2131=£58,200). **Partial seed by design** — unlisted codes fall back to flat thresholds; log records exactly what's covered. 3544/3573 absent from Table 1 (not RQF6-eligible), intentionally unseeded.
- **SOC resolution never guesses:** raw reader hints live in `soc_hint` (evidence); `soc_code` only accepts resolver-confirmed official codes (name/related-title exact match, ambiguous→None). Legacy free-text backfill: 34/580 resolved, 546 NULL. Wall verdicts show their basis in `wall_basis`.
- **Wall semantics:** with a code — salary_max ≥ greatest(going rate, flat standard) = clears; ≥ greatest(70% going rate, flat new-entrant) = clears_new_entrant (70% = official new-entrant band). Without — flat thresholds. Advisory always.
- **FOUNDER REVIEW NEEDED — fit-filter drift:** the queue's title regex and `target_roles` disagree. Switching the view to DB-driven matching today would drop 23 of 84 queue roles (search-title coverage gap). Left the regex untouched; fix = enrich target_roles search titles, then switch (natural fit: Phase 6 discovery, or a 20-minute founder review of the 39 titles).
- **owner_id DEFAULT** ('…0001', the founder's profile) is a single-user convenience — Phase 9 removes it.

---

## 2026-07-10 21:23 BST — Phase 1 build complete except the rotation gate; nothing committed yet

- **Tasks 2–11 all done, 70/70 tests passing** (was 45 at phase start). Full task-by-task record in `progress-log.md`.
- **Open:** Task 0/1 — rotation gate. Everything sits UNCOMMITTED in the working tree per the gate (no commit/push/live-Gemini until Shayan confirms rotation). On confirmation: record it here, live-test the new Gemini key, then commit the phase as a clean series.
- **Decisions made during build:** partial unique index (not blanket) on my_constraints — kill_keyword legitimately has 8 rows, only the three singleton threshold kinds are constrained (0017). requirements.txt deleted — pyproject.toml is the dependency source of truth, requirements.lock (pip freeze) is the exact-reproduction file. `enrich_salary` updates are now conditional (IS DISTINCT FROM) so updated_at only moves when values actually change. Migration 0016 backfilled extracted_at for 733/754 listings, mirroring the old read-once rule exactly; 11 open roles remain genuinely unread.
- **Noted for later phases:** advisor warnings (function search_path on set_skill_norm/set_updated_at, pg_trgm in public schema, always-true RLS policies on pre-existing tables) are pre-existing, untouched per rule 2 — they belong to Phase 9's real RLS work. The v_apply_queue UK backstop still uses the old weaker pattern (Phase 2 rebuilds the view). The venv's pip shebang is stale from a folder move (`python -m pip` works; a venv rebuild fixes it whenever convenient).

---

## 2026-07-10 21:12 BST — Phase 1 Task 4: is_uk() hardened; DB verified clean

- **Fix:** `is_uk()` split into strong markers (UK/GB/England/… decide alone) vs ambiguous UK city names (count only with no foreign country word or comma-anchored US/CA/AU region code alongside). An explicit non-UK 2–3-letter country code is now authoritative. 3 new pinning tests (RED verified first); suite 48/48 green.
- **Purge evidence:** 754 stored listings scanned with the new matcher — **0 false-UK rows** (migration 0011's deletion still holding; nothing fetched since). Before: 754 / after: 754.
- **Noted, not touched (rule 2):** the SQL UK backstop in `v_apply_queue` still carries the weaker pattern — gets rebuilt anyway in Phase 2's owner-aware view work.
- **Gate note:** commits deferred — rotation gate still open; all work sits in the working tree.

---

## 2026-07-10 20:54 BST — Log created; phase-transition protocol locked

- **Phase-transition protocol (Shayan):** when a phase completes → (1) copy root `CLAUDE.md` to `docs/claude-md-archive/` under a non-loading name; (2) log completion + decisions here and progress in `docs/progress-log.md`; (3) update the phase-history lines in `docs/handoffs/architecture-handoff.md`; (4) build the next phase's `CLAUDE.md` via /builder-md; (5) replace root `CLAUDE.md`.
- **Architecture v2 confirmed and filed** (`docs/architecture/architecture-v2.md`, 10 phases). Phase 1 = Foundation Reset & Hardening; its CLAUDE.md is live at repo root.
- **GA-001 rotation gate:** OPEN — awaiting founder confirmation that the Supabase DB password, Supabase secret key, and Gemini key are rotated. No commit, push, or live Gemini call until closed.
