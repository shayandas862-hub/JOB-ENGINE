# PRD — Goal A Engine (Architecture v2)

**Confirmed:** 2026-07-10 by Shayan Das. Source of truth for *what* the system does. The *how* lives in `architecture/architecture-v2.md`.

## What This Product Is

A sponsor-aware UK job-search system. It discovers and tracks job listings matching its owner's criteria, remembers every listing's history, generates a tailored ATS-friendly CV per role worth applying to, files everything in a Notion tracker, and nudges the owner's phone daily. The owner always presses apply.

**Who it's for:** Shayan Das first (Goal A — a visa-sponsored UK job). Built person-agnostic so any third party can later run it with their own criteria, via hosted app or hosted MCP.

**Core principle:** code-first, MCP-second. A deterministic Python engine does all the work and runs whole without Claude. Claude connects through an MCP server as the reasoning layer that directs the engine's tools. AI appears at exactly three caged spots — JD reading, skill-synonym mapping, CV wording — each with a working no-AI fallback.

## What It Does (capabilities)

1. **Any-company targeting** — the owner names any company; the system does its best to find and fetch its job board (accepting some boards can't be fetched), filters by the owner's criteria, and files roles in the database.
2. **Automatic criteria-based fetching** — runs daily on a schedule with no human present; criteria (roles, salary floor, locations, kill-words) live in the database, never in code.
3. **Automatic job discovery** — finds jobs the owner never pointed it at: walking the UK sponsor register by criteria, probing discovered companies' boards, plus legitimate job-search APIs (Adzuna, Reed) cross-checked against the register.
4. **Job history** — for every listing: when first seen, what changed and when, when it closed/reopened, and an advisory apply-by estimate.
5. **Skill pipeline** — extracts each JD's demanded skills (grounding-checked), canonicalises names, computes the owner's skill gaps.
6. **Ranked apply queue** — fit first, sponsor confidence second, freshness third; salary wall judged against the per-occupation going rate, always advisory.
7. **Tailored CV maker** — per gated listing, an ATS-friendly .docx built from the owner's verified career facts; AI only rephrases supplied facts (truth-gated — it can never invent experience).
8. **Notion filing** — one tracker card per ready-to-apply role: details, deadline estimate, sponsor evidence, CV attached; "Applied" status syncs back.
9. **Nudges** — daily phone push when roles are ready ("N roles ready — CVs and links in Notion") and when a run fails. Silence never masks a breakage.
10. **Claude as the brain (MCP)** — inspect/explain the queue, adjust criteria, onboard companies, resolve flagged ambiguities, re-tailor CVs; every Claude action audited.
11. **(Stretch) Apply-assist** — a browser agent fills application forms and stops; enforced in code that it can never submit.

## Hard Rules

- The engine **never applies**; even apply-assist cannot press submit.
- All machine output is **provisional** until the owner confirms.
- **Nothing personal or secret in code** — criteria, career facts, tokens: database or environment only.
- Salary signals are **advisory, never a filter** (~13% of postings state pay).
- No scraping of sites that forbid it; discovery uses public feeds, public registers, and licensed APIs.

## Non-Goals (v2)

- Not a general job board or search engine for the whole market.
- No auto-submission of applications, ever.
- Multi-user operation is a **provision** (schema + no hardcoding), not a launch feature — single-user first.

## Build Plan

Ten dependency-ordered phases — see `architecture/architecture-v2.md` SECTION 2. Pacing is governed by the GOAL build brief: building only continues alongside real applications (D-053).
