"""Render the public status page — one self-contained HTML document.

Two rules shape every line here. (1) The page renders a FIXED set of keys, so
a view that widened by accident still cannot print something new to the world.
(2) No naked numbers (house rule 5): every figure carries what it counts, and
the honest gaps are stated rather than hidden — a status page that can only
look green is worth nothing.

Self-contained: inline CSS, no scripts, no external assets. It is served to
strangers, so it must not fetch anything from anywhere.
"""
from __future__ import annotations

from html import escape

# (key, label, unit) — the ONLY figures that ever reach the page.
COVERAGE = [
    ("register_rows", "sponsor licences on the register", ""),
    ("census_organisations", "organisations in the census", ""),
    ("census_boards", "job boards found", ""),
    ("ads_collected", "job adverts collected", ""),
    ("listings_tracked", "listings tracked", ""),
    ("listings_open", "listings currently open", ""),
    ("companies_tracked", "companies tracked", ""),
    ("companies_with_boards", "tracked companies with a live board", ""),
]

_CSS = """
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{margin:0;font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',
Roboto,Helvetica,Arial,sans-serif;background:#0e1116;color:#e6edf3}
main{max-width:60rem;margin:0 auto;padding:2.5rem 1.25rem 4rem}
h1{font-size:1.6rem;margin:0 0 .25rem}
.sub{color:#8b949e;margin:0 0 2rem;font-size:.95rem}
.banner{border-radius:10px;padding:1rem 1.25rem;margin:0 0 2rem;
border:1px solid #30363d;background:#161b22}
.banner.ok{border-color:#238636}
.banner.bad{border-color:#b62324}
.banner b{font-size:1.15rem}
h2{font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;
color:#8b949e;margin:2rem 0 .75rem;font-weight:600}
.grid{display:grid;gap:.75rem;
grid-template-columns:repeat(auto-fit,minmax(13rem,1fr))}
.tile{border:1px solid #30363d;border-radius:10px;padding:.9rem 1rem;
background:#161b22}
.n{font-size:1.5rem;font-weight:650;letter-spacing:-.02em}
.l{color:#8b949e;font-size:.85rem;margin-top:.15rem}
table{border-collapse:collapse;width:100%;font-size:.92rem}
td{border-bottom:1px solid #21262d;padding:.45rem .5rem}
td.s{color:#8b949e;text-align:right;width:6rem}
.tick{color:#3fb950;width:1.5rem}
.cross{color:#f85149;width:1.5rem}
footer{color:#8b949e;font-size:.85rem;margin-top:2.5rem;
border-top:1px solid #21262d;padding-top:1rem}
@media(prefers-color-scheme:light){
body{background:#fff;color:#1f2328}
.banner,.tile{background:#f6f8fa}
.sub,.l,td.s,footer,h2{color:#59636e}
td{border-bottom-color:#d1d9e0}}
"""


def _num(value) -> str:
    """Thousands-separated, or an em dash when the figure is genuinely absent."""
    if value is None or value == "":
        return "—"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return escape(str(value))


def _age(days) -> str:
    if days is None:
        return "unknown"
    days = int(days)
    return "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} ago"


def _banner(row: dict) -> str:
    """The one question a stranger actually has: is this thing alive?"""
    last = row.get("last_run_at")
    if not last:
        return ("<div class='banner'><b>No run recorded yet.</b>"
                "<div class='l'>The daily pipeline has never finished a run.</div>"
                "</div>")
    status = str(row.get("last_run_status") or "unknown")
    ok = status.lower() == "ok"
    done, total = row.get("last_run_stages_ok"), row.get("last_run_stages")
    secs = row.get("last_run_seconds")
    detail = f"{_num(done)} of {_num(total)} stages"
    if secs:
        detail += f" in {int(secs) // 60}m {int(secs) % 60}s"
    return (f"<div class='banner {'ok' if ok else 'bad'}'>"
            f"<b>Last run: {escape(status)}</b>"
            f"<div class='l'>{detail} &middot; finished "
            f"{escape(str(last)[:16])} UTC</div></div>")


def _tiles(row: dict) -> str:
    cells = "".join(
        f"<div class='tile'><div class='n'>{_num(row.get(key))}</div>"
        f"<div class='l'>{escape(label)}</div></div>"
        for key, label, _unit in COVERAGE)
    return f"<div class='grid'>{cells}</div>"


def _stages(stages: list[dict]) -> str:
    if not stages:
        return "<p class='l'>No stage detail for the last run.</p>"
    rows = "".join(
        "<tr>"
        f"<td class='{'tick' if s.get('ok') else 'cross'}'>"
        f"{'&check;' if s.get('ok') else '&times;'}</td>"
        f"<td>{escape(str(s.get('stage') or '?'))}</td>"
        f"<td class='s'>{'' if s.get('ok') else 'failed '}"
        f"{escape(str(s.get('duration_s') or 0))}s</td></tr>"
        for s in stages)
    return f"<table>{rows}</table>"


def render_status(row: dict, stages: list[dict], *, generated_at: str) -> str:
    """The whole page. Renders only known keys — never 'whatever the row holds'."""
    row = row or {}
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Goal A Engine — status</title>"
        f"<style>{_CSS}</style></head><body><main>"
        "<h1>Goal A Engine</h1>"
        "<p class='sub'>A sponsor-aware UK job-search engine. It verifies which "
        "employers can legally sponsor a visa, tracks their jobs nightly, and "
        "matches them with receipts. This page is generated from the live "
        "database and shows machine health only &mdash; no personal data.</p>"
        f"{_banner(row)}"
        "<h2>Nightly run &mdash; every stage</h2>"
        f"{_stages(stages)}"
        "<h2>What it covers</h2>"
        f"{_tiles(row)}"
        "<h2>Freshness</h2>"
        "<div class='grid'>"
        f"<div class='tile'><div class='n'>{_age(row.get('register_age_days'))}</div>"
        "<div class='l'>sponsor register last refreshed</div></div>"
        f"<div class='tile'><div class='n'>{_num(row.get('runs_completed'))}</div>"
        "<div class='l'>pipeline runs completed</div></div>"
        "</div>"
        f"<footer>Generated {escape(generated_at)} &middot; "
        "read-only aggregates from curated views &middot; "
        "the engine never applies to a job on anyone&rsquo;s behalf"
        "</footer></main></body></html>")
