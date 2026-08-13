"""Render the Today page — pure HTML from view rows, zero logic, zero JS.

One lane at a time: a tab bar (Ready / Needs / Reading tray / Company
watch / Sponsors) whose counts come from the scorecard, the honesty-panel
tiles on every tab, and a pager (PAGE_SIZE per page) whose links carry the
query prefix the server supplies. The Sponsors tab browses the whole
register by plain-English industry and town (a zero-JS GET form); its
filtered pager total rides on the rows themselves. Status is always icon +
colour + label; every number sits next to its receipt, receipts render as
scannable chips. All dynamic values are escaped; the page carries no
scripts and no external assets, and refreshes itself every 5 minutes.
"""
from __future__ import annotations

from html import escape
from math import ceil
from urllib.parse import quote_plus

from dashboard.queries import PAGE_SIZE
from dashboard.style import CSS

TABS = (
    ("ready", "Ready to apply", "ready_rows",
     "Nothing ready yet — tonight's run fills this."),
    ("needs", "Needs something", "needs_rows",
     "Nothing waiting — every queue row is ready."),
    ("tray", "Reading tray", "staged_now",
     "Nothing staged — the tray fills after each run; a reader drains it."),
    ("companies", "Company watch", "companies_tracked",
     "No companies tracked yet."),
    ("sponsors", "Sponsors", "sponsors_total",
     "No sponsors match — clear a filter, or the census is still knocking."),
)
TAB_KEYS = tuple(key for key, *_ in TABS)


def _e(value) -> str:
    if value is None:
        return "—"
    if hasattr(value, "strftime"):          # dates/timestamps render short
        return escape(value.strftime("%Y-%m-%d %H:%M")
                      if hasattr(value, "hour") else value.strftime("%Y-%m-%d"))
    return escape(str(value))


def _n(value) -> str:
    """Numbers with thousands separators; None stays an honest dash."""
    return f"{value:,}" if isinstance(value, (int, float)) else "—"


def _read_label(row: dict) -> str:
    if row.get("read_quality"):
        return str(row["read_quality"])
    return "unlabelled" if row.get("has_reading") else "not yet"


def _chip(text: str, cls: str = "") -> str:
    klass = f"chip {cls}".strip()
    return f"<span class='{klass}'>{text}</span>"


def _chips(row: dict) -> str:
    fit = row.get("fit_rank")
    fit_cls = {"High": "hi", "Med": "mid"}.get(str(fit), "")
    parts = [_chip(f"fit {_e(fit)}", fit_cls),
             _chip(f"sponsor {_e(row.get('sponsor_signal'))}"),
             _chip(f"wall {_e(row.get('salary_wall'))} "
                   f"({_e(row.get('wall_basis'))})"),
             _chip(f"read {_e(_read_label(row))}")]
    if row.get("deadline"):
        parts.append(_chip(f"by {_e(row['deadline'])} "
                           f"({_e(row.get('deadline_source'))})"))
    parts.append(_chip(f"seen {_e(row.get('age_days'))}d "
                       f"via {_e(row.get('source'))}"))
    if row.get("skill_asked"):                 # the fit column's receipts (U6)
        parts.append(_chip(
            f"skills {_e(row.get('skill_have'))}/{_e(row['skill_asked'])}"))
    if row.get("is_new_today"):
        parts.append(_chip("new today", "hi"))
    if row.get("in_reading_tray"):
        parts.append(_chip("in reading tray", "mid"))
    if row.get("needs_what"):
        parts.append(_chip(f"&#9684; {_e(row['needs_what'])}", "warn"))
    return f"<div class='chips'>{''.join(parts)}</div>"


def _listing_row(row: dict) -> str:
    bucket = row.get("bucket") or "ready"
    badge = ("<span class='badge ready'>&#9679; ready</span>" if bucket == "ready"
             else "<span class='badge needs'>&#9684; needs</span>")
    return (
        "<article class='row'>"
        f"<div class='row-head'><a href='{_e(row.get('role_url'))}' "
        f"rel='noopener'>{_e(row.get('role_title'))}</a>{badge}</div>"
        f"<div class='row-sub'>{_e(row.get('company_name'))} · "
        f"{_e(row.get('location'))} · {_e(row.get('salary_text'))}</div>"
        f"{_chips(row)}</article>")


def _lane_rows(today: list[dict], tab: str) -> list[dict]:
    if tab == "tray":
        return [r for r in today if r.get("in_reading_tray")]
    return [r for r in today if (r.get("bucket") or "ready") == tab]


def _tabs_bar(s: dict, active: str, qs: str) -> str:
    q = escape(qs, quote=True)
    links = []
    for key, label, count_key, _empty in TABS:
        current = " aria-current='page'" if key == active else ""
        links.append(
            f"<a href='{q}tab={key}&amp;page=1'{current}>"
            f"{label} ({_n(s.get(count_key))})</a>")
    return f"<nav class='tabs'>{''.join(links)}</nav>"


def _pager(total, page: int, tab: str, qs: str,
           page_size: int = PAGE_SIZE, extra: str = "") -> str:
    pages = max(1, ceil((total or 0) / page_size))
    if pages <= 1:
        return ""
    q, x = escape(qs, quote=True), escape(extra, quote=True)
    parts = []
    if page > 1:
        parts.append(f"<a rel='prev' href='{q}tab={tab}{x}&amp;"
                     f"page={page - 1}'>&#8249; prev</a>")
    parts.append(f"<span>page {page} of {pages}</span>")
    if page < pages:
        parts.append(f"<a rel='next' href='{q}tab={tab}{x}&amp;"
                     f"page={page + 1}'>next &#8250;</a>")
    return f"<div class='pager'>{''.join(parts)}</div>"


def _tile(label: str, value: str, receipt: str) -> str:
    return (f"<div class='tile'><div class='k'>{label}</div>"
            f"<div class='v'>{value}</div><div class='r'>{receipt}</div></div>")


def _scorecard_tiles(s: dict) -> str:
    run = (f"{_e(s.get('last_run_status'))} · {_e(s.get('last_run_at'))}"
           if s.get("last_run_at") else "never ran")
    tiles = [
        _tile("Applications", _n(s.get("applications_total")),
              f"{_n(s.get('applications_today'))} today — the number that matters"),
        _tile("Queue", _n(s.get("queue_rows")),
              f"{_n(s.get('ready_rows'))} ready · {_n(s.get('needs_rows'))} need something"),
        _tile("Read quality", f"{_n(s.get('read_ai'))} ai",
              f"{_n(s.get('read_keywords'))} keywords · "
              f"{_n(s.get('read_unlabelled'))} unlabelled · "
              f"{_n(s.get('unread_with_jd'))} unread"),
        _tile("Reading tray", _n(s.get("staged_now")),
              f"{_n(s.get('claimed_now'))} claimed by a reader"),
        _tile("Reviews open", _n(s.get("reviews_open")),
              "waiting for a human decision"),
        _tile("Coverage", f"{_n(s.get('companies_tracked'))} companies",
              f"{_n(s.get('companies_with_boards'))} with boards · "
              f"{_n(s.get('ads_merged'))} ads merged · "
              f"{_n(s.get('ads_awaiting_merge'))} awaiting"),
        _tile("Register", _n(s.get("register_rows")),
              f"loaded {_n(s.get('register_age_days'))} days ago"),
        _tile("Last run", run, "the daily loop's report card"),
    ]
    return ("<section><h2>Honesty panel</h2>"
            f"<div class='tiles'>{''.join(tiles)}</div></section>")


def _mirror_section(rows: list[dict]) -> str:
    """"What the system understands about you" — Phase 9.5 task 1.

    The honesty panel above measures the machine. This measures what the
    machine has understood about the person, and it leads with the
    uncomfortable half on purpose: a count of facts is flattering and useless,
    while the number of recorded skills with no fact behind them is the one
    that predicts a thin CV. The truth gate will decline exactly those skills,
    so the owner should meet them here first.
    """
    if not rows:
        return ""
    cards = []
    for row in rows:
        live = row.get("skills_live") or 0
        evidenced = row.get("skills_evidenced") or 0
        missing = row.get("skills_unevidenced") or 0
        outside = row.get("evidenced_outside_paid_work") or 0
        drafts = row.get("facts_drafts") or 0
        # A share, never a fake 0% — an owner the machine has not met yet has
        # no coverage to report, and 0% would read as a verdict on them
        # (cv.mirror returns None for the same reason).
        share = (f"{round(100 * evidenced / live)}% of what you have recorded"
                 if live else "no skills recorded yet")
        cards.append(
            "<div class='tiles'>"
            + _tile("Facts", _n(row.get("facts_confirmed")),
                    f"{_n(drafts)} draft(s) awaiting your word · "
                    f"{_n(row.get('facts_retired'))} retired · "
                    f"{_n(row.get('fact_kinds'))} kinds")
            + _tile("Skills proven", f"{_n(evidenced)} of {_n(live)}",
                    f"{share} · "
                    f"{_n(outside)} evidenced outside paid work")
            + _tile("A CV cannot claim", _n(missing),
                    "recorded skills with no confirmed fact behind them"
                    if missing else "every recorded skill is evidenced")
            + "</div>")
    heading = ("<section><h2>What the system understands about you</h2>"
               "<p class='meta'>Re-read from your facts every time this page "
               "loads — nothing here is a stored opinion.</p>")
    return heading + "".join(cards) + "</section>"


def _health_status(row: dict) -> str:
    status = row.get("feed_status")
    if status == "error":
        return "<span class='st-bad'>&#10007; error</span>"
    if status == "empty":
        return "<span class='st-quiet'>&#9675; empty</span>"
    if status == "ok":
        return "<span class='st-ok'>&#10003; ok</span>"
    return "<span class='st-quiet'>&#8212; no board yet</span>"


def _board_status(row: dict) -> str:
    outcome = row.get("probe_outcome")
    if outcome == "board_found":
        return "<span class='st-ok'>&#10003; board_found</span>"
    if outcome:
        return f"<span class='st-quiet'>{_e(outcome)}</span>"
    return "<span class='st-quiet'>&#8212; not knocked yet</span>"


def _sponsor_name(row: dict) -> str:
    name = _e(row.get("organisation_name"))
    url = row.get("careers_url")
    return f"<a href='{_e(url)}' rel='noopener'>{name}</a>" if url else name


def _sponsor_table(rows: list[dict], empty_text: str) -> str:
    if not rows:
        return f"<p class='empty'>{empty_text}</p>"
    cells = "".join(
        "<tr>"
        f"<td>{_sponsor_name(r)}</td>"
        f"<td>{_e(r.get('town_city'))}</td>"
        f"<td>{_e(' · '.join(r.get('industry_descriptions') or []))}</td>"
        f"<td>{_board_status(r)}</td>"
        f"<td>{_n(r.get('local_jobs_seen'))}</td>"
        "</tr>" for r in rows)
    return ("<table class='watch'><thead><tr><th>Sponsor</th><th>Town</th>"
            "<th>Industry (official)</th><th>Board</th><th>Jobs seen</th>"
            "</tr></thead>"
            f"<tbody>{cells}</tbody></table>")


def _filter_form(qs: str, industry: str, town: str) -> str:
    """The zero-JS filter: a GET form that re-carries every existing query
    param (the token included) as hidden inputs, pinned to the sponsors tab."""
    hidden = []
    for pair in qs.lstrip("/?").rstrip("&").split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k not in ("tab", "page", "industry", "town") and v:
                hidden.append(f"<input type='hidden' "
                              f"name='{escape(k, quote=True)}' "
                              f"value='{escape(v, quote=True)}'>")
    return ("<form class='filter' method='get' action='/'>"
            + "".join(hidden) +
            "<input type='hidden' name='tab' value='sponsors'>"
            "<input name='industry' placeholder='industry words, e.g. care'"
            f" value='{escape(industry or '', quote=True)}'>"
            "<input name='town' placeholder='town'"
            f" value='{escape(town or '', quote=True)}'>"
            "<button>Filter</button></form>")


def _company_watch(rows: list[dict], empty_text: str) -> str:
    if not rows:
        return f"<p class='empty'>{empty_text}</p>"
    cells = "".join(
        "<tr>"
        f"<td>{_e(r.get('company_name'))}</td>"
        f"<td>{_health_status(r)}</td>"
        f"<td>{_e(r.get('ats_type')) if r.get('has_board') else '—'}</td>"
        f"<td>{_n(r.get('open_roles'))}</td>"
        f"<td>{_n(r.get('applied_roles'))}</td>"
        f"<td>{_e(r.get('last_fetched_at'))}</td>"
        "</tr>" for r in rows)
    return ("<table class='watch'><thead><tr><th>Company</th>"
            "<th>Feed</th><th>Board</th><th>Open</th><th>Applied</th>"
            "<th>Last fetched</th></tr></thead>"
            f"<tbody>{cells}</tbody></table>")


def _lane_section(tab: str, today: list[dict], health: list[dict],
                  sponsors: list[dict], s: dict, page: int, page_size: int,
                  qs: str, industry: str, town: str) -> str:
    key, label, count_key, empty_text = next(t for t in TABS if t[0] == tab)
    total = s.get(count_key)
    extra = ""
    if tab == "companies":
        body = _company_watch(health, empty_text)
    elif tab == "sponsors":
        body = (_filter_form(qs, industry, town)
                + _sponsor_table(sponsors, empty_text))
        # the FILTERED total rides on the rows; pager links keep the filters
        total = sponsors[0].get("total_rows") if sponsors else 0
        extra = (f"&industry={quote_plus(industry or '')}"
                 f"&town={quote_plus(town or '')}")
    else:
        rows = _lane_rows(today, tab)
        body = ("".join(_listing_row(r) for r in rows) if rows
                else f"<p class='empty'>{empty_text}</p>")
    pager = _pager(total, page, tab, qs, page_size, extra)
    return (f"<section><h2>{label} <small>({_n(total)})</small></h2>"
            f"{body}{pager}</section>")


def render_page(today: list[dict], scorecard: dict, health: list[dict],
                sponsors: list[dict] | None = None, *,
                mirror: list[dict] | None = None,
                generated_at: str = "", tab: str = "ready", page: int = 1,
                page_size: int = PAGE_SIZE, qs: str = "?",
                industry: str = "", town: str = "") -> str:
    """The whole page from the four views' rows. Pure; no DB, no clock."""
    s = scorecard or {}
    tab = tab if tab in TAB_KEYS else "ready"
    new_today = s.get("new_today") or 0
    new_chip = (f" · {_n(new_today)} new today" if new_today else "")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta http-equiv='refresh' content='300'>"
        "<title>Goal A — Today</title>"
        f"<style>{CSS}</style></head><body><main>"
        "<header><h1>Goal A — Today</h1>"
        f"<span class='meta'>generated {_e(generated_at)} · refreshes itself"
        "</span></header>"
        f"<p class='apps'>Applications: <b>{_n(s.get('applications_total'))}"
        f"</b> total · {_n(s.get('applications_today'))} today{new_chip}</p>"
        + _scorecard_tiles(s)
        + _mirror_section(mirror or [])
        + _tabs_bar(s, tab, qs)
        + _lane_section(tab, today, health, sponsors or [], s, page,
                        page_size, qs, industry, town)
        + "<footer>read-only · local · token-protected · Goal A engine"
          "</footer></main></body></html>")
