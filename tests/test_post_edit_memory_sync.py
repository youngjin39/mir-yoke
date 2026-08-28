from __future__ import annotations

import json
from pathlib import Path

from scripts import post_edit_memory_sync


def test_relevant_paths_extracts_durable_edits_and_excludes_projections(tmp_path: Path) -> None:
    payload = {
        "tool_input": {
            "patch": """*** Begin Patch
*** Update File: docs/decision.md
*** Update File: tasks/lessons.md
*** Update File: src/app.py
*** End Patch
"""
        }
    }

    assert post_edit_memory_sync.relevant_paths(payload, tmp_path) == ("docs/decision.md",)


def test_relevant_paths_extracts_current_codex_apply_patch_command(tmp_path: Path) -> None:
    payload = {
        "tool_name": "apply_patch",
        "tool_input": {
            "command": """*** Begin Patch
*** Update File: docs/current-decision.md
*** Update File: src/app.py
*** End Patch
"""
        },
    }

    assert post_edit_memory_sync.relevant_paths(payload, tmp_path) == (
        "docs/current-decision.md",
    )


def test_main_is_quiet_for_non_memory_edit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps({
        "tool_input": {"file_path": "src/app.py"}
    })))

    assert post_edit_memory_sync.main([str(tmp_path)]) == 0


def test_main_reports_unready_memory_for_durable_edit(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps({
        "tool_input": {"file_path": "docs/decision.md"}
    })))

    assert post_edit_memory_sync.main([str(tmp_path)]) == 1
    assert "bootstrap memory is not ready" in capsys.readouterr().err
