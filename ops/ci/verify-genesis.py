#!/usr/bin/env python3
"""Prove ops/ci/01-genesis.sql is a correct reconstruction, by outcome not by eye.

Builds the whole schema on a throwaway Postgres exactly as CI does — bootstrap,
genesis, then all of db/migrations/ in order — and diffs the result against the
LIVE schema: every column with its type, nullability, default and generated
expression, every constraint, index, policy, view and RLS flag.

This is the check that makes the genesis baseline trustworthy. A reconstruction
of a pre-migration schema is a guess until something compares it to reality;
B-GAE-015, 020 and 022 were all a scaffold that had silently stopped matching
the table it imitated, and nobody was comparing.

It CANNOT run in CI and must not: CI has no database credential and the lane is
deliberately secret-free. This is a laptop tool, run when the baseline is
regenerated or a migration touches a genesis table.

    ./ops/ci/verify-genesis.py

Needs DATABASE_URL (read-only use) and docker. Exit 0 means identical.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

CONTAINER = "gae-genesis-verify"
PORT = 55433
CI_URL = f"postgresql://postgres:verify-example-not-a-secret@localhost:{PORT}/goal_a"

# Everything that makes two schemas the same or different. Deliberately
# includes defaults and generated expressions: B-GAE-013 was a generated column
# and B-GAE-014 was a type mismatch, so a comparison blind to either would miss
# this project's two most expensive bugs.
QUERIES = {
    "columns": """
        select table_name||'.'||column_name||' type='||data_type
               ||' null='||is_nullable||' gen='||is_generated
               ||' def='||coalesce(column_default, '-')
        from information_schema.columns where table_schema = 'public'""",
    "constraints": """
        select c.conrelid::regclass::text||' '||c.conname||' '
               ||pg_get_constraintdef(c.oid)
        from pg_constraint c
        join pg_namespace n on n.oid = c.connamespace
        where n.nspname = 'public'""",
    "indexes": "select indexdef from pg_indexes where schemaname = 'public'",
    "policies": """
        select tablename||' '||policyname||' roles='||roles::text
               ||' using='||coalesce(qual, '-')
               ||' check='||coalesce(with_check, '-')
        from pg_policies where schemaname = 'public'""",
    # Names AND bodies. Comparing only the name list is the B-GAE-004 shape: it
    # would have reported "views match" while CI's v_apply_queue still carried
    # the founder's hardcoded title regex that Phase 8.5 removed, because 0046
    # changed that view's WHERE clause without changing its columns.
    "view_names": """
        select table_name from information_schema.views
        where table_schema = 'public'""",
    "view_bodies": """
        select table_name||' :: '||md5(pg_get_viewdef(
                   ('public.'||quote_ident(table_name))::regclass, true))
        from information_schema.views where table_schema = 'public'""",
    # security_invoker lives in reloptions, and CREATE OR REPLACE VIEW drops it
    # silently — that is B-GAE-006, which get_advisors caught only because
    # someone ran it. Comparing reloptions makes the lane catch it instead.
    "view_reloptions": """
        select c.relname||' '||coalesce(array_to_string(c.reloptions, ','), '-')
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'v'""",
    "rls_enabled": """
        select c.relname from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r' and c.relrowsecurity""",
    "triggers": """
        select c.relname||' '||t.tgname||' -> '||p.proname
        from pg_trigger t
        join pg_class c on c.oid = t.tgrelid
        join pg_proc p on p.oid = t.tgfoid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and not t.tgisinternal""",
}


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=check)


def build_ci_schema(repo: str) -> None:
    run("docker", "rm", "-f", CONTAINER, check=False)
    run("docker", "run", "-d", "--name", CONTAINER,
        "-e", "POSTGRES_PASSWORD=verify-example-not-a-secret", "-e", "POSTGRES_DB=goal_a",
        "-p", f"{PORT}:5432", "postgres:17")
    for _ in range(60):
        if run("docker", "exec", CONTAINER, "pg_isready", "-U", "postgres",
               "-d", "goal_a", check=False).returncode == 0:
            break
        time.sleep(1)
    else:
        sys.exit("the throwaway Postgres never became ready")
    run("docker", "cp", repo, f"{CONTAINER}:/repo")
    applied = subprocess.run(
        ["docker", "exec", "-e",
         "DATABASE_URL=postgresql://postgres:verify-example-not-a-secret@localhost:5432/goal_a",
         CONTAINER, "bash", "/repo/ops/ci/apply-schema.sh"],
        capture_output=True, text=True,
    )
    if applied.returncode != 0:
        print(applied.stdout[-3000:])
        print(applied.stderr[-3000:], file=sys.stderr)
        sys.exit("the schema did not build — fix that before comparing")


def fetch(url: str) -> dict[str, set[str]]:
    import psycopg

    out: dict[str, set[str]] = {}
    with psycopg.connect(url) as conn:
        for name, query in QUERIES.items():
            out[name] = {r[0] for r in conn.execute(query).fetchall()}
    return out


def main() -> None:
    live_url = os.environ.get("DATABASE_URL")
    if not live_url:
        sys.exit("DATABASE_URL is not set — this tool reads the live schema.")
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    build_ci_schema(repo)
    live, ci = fetch(live_url), fetch(CI_URL)

    identical = True
    for name in QUERIES:
        only_live = sorted(live[name] - ci[name])
        only_ci = sorted(ci[name] - live[name])
        verdict = "match" if not only_live and not only_ci else "DIFFERS"
        if verdict == "DIFFERS":
            identical = False
        print(f"{name:14} live={len(live[name]):4} ci={len(ci[name]):4}  {verdict}")
        for item in only_live:
            print(f"    live only : {item}")
        for item in only_ci:
            print(f"    ci only   : {item}")

    run("docker", "rm", "-f", CONTAINER, check=False)
    if identical:
        print("\nIDENTICAL — the CI lane builds the schema production runs.")
    else:
        print("\nDIFFERENCES above. The genesis baseline or a migration is wrong.")
        sys.exit(1)


if __name__ == "__main__":
    main()
