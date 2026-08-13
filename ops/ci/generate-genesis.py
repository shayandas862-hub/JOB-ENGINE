#!/usr/bin/env python3
"""Regenerate ops/ci/01-genesis.sql — the schema as it stood BEFORE migration 0001.

Why this file exists (B-GAE-024): db/migrations/ is not a complete schema. It
opens at 0001 with `alter table public.role_listings`, because eight tables were
created in Phase 1 through the Supabase dashboard before mirroring began. So
`psql -f` over the log cannot build the database on a blank Postgres, and the CI
database lane needs something to apply the log ON TOP OF.

The reconstruction is DERIVED, never hand-written — that is the whole point.
B-GAE-015, 020 and 022 were all one bug: a hand-written CREATE TABLE in a test
drifting from the table it imitated. A hand-maintained genesis file would be
that bug at schema scale. So:

  * every column type, default, generated expression and identity clause comes
    from `pg_dump` against the live database, verbatim;
  * what to REMOVE is parsed out of db/migrations/*.sql, not listed here, so a
    new `add column` lands in the subtraction automatically;
  * the output is PROVEN by ops/ci/apply-schema.sh, which applies genesis + all
    58 migrations to a blank Postgres and then diffs the result against live.
    If this reconstruction is wrong, that diff fails. It is not a judgement
    call that has to be trusted.

Run it when a migration changes one of the genesis tables' pre-0001 shape —
which should be never. Needs DATABASE_URL and docker.

    ./ops/ci/generate-genesis.py > ops/ci/01-genesis.sql
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys

# The eight tables no migration creates. Measured, not assumed:
#   live public tables  MINUS  every table any migration CREATEs.
GENESIS = [
    "cowork_findings", "decisions", "licensed_sponsors", "role_listings",
    "role_skills", "skilled_worker_occupations", "target_companies",
    "target_roles",
]

MIGRATIONS = "db/migrations/*.sql"


def migration_additions() -> tuple[dict[str, set[str]], set[str], set[str]]:
    """Columns, constraints and policies the migration log adds to genesis tables.

    Parsed from the log so this never has to be maintained by hand.
    """
    columns: dict[str, set[str]] = {t: set() for t in GENESIS}
    constraints: set[str] = set()
    policies: set[str] = set()
    for path in sorted(glob.glob(MIGRATIONS)):
        body = "\n".join(
            line for line in open(path).read().splitlines()
            if not line.strip().startswith("--")
        )
        for stmt in body.split(";"):
            squashed = " ".join(stmt.split())
            for pol in re.finditer(
                r"create\s+policy\s+([a-z_0-9]+)", squashed, re.I
            ):
                policies.add(pol.group(1).lower())
            m = re.match(
                r"alter\s+table\s+(?:if\s+exists\s+)?(?:public\.)?([a-z_0-9]+)\s+(.*)",
                squashed, re.I,
            )
            if not m:
                continue
            table, rest = m.group(1).lower(), m.group(2)
            if table not in columns:
                continue
            for col in re.finditer(
                r"add\s+column\s+(?:if\s+not\s+exists\s+)?([a-z_0-9]+)", rest, re.I
            ):
                columns[table].add(col.group(1).lower())
            for con in re.finditer(
                r"add\s+constraint\s+([a-z_0-9]+)", rest, re.I
            ):
                constraints.add(con.group(1).lower())
    return columns, constraints, policies


def genesis_functions() -> list[str]:
    """The trigger functions the genesis tables need, read from live.

    pg_dump -t brings a table's TRIGGERS but not the functions they call, so
    without this the baseline fails on `function public.set_updated_at() does
    not exist`. Measured on live: 34 functions in public, of which 31 belong to
    pg_trgm (the bootstrap's CREATE EXTENSION supplies those) and one,
    app_owner(), is created by migration 0053. That leaves exactly two.
    """
    import psycopg  # local import: only this path needs a live connection

    url = os.environ["DATABASE_URL"]
    log = "\n".join(open(f).read() for f in sorted(glob.glob(MIGRATIONS))).lower()
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            """
            select p.proname, pg_get_functiondef(p.oid)
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public'
              and p.prokind = 'f'
              -- exclude anything an extension owns; pg_trgm's 31 live here
              and not exists (
                select 1 from pg_depend d
                where d.objid = p.oid and d.deptype = 'e'
              )
            order by p.proname
            """
        ).fetchall()
    return [
        definition for name, definition in rows
        if f"function public.{name}" not in log and f"function {name}" not in log
    ]


def dump_live() -> str:
    """pg_dump the genesis tables from live, through a version-matched image."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set — this tool reads the live schema.")
    tables = [arg for t in GENESIS for arg in ("-t", f"public.{t}")]
    inner = (
        "pg_dump --schema-only --no-owner --no-privileges --no-comments "
        + " ".join(tables) + ' "$PGURL"'
    )
    out = subprocess.run(
        ["docker", "run", "--rm", "-e", f"PGURL={url}", "postgres:17", "sh", "-c", inner],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(f"pg_dump failed:\n{out.stderr}")
    return out.stdout


def strip_columns(create_body: str, drop: set[str]) -> tuple[str, set[str]]:
    """Remove the named columns from a CREATE TABLE body. Returns (body, removed).

    Inline table constraints go too when they mention a removed column — the
    migration that adds the column is the one that adds its CHECK.
    """
    kept, removed = [], set()
    for line in create_body.splitlines():
        if not line.strip():
            continue
        inline = re.match(r"\s+CONSTRAINT\s+[a-z_0-9]+\s", line, re.I)
        if inline:
            mentioned = set(re.findall(r"\b([a-z_][a-z_0-9]*)\b", line.lower()))
            if mentioned & drop:
                continue
            kept.append(line)
            continue
        name = re.match(r"\s+([a-z_0-9]+)\s", line)
        if name and name.group(1).lower() in drop:
            removed.add(name.group(1).lower())
            continue
        kept.append(line)
    # the last surviving column must not carry a trailing comma
    for i in range(len(kept) - 1, -1, -1):
        if kept[i].strip():
            kept[i] = kept[i].rstrip().rstrip(",")
            break
    return "\n".join(kept), removed


def main() -> None:
    added_columns, added_constraints, log_policies = migration_additions()
    dump = dump_live()

    # pg_dump 17.10 wraps output in \restrict/\unrestrict psql meta-commands and
    # a preamble of SETs. Drop both: this file is applied by apply-schema.sh
    # into a database it does not own, and an empty search_path would break the
    # migrations that follow it.
    statements = []
    for chunk in dump.split(";\n"):
        lines = [
            l for l in chunk.splitlines()
            if not l.startswith(("--", "\\restrict", "\\unrestrict", "SET ", "SELECT pg_catalog.set_config"))
        ]
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)

    removed_by_table: dict[str, set[str]] = {}
    out: list[str] = []
    for stmt in statements:
        flat = " ".join(stmt.split())

        create = re.match(r"CREATE TABLE public\.([a-z_0-9]+) \((.*)\)$", stmt, re.S)
        if create:
            table = create.group(1)
            body, removed = strip_columns(create.group(2), added_columns.get(table, set()))
            removed_by_table[table] = removed
            out.append(f"CREATE TABLE public.{table} (\n{body}\n)")
            continue

        # An identity clause on a column we removed goes with it.
        ident = re.match(
            r"ALTER TABLE public\.([a-z_0-9]+) ALTER COLUMN ([a-z_0-9]+) ADD GENERATED",
            flat,
        )
        if ident and ident.group(2).lower() in removed_by_table.get(ident.group(1), set()):
            continue

        # Constraints and indexes a migration adds must not pre-exist here.
        named = re.search(r"(?:ADD CONSTRAINT|CREATE (?:UNIQUE )?INDEX) ([a-z_0-9]+)", flat)
        if named and named.group(1).lower() in added_constraints:
            continue

        # Ditto policies. The four that SURVIVE this filter are the finding
        # worth reading twice: occ_/sponsors_ anon+authenticated policies on the
        # two public-reference tables are genesis, created in Phase 1 and named
        # in no migration — which is why 00-bootstrap.sql has to create the anon
        # and authenticated roles. Everything app_* comes from 0053/0055/0056.
        policy = re.search(r"CREATE POLICY ([a-z_0-9]+)", flat)
        if policy and policy.group(1).lower() in log_policies:
            continue

        # A foreign key to a table no migration-free schema has yet (profiles,
        # fetch_runs, soc codes) is added by the migration that creates it.
        fk = re.search(r"FOREIGN KEY \([a-z_0-9, ]+\) REFERENCES public\.([a-z_0-9]+)", flat)
        if fk and fk.group(1).lower() not in GENESIS:
            continue

        # Anything mentioning a column we removed goes too.
        table_m = re.search(r"(?:ON|TABLE(?: ONLY)?) public\.([a-z_0-9]+)", flat)
        if table_m:
            gone = removed_by_table.get(table_m.group(1).lower(), set())
            cols = set(re.findall(r"\(([a-z_0-9, ]+)\)", flat))
            mentioned = {c.strip() for group in cols for c in group.split(",")}
            if gone & mentioned:
                continue

        out.append(stmt)

    # 0055 drops target_roles_search_title_key WITHOUT `if exists`, so genesis
    # must carry the single-column UNIQUE that Phase 1 created. Live no longer
    # has it (0055 replaced it with the owner-scoped key), so it cannot be
    # dumped — it is restored here, and apply-schema.sh's diff proves the end
    # state matches live regardless.
    out.append(
        "ALTER TABLE ONLY public.target_roles\n"
        "    ADD CONSTRAINT target_roles_search_title_key UNIQUE (search_title)"
    )

    print(__header__)
    print("-- Trigger functions first: the tables' triggers call them.\n")
    for definition in genesis_functions():
        print(definition.rstrip().rstrip(";") + ";\n")
    for stmt in out:
        print(stmt + ";\n")


__header__ = """-- ops/ci/01-genesis.sql — GENERATED. Do not edit by hand.
--
-- The schema as it stood BEFORE migration 0001: the eight tables Phase 1
-- created through the Supabase dashboard, before db/migrations/ existed.
-- See B-GAE-024. Regenerate with ops/ci/generate-genesis.py; the result is
-- proven by ops/ci/apply-schema.sh, which applies this plus every migration to
-- a blank Postgres and diffs the outcome against the live schema.
--
-- Column types, defaults, generated expressions and identity clauses are
-- pg_dump's, verbatim. Columns, constraints and indexes that migrations add
-- are subtracted, parsed from the log itself."""


if __name__ == "__main__":
    main()
