from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / ".claude" / "hooks" / "sub-agent-policy-gate.sh"
AGENT_CALL = json.dumps({"tool_name": "Agent", "tool_input": {"subagent_type": "quality-agent"}})


def _write(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _run_gate(project: Path, env_policy: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(project)}
    if env_policy is not None:
        env["MIR_SUB_AGENT_POLICY"] = str(env_policy)
    return subprocess.run(
        ["bash", str(GATE)],
        input=AGENT_CALL,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_gate_reads_the_deployed_lock_mode_before_the_env_policy(tmp_path: Path) -> None:
    _write(tmp_path / "config" / "sub-agent-policy.json", {"per_project": {}})
    lock = tmp_path / "config" / "model-routing.lock.json"
    overlay = _write(tmp_path / "overlay.json", {"mode": "force_codex"})

    _write(lock, {"policy": {"delegation": {"mode": "user_command_priority"}}})
    assert _run_gate(tmp_path, overlay).returncode == 0

    _write(lock, {"policy": {"delegation": {"mode": "force_codex"}}})
    blocked = _run_gate(tmp_path)
    assert blocked.returncode == 2
    assert "config/model-routing.lock.json" in blocked.stderr
    assert "edit config/sub-agent-policy.json" not in blocked.stderr
