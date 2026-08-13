# Product Brief — The Sponsor-Aware Job Machine ("Goal A Engine")

Written 2026-08-03, at the founder's request, during the product walkthrough.
Companion documents: `docs/PRD.md` (requirements), `plans/0009` (market
position), `docs/architecture/architecture-v2.md` (how it's built).
This brief describes the product AT FULL STRENGTH — all staged phases landed,
tested, no bugs — with an honest status footer.

## One line

A personal job-search machine for people who need visa sponsorship: it finds
every employer legally allowed to say yes, watches their jobs all night,
matches them to you with proof attached — and you just apply each morning.

## The problem

Every year, hundreds of thousands of people in the UK — graduates on
time-limited visas, care workers, engineers, chefs — search for jobs under one
brutal extra rule: the company must hold a government sponsor licence, and the
salary must clear a legal wall. Today they discover this the worst way:
AFTER applying. The information exists — the government publishes the licence
list — but as a raw 143,000-row spreadsheet nobody can use. So people burn
months applying to companies that could never say yes, miss deadlines they
never knew existed, and rewrite their CV by hand fifty times. The market's
tools (job boards, LinkedIn filters) treat "visa sponsorship" as a keyword,
which is to say: as a rumour.

## The product, at full strength

**Day one, fifteen minutes:** the user connects THEIR OWN AI — ChatGPT,
Claude, Gemini, any — and answers a few human questions in chat. "Care homes
around Leeds, can't go below £39k, here's what I can do." Their words become
their profile (rows, never code). No forms, no codes, no manual.

**Every night, unattended:** refresh the government licence list (weekly,
stamped, never-forgetting) → learn what every new company does from its own
government filing → knock on company job boards → sweep the big ad sites →
throw out recruiters and non-sponsors → check every salary against the visa
wall → compute match scores WITH RECEIPTS → stage job descriptions for
reading → set deadlines learned from how fast similar jobs actually close.

**Every morning, two minutes:** a nudge. "9 ready." Each one: company,
sponsor ✓, salary vs the wall, fit score with its proof, deadline, direct
link. The user's AI reads the new job descriptions over coffee — the machine
checks every claim word-for-word before believing it (AI reads, code judges).
One click to the real application. A truth-gated CV tailored per job. "Mark
it applied" — tracked forever. Gap analysis on demand: "medication-audit
experience appears in 40% of your target ads — learning it closes a third of
your gap."

## What makes it unlike anything in the market

1. **It starts from the law, not from listings.** Sieve 1 is the government
   register. Every minute of compute is spent only on legally possible
   employers. No one else builds on this floor.
2. **No naked numbers.** Every score, deadline, and label carries its
   receipt — recomputable, checkable, honest. Trust is the interface.
3. **Bring-your-own-AI.** All intelligence runs on the USER'S AI account
   through a guarded connector. Operator's AI bill: ~zero. User's privacy:
   their AI, their data room. Vendor-agnostic forever.
4. **A deterministic engine with AI at the edges.** The machine runs whole
   with zero AI reachable; AI only visits through caged, verified doors.
   Auditable, cheap, repeatable, boring — the good kind of boring.
5. **Person- and country-agnostic bones.** A user is rows, never code. A
   country is one register module + one company-registry module. UK today;
   the design already knows how to move.

## If it all lands: what it does in the market

It becomes the missing layer between the government's register and the apply
button — the thing every visa-needing job seeker quietly builds a broken
spreadsheet version of. Concretely: it converts wasted applications into
targeted ones (the market's single largest source of pain); it accumulates a
skills-demand data bank that gets smarter with every read (a moat that
compounds daily); and its census — every sponsor × industry × hiring
activity — becomes a research instrument nobody else has assembled. The
operator's marginal cost per extra user is approximately: database rows.
That cost structure lets it be free or nearly-free for the people who need
it most, which is exactly how it wins.

## The ideal user

**Priya, 26.** MSc Data Science, Manchester. On a Graduate visa with 14
months left on the clock — every week that passes, her runway shrinks. She
has real skills and no UK network. She's sent 60 applications; 40 died
silently at companies that never held a licence. She doesn't need
motivation — she needs AIM.

The analogy: **Priya is standing on a train platform where the departure
board is broken.** Trains (jobs) leave constantly; she can't see which ones
she's allowed to board (sponsorship), which she can afford (salary wall), or
when each departs (deadlines) — so she sprints at random trains. This
product is the working departure board plus a porter who's been up all
night: "these 9 trains, you're allowed on, you can afford, they leave
Friday — platform links here, ticket (CV) already stamped with only true
facts." She stops sprinting. She starts boarding.

Widening circles around her: the senior carer whose whole industry hires
through ads, not fancy boards (the machine's two roads were built for
exactly him) · the final-year international student starting six months
before graduation · the overseas engineer planning the move · and later,
with one module swapped: other countries.

## The number the whole machine bows to

**Applications submitted.** Not data collected, not companies tracked, not
scores computed — those are means. The product exists to move one counter,
and its own dashboard shows it first, always.

## Honest footer — where it stands (2026-08-03)

Engine, matching, reading tray, dashboard, and the connector's 29 tools:
built, 604 tests green. Going Live (Phase 8): task 1 of 7 done
(containerized), the rest waits on five founder switches. Universal-lens
layer (Phase 8.5) and multi-user (Phase 9): staged, buildable hands-free.
Applications so far: 0 — the counter this was all built to move.
