"""ntfy push client. A failed push returns False — it never sinks the run."""
from __future__ import annotations

import sys

import requests

NTFY_BASE = "https://ntfy.sh"
TIMEOUT = 10


def _shout(message: str) -> None:
    """Say it loudly on stderr, in a shape nothing else emits.

    The standing rule earned on 2026-08-09: a check must fail LOUDLY and
    differently from "all clear". When ntfy cannot carry the alert, Cloud
    Logging still can — but only if something is actually printed.
    """
    print(f"!!! PIPELINE ALERT UNDELIVERED — {message}", file=sys.stderr, flush=True)


def send_push(channel: str | None, title: str, body: str,
              session=None, timeout: int = TIMEOUT) -> bool:
    """Send one push to an 'ntfy:<topic>' channel. False on any failure."""
    if not channel or not channel.startswith("ntfy:"):
        return False
    topic = channel.split(":", 1)[1].strip()
    if not topic:
        return False
    try:
        resp = (session or requests).post(
            f"{NTFY_BASE}/{topic}",
            data=body.encode("utf-8"),
            # Encode the title OURSELVES. Handed a str, http.client puts it on
            # the wire as latin-1, and an em-dash or accent then raises
            # UnicodeEncodeError — which is NOT a requests.RequestException,
            # so it escapes the except below entirely (found live 2026-08-09).
            headers={"Title": title.encode("utf-8")},
            timeout=timeout,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def notify_failure(cur, failed_names: list[str]) -> bool:
    """A broken run must never be silent: push the failing stage names.

    Never raises. It runs BEFORE finish_run, so an exception escaping here
    would cost the run report as well as the alert. Whenever the push cannot
    be delivered — no channel, a refusal, or a fault in the alerting path
    itself — it shouts on stderr instead, so the failure is still visible in
    Cloud Logging even when ntfy is not reachable at all.
    """
    from criteria.loader import default_profile_id
    from notify.nudges import load_channel

    stages = ", ".join(failed_names)
    try:
        # A machine-health alert, so it goes to the machine's owner — the
        # local profile — not to whoever's run happened to fail. Task 3
        # revisits this when runs become per-owner.
        channel = load_channel(cur, default_profile_id(cur))
        if not channel:
            _shout(f"no notification channel configured. Failed stages: {stages}")
            return False
        sent = send_push(
            channel,
            "Pipeline run FAILED",
            "Failed stages: " + stages +
            "\nCheck pipeline_runs for the stage summaries.",
        )
        if not sent:
            _shout(f"the push did not go through. Failed stages: {stages}")
        return bool(sent)
    except Exception as exc:                      # the alert path itself broke
        _shout(f"alerting raised {exc!r}. Failed stages: {stages}")
        return False


def send_test(cur, owner_id) -> dict:
    """Send a one-off test nudge to THIS owner's channel. Reports whether a
    channel is set and whether the push went through — never the channel itself
    (it's a secret).

    The owner is required (Phase 9 task 1b): reached from the MCP surface, this
    was the one call that could act on another person's phone rather than their
    rows, because it read the first profile's channel whoever asked.
    """
    from notify.nudges import load_channel

    channel = load_channel(cur, owner_id)
    if not channel:
        return {"channel_configured": False, "sent": False}
    sent = send_push(
        channel,
        "GOAL A — test nudge",
        "Test push from the MCP server. If you can see this, nudges are working.",
    )
    return {"channel_configured": True, "sent": bool(sent)}
