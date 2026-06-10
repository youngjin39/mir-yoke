from __future__ import annotations

import argparse
import datetime
from dataclasses import replace
from pathlib import Path

from tools.plan_archive.archiver import apply_archive, classify, dry_run, parse_sections


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Archive old DONE sections from tasks/plan.md.")
    parser.add_argument("--apply", action="store_true", help="write archive files and rebuild plan")
    parser.add_argument("--plan", default="tasks/plan.md", help="path to plan.md")
    parser.add_argument("--archive-dir", default="tasks/archive", help="archive output directory")
    parser.add_argument(
        "--month",
        default=None,
        help="fallback YYYY-MM for DONE headings without a date",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.month is None:

        args.month = datetime.date.today().strftime("%Y-%m")
    plan_path = Path(args.plan)
    archive_dir = Path(args.archive_dir)
    result = classify(parse_sections(plan_path.read_text(encoding="utf-8")))
    result = replace(
        result,
        plan_path=plan_path,
        archive_dir=archive_dir,
        fallback_month=args.month,
    )

    if args.apply:
        summary = apply_archive(result)
        print(f"Archived {summary['archived']} sections.")
        print(f"Tombstones written: {summary['tombstones_written']}.")
        return 0

    summary = dry_run(result, fallback_month=args.month)
    print(f"[DRY-RUN] Archivable sections: {summary['archivable']}")
    by_month = summary["by_month"]
    if isinstance(by_month, dict):
        for month, count in by_month.items():
            print(f"{month}: {count}")
    return 0
