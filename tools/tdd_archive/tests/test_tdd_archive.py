from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from tools.tdd_archive.compactor import (
    apply_compaction,
    classify_changes,
    collect_pinned_ids,
    dry_run,
    load_tdd,
)


def _entry(
    index: int,
    status: str = "pass",
    entry_id: str | None = None,
) -> dict[str, object]:
    return {
        "id": entry_id or f"entry-{index}-2026-06-10",
        "target": f"tools/example_{index}.py",
        "categories": {
            "unit": {"status": status},
            "integration": {"status": "not_applicable"},
            "architecture": {"status": "covered_existing"},
        },
    }


def _data(changes: list[dict[str, object]]) -> dict[str, object]:
    return {
        "version": 1,
        "history": [{"event": "created"}],
        "changes": changes,
        "keyed-slug-2026-06-10": {"target": "tools/kept.py"},
    }


def _write_tdd(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_classify_all_terminal_statuses_are_archivable():
    result = classify_changes(_data([_entry(0)]), recency_keep=0)

    assert result.archivable_count == 1
    assert result.kept_count == 0
    assert result.entries_to_archive == [_entry(0)]


def test_classify_non_archivable_status_stays_kept():
    entry = _entry(0, status="planned")
    result = classify_changes(_data([entry]), recency_keep=0)

    assert result.archivable_count == 0
    assert result.kept_count == 1
    assert result.entries_to_keep == [entry]


def test_last_50_entries_are_always_kept():
    changes = [
        _entry(index, entry_id=f"entry-{index}-2026-06-10")
        for index in range(60)
    ]

    result = classify_changes(_data(changes))

    assert result.archivable_count == 10
    assert result.entries_to_archive == changes[:10]
    assert result.entries_to_keep == changes[10:]


def test_exactly_50_entries_archive_none():
    changes = [
        _entry(index, entry_id=f"entry-{index}-2026-06-10")
        for index in range(50)
    ]

    result = classify_changes(_data(changes))

    assert result.archivable_count == 0
    assert result.kept_count == 50


def test_51_entries_archives_first_when_archivable():
    changes = [
        _entry(index, entry_id=f"entry-{index}-2026-06-10")
        for index in range(51)
    ]

    result = classify_changes(_data(changes))

    assert result.archivable_count == 1
    assert result.entries_to_archive == [changes[0]]
    assert result.kept_count == 50


def test_51_entries_keeps_first_when_planned():
    changes = [_entry(0, status="planned", entry_id="entry-0-2026-06-10")]
    changes.extend(
        _entry(index, entry_id=f"entry-{index}-2026-06-10")
        for index in range(1, 51)
    )

    result = classify_changes(_data(changes))

    assert result.archivable_count == 0
    assert result.entries_to_keep == changes


def test_dry_run_counts_and_year_breakdown():
    changes = [
        _entry(0, entry_id="alpha-2024-12-31"),
        _entry(1, entry_id="beta-2026-06-10"),
        _entry(2, entry_id="gamma-2026-extra-2025"),
    ]
    result = classify_changes(_data(changes), recency_keep=0)

    summary = dry_run(result)

    assert summary["archivable"] == 3
    assert summary["kept"] == 0
    assert summary["by_year"] == {"2024": 1, "2025": 1, "2026": 1}


def test_apply_compaction_creates_archive_file(tmp_path):
    tdd_path = tmp_path / "tdd.json"
    archive_dir = tmp_path / "archive"
    _write_tdd(tdd_path, _data([_entry(0, entry_id="alpha-2026-06-10")]))

    result = classify_changes(load_tdd(tdd_path), recency_keep=0)
    summary = apply_compaction(result, tdd_path, archive_dir)

    archive_data = json.loads(
        (archive_dir / "tdd-archive-2026.json").read_text(encoding="utf-8")
    )
    assert summary["archived"] == 1
    assert summary["remaining"] == 0
    assert summary["restored"] == 0
    assert archive_data == {
        "version": 1,
        "changes": [_entry(0, entry_id="alpha-2026-06-10")],
    }


def test_apply_compaction_is_idempotent(tmp_path):
    tdd_path = tmp_path / "tdd.json"
    archive_dir = tmp_path / "archive"
    _write_tdd(tdd_path, _data([_entry(0, entry_id="alpha-2026-06-10")]))

    first = apply_compaction(
        classify_changes(load_tdd(tdd_path), recency_keep=0),
        tdd_path,
        archive_dir,
    )
    second = apply_compaction(
        classify_changes(load_tdd(tdd_path), recency_keep=0),
        tdd_path,
        archive_dir,
    )

    archive_data = json.loads(
        (archive_dir / "tdd-archive-2026.json").read_text(encoding="utf-8")
    )
    assert first["archived"] == 1
    assert first["remaining"] == 0
    assert first["restored"] == 0
    assert second["archived"] == 0
    assert second["remaining"] == 0
    assert second["restored"] == 0
    assert (
        archive_data["changes"].count(_entry(0, entry_id="alpha-2026-06-10"))
        == 1
    )


def test_apply_compaction_preserves_keyed_entries_version_and_history(tmp_path):
    tdd_path = tmp_path / "tdd.json"
    archive_dir = tmp_path / "archive"
    data = _data([_entry(0, entry_id="alpha-2026-06-10")])
    _write_tdd(tdd_path, data)

    apply_compaction(
        classify_changes(load_tdd(tdd_path), recency_keep=0),
        tdd_path,
        archive_dir,
    )

    compacted = json.loads(tdd_path.read_text(encoding="utf-8"))
    assert compacted["version"] == data["version"]
    assert compacted["history"] == data["history"]
    assert compacted["keyed-slug-2026-06-10"] == data["keyed-slug-2026-06-10"]
    assert compacted["changes"] == []


def test_year_extraction_uses_last_year_token():
    result = classify_changes(
        _data([_entry(0, entry_id="some-slug-2024-rechecked-2026-06-10")]),
        recency_keep=0,
    )

    assert dry_run(result)["by_year"] == {"2026": 1}


def test_fallback_year_used_when_id_has_no_year():
    result = classify_changes(
        _data([_entry(0, entry_id="no-year-entry")]),
        recency_keep=0,
    )
    result = replace(result, fallback_year="2030")

    assert dry_run(result)["by_year"] == {"2030": 1}


# --- New tests: pinned-id protection ---


def test_pinned_entry_not_archived(tmp_path):
    """A pinned entry with all-pass statuses must not be archived."""
    phase_path = tmp_path / "phase.json"
    phase_path.write_text(
        json.dumps({"phases": [{"id": "P1", "tdd_links": ["pinned-entry-2026"]}]}),
        encoding="utf-8",
    )
    pinned = collect_pinned_ids(phase_path)
    entry = _entry(0, entry_id="pinned-entry-2026")
    data = _data([entry])

    result = classify_changes(data, recency_keep=0, pinned_ids=pinned)

    assert result.archivable_count == 0
    assert result.kept_count == 1
    assert result.entries_to_keep == [entry]


def test_pinned_entry_in_archive_gets_restored(tmp_path):
    """A pinned entry sitting in archive must be moved back to live tdd on apply."""
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    pinned_entry = _entry(0, entry_id="pinned-2026")
    archive_file = archive_dir / "tdd-archive-2026.json"
    archive_file.write_text(
        json.dumps({"version": 1, "changes": [pinned_entry]}) + "\n",
        encoding="utf-8",
    )

    tdd_path = tmp_path / "tdd.json"
    _write_tdd(tdd_path, _data([]))  # entry already archived

    phase_path = tmp_path / "phase.json"
    phase_path.write_text(
        json.dumps({"phases": [{"id": "P1", "tdd_links": ["pinned-2026"]}]}),
        encoding="utf-8",
    )
    pinned_ids: frozenset[str] = collect_pinned_ids(phase_path)

    result = classify_changes(load_tdd(tdd_path), recency_keep=0, pinned_ids=pinned_ids)
    summary = apply_compaction(result, tdd_path, archive_dir, pinned_ids=pinned_ids)

    assert summary["restored"] == 1

    live = json.loads(tdd_path.read_text(encoding="utf-8"))
    live_ids = [e["id"] for e in live.get("changes", []) if isinstance(e, dict)]
    assert "pinned-2026" in live_ids

    archive_data = json.loads(archive_file.read_text(encoding="utf-8"))
    archive_ids = [e.get("id") for e in archive_data.get("changes", [])]
    assert "pinned-2026" not in archive_ids


def test_absent_phase_json_behaves_as_before(tmp_path):
    """collect_pinned_ids returns empty set for missing file; archiving unchanged."""
    pinned = collect_pinned_ids(tmp_path / "nonexistent.json")
    assert pinned == frozenset()

    entry = _entry(0, entry_id="regular-2026")
    result = classify_changes(_data([entry]), recency_keep=0, pinned_ids=pinned)

    assert result.archivable_count == 1
    assert result.kept_count == 0
