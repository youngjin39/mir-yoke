"""Exercise both live hook routes without a Python contract validator."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_hook_executability import _isolated_guard, _run_pre_tool_use

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX hook cutover")


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    supplied = os.environ.get("W1_PROJECT_HOOKS_NATIVE")
    if supplied:
        return Path(supplied)
    target = Path(os.environ.get("CARGO_TARGET_DIR") or tmp_path_factory.mktemp("contract-target"))
    subprocess.run([
        "cargo", "build", "--offline", "--locked", "-j", "2", "--manifest-path",
        str(ROOT / "native/handoff-packet/Cargo.toml"), "--bin", "project-hooks",
    ], check=True, timeout=180, capture_output=True,
        env={**os.environ, "CARGO_TARGET_DIR": str(target)})
    return target / "debug/project-hooks"


@pytest.mark.parametrize("route", ["shell", "native"])
@pytest.mark.parametrize("mode", ["disabled", "log", "required"])
@pytest.mark.parametrize("contract", ["missing", "valid", "invalid"])
def test_live_contract_gate(native, tmp_path, route, mode, contract):
    script = _isolated_guard(tmp_path)
    installed = tmp_path / ".mir/bin/project-hooks"
    installed.parent.mkdir(parents=True)
    shutil.copy2(native, installed)
    marker = "PRIVATE_CONTRACT_INPUT_FIXTURE"
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "file.txt", "new_string": marker}}
    if contract != "missing":
        payload["tool_input"]["_mir_contract"] = {
            "idempotency_key": "key", "precondition": "ready", "dry_run": False,
            "side_effect_summary": marker if contract == "valid" else marker * 20,
        }
    flags = {"MIR_TOOL_CONTRACT_REQUIRED": "1" if mode == "required" else "0",
             "MIR_TOOL_CONTRACT_LOG": "1" if mode == "log" else "0"}
    # This prepares a synthetic bootstrap receipt and exercises the shell route.
    result = _run_pre_tool_use("", tmp_path, script=script, payload=payload, extra_env=flags)
    if route == "native":
        result = subprocess.run(
            [str(native), "pre-tool-use"], input=json.dumps(payload), text=True,
            capture_output=True, timeout=20, cwd=tmp_path,
            env={**os.environ, **flags, "CLAUDE_PROJECT_DIR": str(tmp_path)},
        )
    assert result.returncode == (2 if mode == "required" and contract != "valid" else 0)
    assert ("tool contract validation failed" in result.stderr) == (
        mode == "required" and contract != "valid")
    assert ("TC ADVISORY LOG" in result.stderr) == (mode == "log" and contract == "missing")
    assert marker not in result.stdout + result.stderr
    assert not (tmp_path / "tools/hooks").exists()


def test_shell_required_validator_unavailable_blocks(tmp_path):
    script = _isolated_guard(tmp_path)
    result = _run_pre_tool_use("echo safe", tmp_path, script=script,
                               extra_env={"MIR_TOOL_CONTRACT_REQUIRED": "1"})
    assert result.returncode == 2
    assert "required native tool contract validator missing" in result.stderr


@pytest.mark.parametrize("status", [64, 126, 127])
def test_shell_required_validator_outdated_blocks(tmp_path, status):
    script = _isolated_guard(tmp_path)
    binary = tmp_path / ".mir/bin/project-hooks"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        '#!/bin/bash\ncase "$1" in\n'
        '  --mir-warmup) exit 0 ;;\n'
        '  capabilities) echo mir-project-hooks-tool-contract-v1 ;;\n'
        f'  tool-contract) exit {status} ;;\nesac\n'
    )
    binary.chmod(0o755)
    result = _run_pre_tool_use("echo safe", tmp_path, script=script,
                               extra_env={"MIR_TOOL_CONTRACT_REQUIRED": "1"})
    assert result.returncode == 2
    assert "validator unavailable or outdated" in result.stderr
    assert "scripts/mir.sh project-hooks install" in result.stderr


@pytest.mark.parametrize(
    ("warmup_status", "capability"),
    [
        (0, ""),
        (0, "mir-project-hooks-tool-contract-v10"),
        (1, "mir-project-hooks-tool-contract-v1"),
    ],
)
def test_shell_required_validator_admission_blocks(tmp_path, warmup_status, capability):
    script = _isolated_guard(tmp_path)
    binary = tmp_path / ".mir/bin/project-hooks"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        '#!/bin/bash\ncase "$1" in\n'
        f'  --mir-warmup) exit {warmup_status} ;;\n'
        f'  capabilities) printf "%s" "{capability}" ;;\n'
        '  tool-contract) touch "$CLAUDE_PROJECT_DIR/validated" ;;\n'
        'esac\n'
    )
    binary.chmod(0o755)
    result = _run_pre_tool_use(
        "", tmp_path, script=script,
        payload={"tool_name": "Edit", "tool_input": {"file_path": "file.txt"}},
        extra_env={"MIR_TOOL_CONTRACT_REQUIRED": "1"},
    )
    assert result.returncode == 2, result.stderr
    assert "required native tool contract validator unavailable or outdated" in result.stderr
    assert "scripts/mir.sh project-hooks install --project-root ." in result.stderr
    assert not (tmp_path / "validated").exists()


@pytest.mark.parametrize("linked", ["binary", "bin", "placement"])
def test_shell_required_validator_linked_placement_blocks(tmp_path, linked):
    script = _isolated_guard(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    marker = outside / "invoked"
    real = outside / "project-hooks"
    real.write_text(f"#!/bin/bash\ntouch '{marker}'\nexit 0\n")
    real.chmod(0o755)
    mir = tmp_path / ".mir"
    if linked == "placement":
        mir.symlink_to(outside, target_is_directory=True)
        (outside / "bin").mkdir()
        shutil.copy2(real, outside / "bin/project-hooks")
    elif linked == "bin":
        mir.mkdir()
        (mir / "bin").symlink_to(outside, target_is_directory=True)
    else:
        (mir / "bin").mkdir(parents=True)
        (mir / "bin/project-hooks").symlink_to(real)
    result = _run_pre_tool_use("echo safe", tmp_path, script=script,
                               extra_env={"MIR_TOOL_CONTRACT_REQUIRED": "1"})
    assert result.returncode == 2
    assert not marker.exists()
    assert "required native tool contract validator missing or linked" in result.stderr
