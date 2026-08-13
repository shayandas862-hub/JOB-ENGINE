# CV Master Fact Bank — intake for Shayan

> **Fill this once.** This is NOT a CV. It is the complete set of **true facts** about you.
> The engine tailors a *different* CV per role by automatically selecting and rephrasing
> the right facts from this bank — so a role at Anthropic and the same role at Google come
> out genuinely different, but both 100% true and ATS-clean.
>
> **Rules that make it work:**
> - Every fact must be literally true and verifiable. The engine **never invents** — it only
>   rephrases what's here. Untraceable claims get replaced by your verbatim fact (the "truth gate").
> - Put **numbers/metrics** wherever real (%, £, headcount, time saved, users). Metrics are what
>   make a tailored CV land — and the engine can only use numbers that appear here.
> - Give the **superset** — everything true, even if it won't fit one CV. The engine picks per role.
> - Tag each fact with the **skills it proves** (lowercase, e.g. `python`, `stakeholder management`).
>   These are matched against each job's required skills to decide what surfaces.
>
> Delete the examples and fill in your own. Add as many EXPERIENCE / ACHIEVEMENT / SKILL-EVIDENCE
> entries as you have. When done, hand it back and I'll load it into `cv_blocks` as drafts for
> your confirmation.

---

## 1. HEADER / PROFILE  (one entry)
- **Full name:** 
- **Target job titles:** (e.g. AI Engineer, Data Analyst — the roles you're aiming at)
- **Phone:** 
- **Email:** 
- **Location / base:** 
- **LinkedIn / GitHub / portfolio URLs:** 
- **Work authorisation line:** (e.g. "Requires UK visa sponsorship" — or however you want it stated, or leave blank)
- **Master headline (optional):** one true sentence summarising you (the engine may re-angle it per role)

---

## 2. EXPERIENCE  (one block per job — repeat as many as needed)

### Job 1
- **Title:** 
- **Organisation:** 
- **Dates:** (e.g. Jan 2023 – Present)
- **Fact bullets** (each a true, standalone statement — add a metric wherever real):
  - Fact: `______`  → proves skills: `skill-a, skill-b`
  - Fact: `______`  → proves skills: `______`
  - Fact: `______`  → proves skills: `______`

### Job 2
- **Title:** 
- **Organisation:** 
- **Dates:** 
- **Fact bullets:**
  - Fact: `______`  → proves skills: `______`
  - Fact: `______`  → proves skills: `______`

*(copy the block for Job 3, 4, …)*

---

## 3. STANDALONE ACHIEVEMENTS  (optional — awards, big wins not tied to one job)
- Achievement: `______`  → proves skills: `______`
- Achievement: `______`  → proves skills: `______`

---

## 4. SKILL EVIDENCE  (proof for your most important skills)
> For each key skill, one concrete proof — a project, result, or thing you built.
> This lets the engine surface a skill *with evidence* when a job demands it.
- Skill: `python` — proof: `______`
- Skill: `______` — proof: `______`
- Skill: `______` — proof: `______`

---

## 5. EDUCATION  (one per qualification)
- **Qualification:** (e.g. BSc Computer Science)
- **Institution:** 
- **Dates:** 
- **Notable facts:** (grade, thesis, relevant modules — only if true & useful) → skills: `______`

---

## 6. PROJECTS / OTHER  (optional — side projects, open source, this very engine, etc.)
- **Name:** 
- **What it is (true facts + metrics):** `______`  → skills: `______`

---

### Notes for me (Claude) — leave blank, I fill on load
- Maps to `cv_blocks`: kind ∈ {role, achievement, skill_evidence, education}; fact_text = the fact;
  skill_norms = normalised proves-skills; header/profile → `profiles`.
- All rows load as `confirmed = false`; Shayan confirms before any CV uses them.
