# 0008 — Third-party product: the engine for another person (friend's profile)

- **Status:** 🔲 Todo (plan only — founder said "make a plan, do not change anything")
- **Created:** 2026-07-21  ·  **Last updated:** 2026-07-21
- **Depends on / blocked by:** plan 0007 (aggregator-first coverage — mandatory for
  non-tech professions); plan 0005 / Phase 8 (only for the hosted pathway); plan 0006
  task 3 (register-loader script — shared task, first build item either way);
  founder go to build
- **Owner / last touched by:** Claude session 2026-07-21

## Goal
A friend wants the engine for a **different job profile** (not software), still UK
**sponsored** jobs — and wants **email nudges** (open jobs, applied, and reply
tracking; the founder wants the same). This plan captures everything that must
change, the two delivery pathways, the Claude/MCP story for a second user, and the
product feature list — so building it later is execution, not archaeology.

## Why this is small: the design already carries it
Personalisation lives in **data, not code** (profiles, target_roles, my_skills,
criteria, salary constraints — all per-owner DB rows). Census Pass 1 classified all
126,342 sponsors with industry codes **for every industry**, so any profession's
company lot is one query. Sponsorship verification is profession-blind.

## What actually changes (the generalisation list)
- [ ] **Industry set becomes per-profile data** — `SOFTWARE_SIC` is a hard-coded
      constant in `discover/classify.py` / used by `probe_pick.py`; make the
      industry-code set a profile/criteria setting so Pass 2 and
      `list_software_companies` work for "healthcare lot" / "finance lot" etc.
      (underlying fns already take the set as a parameter — small, test-first)
- [ ] **SOC going-rates seeding for the second profession** — data task: their
      occupation codes + official going rates (salary wall is already per-SOC)
- [ ] **Aggregator-first coverage** (= plan 0007 tasks 2–3) — non-tech employers
      live on Reed/Adzuna/others far more than on the 5 tech ATS boards; for the
      friend this is the PRIMARY job source, not a supplement. Their keys, their quota.
- [ ] **Register-loader script + SETUP.md** (= plan 0006 task 3 + new guide) —
      today the register load is unscripted (done once by hand); a third party
      cannot bootstrap without it. SETUP.md: Supabase project → migrations →
      .env → register load → profile/skills seed → first run.
- [ ] **Single-owner assumption sweep** — audit `default_profile_id()` call sites
      and anything else that assumes one owner, so a second profile on ONE
      instance (hosted path) can't cross-read; per-owner isolation tests pinned.
      (Local path: not needed — one instance per person = natural isolation.)
- [ ] **Profile-seeding helper** — a guided script (or Claude skill) that turns a
      person's answers (roles, skills, salary floor, locations) into the seed rows,
      so onboarding a new profile is an hour, not a schema lesson.

## The email-nudge feature (founder wants it too — new notify channel)
Today's nudge = ntfy phone push (owner's topic unset even for the founder). Email adds:
- [ ] **(a) Open-jobs digest email** — daily/on-run summary of new + still-open
      matched jobs. Engine-side: a caged SMTP/API sender (e.g. Resend/SES free tier,
      key in .env, blank = skipped) beside the existing ntfy nudge. Small.
- [ ] **(b) "Applied" confirmation email** — fires on `mark_applied`. Small,
      rides the same sender.
- [ ] **(c) Reply tracking ("did the company answer?")** — REQUIRES reading the
      user's inbox. Two honest routes, decide at build time:
      1. **Claude-side (recommended first):** the user's own Claude reads their
         Gmail/Outlook via connector, matches replies to applied jobs (via the
         MCP apply-queue), updates status through `mark_applied`-style tools.
         Zero engine credentials, user's data stays in their Claude.
      2. **Engine-side IMAP/Gmail-API poller:** engine holds mail credentials —
         real privacy/security surface (esp. hosted); only with explicit consent,
         scoped app-password, and its own audit trail. Phase-8-grade hardening.
      Decision logged when building; default to route 1.

## Pathway A — LOCAL (self-hosted by the friend). Ready soonest, £0
Friend runs their own instance on their machine: own free Supabase, own free keys
(Companies House, Gemini optional, Reed/Adzuna), own data.
- Founder gives: the public repo URL (snapshot already staged), SETUP.md, the
  seeding helper, this plan's generalisations once built.
- Friend gives (to themselves): ~an hour of setup, their profile/roles/skills,
  their CV facts if they want the CV maker, a laptop that can idle for runs.
- Privacy: total — nothing of theirs touches the founder's systems, and vice versa.
- Needs from this plan: generalisation list + loader/SETUP + (for their industry)
  the aggregator build. No Phase 8 dependency.

## Pathway B — HOSTED (founder runs it as a service). The product play, later
One cloud deployment (Phase 8: Cloud Run + Scheduler + Secret Manager), friend is a
second **owner** in the multi-tenant DB (Phase 9 hardening: per-owner isolation
pinned by tests, per-owner spend caps, hosted MCP tokens per user).
- Founder gives: an account (owner row + hosted-MCP bearer token), onboarding.
- Friend gives: their profile data, their own aggregator keys (or founder meters
  shared ones — decide), possibly a fee later (product pricing out of scope here).
- Blocked by: Phase 8 THEN the Phase 9 isolation work. Do not host a second
  person's data before the isolation tests exist.

## Claude + MCP for the second user — what they need, what they can do
- **Local pathway:** friend installs Claude Desktop (any paid plan), adds the
  engine's MCP server to their config (the repo ships `ops/claude-mcp-config.json`
  as a template — stdio, points at THEIR clone). Their Claude then drives THEIR
  engine: nothing shared with the founder's.
- **Hosted pathway (Phase 8+):** friend's Claude connects to the hosted MCP over
  HTTP with a bearer token the founder issues; token maps to their owner_id only.
- **What the 24 tools give them (product feature list, user-facing words):**
  1. "Show my apply queue" — ranked sponsored jobs matching THEIR profile
  2. "What's the skill gap for this job?" — have/missing/coverage per job
  3. "Which companies in MY industry are hiring?" — census cut by their SIC set*
  4. "Run the pipeline / census / sweep now" + live status scoreboards
  5. "Promote this company into my pipeline" — audited, human-gated
  6. "Mark this one applied" — status truth in their DB
  7. CV per shortlisted job (once their CV fact-bank is seeded) — truth-gated .docx
  8. Notion/Sheets mirroring via their Claude's own connectors (plan 0004 model)
  9. Email nudges per this plan; reply-tracking via their Claude's mail connector
  (*after the industry-set generalisation above)

## What the founder shares vs never shares
- **Shares:** public repo, SETUP.md, seeding helper, this plan's features; for
  hosted: an owner account + token. Optionally: guidance hours.
- **Never:** his .env/keys, his Supabase, his profile/CV data, PROJECT-MEMORY,
  the private repo. The friend's inbox credentials never touch the founder either
  (reply-tracking route 1 keeps mail inside the friend's own Claude).

## Build order (when founder says go)
1. Register-loader + SETUP.md (unblocks Pathway A entirely; also plan 0006 task 3)
2. Industry-set → per-profile data (+ tests; keeps founder's software flow identical)
3. Aggregator work = plan 0007 tasks 2–3 (needs keys — friend's industry demands it)
4. Profile-seeding helper; SOC seeding for the friend's profession
5. Email nudges (a) + (b) engine-side; (c) as a Claude-side routine first
6. — hosted only — Phase 8, then Phase 9 isolation, then friend onboarding

## Notes / log
- 2026-07-21 23:37 BST — Plan captured from founder ("friend wants it for a
  different profile, sponsored jobs; email nudges incl. replies — in my pipeline
  too; make a plan, change nothing"). Nothing built. Sweep (Pass 2) untouched and
  running throughout. Key insight recorded: Pass 1's industry codes already cover
  every profession — the engine's software-first behaviour is one constant deep.
