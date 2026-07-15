from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tools.plan_archive.archiver import (
    apply_archive,
    classify,
    dry_run,
    parse_sections,
)
from tools.plan_archive.cli import build_parser


def _done(index: int, month: str = "2026-01") -> str:
    return f"## Done {index} ({month}-{index + 1:02d}, DONE)\nbody {index}\n\n"


def _result_for(plan_path: Path, fallback_month: str = "2026-06"):
    result = classify(parse_sections(plan_path.read_text(encoding="utf-8")))
    return replace(
        result,
        plan_path=plan_path,
        archive_dir=plan_path.parent / "archive",
        fallback_month=fallback_month,
    )


def test_parse_sections_preamble_and_sections():
    text = "intro\n\n## Active\nactive body\n\n## Done (2026-04-10, DONE)\ndone body\n"

    sections = parse_sections(text)

    assert [section.heading for section in sections] == [
        "",
        "Active",
        "Done (2026-04-10, DONE)",
    ]
    assert sections[0].content == "intro\n\n"
    assert sections[1].content == "active body\n\n"
    assert sections[2].done_month == "2026-04"


def test_classify_done_active_and_kept():
    text = (
        "preamble\n\n"
        "## Active\nactive\n\n"
        + "".join(_done(index) for index in range(7))
    )

    result = classify(parse_sections(text))

    assert [section.heading for section in result.archivable] == [
        f"Done {index} (2026-01-{index + 1:02d}, DONE)" for index in range(4)
    ]
    assert [section.heading for section in result.kept_done] == [
        f"Done {index} (2026-01-{index + 1:02d}, DONE)" for index in range(4, 7)
    ]
    assert [section.heading for section in result.active_sections] == ["", "Active"]


def test_three_done_sections_are_all_kept():
    result = classify(parse_sections("".join(_done(index) for index in range(3))))

    assert result.archivable == []
    assert len(result.kept_done) == 3


def test_four_done_sections_archives_one():
    result = classify(parse_sections("".join(_done(index) for index in range(4))))

    assert [section.heading for section in result.archivable] == ["Done 0 (2026-01-01, DONE)"]
    assert len(result.kept_done) == 3


def test_zero_recency_archives_all_completed_sections():
    result = classify(
        parse_sections("".join(_done(index) for index in range(3))),
        recency_keep=0,
    )

    assert len(result.archivable) == 3
    assert result.kept_done == []


def test_cli_accepts_explicit_recency_keep():
    args = build_parser().parse_args(["--recency-keep", "0"])

    assert args.recency_keep == 0


def test_complete_heading_is_classified_as_completed():
    result = classify(parse_sections("## Current audit — COMPLETE\nbody\n"))

    assert [section.heading for section in result.kept_done] == [
        "Current audit — COMPLETE"
    ]


def test_dry_run_counts_by_month_and_fallback():
    text = (
        "## Done A (2026-01-01, DONE)\na\n\n"
        "## Done B (DONE)\nb\n\n"
        + "".join(_done(index, month="2026-03") for index in range(3))
    )
    result = classify(parse_sections(text))

    summary = dry_run(result, fallback_month="2026-09")

    assert summary == {
        "archivable": 2,
        "by_month": {
            "2026-01": 1,
            "2026-09": 1,
        },
    }


def test_apply_archive_is_idempotent(tmp_path):
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("".join(_done(index) for index in range(4)), encoding="utf-8")

    first = apply_archive(_result_for(plan_path))
    second = apply_archive(_result_for(plan_path))

    archive_text = (tmp_path / "archive" / "plan-archive-2026-01.md").read_text(
        encoding="utf-8"
    )
    assert first == {"archived": 1, "tombstones_written": 1}
    assert second == {"archived": 0, "tombstones_written": 1}
    assert archive_text.count("## Done 0 (2026-01-01, DONE)") == 1


def test_tombstone_cap_at_three(tmp_path):
    plan_path = tmp_path / "plan.md"
    old_tombstones = "".join(
        f"Archived to tasks/archive/plan-archive-2025-01.md: ## Old {index:02d}\n"
        for index in range(26)
    )
    plan_path.write_text(
        "".join(_done(index) for index in range(4)) + "\n" + old_tombstones,
        encoding="utf-8",
    )

    result = apply_archive(_result_for(plan_path))

    tombstones = [
        line
        for line in plan_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("Archived to ")
    ]
    assert result == {"archived": 1, "tombstones_written": 3}
    assert len(tombstones) == 3
    assert not any("Old 23" in line for line in tombstones)
    assert any("Old 24" in line for line in tombstones)
    assert tombstones[-1].endswith("## Done 0 (2026-01-01, DONE)")


def test_archive_file_content(tmp_path):
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("".join(_done(index) for index in range(4)), encoding="utf-8")

    apply_archive(_result_for(plan_path))

    archive_text = (tmp_path / "archive" / "plan-archive-2026-01.md").read_text(
        encoding="utf-8"
    )
    assert archive_text.startswith("# Plan Archive 2026-01\n\n")
    assert "## Done 0 (2026-01-01, DONE)\nbody 0\n" in archive_text


def test_done_month_extraction():
    sections = parse_sections(
        "## Done With Date (2026-05-12, DONE)\na\n"
        "## Done Without Date (DONE)\nb\n"
    )

    assert sections[0].done_month == "2026-05"
    assert sections[1].done_month is None


def test_fallback_month_for_no_date_section(tmp_path):
    plan_path = tmp_path / "plan.md"
    plan_path.write_text(
        "## Done Without Date (DONE)\nold\n\n"
        + "".join(_done(index, month="2026-07") for index in range(3)),
        encoding="utf-8",
    )

    result = _result_for(plan_path, fallback_month="2026-08")
    assert dry_run(result, fallback_month="2026-08")["by_month"] == {"2026-08": 1}

    apply_archive(result)

    archive_text = (tmp_path / "archive" / "plan-archive-2026-08.md").read_text(
        encoding="utf-8"
    )
    assert "## Done Without Date (DONE)\nold\n" in archive_text


def test_heading_closed_is_archivable():
    result = classify(parse_sections(
        "## Session X (2026-01-01, CLOSED)\nbody\n\n"
        + "".join(_done(index) for index in range(3))
    ))
    assert any(s.heading == "Session X (2026-01-01, CLOSED)" for s in result.archivable)


def test_elevation_closed_body_is_archivable():
    text = (
        "## Session Y\nelevation: CLOSED\nbody\n\n"
        + "".join(_done(index) for index in range(3))
    )
    result = classify(parse_sections(text))
    assert any(s.heading == "Session Y" for s in result.archivable)


def test_step_done_body_is_archivable():
    text = (
        "## Session Z\nStep 1: DONE\nbody\n\n"
        + "".join(_done(index) for index in range(3))
    )
    result = classify(parse_sections(text))
    assert any(s.heading == "Session Z" for s in result.archivable)


def test_active_in_body_is_hard_keep():
    text = (
        "## Session A\nelevation: ACTIVE\nbody\n\n"
        + "".join(_done(index) for index in range(4))
    )
    result = classify(parse_sections(text))
    headings = [s.heading for s in result.archivable] + [s.heading for s in result.kept_done]
    assert "Session A" not in headings


def test_pinned_tracker_policies_never_moves():
    text = (
        "## Pinned Tracker Policies (2026-01-01, DONE)\npolicy body\n\n"
        + "".join(_done(index) for index in range(4))
    )
    result = classify(parse_sections(text))
    headings = [s.heading for s in result.archivable] + [s.heading for s in result.kept_done]
    assert "Pinned Tracker Policies (2026-01-01, DONE)" not in headings


def test_unclassified_section_is_kept():
    result = classify(parse_sections("## Some Unclassified Work\njust notes\n"))
    assert result.archivable == []
    assert result.kept_done == []
    assert result.active_sections[0].heading == "Some Unclassified Work"
