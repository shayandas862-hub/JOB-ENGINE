"""The OTHER door: Supabase's auto-generated data API (B-GAE-032).

Every other security test in this repo asks whether the MCP door is safe.
This one asks about the door nobody opened: Supabase publishes a PostgREST
API over the same database, reachable by anyone holding the project's
publishable key (`anon`) or any signed-in user's JWT (`authenticated`). The
engine has never used it — no surface in this repo names it, and neither
Cloud Run service carries the key — so it was never in frame while task 2a
sorted `goal_a_app` policies table by table.

Measured before this file existed: `anon` and `authenticated` each held
INSERT, UPDATE **and** DELETE on all 42 relations in `public` (252 write
grants), and two genesis-era policies — `sponsors_authenticated_all`,
`occ_authenticated_all`, both `FOR ALL USING (true) WITH CHECK (true)` — let
those privileges through RLS on the sponsor register and the SOC table.
Nothing was exploitable while sign-in was off and no auth user existed. Task 6
turns sign-in on, at which point "authenticated" stops meaning nobody.

So the assertions are over **classes, not lists**:

  * every relation in `public`, because Supabase's default privileges grant
    writes to every FUTURE table too — a list would pass while the next table
    created reopens the hole;
  * every policy naming a native role, because a grant is only reachable
    through a policy that admits it;
  * the default privileges themselves, which is the could-it-return half:
    without it, the next `CREATE TABLE` re-grants everything this closed.

`public` (the pseudo-role) rides along in every check: a grant to PUBLIC
reaches anon and authenticated by definition, and is the shape that would
slip past a check written against two role names.

Read-only, and paired with a control everywhere: a probe that returns nothing
because it is broken looks exactly like a database that is locked down.
"""
from __future__ import annotations

import os

import pytest

DB_ONLY = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="DB integration tests are opt-in: RUN_DB_TESTS=1")

# The roles Supabase's own API authenticates as. `service_role` is deliberately
# absent: it is the secret-key role, it bypasses RLS by design, and it is not
# reachable from a browser or a signed-in stranger.
NATIVE = ("anon", "authenticated", "PUBLIC")

# Everything that changes a row or the table under it. TRUNCATE matters as much
# as DELETE here — the register is a keep-all table, and TRUNCATE empties it
# without touching a single policy. REFERENCES and TRIGGER are the two that
# look harmless and are not: TRIGGER lets a role attach code to somebody else's
# writes, REFERENCES lets it pin rows in place with a foreign key.
WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE",
                    "REFERENCES", "TRIGGER")

# A policy for one of these commands is what turns a write grant into a write.
WRITE_COMMANDS = ("ALL", "INSERT", "UPDATE", "DELETE")

APP_ROLE = "goal_a_app"


@DB_ONLY
def test_no_supabase_native_role_can_write_any_relation_in_public():
    # The finding itself, asserted over every relation rather than the two
    # tables that had policies. Views are relations too and are included on
    # purpose: an updatable view is a write path that carries its own grants.
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select grantee, privilege_type, count(*) as n "
                "from information_schema.role_table_grants "
                "where table_schema = 'public' "
                "  and grantee = any(%s) and privilege_type = any(%s) "
                "group by grantee, privilege_type "
                "order by grantee, privilege_type",
                (list(NATIVE), list(WRITE_PRIVILEGES)))
            held = [(r["grantee"], r["privilege_type"], r["n"])
                    for r in cur.fetchall()]

            # The control. An empty answer above is only meaningful if the
            # probe can see grants at all — a typo'd schema name, a renamed
            # information_schema view or a database with no tables all return
            # nothing and would read as "locked down".
            cur.execute(
                "select count(*) as n from information_schema.role_table_grants "
                "where table_schema = 'public' and grantee = %s "
                "and privilege_type = 'INSERT'", (APP_ROLE,))
            app_writes = cur.fetchone()["n"]
        conn.rollback()

    assert app_writes > 0, (
        "the probe found no INSERT grant for the app role either, so it is "
        "measuring nothing — fix the query before trusting the refusal")
    assert held == [], (
        "Supabase's own API roles can write this database: "
        + "; ".join(f"{g} holds {p} on {n} relations" for g, p, n in held))


@DB_ONLY
def test_no_policy_admits_a_native_role_to_a_write():
    # Grants and policies are two locks on the same door, and B-GAE-032 was
    # both of them being open at once. This is the second lock: even if a
    # grant came back, a write needs a policy that names the role.
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select tablename, policyname, roles::text as roles, cmd "
                "from pg_policies where schemaname = 'public' "
                "  and roles::text[] && %s::text[] and cmd = any(%s) "
                "order by tablename, policyname",
                (list(NATIVE) + ["public"], list(WRITE_COMMANDS)))
            admitted = [(r["tablename"], r["policyname"], r["roles"], r["cmd"])
                        for r in cur.fetchall()]

            # The control: policies must exist to be scanned at all.
            cur.execute("select count(*) as n from pg_policies "
                        "where schemaname = 'public'")
            total = cur.fetchone()["n"]
        conn.rollback()

    assert total > 0, "no policies at all in public — the scan proves nothing"
    assert admitted == [], (
        "a write policy names a Supabase-native role: "
        + "; ".join(f"{t}.{p} ({roles}, {cmd})" for t, p, roles, cmd in admitted))


@DB_ONLY
def test_a_table_created_tomorrow_does_not_re_grant_writes_to_them():
    # The could-it-return half, and the reason B-GAE-032's guard had to be a
    # class. Supabase ships default privileges that grant every privilege on
    # every NEW table to anon and authenticated — so a revoke alone lasts
    # exactly until the next CREATE TABLE.
    #
    # Scope, stated because it is a real limit rather than an oversight: a
    # default ACL belongs to the role that creates the object, and `postgres`
    # here is neither superuser nor a member of `supabase_admin`, so
    # supabase_admin's own default ACL cannot be altered with the credentials
    # this project has. Everything that creates a table in this project —
    # migrations through the Supabase MCP, the SQL editor, the engine — runs
    # as `postgres`. That is the grantor asserted on; and if a table ever does
    # appear with native write grants by some other route, the first test in
    # this file catches it the moment it exists.
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select a.grantee::regrole::text as grantee, a.privilege_type "
                "from pg_default_acl d, aclexplode(d.defaclacl) a "
                "where d.defaclobjtype = 'r' "
                "  and d.defaclrole = 'postgres'::regrole "
                "  and d.defaclnamespace in (0, 'public'::regnamespace::oid) "
                "  and a.grantee::regrole::text = any(%s) "
                "  and a.privilege_type = any(%s) "
                "order by grantee, privilege_type",
                (["anon", "authenticated", "-"], list(WRITE_PRIVILEGES)))
            future = [(r["grantee"], r["privilege_type"]) for r in cur.fetchall()]

            # The control: this project's default ACL must still say something
            # (the app role's own future-table grants live in the same row).
            cur.execute(
                "select count(*) as n from pg_default_acl d, "
                "aclexplode(d.defaclacl) a "
                "where d.defaclobjtype = 'r' "
                "  and d.defaclrole = 'postgres'::regrole "
                "  and a.grantee::regrole::text = %s", (APP_ROLE,))
            app_future = cur.fetchone()["n"]
        conn.rollback()

    assert app_future > 0, (
        "no default privileges for the app role — the probe is looking at the "
        "wrong grantor or the wrong schema")
    assert future == [], (
        "the next table created will hand writes straight back: "
        + "; ".join(f"{g} would get {p}" for g, p in future))


@DB_ONLY
def test_every_table_in_public_still_has_row_level_security_on():
    # This one was green when written, and it is here to keep a decision
    # honest rather than to close a hole. 0061 left the native roles' SELECT
    # *grants* alone — inert, because RLS is on and no policy admits them —
    # and dropped the two anon read policies instead. "Inert" is true exactly
    # while RLS stays on: a single table created with it off would be
    # world-readable through the data API with no policy involved and nothing
    # else in the suite would notice.
    #
    # Measured at the time of writing: 30 tables in public, all with RLS on.
    from db.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select c.relname from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relkind in ('r','p') "
                "  and c.relrowsecurity = false order by c.relname")
            unprotected = [r["relname"] for r in cur.fetchall()]

            cur.execute(
                "select count(*) as n from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relkind in ('r','p')")
            total = cur.fetchone()["n"]
        conn.rollback()

    assert total > 20, f"only {total} tables found in public — the probe is wrong"
    assert unprotected == [], (
        "RLS is off, so anon's SELECT grant is live on: "
        + ", ".join(unprotected))
