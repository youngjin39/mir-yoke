from __future__ import annotations

import argparse
import datetime
from dataclasses import replace
from pathlib import Path

from tools.tdd_archive.compactor import (
    apply_compaction,
    classify_changes,
    collect_pinned_ids,
    dry_run,
    load_tdd,
)

_TDD_GUARD_NOTE = (
    "Note: re-editing a file whose changes[] entry was archived triggers a TDD-guard "
    "block; resolution = create a new TDD entry."
)


def build_parser(default_year: str | None = None) -> argparse.ArgumentParser:
    year = default_year or str(datetime.date.today().year)
    parser = argparse.ArgumentParser(
        description="Archive completed changes[] entries from tasks/tdd.json.",
        epilog=_TDD_GUARD_NOTE,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write archive files and compact tdd",
    )
    parser.add_argument("--tdd", default="tasks/tdd.json", help="path to tdd.json")
    parser.add_argument(
        "--archive-dir",
        default="tasks/archive",
        help="archive output directory",
    )
    parser.add_argument(
        "--year",
        default=year,
        help="fallback YYYY for entries without a detectable year",
    )
    parser.add_argument(
        "--phase",
        default="tasks/phase.json",
        help="path to phase.json for pinned tdd_links (absent file = no pinning)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tdd_path = Path(args.tdd)
    archive_dir = Path(args.archive_dir)
    pinned_ids = collect_pinned_ids(Path(args.phase))

    result = classify_changes(load_tdd(tdd_path), pinned_ids=pinned_ids)
    result = replace(
        result,
        fallback_year=args.year,
        archive_path=archive_dir / f"tdd-archive-{args.year}.json",
    )

    if args.apply:
        summary = apply_compaction(result, tdd_path, archive_dir, pinned_ids=pinned_ids)
        print(
            f"Archived {summary['archived']} entries. "
            f"Restored {summary['restored']} pinned entries. "
            f"Remaining: {summary['remaining']}."
        )
        return 0

    summary = dry_run(result, pinned_ids=pinned_ids)
    print(
        f"[DRY-RUN] Archivable: {summary['archivable']}, "
        f"Would keep: {summary['kept']}, "
        f"Pinned (kept from archive): {summary['pinned_kept']}"
    )
    by_year = summary["by_year"]
    if isinstance(by_year, dict):
        for year, count in by_year.items():
            print(f"{year}: {count}")
    return 0
