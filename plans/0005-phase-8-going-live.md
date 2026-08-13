# 0005 — Phase 8: Going Live

- **Status:** ✅ Done (Phase 8 complete 2026-08-10, and Phases 8.5 and 9 have shipped since)
- **Created:** 2026-07-14  ·  **Last updated:** 2026-07-14
- **Depends on / blocked by:** founder greenlight; commits are now allowed **locally only** (hold lifted for local 2026-07-13) — pushing/publishing still gated by the security pass + explicit founder authorization
- **Owner / last touched by:** Claude session 2026-07-14

## Goal
The system leaves the laptop: daily pipeline + nightly census as scheduled Cloud
Run Jobs, hosted MCP behind a token with a hard spend cap, a public status page
(no personal data), CI, a security pass, then the public repo flip.
Full card: root `CLAUDE.md` + `docs/architecture/architecture-v2.md` (Phase 8).

## Tasks (high level — see the phase card for detail)
- [ ] Containerize (one image, entrypoint dispatch)
- [ ] Cloud Run Jobs + Scheduler + Google Secret Manager; retire local launchd
- [ ] Hosted MCP over HTTP + bearer token + **hard monthly spend cap** (tested)
- [ ] Public status page — aggregates only, **no personal data** (no-leak test)
- [ ] CI (GitHub Actions, full suite on push)
- [ ] Pre-flip **security-review** pass (mandatory gate) + scrub Supabase ref / key-leak narrative
- [ ] The flip — public product-named repo from a squashed, scrubbed snapshot (founder-authorized)

## Notes / log
- 2026-07-14 — Reference entry only. This is the current staged phase; the
  authoritative spec is the root `CLAUDE.md`. Publishing + public endpoints are
  irreversible → need explicit founder authorization AND the security pass first.
- 2026-07-14 — Stale dependency corrected: the founder lifted the commit hold for
  LOCAL commits on 2026-07-13 (snapshot `dbb0e8f`, vision work `b8db398`). Remote
  push / public repo remain gated as above. Also note: launchd retirement (Task 2)
  ties into plan 0006 (scheduling map).
- 2026-08-12 — **Phase 9 close, carry-forward sweep: DONE and two phases stale.** Phase 8 completed 2026-08-10 13:55 BST — Cloud Run job + scheduler running unattended at 06:30, hosted MCP live behind a bearer token, the public status page live and person-free, WIF deploy-on-green with no service-account key in existence, and the flip into the public repo. Everything this plan staged is live; the status line had simply never been turned over.
