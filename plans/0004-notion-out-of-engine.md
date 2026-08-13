# 0004 — Notion leaves the engine

- **Status:** ⏸️ Deferred with a NAMED trigger (Phase 9 task 4 — see the 2026-08-12 entry)
- **Created:** 2026-07-14  ·  **Last updated:** 2026-07-14
- **Depends on / blocked by:** best done alongside plan 0001 (CV filing) or Phase 8 filing stage
- **Owner / last touched by:** Claude session 2026-07-14

## Goal
The engine writes the apply queue to its **own DB** (source of truth). **Claude**
mirrors to Notion via its own connector, on demand/scheduled. No `NOTION_TOKEN`
in the engine.

## Tasks
- [ ] Retire `src/notion/*`
- [ ] Retire the Notion half of `src/cv/filing.py`
- [ ] Remove `NOTION_*` config from `src/config.py` + `.env(.example)`
- [ ] `mark_applied` becomes the app-status source of truth (replaces the
      Notion→engine `sync_applied` path)
- [ ] Confirm CV generation stays engine-side; only the *mirroring* moves to Claude

## Notes / log
- 2026-07-14 — Captured from the 2026-07-12 decision (see `docs/decision-log.md`).
  Not actioned yet — fold into the filing stage when plan 0001 or Phase 8 touches it.
- 2026-08-12 — **Phase 9 close, carry-forward sweep: still deferred, but the trigger is now written down instead of implied.** Phase 9 task 4 added `set_notion_token_ref`, so each owner can store the NAME of their own Notion credential — and **nothing reads it yet**, deliberately. One credential opens one board, so the filing stage RUNS for the owner that credential belongs to and **refuses, with a reason, for everyone else** rather than writing their cards where they cannot read them. **Trigger to build: the first real second owner who wants a board.** Then a resolver (Secret Manager read, by ref, engine-side) REPLACES the refusal `if` — B-GAE-027 pins that it must never simply be deleted, or the second owner's cards go to the first owner's board the moment the guard comes out.
