# Runbook — running the machine

The operator's handbook. Written for the person who owns this thing, not for a
developer: what to type, what it means, and what to do when something breaks.

| Section | Answers |
|---|---|
| [1 · Adding a user](#1--adding-a-user-friend-tier) | how a friend gets in |
| [2 · Keys](#2--keys-list-revoke-rotate) | list, revoke, rotate |
| [3 · Reading the machine](#3--reading-the-machine) | did it run, and what happened |
| [4 · Budgets](#4--budgets) | what a refusal means, how to change a cap |
| [5 · Incidents](#5--incidents) | it broke — now what |
| [6 · Hard rules](#6--hard-rules) | the lines that are never crossed |
| [7 · Turning sign-in on](#7--turning-sign-in-on-strangers) | the switch that lets strangers in |

Every command runs from the repository root unless it says otherwise.

---

## 1 · Adding a user (friend tier)

**Two things are yours:** you create their profile by talking to your own
Claude, then you mint their key at the terminal. Everything after that they do
themselves, by conversation.

### The steps

1. **Create the profile.** In your own Claude session — the one on your
   operator token — say *"create a profile for Sam"*. That calls
   `create_profile` and hands back a `profile_id`. A friend key is refused
   here on purpose: whoever can create identities decides who the machine
   answers to, and until sign-in lands that is you alone.

2. **Mint their key.** One command, at the terminal, from the repository root:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/mint_access_key.py --owner <profile-id> --label "sam-laptop"
   ```

   The `--label` is required — an unlabelled key cannot be revoked safely,
   because you would not know whose it was.

3. **Copy the key now.** It is printed **once**. The database keeps only its
   SHA-256, so there is nowhere to look it up later. Losing it means minting
   another, which is the correct trade.

4. **Hand it over out of band.** A phone call, a password-manager share, in
   person. Never a file in this repository, never an email you keep, never a
   chat that is logged.

5. **They connect their own Claude.** One command on their machine, with their
   key in place of `THEIR-KEY`:

   ```bash
   claude mcp add --transport http goal-a-engine https://goal-a-mcp-730809616632.europe-west2.run.app/mcp --header "Authorization: Bearer THEIR-KEY"
   ```

6. **Their first five calls, in this order.** Their own AI does all of it; you
   are not involved.

   | Call | What it does |
   |---|---|
   | `get_intake_interview` | the engine's own interview — builds their career fact base |
   | `find_industry_codes` | their plain words ("care homes") become industry codes |
   | `set_promotion_rule` | writes those codes — **and auto-starts knocking their doors** |
   | `set_notification_channel` | their own phone topic — stored, never echoed back |
   | `send_test_nudge` | proves the phone actually buzzes |

### What day 1 honestly looks like

- **Their brief will say the doors are still being knocked** — something like
  *"your industry's doors are still being knocked — 1,240/9,880 done"*. That is
  the truth, not a fault. Setting their rule starts a sweep of their industry
  the same minute, and it runs at the outside APIs' pace over the following
  nights. The line stays up while coverage is under half.
- **Their queue will be thin on day 1** and thicken every night.
- **Their nightly pass runs with everybody else's**, at 06:30 London — their
  own rule, apply window, tray and phone.

### What they do not get yet

- **No Notion board.** There is one Notion credential in the environment and it
  opens one person's board. So the `file` stage runs for that one owner and
  returns a stated skip for everyone else — deliberately, rather than writing
  their cards somewhere they can never read them. Per-owner Notion is a
  recorded deferral, not an oversight. Everything else works for them:
  nudges, the queue, the reading tray, skill gaps, and engine-rendered CVs.
- **No sign-in.** There is no password and no self-serve signup. Their key *is*
  their identity, which is why section 2 matters.

---

## 2 · Keys: list, revoke, rotate

**Minting is the one action that decides who the machine answers to**, so it is
not an MCP tool and no AI can reach it. You run it from a terminal, and nobody
else can.

### List every key

```bash
PYTHONPATH=src .venv/bin/python scripts/mint_access_key.py --list
```

Shows key id, owner, label, last used, and live/REVOKED. It never shows a key
or its hash — there is nothing on that screen worth stealing.

### Revoke one

```bash
PYTHONPATH=src .venv/bin/python scripts/mint_access_key.py --revoke <key-id>
```

A revoke is a **stamp**, not a delete: the row stays with the time it was
revoked, so the history of who held what is never lost.

### Rotate

There is no rotate command on purpose. **Rotate = revoke, then mint.**

1. Revoke the old key by its id (above).
2. Mint a new one for the same `--owner`, with a fresh `--label`
   ("sam-laptop-2").
3. Hand it over out of band.
4. They remove the old server entry and re-run the `claude mcp add` line from
   section 1 with the new key.

**Rotate on suspicion, not on proof.** It costs one minute and nothing else:

- a lost or stolen laptop or phone
- a key pasted into a chat, a ticket, a screenshot, or any file
- a person you are no longer working with
- anything at all you are unsure about

### The honest limit — worth saying out loud when you hand a key over

The mint script says it in its own words: **"This key is a door lock, not a
vault. Mint for people the founder trusts."**

Through the MCP door the database itself does the refusing — that door connects
as a restricted role, and cross-owner reads and writes are refused by the
database, proven by attempting them. The nightly **engine** does not: it
connects as a role that bypasses row security, deliberately, because the world
half of the night has to write across every owner at once. So inside the engine
the boundary is the per-owner scoping in the code and its tests, not the
database. A key should go to someone you would trust with a spare front-door
key.

---

## 3 · Reading the machine

**Three places, in order of effort:** ask your Claude, look at the page, look at
the cloud.

### 1. Ask your own Claude

`get_run_report` gives last night's report card — every stage, whether it was
ok, how long it took, and what it did. `daily_brief` gives the day's agenda.
Neither needs a terminal.

### 2. The public status page

Anonymous, person-free, and safe to show anyone:

```bash
open https://goal-a-status-730809616632.europe-west2.run.app
```

It shows "15 of 15 stages" and the headline counts. No names, no salaries, no
owner — the page cannot leak a person because it does not know the name of a
single personal column.

### 3. The cloud, when a stage is red

```bash
gcloud run jobs executions list --job=goal-a-daily --region=europe-west2
```

Then open that execution's log in the console. The stage that failed prints its
own reason there.

### The per-owner lines are NUMBERED, not named — and that is deliberate

A run report's stages carry an `owners` list, and each entry is `seq: 1`,
`seq: 2`, and so on. **No profile id ever reaches that table.** The reason:
the run table is world-readable — every key holder can call `get_run_report` —
and a profile id is exactly the value somebody would need to attempt a
cross-owner read. Numbering keeps a failed owner visible without handing out
the one value that matters.

**The number → person map is printed only in the run's own log** (Cloud
Logging), as lines like `[owner 2] <id>`. That log is operator-only. So when
owner 2's nudge stage fails, you read the log to learn who owner 2 is, and
nobody else can.

### Today's spend

`sweep_status` now shows today's API budget for every source — spent, cap and
remaining, **both yours and the world's**. Everything resets at midnight UTC.

Or from the shell, without leaving it:

```bash
PYTHONPATH=src .venv/bin/python -c "
from budget.ledger import SOURCES, remaining
from db.connection import get_conn
with get_conn() as c, c.cursor() as cur:
    [print(remaining(cur, s)) for s in SOURCES]"
```

---

## 4 · Budgets

**Three outside APIs cost quota** — `adzuna`, `reed`, `companies_house` — and
every call is counted **twice**: against the world cap (the provider's shared
day, which belongs to everybody) and, when a person triggered it, against that
person's own daily budget. So one key holder can never eat the shared quota,
and the nightly world half — which acts for nobody — spends only the world's.

### What a refusal looks like

Not an error. A **stop, with receipts**:

```text
adzuna budget spent — resets at midnight UTC (owner 100/100 today)
```

The numbers are the scope that actually refused — `owner N/N` if it was that
person's budget, `world N/N` if it was the shared day. The runner stops there
and picks up tomorrow. It never turns one exhausted day into a flood of fake
failures; that is guarded, and section 5 says why.

### Today's caps

| Source | World / day | One owner / day | Why that number |
|---|---|---|---|
| `adzuna` | 250 | 100 | the free tier is 250 |
| `reed` | 950 | 300 | the provider free day the sweep and the JD drip already share |
| `companies_house` | 20,000 | 2,000 | no published daily limit — our own runaway backstop |

### Changing a cap is one row, and needs no deploy

In the Supabase SQL editor:

```sql
update api_budget_caps set world_daily = 400 where source = 'adzuna';
```

Two things the database will enforce for you:

- An owner's budget can never exceed the world cap. Lower the world cap below
  somebody's owner budget and the update is **refused**, not silently applied.
- **A source with no cap row has no budget at all.** The gate fails closed and
  refuses every call to it. Never delete a row to "remove a limit" — that stops
  the source entirely.

### The open Adzuna question — this one needs your decision

Until this phase, the nightly `discover` stage was never counted at all. It
makes one call per role pattern per source, and there are **49 patterns**
today.

That means on a day the broad advert sweep also runs, Adzuna totals **240**
(the sweep's own `--adzuna-cap`) **+ 49 = 289 calls against a 250 free tier**.
Which also means the machine has probably been over that tier on those days
already, invisibly, and the old ledger's 240 peak was the sweep's own cap
binding rather than the truth.

The cap was left at the documented 250 rather than raised to hide it. Two ways
out, and the choice is yours:

1. **Lower the sweep's `--adzuna-cap` to about 200**, so 200 + 49 sits under
   250 on any day.
2. **Confirm the account's real tier with Adzuna and raise the row** — one
   `update`, as above.

Until you pick one, a sweep day's tail stops with `quota_exhausted` and resumes
tomorrow. That is the designed behaviour, not a failure.

---

## 5 · Incidents

**Every incident starts the same way: read the run's own log.**

### A "Pipeline run FAILED" nudge on your phone

1. Find the execution:

   ```bash
   gcloud run jobs executions list --job=goal-a-daily --region=europe-west2
   ```

2. Open that execution's log in the console and read the failed stage's own
   output. The `[owner N] <id>` map is in the same log, so a per-owner failure
   tells you whose it was.
3. Or, without leaving your chat: `get_run_report` names the failed stages.

### A budget stop is not an incident

A runner that hits its cap **stops with receipts** and says `budget spent —
resets at midnight UTC` with the numbers. It does not flood the report with
fabricated errors — that was a real defect (a registry batch would have stamped
up to 2,000 organisations "error" for one exhausted day), and three runners now
catch the refusal above their per-item error handling. If a stage reports a
budget stop, nothing is broken. Tomorrow it resumes.

### Nothing ran at all

Check the cron is still there:

```bash
gcloud scheduler jobs list --location=europe-west2
```

Two Cloud Monitoring alerts watch the infrastructure independently of the
nudges, because an in-app nudge cannot report the database being unreachable.

### A bad deploy — roll back

Images are tagged by commit sha. Point the job back at the previous tag:

```bash
gcloud run jobs update goal-a-daily --region=europe-west2 --image=europe-west2-docker.pkg.dev/goal-a-engine/engine/goal-a-engine:<previous-sha>
```

Then hand-run it and read the report:

```bash
gcloud run jobs execute goal-a-daily --region=europe-west2 --wait
```

The two services roll the same way with `gcloud run services update`, and in
the console a bad revision is one click back.

### Re-running is always safe

Two runs can never overlap — the run script takes a file lock and a second
start exits immediately saying so. And the engine is deterministic: a stage
that already did its work does it again to the same result. So when in doubt,
run it again and read the report.

```bash
gcloud run jobs execute goal-a-daily --region=europe-west2 --wait
```

---

## 6 · Hard rules

**These are not preferences.**

1. **Never print or commit a channel topic or a key value.** A phone topic *is*
   the capability to reach that phone; it lives only in the profile row, never
   in a file, a log, or a chat. A minted key prints once, to your terminal, and
   travels out of band. Tests scan the whole repository for both shapes, so a
   slip fails loudly — but do not rely on that instead of care.

2. **Every push needs your explicit word.** Local commits are fine. Pushing
   anywhere — this repository, the public snapshot, anything — is a gate, every
   time, no exceptions.

3. **Any engine-stage change follows the 06:30 lane rule**, in this order and
   no other:

   1. rebuild and deploy the image (CI does this on green — it points the job
      at the new image and deliberately does **not** run it)
   2. hand-run it:

      ```bash
      gcloud run jobs execute goal-a-daily --region=europe-west2 --wait
      ```

   3. verify **15 of 15** stages ok in the report
   4. only then may the 06:30 cron meet it

   The reason: a run takes about thirteen minutes, sends real nudges, and
   writes real rows. It is a deliberate act, never a side effect of merging.

4. **A cap is a row; a column is not.** Cap values are edited live, as in
   section 4. Anything that changes the shape of the database goes through a
   migration, mirrored into `db/migrations/`.

5. **Never delete rows to fix something.** Removals in this system are stamps —
   a revoked key, a skipped reading, a retired CV block all keep their row and
   gain a timestamp. A delete destroys the history that makes the next incident
   readable.

---

## 7 · Turning sign-in on (strangers)

Everything in sections 1 and 2 is the **friend tier**: you create the profile,
you mint the key, you hand it over. It works exactly as far as the people you
have met.

Sign-in is the switch that removes you from that loop. After it, somebody you
have never met signs in with Google, gets their own profile, mints their own
key, and sees nothing of yours. **The code for all of that is built, tested and
committed. Nothing is switched on.** Three things stand between here and a live
stranger, and all three are yours to do.

### What is already true

* The door verifies Google sign-in tokens — signature, issuer, audience and
  expiry all checked, forged and expired tokens refused
  (`tests/test_signin_door.py`).
* A verified first sign-in creates that person's profile automatically, and RLS
  scopes them and the budget meter counts them with no extra work
  (`tests/test_signin_identity.py`).
* `issue_my_key` and `revoke_my_key` exist for signed-in owners only — a friend
  key cannot mint another key, and neither can your operator token.
* The data API that a signed-in stranger could otherwise have written through
  is shut (`B-GAE-032`, migration 0061). This one was a real hole and it is
  closed.

### Step 1 · The Google client (~15 minutes, your hands only)

This is the part that needs your Google account, and it is why nothing here can
be done for you.

1. **Google Cloud console** → the `goal-a-engine` project → **APIs & Services →
   OAuth consent screen**. Choose **External**, fill in the app name and your
   support email, and save. Leave it in *Testing* while you try it — that limits
   sign-in to accounts you list, which is exactly what you want first.
2. **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Web application.**
3. Under **Authorised redirect URIs**, add exactly one entry — Supabase's
   callback:

   ```
   https://<your-project-ref>.supabase.co/auth/v1/callback
   ```

   Your project ref is the first part of the host in your `SUPABASE_URL`.
4. Copy the **Client ID** and **Client secret**. Treat the secret like any other
   credential: never into a file in this repository.
5. **Supabase dashboard** → **Authentication → Sign In / Providers → Google** →
   enable it, paste the Client ID and secret, save.

**The moment you save that, strangers are real.** Anyone who can reach the
hosted MCP URL and sign in with Google gets a profile. While the consent screen
stays in *Testing*, that is only the accounts you listed — do it that way first.

### Step 2 · Tell the door which project to trust

The door refuses every sign-in token until it knows the issuer. One variable:

```bash
grep -q '^SUPABASE_URL=' .env || echo "SUPABASE_URL=https://<your-project-ref>.supabase.co" >> .env
```

Then push it and redeploy the MCP service (it is the only surface that gets it —
the daily job and the status page have no identity to verify):

```bash
./ops/cloud/push-secrets.sh && ./ops/cloud/setup.sh
```

Unset, the door serves the friend tier alone and refuses every JWT. That is a
supported way to run — it is what runs today.

### Step 3 · Prove it with your own account before anyone else

Sign in yourself, then check the two things that matter:

```bash
PYTHONPATH=src .venv/bin/python -c "from db.connection import get_conn
with get_conn() as c, c.cursor() as k:
    k.execute('select name, created_at from profiles where auth_user_id is not null order by created_at desc limit 5')
    print(k.fetchall())"
```

A row means the door created a profile from a verified token. Then ask that
signed-in session for its apply queue: it must come back **empty**. If it shows
your listings, stop and say so — that is the isolation failing, and it is the
one failure that must never be worked around.

### What is NOT built, and what it would take

**The connector's one-click "Connect" button does not work yet, and the reason
is on Supabase's side, not ours.** Measured on 2026-08-12: your project answers
`/auth/v1/.well-known/oauth-authorization-server` with **404, "OAuth server is
disabled"**, and its OpenID discovery advertises no client-registration
endpoint. An MCP connector's browser sign-in flow needs both. So today a
signed-in user has to obtain their token another way (a small web page, or the
dashboard) and paste it — which is workable for a first friend and is not
self-serve.

When Supabase's OAuth server is enabled for the project, the wiring on our side
is one composition, not a rewrite: FastMCP ships a `SupabaseProvider` that
serves the two `.well-known` documents and accepts our existing verifier
unchanged. That is a deliberate build, gated on you, and it is written up in the
decision log for 2026-08-12.

Also still yours, and deliberately not done here: the **dashboard sign-in
button** (the dashboard is still your single-user surface on its own token), and
the **deploy** — nothing in this section has been run against the cloud.

### If you want to undo it

Disabling the Google provider in Supabase stops new sign-ins immediately.
Existing profiles stay (nothing in this system deletes rows) and any key those
owners already minted keeps working until it is revoked — revoke them from
section 2. Clearing `SUPABASE_URL` and redeploying shuts the JWT path itself.
