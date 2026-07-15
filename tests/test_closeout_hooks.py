"""Regression tests for the single canonical closeout state."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_session_end(project_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return subprocess.run(
        ["/bin/bash", str(ROOT / ".claude" / "hooks" / "session-end.sh")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_session_end_refreshes_only_the_canonical_handoff(tmp_path: Path) -> None:
    handoff_dir = tmp_path / "tasks" / "handoffs"
    handoff_dir.mkdir(parents=True)
    handoff = handoff_dir / "session-handoff-LATEST.md"
    handoff.write_text(
        "# Session Handoff — Current\n\n"
        "## Completed Work\n\n- Curated outcome.\n\n"
        "## Key Risks\n\n- Curated risk.\n",
        encoding="utf-8",
    )

    first = _run_session_end(tmp_path)
    second = _run_session_end(tmp_path)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    body = handoff.read_text(encoding="utf-8")
    assert "Curated outcome." in body
    assert "Curated risk." in body
    assert body.count("<!-- mir:runtime-snapshot:begin -->") == 1
    assert body.count("<!-- mir:runtime-snapshot:end -->") == 1
    assert sorted(path.name for path in handoff_dir.iterdir()) == [handoff.name]
    assert not list((tmp_path / "tasks").glob("sessions/session-*.md"))


def test_session_end_creates_the_compact_handoff_scaffold(tmp_path: Path) -> None:
    completed = _run_session_end(tmp_path)

    assert completed.returncode == 0, completed.stderr
    handoff = tmp_path / "tasks" / "handoffs" / "session-handoff-LATEST.md"
    body = handoff.read_text(encoding="utf-8")
    for heading in (
        "## Completed Work",
        "## Decisions",
        "## Unresolved Issues",
        "## Next Actions",
        "## Modified Files",
        "## Verification Results",
        "## Key Risks",
    ):
        assert heading in body


def test_claude_settings_wires_session_end_to_canonical_closeout() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for group in settings["hooks"]["SessionEnd"]
        for hook in group["hooks"]
    ]
    assert commands == [".claude/hooks/session-end.sh"]
