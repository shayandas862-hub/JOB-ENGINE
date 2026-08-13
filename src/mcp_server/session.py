"""The MCP door's connection: scoped to the caller before a tool body runs.

Task 2a wrote RLS policies on all 28 tables and proved they refuse — but every
door still connected as `postgres`, which carries `rolbypassrls`, so in
production they refused nobody. This module is the cutover: the hosted and
local MCP doors now run their tool bodies as `goal_a_app`, a role that cannot
bypass RLS, with the caller's identity carried in a per-transaction setting the
policies read through `public.app_owner()`.

**The order of the four steps is load-bearing and only works this way:**

1. Resolve the owner FIRST, still on the engine role. The door has to read a
   key before it can know whose it is, and the stdio fallback reads `profiles`
   before any owner is established. Both of those tables carry policies keyed
   on the owner, so assuming the role first would make both return nothing and
   the door would resolve every caller to nobody.
2. THEN `SET LOCAL ROLE goal_a_app`, which is what actually drops the bypass —
   RLS is evaluated against `current_user`. `FORCE ROW LEVEL SECURITY` would
   not do this; it removes the table-owner exemption, not the role attribute.
3. THEN publish the owner into `app.owner_id`. `app_owner()` fails closed:
   unset means NULL, and NULL matches no policy, so a bug that skips this step
   shows up as an empty result rather than as somebody else's data.
4. Only then hand the connection to the tool.

`SET LOCAL` and `set_config(..., true)` are transaction-scoped rather than
cursor-scoped, which is why both survive into the cursors a tool opens later
and why both are gone when the transaction ends. Nothing has to be unwound.

**What this deliberately does NOT cover** — four doors, and each stays on the
engine role for its own stated reason:

* `transport.py` resolves a presented key to an owner, which is step 1's
  problem and cannot be done under a policy keyed on the answer.
* `scripts/run.py` and the nightly Cloud Run job: the daily pass is world work
  that legitimately spans owners until task 3 gives it a per-owner loop, and
  B-GAE-018 would crash its `merge` stage under this role today.
* The dashboard and the status page: both are the founder's own single-user
  surfaces, both read only curated views, and neither is reachable by a
  stranger. They follow the nightly job in task 3 rather than being cut over
  piecemeal here — a decision, not an oversight, and the reason this file's
  cutover is described as the MCP door rather than the engine.

So the boundary today is: **anything a key holder can reach runs as
`goal_a_app`; everything the founder alone reaches does not.** Task 6 must not
open the stranger tier while any stranger-reachable path is outside that.

Tools import this as ``get_conn``, so every existing call site and every test
that patches ``<module>.get_conn`` keeps working unchanged. That convenience is
also a trap worth naming: those patched fakes never exercise the role switch,
so a green offline suite says nothing at all about this file.
``tests/test_rls_cutover.py`` is the proof that does — a real tool, a real
connection, the application filter removed.
"""
from __future__ import annotations

from contextlib import contextmanager

from db.connection import get_conn

from mcp_server.identity import current_owner

APP_ROLE = "goal_a_app"
OWNER_SETTING = "app.owner_id"


@contextmanager
def scoped_conn():
    """`get_conn()`, but the transaction is already scoped to the caller."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            owner = current_owner(cur)
            cur.execute(f"set local role {APP_ROLE}")
            cur.execute("select set_config(%s, %s, true)",
                        (OWNER_SETTING, str(owner)))
        yield conn


def adopt_owner(cur, owner_id) -> None:
    """Re-scope the CURRENT transaction to another owner — the sanctioned
    exception, and there is exactly one legitimate caller.

    create_profile must write a profiles row for an owner who does not
    exist yet, and the app role's own policy (WITH CHECK
    ``profile_id = app_owner()``) means that insert can only happen AS the
    new owner. So the tool adopts the new id for the insert and scopes
    straight back for its audit row. Transaction-scoped exactly like the
    door's own set_config — nothing survives the request.

    Any other set_config on this setting is a tool smuggling identity past
    the door; tests/test_onboarding.py scans src/ to keep this the only
    module that spells it.
    """
    cur.execute("select set_config(%s, %s, true)",
                (OWNER_SETTING, str(owner_id)))
