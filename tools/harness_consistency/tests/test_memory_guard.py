from __future__ import annotations

import json
import runpy
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_shared_repo_check_disables_only_memory_rerender(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inspect the shared test's command without executing any live-root rule."""
    namespace = runpy.run_path(str(PROJECT_ROOT / "tests/test_harness_consistency.py"))
    original = (PROJECT_ROOT / "config/harness-consistency.json").read_bytes()
    expected = json.loads(original)
    for rule in expected["rules"]:
        if rule["name"] == "generated_marker_rerender":
            rule["enabled"] = False
    calls = []

    def inspect_command(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(command)
        assert "--manifest" in command, "live-root test would run R11 with the default manifest"
        path = Path(command[command.index("--manifest") + 1])
        assert path != PROJECT_ROOT / "config/harness-consistency.json"
        assert json.loads(path.read_text()) == expected
        assert kwargs["cwd"] == PROJECT_ROOT
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"overall": "pass", "summary": {"error": 0}}), "",
        )

    monkeypatch.setattr(subprocess, "run", inspect_command)
    check = namespace["test_harness_consistency_zero_error_on_current_repo"]
    check(tmp_path)
    assert len(calls) == 1
    assert (PROJECT_ROOT / "config/harness-consistency.json").read_bytes() == original
