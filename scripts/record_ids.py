#!/usr/bin/env python3
"""Read-only extractor for the shared record naming convention.

One identity, two renderings:
    native  <KIND>-<CODE>-<NNN>   (in markdown; NNN zero-padded to 3)
    canonical <project>.<kind>.<seq>  (in databases; exactly two dots)

Rules this tool enforces on itself:
- It NEVER modifies a file. Existing identifiers stay byte-identical;
  canonical forms are computed at read time only.
- It parses this repo's own log shapes (decision-log `##` dated headings,
  progress-log dated bullet lines, plans/ numbered filenames) — it never
  reshapes a file to match another project's layout.
- It refuses its own output unless three checks pass:
    reassembly — parsed lines rejoin byte-identical to the original file
    ownership  — no content line after the first record is left unowned
    counts     — record and ID totals match independent regex measurement
- It never invents an ID from a title, a position, or a content hash.
  Allocation state lives in docs/id-registry.json (high-water marks).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

KIND_CODES = {
    "vision": "V",
    "decision": "D",
    "arch-decision": "AD",
    "progress": "PR",
    "plan": "P",
    "working-note": "WN",
    "addendum": "ADD",
    "document": "DOC",
    # Added 2026-08-10 on the founder's standing instruction: bugs get their
    # own log book (docs/bug-log.md), because "what broke, why, and can it
    # come back" is a question none of the other kinds answer.
    "bug": "B",
}
CODES_TO_KIND = {v: k for k, v in KIND_CODES.items()}

NATIVE_RE = re.compile(r"\b(V|D|AD|PR|P|WN|ADD|DOC|B)-([A-Z]{2,4})-([0-9]{1,6})\b")
DECISION_HEADING_RE = re.compile(r"^## ")
STRAY_H1_RE = re.compile(r"^# [^#]")
PROGRESS_RECORD_RE = re.compile(r"^- 20[0-9]{2}-[0-9]{2}")
PLAN_FILE_RE = re.compile(r"^([0-9]{4})-.+\.md$")
REGISTRY_REL = "docs/id-registry.json"


def format_native(kind: str, code: str, seq: int) -> str:
    return f"{KIND_CODES[kind]}-{code}-{seq:03d}"


def canonical_from_native(native: str, code_map: dict[str, str]) -> str | None:
    """code_map maps project code -> project slug (e.g. GAE -> goal-a-engine)."""
    m = NATIVE_RE.fullmatch(native)
    if not m:
        return None
    kind_code, code, num = m.groups()
    project = code_map.get(code)
    if project is None:
        return None
    return f"{project}.{CODES_TO_KIND[kind_code]}.{int(num)}"


@dataclass
class Record:
    kind: str
    title: str
    lines: list[str]
    native_ids: list[str] = field(default_factory=list)


@dataclass
class Parsed:
    path: str
    kind: str
    raw: str
    segments: list[tuple[str, list[str]]]
    records: list[Record]
    unowned: list[tuple[int, str]]


def _scan_ids(lines: list[str]) -> list[str]:
    return [m.group(0) for line in lines for m in NATIVE_RE.finditer(line)]


def parse_decision_log(path: Path) -> Parsed:
    """`##` dated headings delimit records; everything before the first is preamble."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    segments, records, unowned = [], [], []
    i = 0
    while i < len(lines) and not DECISION_HEADING_RE.match(lines[i]):
        i += 1
    if i:
        segments.append(("preamble", lines[:i]))
    while i < len(lines):
        start = i
        i += 1
        while i < len(lines) and not DECISION_HEADING_RE.match(lines[i]):
            if STRAY_H1_RE.match(lines[i]):
                unowned.append((i + 1, lines[i].rstrip("\n")))
            i += 1
        body = lines[start:i]
        records.append(Record("decision", body[0].rstrip("\n"), body, _scan_ids(body)))
        segments.append(("record", body))
    return Parsed(str(path), "decision", raw, segments, records, unowned)


def parse_progress_log(path: Path) -> Parsed:
    """Dated `- YYYY-MM-DD` bullets are records (indented lines continue them);
    everything before the first bullet is preamble; blanks separate; any other
    line after the first record is unowned and fails the ownership check."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    first = next((n for n, line in enumerate(lines)
                  if PROGRESS_RECORD_RE.match(line)), len(lines))
    segments, records, unowned = [], [], []
    if first:
        segments.append(("preamble", lines[:first]))
    i = first
    while i < len(lines):
        line = lines[i]
        if PROGRESS_RECORD_RE.match(line):
            start = i
            i += 1
            while i < len(lines) and lines[i].startswith(("  ", "\t")):
                i += 1
            body = lines[start:i]
            records.append(Record("progress", body[0].rstrip("\n"), body,
                                  _scan_ids(body)))
            segments.append(("record", body))
        elif line.strip() == "":
            segments.append(("blank", [line]))
            i += 1
        else:
            unowned.append((i + 1, line.rstrip("\n")))
            segments.append(("unowned", [line]))
            i += 1
    return Parsed(str(path), "progress", raw, segments, records, unowned)


def plan_inventory(plans_dir: Path) -> list[tuple[int, str]]:
    """Plans are one record per file; the 4-digit filename prefix is the sequence."""
    out = []
    for p in sorted(plans_dir.iterdir()):
        m = PLAN_FILE_RE.match(p.name)
        if m:
            out.append((int(m.group(1)), p.name))
    return out


def check_reassembly(parsed: Parsed) -> bool:
    rejoined = "".join(line for _, seg in parsed.segments for line in seg)
    return rejoined == parsed.raw


def check_ownership(parsed: Parsed) -> bool:
    return not parsed.unowned


def check_counts(parsed: Parsed) -> bool:
    pattern = (DECISION_HEADING_RE if parsed.kind == "decision"
               else PROGRESS_RECORD_RE)
    expected = sum(1 for line in parsed.raw.splitlines() if pattern.match(line))
    raw_ids = len(NATIVE_RE.findall(parsed.raw))
    owned_ids = len(_scan_ids([line for _, seg in parsed.segments for line in seg]))
    return expected == len(parsed.records) and raw_ids == owned_ids


# The two logs whose every line must belong to a record. docs/bug-log.md is
# deliberately NOT here: it has its own entry shape, and its own checks live
# in tests/test_bug_log.py (required fields, unique ids, registry high-water,
# public-safety). Absence from this tuple is a decision, not an oversight.
LOG_FILES = (
    ("docs/decision-log.md", parse_decision_log),
    ("docs/progress-log.md", parse_progress_log),
)


def run_checks(repo: Path) -> dict:
    files, unnumbered = [], {}
    for rel, parser in LOG_FILES:
        parsed = parser(repo / rel)
        files.append({
            "path": rel,
            "records": len(parsed.records),
            "reassembly": check_reassembly(parsed),
            "ownership": check_ownership(parsed),
            "counts": check_counts(parsed),
            "unowned": parsed.unowned,
            "native_ids": sorted({m.group(0)
                                  for m in NATIVE_RE.finditer(parsed.raw)}),
        })
        unnumbered[parsed.kind] = sum(1 for r in parsed.records
                                      if not r.native_ids)
    plans = plan_inventory(repo / "plans")
    return {
        "files": files,
        "plans": {"count": len(plans),
                  "high_water": max((seq for seq, _ in plans), default=0)},
        "unnumbered": unnumbered,
        "all_checks_pass": all(f["reassembly"] and f["ownership"] and f["counts"]
                               for f in files),
    }


def registry_violations(registry: dict, repo: Path) -> list[str]:
    """Allocated high-water marks must cover every number already in use."""
    problems = []
    if registry.get("kinds") != KIND_CODES:
        problems.append("kinds map drifted from the shared convention")
    if not re.fullmatch(r"[A-Z]{2,4}", registry.get("code", "")):
        problems.append("project code must be 2-4 uppercase letters")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", registry.get("project", "")):
        problems.append("project slug must be a lowercase slug")
    allocated = registry.get("allocated", {})
    plans = plan_inventory(repo / "plans")
    plan_max = max((seq for seq, _ in plans), default=0)
    if allocated.get("plan", 0) < plan_max:
        problems.append(f"allocated.plan {allocated.get('plan')} < "
                        f"highest plan file {plan_max}")
    for rel, parser in LOG_FILES:
        parsed = parser(repo / rel)
        for m in NATIVE_RE.finditer(parsed.raw):
            kind_code, code, num = m.groups()
            if code != registry.get("code"):
                continue
            kind = CODES_TO_KIND[kind_code]
            if allocated.get(kind, 0) < int(num):
                problems.append(f"allocated.{kind} < cited {m.group(0)} in {rel}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".", help="repo root (default: cwd)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()

    report = run_checks(repo)
    registry_path = repo / REGISTRY_REL
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        problems = registry_violations(registry, repo)
        report["registry"] = {"code": registry.get("code"),
                              "allocated": registry.get("allocated"),
                              "violations": problems}
    else:
        problems = [f"{REGISTRY_REL} missing"]
        report["registry"] = {"violations": problems}

    ok = report["all_checks_pass"] and not problems
    if args.as_json:
        print(json.dumps(report, indent=2))
        return 0 if ok else 1

    print(f"record-ids — {repo}")
    for f in report["files"]:
        verdicts = " · ".join(f"{name} {'PASS' if f[name] else 'FAIL'}"
                              for name in ("reassembly", "ownership", "counts"))
        print(f"  {f['path']}: {f['records']} records · {verdicts}"
              f" · unowned {len(f['unowned'])}"
              f" · native IDs cited: {f['native_ids'] or 'none'}")
    plans = report["plans"]
    print(f"  plans/: {plans['count']} numbered files · high-water "
          f"{plans['high_water']}")
    print(f"  unnumbered records (no ID invented): {report['unnumbered']}")
    print(f"  registry: {report['registry'].get('allocated', '(missing)')}"
          f" · violations: {problems or 'none'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
