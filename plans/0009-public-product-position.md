# 0009 — Public product: market position, differentiation, and the build gap

- **Status:** 🔲 Todo (analysis + plan only — nothing built, nothing changed)
- **Created:** 2026-07-26 19:54 BST  ·  **Last updated:** 2026-07-26 19:54 BST
- **Depends on / blocked by:** the API terms-of-service check (gates everything commercial);
  plan 0007 task 3 (aggregator ads → first-class listings); plan 0008 (the generalisation
  list — this plan supersedes its *product* framing but not its build items); Phase 8
  (containerise / hosted MCP) and Phase 9 (per-owner isolation) for anything hosted.
- **Owner / last touched by:** Claude session 2026-07-26 (philosophy → product session)

## Goal
Answer three founder questions on record: what the market already gives this customer,
what this engine gives that nothing else does, and — precisely — what must be **built**,
**changed**, or **finished** to serve that value to someone who isn't Shayan. Every figure
below was read live from the database on 2026-07-26 at 19:54 BST, not recalled.

---

## 1. The customer and the question

Someone who needs a UK visa to work. On a clock, self-funding the search, and every
wasted application costs time they don't have.

Their question is **not** *"what jobs exist?"* — a hundred sites answer that. It is:

> **"Of these results, which employers can legally hire me?"**

Today they answer it by hand: copy a company name → open a 141,956-row government
spreadsheet → search → hope the advert's trading name resembles the legal name on the
licence. ~3 minutes per job, frequently wrong.

Two consequences shape the whole product:
- **The need is intense but finite.** It ends the day they are hired. Churn is 100% by
  design; subscription economics do not apply. Price a *search season*, not a month.
- **They are surrounded by people with the identical problem.** Every success is a
  testimonial in a word-of-mouth market. The exit is the marketing moment.

---

## 2. What the market already gives them

| Where they go today | What it does well | Where it fails this customer |
|---|---|---|
| **General job boards** (Indeed, LinkedIn, Reed, Totaljobs) | Enormous, fresh, free inventory | No sponsorship truth. Any "visa" filter is employer self-declared — usually blank, sometimes wrong. The core question is unanswerable here |
| **The Home Office register** | Free, official, complete, the actual source of truth | A spreadsheet: name, town, rating. No jobs, no industry, no links. Manual matching breaks on trading names |
| **Curated sponsor job boards** | They *do* perform the join | Hand-built → small inventories, mostly tech. Staleness invisible. No evidence behind the claim |
| **Browser extensions / overlays** | Verdict appears where the person already is | Only covers the page in front of you. Crude name matching, no confidence, no reverse search, no stated coverage |
| **Community spreadsheets** | Free, generous, socially trusted | Stale within weeks, unverifiable, rarely have live jobs attached |
| **Immigration advisers** | Real legal expertise on the visa | Advise on the application, not the search. Expensive. Don't find jobs |
| **General AI assistants** | Instant, conversational, already open | No live index; invents company names confidently. In this category that is worse than useless |

**The pattern:** everything above either has the jobs **or** has the licences.
**Nothing holds both at scale.**

---

## 3. What this gives — and what honestly works today

| Capability | Exists elsewhere? | State | Honest note |
|---|---|---|---|
| Every live advert checked against the licence register | Not at national scale | ✅ Works | 44,877 ads swept; 4,974 ads at 544 licensed sponsors |
| **Reverse search** — start from the company, not the job | Nowhere, at any price | 🟡 Partial | The data answers it; there is no interface to ask through |
| Evidence behind every verdict, not a badge | No | ✅ Works | Registry number, licence route, rating, date checked |
| Uncertainty recorded rather than guessed | Nobody does this | 🟡 Partial | 740 refusals held in a queue — never shown to a user |
| Knows its own coverage and blind spots | Nobody does this | 🟡 Partial | Measured internally; publishing it is the trust play |
| Remembers what the sources forget | No | ✅ Works | Nothing is deleted, so history accumulates by itself |
| Legal salary floor checked per occupation | Rarely, never per role | 🟡 Partial | Only 17 occupations loaded — all technical |
| Map of skills sponsors actually ask for | No | 🟡 Partial | 8,137 records, locked inside one person's private layer |
| Ask anything conversationally (MCP) | No | 🟡 Partial | 24 tools working — local-only, one user, no sign-in |
| Works for **any** profession | No | 🔴 Missing | All 126,342 orgs already classified; the code is hard-wired to software |

### The differentiation, in one line

> **Everyone else has the jobs, or has the licences. This holds both — and admits what it hasn't checked.**

The register is public. The adverts are public. **The moat is the reconciliation** — the
slow work of making 141,956 messy legal names line up against adverts written under
trading names, and refusing to guess when they don't. That is why the category is full of
small hand-curated lists: nobody wants to do the boring part.

Which yields an unusual marketing position: in a category crowded with confident claims
and stale spreadsheets, **publish your own blind spots**. State how much of each source
has been read, and when each verdict was last checked. No competitor can copy that
without first building what you built.

---

## 4. BUILD — does not exist today

Sizes: **S** = days · **M** = a week or two · **L** = longer.

| # | Build | Why it matters | Blocks | Size |
|---|---|---|---|---|
| B1 | **A way for a stranger to install it** | The 141,956 sponsor records were loaded once, by hand. No script, no guide | Every third-party use, free or paid | M |
| B2 | **Per-user data walls** | RLS is `on` for all 24 tables but **20 carry zero policies** — no wall between two people's data | Hard gate on hosting anyone else | M |
| B3 | **Hosted access with a sign-in** | Conversational layer is local, single-user, unauthenticated. Needs per-user token, rate limits, a spend ceiling that actually stops spend | Any paid or shared version | M |
| B4 | **Spend metered per person** | The quota ledger is keyed on (source, day) — no owner. On shared keys one user drains everyone and you can't tell who | Shared-key hosting | S |
| B5 | **A page per company — all 126,342** | *"Does [company] sponsor visas?"* is searched constantly and answered badly everywhere. You hold the only complete answer, and it refreshes itself | Growth — the acquisition engine | M |
| B6 | **A public search page** | The front door. Most of this audience is on a phone and will never configure anything | Launch | L |
| B7 | **The digest email** | Only a phone push exists. The weekly email is the habit and the reason anyone returns | Retention | S |
| B8 | **"Last checked" on every verdict** | The date exists and is never shown. A stale verdict is worse than none — and once you charge, freshness is a promise | Trust; charging anyone | S |
| B9 | **Accounts and onboarding** | No sign-up path, no way to create a second person | Paid tier | M |
| B10 | **One image that runs anywhere** | Everything runs from a laptop and a local virtual environment | Cloud deployment | S |
| B11 | **Tests that run on every change** | ~425 tests exist, run by hand. Releasing to strangers without automation means a silent break reaches them first | Safe release | S |

---

## 5. CHANGE — exists, but wrong shape for anyone else

| # | Change | What's wrong now | Blocks | Size |
|---|---|---|---|---|
| C1 | **"Software" is written into the code** | One person's opinion living in shared data. Every org is already industry-labelled — the answer exists, the code refuses to ask for anything else | Every non-technical user. **Highest value per hour on this list** | S |
| C2 | **Job-skill records sit in the private layer** | *"This job asked for Kubernetes"* is a fact about the world, not about you. Trapped by how it was collected — and it's the most sellable asset here | The skill-demand product; the layer a thousand users improve for all thousand | M |
| C3 | **Swept adverts aren't first-class listings** | 44,877 ads sit in a holding pen as leads. Until promoted, the long tail of sponsors without a careers page stays visible but unusable | The core promise at full breadth | M |
| C4 | **Only 17 occupations have a legal salary rate** | All technical. Outside tech the salary check silently does nothing — worse than visibly missing | Salary verdicts for every other profession | S |
| C5 | **The code assumes one person exists** | A single default identity threaded through the engine | Multi-user anything | M |
| C6 | **Personal habits are wired in** | Notion filing and a personal push channel are yours, not features. Should be optional extras | A clean install for anyone else | S |
| C7 | **Redistribute → link out** | Charging for a product built on republishing two commercial APIs' inventory may breach their terms. Send traffic to the original advert and sell the *verdict* — cleaner legally, better business | **Charging anyone at all. Check first.** | S |

---

## 6. FINISH — started, incomplete

| # | Finish | Where it stands | Owner |
|---|---|---|---|
| F1 | **The coverage sweep** | ~35% of one source read; the second barely begun. Remaining slices are the higher-salary bands — the most relevant ones | Running unattended |
| F2 | **Learning board addresses from adverts** | 3,458 links followed, **zero** addresses learned. Diagnostic not yet run | One session |
| F3 | **Reviewing the 260 companies found** | The machine found them; nobody has looked at the list | Founder — ~1 hour |
| F4 | **Career fact bank** | Empty, so the whole CV half sits built and dark. Cut from the public v1 anyway — but the biggest *personal* unlock | Founder — an evening |

---

## 7. Product shape (v1)

**Include:** search with a verified sponsorship verdict + evidence on every result ·
reverse search (*which licensed sponsors in my field are hiring?*) · salary checked
against the legal minimum for the occupation · link out to the original advert · saved
profile → weekly digest.

**Cut from v1, deliberately:** CV generation (highest effort, highest liability, most
crowded, least differentiated — ship the thing only you can ship) · auto-apply, ever ·
Notion filing (personal workflow, not a feature).

**Pricing shape:** free tier = search + verdict, capped — it must be genuinely useful,
because trust is the only currency here. Paid ≈ **£39 per three-month search season**.
The segment that *doesn't* churn — university international-student offices, immigration
advisers, relocation firms — is where the durable revenue is.

**Distribution:** the 126,342 company pages (B5) before any advertising. Then
nationality/university/immigration communities — this is word-of-mouth, not SEM.

**On MCP:** it is the product's soul but probably not its front door. The overlap between
*needs a sponsored UK job* and *runs Claude Desktop and can configure an MCP server* is
small today. Ship it alongside as the power-user and researcher surface; let the dumb
front door (search box + email) reach the person on a phone.

---

## 8. Risks

| Risk | Severity | Response |
|---|---|---|
| API terms forbid a paid product | 🔴 High | Check before building anything commercial; reshape to link-out (C7) |
| A source cuts you off | 🟡 Medium | Two sources is fragile; add a third once revenue justifies it |
| Verdicts go stale | 🔴 High | Licences are granted and revoked constantly. Freshness *is* the product (B8) |
| Non-technical fields are thinner | 🟡 Medium | Say so plainly. Honesty is the position — don't undercut it on day one |
| This competes with the founder's own job search | 🟡 Medium | The public repo helps fastest and costs least. Build the business after landing |

---

## 9. Order of work

1. **Read both API providers' terms** — gates everything commercial. A day.
2. **Let the sweep finish** (F1) — completeness is the credibility. Already running.
3. **Publish the code** — free, already MIT, and a hiring manager finding this repo
   serves Goal A faster than any customer will.
4. **Unwire "software"** (C1) — one small change turns a personal tool into something a
   nurse or an accountant can use. Nothing else buys that much per hour.
5. **Ship the company pages** (B5) — before spending a pound on advertising.
6. **Ship free search + verdict** (B6, B8) — no account, no friction, one killer answer.
7. **Add the digest and the paid tier** (B7, B9) — price the season, not the month.
8. **Approach one university** — one contract outweighs hundreds of individuals who churn
   by design.

---

## Notes / log
- **2026-07-26 19:54 BST** — Plan captured from a founder session that ran philosophy-first
  (no file names, plain language): what the census/aggregator lanes actually do, what is
  shared world-data vs per-person, and finally *"what value does it give to others."*
  Nothing was built or changed. All figures read live from the database at that time:
  141,956 sponsors · 126,342 census cards · 5,144 census jobs · 44,877 aggregator ads ·
  544 matched sponsors · 8,137 skill records · 740 open review flags · 17 SOC rates ·
  0 CV blocks. RLS finding (B2) verified the same session: RLS `on` for 24/24 tables,
  policies present on only 4. Quota-ledger ownership gap (B4) read from the live schema.
  The aggregator sweep was running throughout (detached, PPID 1) and was not touched.
  Supersedes plan 0008's *product/pricing* framing; 0008's generalisation build items
  remain valid and are restated here as C1/C4/C5 and B1.
