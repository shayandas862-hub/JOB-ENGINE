"""Mint, list and revoke friend-tier access keys (Phase 9 task 1).

The operator's door, and deliberately not an MCP tool: minting a key is the
one action that decides WHO the machine will answer to, so it stays off the
surface any client AI can reach. The founder runs it; nobody else can.

    python scripts/mint_access_key.py --list
    python scripts/mint_access_key.py --owner <profile_id> --label "sam-laptop"
    python scripts/mint_access_key.py --revoke <key_id>

The minted key is printed ONCE and never stored — the database keeps only
its SHA-256. Losing it means minting another, which is the correct trade.
Hand it over out of band; never paste it into a file in this repo.

The task-1a fuse that refused to mint for anyone but the local owner is GONE
(task 1b): the queue, one listing, its gap, its history, the skill gaps and
the writes mark_applied / snooze_listing / send_test_nudge all take an owner
now, and `tests/test_owner_scoping.py` proves a second owner is refused every
one of them by attempting the reads against two seeded owners.

Both surfaces this file used to warn about are now closed:
  * `list_review_flags` / `resolve_review_flag` — B-GAE-017, fixed by
    migration 0056 at the task-2b sitting (not task 3, as this note used to
    say). `review_items.owner_id` is nullable: NULL means the ambiguity is
    about a public fact and belongs to everyone (skill_synonym, sponsor_match,
    company_onboard); a value means it was derived from one person's lens
    (promotion_review) and only they can read or dismiss it. The
    promotion-review cap is per-owner too, so one person's unresolved backlog
    can no longer hold everybody else's promote pass shut.
  * `get_run_report` / `sweep_status` — machine health only (stage name, ok,
    duration, counts), the same class the public status page already publishes
    on purpose. Task 3's per-owner runs kept it that way ON PURPOSE:
    `pipeline_runs` is world-readable, so the per-owner lines in a run report
    are NUMBERED, not named. No profile_id reaches that table, because a
    profile_id is the exact value a cross-owner read attempt needs.

Since task 3 the nightly job runs a separate personal pass per owner — their
own rule, apply window, tray, board and notification channel — so a key holder
gets their own nudges rather than a share of somebody else's. Two things are
still shared and worth saying out loud when handing a key over:
  * **Notion is one board.** There is a single Notion credential in the
    environment and it opens one person's board, so the filing stage RUNS only
    for that owner and skips for everyone else rather than writing their cards
    somewhere they cannot see them. Per-owner Notion is task 4.
  * **API quotas are per-account and shared** (Adzuna, Reed, Companies House).
    Per-user budgets are task 5; until then one heavy user can spend the
    common allowance.

RLS policies exist on all 28 tables, are proven to refuse cross-owner reads
AND writes (task 2a), and the MCP door now connects as `goal_a_app` so the
database itself does the refusing (task 2b). The nightly ENGINE does not: it
connects on DATABASE_URL as `postgres`, whose `rolbypassrls` is true (measured
2026-08-12), which is deliberate because the world half must write across
every owner at once. So inside the engine the database enforces nothing, and
the per-owner scoping proven in `tests/test_per_owner_isolation.py` is the
whole boundary. This key is a door lock, not a vault. Mint for people the
founder trusts.
"""
from __future__ import annotations

import argparse
import sys

from auth.tokens import list_keys, mint_key, revoke_key
from db.connection import get_conn


def _print_keys(rows: list[dict]) -> None:
    if not rows:
        print("no keys minted yet")
        return
    print(f"{'id':>4}  {'owner':38}  {'label':22}  {'last used':26}  state")
    for r in rows:
        state = "REVOKED" if r["revoked_at"] else "live"
        print(f"{r['key_id']:>4}  {r['owner_id']:38}  {r['label']:22}  "
              f"{str(r['last_used_at'] or 'never'):26}  {state}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", help="profile_id the key opens")
    parser.add_argument("--label", help="who holds it, e.g. 'sam-laptop'")
    parser.add_argument("--revoke", type=int, metavar="KEY_ID")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)

    # Every usage error is settled BEFORE the environment is touched. get_conn()
    # loads config, which raises when DATABASE_URL is unset, so a check placed
    # after it can only run where a database is already configured — and an
    # operator should not need one to be told the command is malformed
    # (B-GAE-021: the label refusal passed on a laptop with .env and failed
    # inside the image, which carries none by design).
    if args.owner and not args.label:
        parser.error("--label is required when minting "
                     "(an unlabelled key cannot be revoked safely)")

    with get_conn() as conn, conn.cursor() as cur:
        if args.revoke:
            result = revoke_key(cur, args.revoke)
            print(f"key {result['key_id']}: {result['outcome']}")
        elif args.owner:
            minted = mint_key(cur, args.owner, label=args.label)
            print(f"minted key {minted['key_id']} for {args.owner}")
            print("\n  " + minted["key"] + "\n")
            print("Shown ONCE — the database keeps only its SHA-256.")
            print("Hand it over out of band. Never commit it, never paste it "
                  "into a chat that is logged.")
        else:
            _print_keys(list_keys(cur))
    return 0


if __name__ == "__main__":
    sys.exit(main())
