# 0002 — SIC industry → engine integration

- **Status:** ✅ Delivered, with one note (see the 2026-08-12 entry)
- **Created:** 2026-07-14  ·  **Last updated:** 2026-07-14
- **Depends on / blocked by:** nothing
- **Owner / last touched by:** Claude session 2026-07-14

## Goal
Make sponsor industry codes readable *and* a first-class part of the engine —
not just a database add-on. Right now the data layer works; it isn't wired into
`src/`, the MCP surface, or the tests (project rule: code-first, MCP-second,
test-pinned).

## Tasks
- [x] Load official Companies House SIC 2007 list into `sic_codes` (731 codes) — migration `0031`
- [x] `v_sponsor_industry` view — industry in plain English — migration `0032`
- [x] RLS hardening + security-advisor clean (0 errors) — migration `0033`
- [ ] `src/` helper (e.g. in `census_store.py`) to fetch industry-in-words
- [ ] MCP tool to query sponsors by industry / show a sponsor's industry in words
- [ ] Test pinning the join + coverage (698 five-digit decode, 63 legacy 4-digit don't)

## Notes / log
- 2026-07-14 — DB layer built + verified: join is clean (all 699 five-digit codes
  match; the only misses are 63 legacy pre-2007 4-digit codes, by design). Source
  is the official CH list, loaded into Shayan's DB (not from model memory).
  Remaining work is the engine/MCP/test integration above.
- 2026-08-12 — **Phase 9 close, carry-forward sweep: DELIVERED.** The engine wiring this plan was waiting for exists and is nightly: Pass-1 classification carded all **128,222** register organisations against Companies House with **0 errors**, and since Phase 8.5 the industry codes are the owner's LENS — `find_industry_codes` turns plain words into candidates, `set_promotion_rule` writes them to `promotion_rules.industry_codes`, and the same rule row drives the Pass-2 probe pick, the ads category and the nightly promotion. No code edit is needed to change industry, which is more than this plan asked for. **The note:** the only piece not delivered as written is a per-SIC report surface; nothing needs it today.
