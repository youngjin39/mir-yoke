"""Archive completed tasks/tdd.json changes[] entries.

Important: re-editing a file whose changes[] entry was archived triggers a TDD-guard
block; resolution = create a new TDD entry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ARCHIVABLE_STATUSES = {"pass", "not_applicable", "covered_existing"}
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


@dataclass(frozen=True)
class CompactionResult:
    archivable_count: int
    kept_count: int
    archive_path: Path
    fallback_year: str
    entries_to_archive: list[dict[str, Any]] = field(default_factory=list)
    entries_to_keep: list[dict[str, Any]] = field(default_factory=list)


def load_tdd(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("tdd.json must contain a JSON object")
    return data


def collect_pinned_ids(phase_path: Path) -> frozenset[str]:
    if not phase_path.exists():
        return frozenset()

    data = json.loads(phase_path.read_text(encoding="utf-8"))
    pinned_ids: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "tdd_links" and isinstance(nested, list):
                    pinned_ids.update(item for item in nested if isinstance(item, str))
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return frozenset(pinned_ids)


def collect_restore_entries(
    archive_dir: Path, pinned_ids: frozenset[str]
) -> list[dict[str, Any]]:
    """Return entries in archive files whose id is in pinned_ids.

    Scans all tdd-archive-*.json files in archive_dir sorted by filename.
    Returns entries in filename order, then position order within file.
    If archive_dir is absent, returns [].
    """
    if not archive_dir.exists():
        return []
    results: list[dict[str, Any]] = []
    for archive_path in sorted(archive_dir.glob("tdd-archive-*.json")):
        data = json.loads(archive_path.read_text(encoding="utf-8"))
        for entry in data.get("changes", []):
            if isinstance(entry, dict) and entry.get("id") in pinned_ids:
                results.append(entry)
    return results


def _category_statuses(entry: dict[str, Any]) -> list[str | None]:
    categories = entry.get("categories", {})
    if not isinstance(categories, dict):
        return []
    return [
        category.get("status") if isinstance(category, dict) else None
        for category in categories.values()
    ]


def _is_archivable(entry: dict[str, Any]) -> bool:
    statuses = _category_statuses(entry)
    return bool(statuses) and all(status in ARCHIVABLE_STATUSES for status in statuses)


def _current_year() -> str:
    import datetime

    return str(datetime.date.today().year)


def _year_for(entry: dict[str, Any], fallback_year: str) -> str:
    entry_id = entry.get("id", "")
    matches = _YEAR_RE.findall(str(entry_id))
    if matches:
        return matches[-1]
    return fallback_year


def classify_changes(
    data: dict[str, Any],
    recency_keep: int = 50,
    pinned_ids: frozenset[str] = frozenset(),
) -> CompactionResult:
    changes = data.get("changes", [])
    if not isinstance(changes, list):
        changes = []

    keep_count = max(recency_keep, 0)
    recency_threshold = max(len(changes) - keep_count, 0)
    entries_to_archive: list[dict[str, Any]] = []
    entries_to_keep: list[dict[str, Any]] = []

    for index, entry in enumerate(changes):
        if not isinstance(entry, dict):
            entries_to_keep.append(entry)
            continue
        if index >= recency_threshold:
            entries_to_keep.append(entry)
            continue
        if entry.get("id") in pinned_ids:
            entries_to_keep.append(entry)
            continue
        if _is_archivable(entry):
            entries_to_archive.append(entry)
        else:
            entries_to_keep.append(entry)

    fallback_year = _current_year()
    return CompactionResult(
        archivable_count=len(entries_to_archive),
        kept_count=len(entries_to_keep),
        archive_path=Path(f"tasks/archive/tdd-archive-{fallback_year}.json"),
        fallback_year=fallback_year,
        entries_to_archive=entries_to_archive,
        entries_to_keep=entries_to_keep,
    )


def dry_run(
    result: CompactionResult, pinned_ids: frozenset[str] = frozenset()
) -> dict[str, object]:
    by_year: dict[str, int] = {}
    for entry in result.entries_to_archive:
        year = _year_for(entry, result.fallback_year)
        by_year[year] = by_year.get(year, 0) + 1
    pinned_kept = sum(
        1
        for e in result.entries_to_keep
        if isinstance(e, dict) and e.get("id") in pinned_ids
    )
    return {
        "archivable": result.archivable_count,
        "kept": result.kept_count,
        "pinned_kept": pinned_kept,
        "by_year": dict(sorted(by_year.items())),
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_archive(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "changes": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    changes = data.get("changes", [])
    if not isinstance(changes, list):
        raise ValueError(f"{path} changes must be a JSON array")
    return data


def _append_archives(result: CompactionResult, archive_dir: Path) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in result.entries_to_archive:
        year = _year_for(entry, result.fallback_year)
        grouped.setdefault(year, []).append(entry)

    for year, entries in sorted(grouped.items()):
        archive_path = archive_dir / f"tdd-archive-{year}.json"
        archive_data = _load_archive(archive_path)
        archive_data.setdefault("version", 1)
        archive_data.setdefault("changes", [])
        archive_data["changes"].extend(entries)
        _write_json(archive_path, archive_data)


def apply_compaction(
    result: CompactionResult,
    tdd_path: Path,
    archive_dir: Path,
    pinned_ids: frozenset[str] = frozenset(),
) -> dict[str, int]:
    restored = 0

    if result.archivable_count > 0:
        _append_archives(result, archive_dir)
        data = load_tdd(tdd_path)
        data["changes"] = result.entries_to_keep
        _write_json(tdd_path, data)

    if pinned_ids:
        to_restore = collect_restore_entries(archive_dir, pinned_ids)
        if to_restore:
            restore_ids = {e["id"] for e in to_restore if isinstance(e, dict)}
            for archive_path in sorted(archive_dir.glob("tdd-archive-*.json")):
                archive_data = _load_archive(archive_path)
                original = archive_data.get("changes", [])
                filtered = [
                    e
                    for e in original
                    if not (isinstance(e, dict) and e.get("id") in restore_ids)
                ]
                if len(filtered) != len(original):
                    archive_data["changes"] = filtered
                    _write_json(archive_path, archive_data)

            live = load_tdd(tdd_path)
            live.setdefault("changes", [])
            live["changes"].extend(to_restore)
            _write_json(tdd_path, live)
            restored = len(to_restore)

    return {
        "archived": result.archivable_count,
        "remaining": result.kept_count + restored,
        "restored": restored,
    }
