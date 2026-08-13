"""The profile write behind create_profile (Phase 9 task 4).

One insert, kept out of the skin on purpose. The MCP layer decides WHO may
create a profile (operator-only until sign-in) and AS WHOM the transaction
runs — under the app role's WITH CHECK the row can only be written as the
owner it belongs to, so the tool adopts the new id around this call. This
module owns only the row itself, which is what lets the writer-coverage
ratchet run the real write against a real table.
"""
from __future__ import annotations


def insert_profile(cur, profile_id, name, contact_email=None,
                   auth_user_id=None) -> dict:
    """Write the row every per-owner surface hangs off.

    No secrets ride here: the notification channel and the Notion ref have
    their own owner-called setters.

    `auth_user_id` is the Supabase identity the owner signed in with (task 6),
    or None for a friend-tier profile the operator created. It stays a
    parameter of this one writer rather than a second insert path, so a
    profile row has exactly one place it can be born.
    """
    cur.execute(
        "insert into profiles (profile_id, name, contact_email, auth_user_id) "
        "values (%s, %s, %s, %s)",
        (str(profile_id), name, contact_email, auth_user_id))
    return {"profile_id": str(profile_id), "name": name}


def set_notification_channel(cur, owner_id, channel) -> bool:
    """Point the owner's nudges at their own phone.

    The value is a SECRET — the ntfy topic IS the capability to reach that
    phone. Callers pass facts about the change to logs and audit rows,
    never the value itself; under the app role the policy means an owner
    can only ever hit their own row, whatever owner_id says.
    """
    cur.execute(
        "update profiles set notification_channel = %s "
        "where profile_id = %s", (channel, str(owner_id)))
    return cur.rowcount == 1


def set_notion_token_ref(cur, owner_id, ref) -> bool:
    """Store the NAME of the owner's Notion credential — never the token.

    The column is a pointer by design (task 6 of the phase decides who
    resolves it); the tool layer refuses values that look like actual
    Notion tokens before this is ever reached.
    """
    cur.execute(
        "update profiles set notion_token_ref = %s "
        "where profile_id = %s", (ref, str(owner_id)))
    return cur.rowcount == 1
