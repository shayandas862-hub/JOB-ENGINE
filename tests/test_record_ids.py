"""Tests for scripts/record_ids.py — the read-only record-ID extractor.

The extractor parses the repo's OWN log shapes (decision-log ## headings,
progress-log dated bullets, plans/ numbered filenames) without modifying
anything, and must refuse its own output unless three checks pass:
reassembly (byte-identical rejoin), ownership (no content line outside a
record), counts (record totals match independent regex measurement).
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The Docker image carries scripts/ and tests/ but not docs/ or plans/ —
# the real-repo pins below only run where the logs actually exist.
_REPO_DOCS = all((ROOT / p).exists() for p in
                 ("docs/decision-log.md", "docs/progress-log.md",
                  "docs/id-registry.json", "plans"))
needs_repo_docs = pytest.mark.skipif(
    not _REPO_DOCS, reason="repo docs/plans not present (container image)")

_spec = importlib.util.spec_from_file_location(
    "record_ids", ROOT / "scripts" / "record_ids.py")
record_ids = importlib.util.module_from_spec(_spec)
sys.modules["record_ids"] = record_ids
_spec.loader.exec_module(record_ids)


DECISION_SAMPLE = (
    "# Decision Log — sample\n"
    "\n"
    "Preamble line describing the file. Newest first.\n"
    "\n"
    "---\n"
    "\n"
    "## 2026-08-03 — Newest entry\n"
    "\n"
    "- A bullet with detail.\n"
    "- Another bullet citing D-CL-109 in passing.\n"
    "\n"
    "## 2026-07-10 20:54 BST — Oldest entry\n"
    "\n"
    "Body prose over\n"
    "two lines.\n"
)

PROGRESS_SAMPLE = (
    "# Progress Log — sample\n"
    "\n"
    "One line per completed task. Format note.\n"
    "\n"
    "## ⚑ ATTENTION section — standing, not a log record\n"
    "\n"
    "- an attention bullet that is NOT a dated record\n"
    "\n"
    "---\n"
    "\n"
    "- 2026-08-03 — newest dated record line.\n"
    "\n"
    "- 2026-07-31 08:32 BST — second record.\n"
    "- 2026-07-10 20:54 BST — oldest record.\n"
)


def test_decision_log_reassembles_to_original_bytes(tmp_path):
    # Arrange
    f = tmp_path / "decision-log.md"
    f.write_text(DECISION_SAMPLE, encoding="utf-8")

    # Act
    parsed = record_ids.parse_decision_log(f)

    # Assert
    assert record_ids.check_reassembly(parsed) is True
    rejoined = "".join(line for _, seg in parsed.segments for line in seg)
    assert rejoined == DECISION_SAMPLE


def test_decision_log_counts_records_and_owns_every_line(tmp_path):
    # Arrange
    f = tmp_path / "decision-log.md"
    f.write_text(DECISION_SAMPLE, encoding="utf-8")

    # Act
    parsed = record_ids.parse_decision_log(f)

    # Assert
    assert len(parsed.records) == 2
    assert record_ids.check_ownership(parsed) is True
    assert record_ids.check_counts(parsed) is True
    assert parsed.records[0].title.startswith("## 2026-08-03")


def test_decision_log_finds_cited_native_ids_without_rewriting(tmp_path):
    # Arrange
    f = tmp_path / "decision-log.md"
    f.write_text(DECISION_SAMPLE, encoding="utf-8")

    # Act
    parsed = record_ids.parse_decision_log(f)

    # Assert — the citation is surfaced, the file is never touched
    assert parsed.records[0].native_ids == ["D-CL-109"]
    assert f.read_text(encoding="utf-8") == DECISION_SAMPLE


def test_progress_log_reassembles_with_preamble_and_blanks(tmp_path):
    # Arrange
    f = tmp_path / "progress-log.md"
    f.write_text(PROGRESS_SAMPLE, encoding="utf-8")

    # Act
    parsed = record_ids.parse_progress_log(f)

    # Assert
    assert record_ids.check_reassembly(parsed) is True
    assert len(parsed.records) == 3
    assert record_ids.check_ownership(parsed) is True
    assert record_ids.check_counts(parsed) is True


def test_progress_orphan_paragraph_is_flagged_unowned(tmp_path):
    # Arrange — a bare paragraph between records belongs to no record
    broken = PROGRESS_SAMPLE + "an orphan line that is not a record\n"
    f = tmp_path / "progress-log.md"
    f.write_text(broken, encoding="utf-8")

    # Act
    parsed = record_ids.parse_progress_log(f)

    # Assert — ownership fails loudly, but no byte is lost
    assert record_ids.check_ownership(parsed) is False
    assert len(parsed.unowned) == 1
    assert record_ids.check_reassembly(parsed) is True


def test_progress_indented_continuation_belongs_to_previous_record(tmp_path):
    # Arrange
    text = ("# T\n\n- 2026-08-01 — record one.\n"
            "  wrapped continuation line.\n"
            "- 2026-07-30 — record two.\n")
    f = tmp_path / "progress-log.md"
    f.write_text(text, encoding="utf-8")

    # Act
    parsed = record_ids.parse_progress_log(f)

    # Assert
    assert len(parsed.records) == 2
    assert len(parsed.records[0].lines) == 2
    assert record_ids.check_ownership(parsed) is True
    assert record_ids.check_reassembly(parsed) is True


def test_native_id_formatting_zero_pads_to_three():
    # Arrange / Act / Assert
    assert record_ids.format_native("decision", "GAE", 7) == "D-GAE-007"
    assert record_ids.format_native("vision", "GAE", 2) == "V-GAE-002"
    assert record_ids.format_native("progress", "GAE", 14) == "PR-GAE-014"
    assert record_ids.format_native("plan", "GAE", 1000) == "P-GAE-1000"


def test_canonical_computed_from_native_at_read_time():
    # Arrange
    code_map = {"CL": "calmline", "GAE": "goal-a-engine"}

    # Act / Assert — always exactly two dots, lowercase, unpadded seq
    assert (record_ids.canonical_from_native("D-CL-109", code_map)
            == "calmline.decision.109")
    assert (record_ids.canonical_from_native("V-CL-002", code_map)
            == "calmline.vision.2")
    assert (record_ids.canonical_from_native("PR-GAE-014", code_map)
            == "goal-a-engine.progress.14")
    assert record_ids.canonical_from_native("D-ZZ-001", code_map) is None
    assert record_ids.canonical_from_native("not an id", code_map) is None


def test_plan_inventory_reads_seq_from_filenames_ignoring_readme(tmp_path):
    # Arrange
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / "0002-second.md").write_text("x", encoding="utf-8")
    (plans / "0011-latest.md").write_text("x", encoding="utf-8")
    (plans / "README.md").write_text("x", encoding="utf-8")

    # Act
    inventory = record_ids.plan_inventory(plans)

    # Assert
    assert [seq for seq, _ in inventory] == [2, 11]


def test_unnumbered_records_get_no_invented_ids(tmp_path):
    # Arrange
    f = tmp_path / "progress-log.md"
    f.write_text(PROGRESS_SAMPLE, encoding="utf-8")

    # Act
    parsed = record_ids.parse_progress_log(f)

    # Assert — no ID is ever derived from position, title, or hash
    assert all(rec.native_ids == [] for rec in parsed.records)


@needs_repo_docs
def test_real_repo_logs_pass_all_three_checks():
    # Arrange / Act
    report = record_ids.run_checks(ROOT)

    # Assert — every file, every check
    for file_report in report["files"]:
        assert file_report["reassembly"] is True, file_report["path"]
        assert file_report["ownership"] is True, file_report["path"]
        assert file_report["counts"] is True, file_report["path"]
    assert report["all_checks_pass"] is True


@needs_repo_docs
def test_real_registry_high_water_covers_everything_seen_in_repo():
    # Arrange
    registry_path = ROOT / "docs" / "id-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    # Act
    violations = record_ids.registry_violations(registry, ROOT)

    # Assert — allocated marks are never below a number already in use
    assert violations == []


@needs_repo_docs
def test_cli_exits_zero_on_real_repo(capsys):
    # Arrange / Act
    exit_code = record_ids.main(["--repo", str(ROOT)])

    # Assert
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "reassembly" in out
