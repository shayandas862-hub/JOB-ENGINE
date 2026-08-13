# Vision — Goal A Engine

What the product **is** and **why it exists**, and the log of every change to
that answer. How it is built lives in `architecture/architecture-v2.md`;
choices inside that architecture live in `decision-log.md`. Record IDs follow
`docs/id-registry.json` (project code `GAE`; the next free vision number is
`allocated.vision + 1` there — never retyped here or in a phase card).

---

## §1 — The vision as it stands

**Last verified: 2026-08-06** · rewritten in place whenever §2 gains an entry.

**Why it exists.** Goal A: the founder's own visa-sponsored UK job (deadline
mid-November 2026), searched by a machine instead of by hand — and, from the
same day-one brief, a portfolio-grade public proof that the founder builds and
operates production systems (V-GAE-001).

**What it is.** A sponsor-aware job-search and data-analysis machine. It
starts from the law, not from listings: the government sponsor register is
sieve 1, the census learns what every sponsor *is*, the engine watches their
jobs, matches them to an owner's profile with receipts attached, and nudges
every morning. The human always presses apply. Its bones are person- and
country-agnostic — a user is rows, never code; a country is one register
dataset plus one registry plug-in. All user-side intelligence runs on the
user's **own** AI through a guarded MCP connector; the deterministic engine
runs whole with zero AI reachable.

**The one metric.** Applications submitted. Data collected, companies
tracked, scores computed are means, not the point
(`product-brief.md` — "The number the whole machine bows to").

**What that commits it to.** The morning apply lane is never blocked or
staled by building; every score ships its receipts (no naked numbers);
keep-all evidence layers never lose rows (labels and stamps, never deletes);
no AI runs on the operator's account for users' work; personal data lives in
the database, never in code.

Current full statement: `product-brief.md` (2026-08-03) · requirements:
`PRD.md` · build state: the phase banner in `CLAUDE.md`.

---

## §2 — The vision log

> **Provenance.** Every entry below was **reconstructed on 2026-08-06 from
> the committed record** — none was written contemporaneously with the change
> it describes. Each entry cites the artefact(s) it was read from so the
> reconstruction is checkable. Wording inside quotation marks is verbatim
> from the cited file. Entries are newest first.

### V-GAE-008 — the market position at full strength: the departure board, and one number to bow to
**2026-08-03** · Caused by: founder's product walkthrough · Read from: `docs/product-brief.md`, `plans/0009-public-product-position.md`, `docs/decision-log.md` (2026-08-03 entry)

**What changed in the vision:** the "why" widens from the founder's own search
to a named market — visa-needing seekers (the ideal user "Priya"), for whom
the product is "the missing layer between the government's register and the
apply button": a working departure board. The north star is pinned in
writing: **applications submitted**. The same day, the universal product
layer (any profession through owner lenses; "user words never edit code —
they become rows") was inserted as Phase 8.5.

**Forces:** Phase 8.5 lands before multi-user Phase 9; the dashboard shows
the applications counter first; `product-brief.md` and `plans/0009` become
the standing position documents.

**Still unreconciled:** `docs/product-brief.md` had zero inbound references
from any other document until this file cited it (found in the 2026-08-06
audit).

### V-GAE-007 — all intelligence moves to the user's own AI; the engine stays deterministic
**2026-08-02** · Caused by: founder constraint pinned in the design session · Read from: `docs/decision-log.md` (2026-08-02 15:21 entry)

**What changed in the vision:** from "AI at three caged spots on the
founder's account" to "the hosted engine runs **NO AI on the founder's
account**" — all AI runs in each user's own client (Claude / ChatGPT /
Gemini) over MCP, and the engine's daily run must complete with zero AI
reachable. Bring-your-own-AI becomes product identity: operator AI cost
approximately zero per user, vendor-agnostic by construction.

**Forces:** sieve-3 becomes a staged work queue (the reading tray); prompts
become server-side versioned data; verification is deterministic at the
submission boundary; MCP contract v2; the remaining caged spots gain a hard
spend cap (Phase 8).

### V-GAE-006 — maximum coverage becomes identity: keep every job, filter later, for any third person
**2026-07-22** · Caused by: founder rule of 2026-07-16 ("fetch all the jobs it finds — we filter later") culminating in the founder order of 2026-07-22 · Read from: `docs/decision-log.md` (2026-07-20 18:41 and 2026-07-22 22:22 entries), `docs/progress-log.md` (2026-07-22 22:22 line)

**What changed in the vision:** the machine stops being a filter and becomes
a keep-all evidence layer — "full data of all the jobs of all the companies…
maximum coverage of real data… works for any third person". Storage stamps
labels (`is_local`, `title_match`); filtering happens at query time; no
decision is ever destroyed by storage.

**Forces:** the aggregator keep-all machine (ads layer, quota drip);
"keep-all tables never lose rows" became a standing phase rule; "coverage is
sacred" (2026-07-23 decision) governs every later partition design.

### V-GAE-005 — from personal tool to product for others
**2026-07-21** · Caused by: a friend's request for the engine in a different profession; founder directive "make a plan, do not change anything" · Read from: `docs/decision-log.md` (2026-07-21 23:37 entry), `plans/0008-third-party-product.md`

**What changed in the vision:** the audience formally widens beyond the
founder — LOCAL (self-hosted) and HOSTED (second owner) pathways are named.
The census's official industry codes already cover every profession, so
generalising is per-profile data, not a redesign; sponsorship verification is
profession-blind.

**Forces:** plans 0008/0009; the hosted-MCP direction; Phase 9 (third-party
ready) gains its content; aggregator coverage becomes primary for non-tech
professions.

### V-GAE-004 — the founder's pipeline vision mapped end-to-end
**2026-07-13** · Caused by: founder direction mid-census ("refine my vision, don't break anything, commit locally first") · Read from: `docs/vision-pipeline.md`, `docs/decision-log.md` (2026-07-13/14 entry)

**What changed in the vision:** the product is stated as the founder's own
sequence — census the whole register → take the software lot first → fetch
all their jobs → tier against the profile → skills and gaps → Notion with a
tailored, truth-gated CV → an agent reasons about closing the gaps — every
step driveable from Claude in any combination, with the census→pipeline
bridge explicit and founder-triggered.

**Forces:** the Pass-2 software-first picker, the promote bridge, census
query tools, MCP 19→24 tools; `docs/vision-pipeline.md` becomes the flow's
map.

### V-GAE-003 — "a job-search AND data-analysis machine, not a UK program"
**2026-07-11** · Caused by: founder-directed insertion of Phase 7.5 (the census sweep) · Read from: `docs/architecture/architecture-v2.md` §1, "The machine principle (added 2026-07-11)"

**What changed in the vision:** the UK sponsor register is demoted from the
product's identity to "its first dataset, not its identity". Country-
agnosticism becomes design law: country-neutral column names, the national
registry as a swappable per-country plug-in, board probing already global.

**Forces:** census schema naming (`registry_*`, `country`); the one-import
registry seam; full generalisation of UK visa/salary rules assigned to
Phase 9.

### V-GAE-002 — tool → system: architecture v2 supersedes the implicit v1
**2026-07-10** · Caused by: the founder's 2026-07-10 audit and confirmation session · Read from: `docs/architecture/architecture-v2.md` header ("**Supersedes:** the implicit v1 architecture (Phases 1–6 engine, CLI-only, fixed company list)"), `docs/PRD.md` ("Confirmed: 2026-07-10")

**What changed in the vision:** the same day the origin brief was locked, its
Project-1 scope was superseded: instead of deploying the existing engine
unchanged, the engine becomes a **system** — discovery, job history, CV
maker, MCP reasoning layer, person-agnostic data, a ten-phase build ("From
Tool to System"). The brief carries no clock time; the intra-day order is
brief → architecture confirmation.

**Forces:** the ten-phase plan; `PRD.md` as the what, `architecture-v2.md`
as the how; the going-live shape moves from "this weekend" to Phase 8.

**Still unreconciled:** the origin brief was never updated — it still reads
"engine … UNCHANGED" with "26 tests" (see V-GAE-001). `architecture-v2.md`'s
own header still points at retired companions (`../handoffs/`,
`PROJECT-MEMORY.md` — retired 2026-07-11 per the decision log), and its
folder plan names a `docs/architecture-decisions.md` that was never created
(`decision-log.md` absorbed that role).

### V-GAE-001 — origin: a portfolio-grade proof machine for the founder's own job hunt
**2026-07-10** · Caused by: founder's explicit decision, locked in the GOAL build brief · Read from: `../goal-a-build-brief.md` (outside this repo: "GOAL A — FINAL BUILD BRIEF (locked 10 Jul 2026)", Project 1 "JOB ENGINE, LIVE"), `docs/PRD.md` line citing the brief

**Why the project exists, as first recorded:** Goal A — a visa-sponsored UK
job. Project 1 of the brief is this repo's origin: put the already-built
engine ("960 lines, 6 modules, 26 tests — UNCHANGED") into a container on
Cloud Run with CI and a public status page, as the proof a hiring manager can
see alive. Applications were to start 13 Jul "regardless of build state";
the pacing rule was later pinned as strategist decision D-053 ("building only
continues alongside real applications", cited in `PRD.md`).

**Forces:** the going-live shape that is still Phase 8's card today —
container, Cloud Run + Scheduler, public status page, public repo.

**Still unreconciled:** the brief still carries the superseded Project-1
scope (unchanged engine, 26 tests, weekend sprint dates, Render/Railway
fallback) and was never revised; its pacing rule still governs through D-053
and the standing "Applications: 0" counter in `CLAUDE.md`.

---

## §3 — The standard for this file

- **An entry is owed** when what the product **is** or **why it exists**
  changes: audience, identity, the north-star metric, the AI/cost structure,
  country scope, the reason for building. Component shape changes go to the
  architecture record; choices inside the architecture go to
  `decision-log.md`.
- **Anchor style:** heading-anchored — `### V-GAE-NNN — headline`. The number
  comes from `docs/id-registry.json` (`allocated.vision` + 1), bumped in the
  same change that mints the entry. Numbers are never derived from position,
  title, or content, and never recycled.
- **Every entry carries:** a date · **Caused by** (the upward trace) ·
  **Read from** (for reconstructed entries; contemporaneous entries may omit
  it) · **What changed in the vision** (the before and the after, plainly) ·
  **Forces** (the forward trace) · **Still unreconciled** (when an upstream
  document was superseded and not updated). An entry with neither Caused by
  nor Forces is a note, not a vision change.
- **§1 is rewritten in place** whenever §2 gains an entry, and its
  "Last verified" date is bumped.
- **Reconstructed entries are marked as reconstructed** in a provenance note,
  with the reconstruction date and the artefacts read.
