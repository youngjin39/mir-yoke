"""Frozen shell bytes replayed through native incomplete-bootstrap protocols."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from w1_golden import ROOT, expand, install, normalize, prepare, snapshot

FIXTURE = ROOT / "tests/fixtures/bootstrap-enforce.json"
FROZEN = json.loads(FIXTURE.read_text())


@pytest.fixture(scope="session")
def enforcement_native(tmp_path_factory):
    supplied = os.environ.get("MIR_B1_NATIVE")
    if supplied:
        binary = Path(supplied)
        assert binary.is_file()
        return binary
    target = Path(os.environ.get("CARGO_TARGET_DIR", tmp_path_factory.mktemp("enforce-target")))
    subprocess.run(
        ["cargo", "build", "--locked", "--offline", "--manifest-path",
         str(ROOT / "native/handoff-packet/Cargo.toml"), "--bin", "bootstrap-gate"],
        env=dict(os.environ, CARGO_TARGET_DIR=str(target)), check=True,
        capture_output=True, timeout=180,
    )
    return target / "debug/bootstrap-gate"


def test_bootstrap_enforce_inventory():
    pin = FROZEN["source"]
    assert hashlib.sha256((ROOT / pin["path"]).read_bytes()).hexdigest() == pin["sha256"]
    records = FROZEN["records"]
    assert len({r["id"] for r in records}) == len(records)
    assert len(FROZEN["scenarios"]) == 10
    assert len(records) == 1848
    assert sum(r["retired_branch"] for r in records) == 2
    for record in records:
        assert record["expected"]["delta"] == {}
        assert record["expected"]["deleted"] == []
        if record["retired_branch"]:
            assert b"jq is required" in base64.b64decode(record["expected"]["stderr"])
    # The full state/tool/path product must remain present, including ready.
    path_classes = {
        "spec", "spec-subdir", "adoption-manifest", "content-onboarding",
        "evidence", "evidence-spaces", "normal", "traversal", "traversal-end",
        "dot-component", "outside", "absolute", "windows-outside", "backslash",
        "leading-dot", "symlink-parent", "symlink-leaf", "prefix-collision",
    }
    ids = {r["id"] for r in records}
    assert {
        f"{scenario}/{tool}-{path}"
        for scenario in FROZEN["scenarios"]
        for tool in ("Write", "Edit", "apply_patch", "ApplyPatch", "Bash", "Other")
        for path in path_classes
    } <= ids


def test_enforcement_protocol_arguments(enforcement_native):
    for args in (
        ["enforce"], ["instructions"], ["enforce", "--protocol", "2", "."],
        ["instructions", "--protocol", "1", "missing"],
        ["enforce", "--protocol", "1", ".", "extra"],
    ):
        result = subprocess.run(
            [str(enforcement_native), *args], input=b"{}", capture_output=True, timeout=20,
        )
        assert result.returncode == 64
        assert result.stdout == result.stderr == b""


@pytest.mark.skipif(os.name == "nt", reason="POSIX protocol; Windows type-check is separate")
@pytest.mark.parametrize("record", FROZEN["records"], ids=lambda r: r["id"])
def test_native_enforcement_replay(record, tmp_path, enforcement_native):
    if record["retired_branch"]:
        pytest.skip("retired missing-jq branch; native protocol has no jq dependency")
    # The unquoted provider command deliberately splits a space-bearing path.
    root = tmp_path / "replay with spaces"
    env = prepare(root)
    install({**FROZEN["scenarios"][record["scenario"]]["setup"], **record["setup"]}, root)
    # Only private Git and the receipt-pinned fake CLI remain reachable.
    for path in (root / "tools").iterdir():
        if path.is_symlink():
            path.unlink()
    env.update({k: expand(v, root) for k, v in record["env"].items()})
    before = snapshot(root / "project")
    args = [str(enforcement_native), record["operation"], "--protocol", "1"]
    if record["operation"] == "instructions":
        args.append(record["state"])
    args.append(str(root / "project"))
    result = subprocess.run(
        args, input=expand(base64.b64decode(record["stdin"]).decode(), root).encode(),
        cwd=root / "project", env=env, capture_output=True, timeout=20,
    )
    assert result.returncode == record["expected"]["exit"]
    for stream in ("stdout", "stderr"):
        expected = base64.b64decode(record["expected"][stream])
        assert normalize(getattr(result, stream), root) == expected
    assert snapshot(root / "project") == before
