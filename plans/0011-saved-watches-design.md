# 0011 — Named Saved Watches: full design (DESIGN ONLY — do not build yet)

- **Status:** 🟡 **STARTED 2026-08-12 — the deterministic core is built and
  green; nothing is wired to a stage yet.** Built on the founder's word after
  his quota reset, having been cut from the first Phase 9.5 pass for time
  only. **Nothing below is stale; the design stands as written.**
  - ✅ **§1 the ten dimensions** — `src/watch/dimensions.py`, 23 tests
    (`tests/test_watch_dimensions.py`). The closed space is ENFORCED: an
    unknown key is refused rather than ignored, an empty watch is refused,
    and every always-on protection named as a filter (`salary_wall`,
    `visa_wall`, `skip_wall`) is refused — § admission gate 3 made real.
    Values normalise on the way in so two spellings cannot become two watches
    with a Jaccard of 1.0.
  - ✅ **§2a the yield estimate's arithmetic** — `src/watch/poisson.py`, 22
    tests (`tests/test_watch_poisson.py`). Jeffreys interval on the Poisson
    rate, so 0 catches reads "0, but could be up to X" instead of a fake hard
    zero. No scipy or numpy in this project, so the regularised incomplete
    gamma and its inverse are implemented here and pinned against **published
    chi-square quantiles** and the one closed form that exists (a = 1 is the
    exponential) — a special function nobody checked is just a number
    generator.
  - ⛔ **Not built:** the evaluator (§1 filters → SQL), the rest of the §2
    maths (sensitivity, Jaccard overlap, inter-arrival rhythm, health), the
    two migrations, the store, the four MCP tools, the nightly stage, the
    nudge lines and the dashboard tab.
  - **The open decision that stopped the evaluator, stated so it is not
    rediscovered:** what does a watch evaluate OVER? `v_apply_queue` carries
    the always-on protections (§ gate 3 — the salary wall verdict, applied
    and snoozed hidden) and `fit_rank` for dimension 9, and it is already
    owner-scoped — but it is pre-narrowed to open, local, in-scope roles,
    which would silently break the founder's own first example, "watch Monzo
    — any role". Evaluating over `role_listings` instead means re-applying
    every always-on protection by hand, which is how two implementations of
    one rule drift apart ([[B-GAE-025]]). The likely answer is a new curated
    view for watches that keeps the protections and drops the lens narrowing,
    plus `source` and the census industry codes, which neither existing view
    carries. **That is a schema decision and it deserves its own migration,
    not a guess at the end of a session.**
- **Still true, and it is why the stage was not begun:** it touches
  `scripts/run.py`, so the sacred lane rule applies — rebuild →
  `gcloud run jobs execute goal-a-daily --region europe-west2 --wait` →
  verify 15/15 stages ok → only then may the 06:30 cron meet it. **Nothing
  built so far has a caller**: `src/watch/` is pure library code, no stage
  imports it, and the nightly job is byte-for-byte unaffected.
- **Created:** 2026-08-03 · **Last updated:** 2026-08-03
- **Depends on / blocked by:** Phase 8.5 item 14 (owner-lens: user words → rule rows) must land first; Phase 8 is NOT touched by this plan.
- **Owner / last touched by:** Claude session 2026-08-03 (the walkthrough chat)
- **Supersedes:** plan 0010 item 15 (this is that item, designed in full)

## Goal

One user keeps SEVERAL standing watches — named filter combinations evaluated
every night — each feeding its own labelled line in the morning nudge and its
own view in the dashboard. The user speaks a watch into existence; the
mathematics tell them, BEFORE saving, whether it will feed them or starve
them. Everything deterministic, everything with receipts.

## 1. The combination space (what a watch can be made of)

A watch = **AND** of any chosen dimensions; the user's watch list = **OR** of
watches. Ten dimensions exist in the data today:

| # | Dimension | Backed by (already in DB) |
|---|-----------|---------------------------|
| 1 | Company (one, or a set) | register + census + target_companies |
| 2 | Industry (plain words → SIC set) | sic_codes dictionary + census industry_codes |
| 3 | Role words (synonym-expanded titles; SOC family) | synonyms table + title matcher |
| 4 | Location (town / region / is-local) | listing location + is_local labels |
| 5 | Salary floor (visa wall ALWAYS applies on top, not optional) | salary parsing + per-SOC wall |
| 6 | Source type (company board / ad site / either) | listing source column |
| 7 | Sponsor rating (A-rated only / any) + route | licensed_sponsors generated columns |
| 8 | Freshness (first seen ≤ N days) | first_seen + listing_events |
| 9 | Fit floor (match score ≥ threshold) | src/match score + receipts |
| 10 | Deadline horizon (closes within N days) | survival/stated deadlines |

Examples the founder gave, expressed in this algebra:
- "Watch Monzo — any role" = {company}
- "Anyone advertising senior carer" = {role}
- "Data roles in Leeds above £45k" = {role, location, salary}
- "A-rated fintechs posting this week" = {industry, rating, freshness}

Rule: dimensions 1–10 are the WHOLE space. No free-text query language, no
custom SQL — combinations of these ten, nothing else. That keeps every watch
explainable, testable, and safe.

## 2. The mathematics (what makes this more than a filter)

Every number below is computed from stored history — deterministic, receipts
attached, no AI anywhere.

**(a) Predicted yield — Poisson rate estimation.** Before a watch is saved,
replay it over the last 60 nights of stored listings: it would have caught
k jobs over t nights → estimated nightly rate λ = k/t, shown with a
small-sample interval (Jeffreys interval on the Poisson rate, so 0 catches
honestly reads "0, but could be up to X" instead of a fake hard zero).
Surface: **"this watch would have caught ~2.3 jobs/week over the past two
months (11 real examples attached)."** The replay rows ARE the receipts.

**(b) Too-tight / too-loose advice — one-dimension sensitivity.** Re-run the
replay ten more times, each with ONE dimension relaxed a notch (salary −£2k,
radius +1 town band, freshness +7 days, fit floor −0.05…). The deltas give a
finite-difference sensitivity per dimension: **"loosening salary by £2k
would have caught 5 more; dropping the A-rating filter adds 0."** If
λ ≈ 0 → name the cheapest loosening. If λ > the cap → name the tightening
that cuts most noise ("adding location cuts 40/night to 6"). Pure counting;
no model, no guessing.

**(c) Overlap between watches — Jaccard on catch sets.** Two watches whose
replay catch-sets overlap above ~0.8 → **"Watch A and Watch B are nearly
the same — merge?"** And at nudge time, a job matching several watches
appears ONCE, wearing every watch's name badge (set-union dedupe; a
role_id shows exactly once per morning, ever).

**(d) Company posting rhythm — inter-arrival estimation.** For company
watches: from listing_events, the gaps between that company's past postings
of matching roles → median inter-arrival with MIN_SAMPLE 5 (the survival
module's honesty rule reused): **"Monzo posts a data role roughly every 6
weeks (n=7)"** — or honestly "not enough history yet (n=2)". Sets the
user's expectation so a quiet watch isn't mistaken for a broken one.

**(e) Watch health — drift on the weekly series.** Each watch's weekly
catch counts form a series; a simple trailing comparison (last 3 weeks vs
the prior 12-week average, flagged when below a fixed fraction) marks a
watch **"drying up"** — with advice recomputed from (b) at that moment
("the market moved: 'python engineer' rising, 'data engineer' flat in your
industry's ads"). Deliberately a threshold rule, not a fancy model: honest
and explainable beats clever.

**(f) Ranking inside a watch — existing math core.** Catches rank by fit
score × freshness half-life decay (already built), tie-broken by nearest
deadline. No new scoring is invented for watches.

**(g) Alert-fatigue cap — fixed v1, measured later.** Per-watch nightly cap
(default 5) with an overflow line ("caught 23 — top 5 here, the rest in
the tab"). v2 may tune the cap from the user's own open-rate; v1 keeps a
fixed number so behaviour is predictable.

## 3. What the user can do (the product surface)

1. **Create by conversation:** "watch Monzo for data roles" → their AI calls
   `create_watch` → the reply already contains (a)'s predicted yield + (b)'s
   advice → user confirms or adjusts → saved.
2. **Test without saving:** `test_watch` = the replay alone ("what WOULD
   this have caught?") — try combinations freely, save only keepers.
3. **Morning nudge, per-watch lines:** each active watch contributes its own
   labelled line; badges when one job matches several watches.
4. **Dashboard:** a Watches view — each watch: name, this-morning catches,
   weekly rhythm, health flag; click through to its full catch list.
5. **Pause / resume / edit / delete** — watches are config (deletable);
   their catch HISTORY is keep-all (watch_catches rows survive, stamped).
6. **Per-watch cap** adjustable; overflow always visible in the tab.

## 4. Build shape (for the future build chat — NOT now)

- **Migrations (2):** `watches` (owner_id, name, filters jsonb validated
  against the ten dimensions, active, cap, created_at) and `watch_catches`
  (watch_id, role_id, caught_on, receipts jsonb; keep-all, unique per
  watch×role).
- **Engine (new module `src/watch/`):** pure evaluator (filters → SQL over
  role_listings/views), the replay/sensitivity/overlap math (reuses match,
  survival, decay), and a nightly `watch` stage slotted after deadlines,
  before file/nudge (stage-order pin updated deliberately).
- **Nudge:** digest gains per-watch lines + badges (dedupe rule (c)).
- **MCP tools (4):** create_watch, test_watch, list_watches, edit_watch —
  contract v2 envelopes, owner-scoped.
- **Dashboard:** Watches tab reading a new curated view (complexity pin
  extended with its own test).
- **Tests:** replay determinism, Jeffreys interval edges (k=0), sensitivity
  arithmetic, dedupe/badges, caps, per-owner isolation, stage order.
- **Size estimate:** ~4 modules, 2 migrations, ~35 tests. One chat.

## 5. What this plan deliberately refuses

- No real-time alerts (nightly heartbeat only; cadence is a scheduler
  decision, never a code fork).
- No free-text query language (ten dimensions, forever explainable).
- No AI in evaluation, prediction, or advice — replay counting only.
- No build inside Phase 8 (founder's word); slot after Phase 8.5 item 14.

## Appendix — the complete combination catalogue and its derivation (2026-08-03)

**How the ten dimensions were derived.** Not chosen — filtered. Every stored
fact about a listing/company was passed through four admission gates:
(1) STORED — exists in the DB tonight; (2) USER INTENT — a person would ask
for it; (3) NOT ALWAYS-ON — unconditional protections (salary wall, recruiter
exclusion, applied/snoozed hiding, duplicate absorption) can never be
options; (4) NOT DERIVED — computed outcomes (the ready/needs bucket) are
results, not ingredients. Survivors: the ten dimensions of section 1.
Rejected, for the record: bucket (gate 4), applied/snoozed (3),
read-quality/in-tray (2), duplicate status (3), deadline_source (2).
Near-miss: a REMOTE flag fails gate 1 today (location text only, no clean
flag); the day the machine stores one, remote becomes dimension 11 and the
catalogue becomes 2^11−1. The rule cuts both ways.

**The complete catalogue.** Each dimension is in or out: 2^10 − 1 =
**1,023 watch shapes** (10 singles · 45 pairs · 120 triples · 210 quads ·
252 fives · 210 sixes · 120 sevens · 45 eights · 10 nines · 1 all-dials).
Every subset is legal, none special-cased; values within a shape are
unlimited. The catalogue is an inventory, not a menu of favourites.

**Why no other way of combining exists.** Algebra: AND inside a watch, OR
across the watch list. By disjunctive normal form, ANY nested AND/OR
expression rewrites into a plain list of AND-only watches — "(Leeds OR
Manchester) AND carer" IS two watches — so richer combinators add zero
expressive power, only unexplainable receipts. The single true sacrifice is
NOT (negation): genuinely inexpressible with positive watches; deliberately
excluded from v1, restorable later as an "except these words" VALUE option
inside the role-words dimension, without changing the algebra.

## Notes / log

- 2026-08-03 — Designed in full during the walkthrough chat, at the
  founder's request ("map it with mathematics first; build once the whole
  plan is clear"). Supersedes 0010 item 15. Build trigger: founder's word,
  after Phase 8.5's owner-lens lands.
- 2026-08-03 (later) — Appendix added at the founder's request: the full
  combination catalogue (1,023 shapes), the four admission gates that
  derived the ten dimensions, and the DNF argument for why AND-within /
  OR-across is complete. Remote flagged as the legitimate future 11th
  dimension once stored.
- 2026-08-12 — **Phase 9 close, carry-forward sweep: the trigger fired and is being honoured.** This plan's stated blocker was "Phase 8.5 item 14 (owner-lens: user words → rule rows) must land first". It landed on 2026-08-10 — `promotion_rules` IS the owner's lens row and a lens is set by conversation. Phase 9 then built the per-owner nightly pass the watches must be evaluated inside. So this is no longer deferred-indefinitely: it is **item 5 of plan 0014**, the Phase 9.5 Translator Layer, and it is named in that phase's CLAUDE.md rather than left to be rescued by memory a third time.
