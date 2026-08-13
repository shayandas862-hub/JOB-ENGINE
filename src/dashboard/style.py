"""The Today page's stylesheet — one inline sheet, Railway DNA tokens.

Deep navy ground, hairline-bordered surfaces, violet accent, mint for
ready/ok, 8px rhythm, Inter/system type. No external assets, no scripts;
the page stays self-contained by construction.
"""

CSS = """
:root { --bg:#0B0D0F; --surface:#16181F; --border:rgba(255,255,255,0.06);
  --border-lift:rgba(255,255,255,0.12); --text:#E8E8F0; --muted:#8B8E9E;
  --accent:#A78BFA; --ok:#34D399; --bad:#F87171; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font:400 0.8125rem/1.5
  Inter, system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width:1040px; margin:0 auto; padding:2rem 1.5rem 4rem; }
header { display:flex; justify-content:space-between; align-items:baseline;
  gap:1rem; flex-wrap:wrap; margin-bottom:1rem; }
h1 { font-size:1.125rem; font-weight:600; }
.meta { color:var(--muted); font-size:0.75rem; }
.apps { font-size:0.9375rem; margin-bottom:1.5rem; }
.apps b { color:var(--accent); font-size:1.25rem; font-weight:600; }
h2 { font-size:0.9375rem; font-weight:600; margin:1.5rem 0 0.75rem; }
h2 small { color:var(--muted); font-weight:400; }

nav.tabs { display:flex; gap:1.25rem; border-bottom:1px solid var(--border);
  margin:1.5rem 0 1rem; flex-wrap:wrap; }
nav.tabs a { color:var(--muted); text-decoration:none; font-weight:500;
  padding:0.5rem 0.125rem; border-bottom:2px solid transparent; }
nav.tabs a:hover { color:var(--text); }
nav.tabs a[aria-current='page'] { color:var(--text);
  border-bottom-color:var(--accent); }
nav.tabs a:focus-visible { outline:2px solid var(--accent);
  outline-offset:2px; }

.row { background:var(--surface); border:1px solid var(--border);
  border-radius:8px; padding:1rem; margin-bottom:0.5rem; }
.row:hover { border-color:var(--border-lift); }
.row-head { display:flex; justify-content:space-between; gap:1rem;
  align-items:baseline; }
.row-head a { color:var(--text); font-weight:500; text-decoration:none; }
.row-head a:hover { color:var(--accent); }
.row-head a:focus-visible, a:focus-visible { outline:2px solid var(--accent);
  outline-offset:2px; }
.badge { font-size:0.75rem; white-space:nowrap; }
.badge.ready { color:var(--ok); }
.badge.needs { color:var(--accent); }
.row-sub { color:var(--muted); margin-top:0.25rem; }

.chips { display:flex; flex-wrap:wrap; gap:0.375rem; margin-top:0.625rem; }
.chip { border:1px solid var(--border); border-radius:6px;
  padding:0.125rem 0.5rem; font-size:0.75rem; color:var(--muted);
  white-space:nowrap; }
.chip.hi { color:var(--ok); border-color:rgba(52,211,153,0.25); }
.chip.mid { color:var(--accent); border-color:rgba(167,139,250,0.3); }
.chip.warn { color:var(--accent); border-color:rgba(167,139,250,0.3); }

.pager { display:flex; gap:1rem; align-items:baseline;
  justify-content:center; margin:1rem 0 0.5rem; color:var(--muted);
  font-size:0.8125rem; }
.pager a { color:var(--accent); text-decoration:none; }
.pager a:hover { text-decoration:underline; }
.pager a:focus-visible { outline:2px solid var(--accent);
  outline-offset:2px; }

.empty { color:var(--muted); padding:1rem; border:1px dashed var(--border);
  border-radius:8px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fill,
  minmax(220px, 1fr)); gap:0.5rem; }
.tile { background:var(--surface); border:1px solid var(--border);
  border-radius:8px; padding:1rem; }
.tile .k { color:var(--muted); font-size:0.75rem; }
.tile .v { font-size:0.9375rem; font-weight:600; margin-top:0.25rem; }
.tile .r { color:var(--muted); font-size:0.75rem; margin-top:0.25rem; }
.watch { width:100%; border-collapse:collapse; }
.watch td, .watch th { text-align:left; padding:0.5rem 0.75rem;
  border-bottom:1px solid var(--border); font-size:0.8125rem; }
.watch th { color:var(--muted); font-weight:500; font-size:0.75rem; }
.st-ok { color:var(--ok); } .st-bad { color:var(--bad); }
.st-quiet { color:var(--muted); }
footer { color:var(--muted); font-size:0.75rem; margin-top:3rem; }
"""
