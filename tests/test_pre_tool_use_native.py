"""PreToolUse source provenance, frozen shell replay, and production native parity."""

from __future__ import annotations

import copy
import hashlib
import os
import subprocess
from pathlib import Path

import pytest
from w1_golden import ROOT
from w1_pretool_golden import (
    EXISTING,
    FROZEN,
    HELPER_ABSENCE_RECORDS,
    RECORDS,
    replay,
    with_reference_helpers,
)


def test_pre_tool_use_oracle_provenance():
    assert FROZEN["schema"] == "mir.w1-pre-tool-use@1"
    assert FROZEN["oracle"]["kind"] == "unmodified-shell"
    for source, digest in FROZEN["oracle"]["sources"].items():
        assert hashlib.sha256((ROOT / source).read_bytes()).hexdigest() == digest
    assert len({r["id"] for r in RECORDS}) == len(RECORDS)
    assert {r["id"] for r in RECORDS if "retired_native_reason" in r} == {
        r["id"] for r in HELPER_ABSENCE_RECORDS
    } | {
        "pre-tool-use:bootstrap-helper-missing",
        "pre-tool-use:bootstrap-helper-broken",
        "pre-tool-use:commit-impl-missing-tdd",
    }
    assert len(RECORDS) == 133
    assert len(HELPER_ABSENCE_RECORDS) == 127
    assert all("tool-presence diagnostic" in r["retired_native_reason"]
               for r in HELPER_ABSENCE_RECORDS)
    assert len(EXISTING) == 15
    assert FROZEN["inventory"]["new_records"] == len(RECORDS)
    assert sum(FROZEN["inventory"]["groups"].values()) == len(RECORDS)
    assert not any("native_pending_reason" in r for r in RECORDS)
    adapted = [r for r in RECORDS if "native_engine_failure" in r]
    assert [r["case"] for r in adapted] == ["bootstrap-helper-unexpected"]
    assert "retired_native_reason" not in adapted[0]


@pytest.fixture(scope="session")
def pre_tool_use_native(tmp_path_factory):
    supplied = os.environ.get("W1_PROJECT_HOOKS_NATIVE")
    if supplied:
        return Path(supplied)
    target = Path(os.environ.get("CARGO_TARGET_DIR", tmp_path_factory.mktemp("pretool-target")))
    subprocess.run(
        [
            "cargo",
            "build",
            "--offline",
            "--locked",
            "--manifest-path",
            str(ROOT / "native/handoff-packet/Cargo.toml"),
            "--bin",
            "project-hooks",
        ],
        env=dict(os.environ, CARGO_TARGET_DIR=str(target)),
        check=True,
        capture_output=True,
        timeout=180,
    )
    return target / "debug/project-hooks"


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: r["id"])
def test_pre_tool_use_frozen_shell(record, tmp_path):
    assert replay(record, tmp_path / "shell") == record["expected"], record["id"]


@pytest.mark.parametrize("record", EXISTING + RECORDS, ids=lambda r: r["id"])
def test_pre_tool_use_native_parity(record, tmp_path, pre_tool_use_native):
    if "retired_native_reason" in record:
        pytest.skip(record["retired_native_reason"])
    assert replay(record, tmp_path / "native", pre_tool_use_native) == record["expected"], record[
        "id"
    ]


def test_native_bootstrap_unexpected_failure_blocks_before_policy(tmp_path, pre_tool_use_native):
    record = next(r for r in RECORDS if r["case"] == "bootstrap-helper-unexpected")
    assert replay(record, tmp_path / "failure", pre_tool_use_native) == record["expected"]


def test_pre_tool_use_capability_is_advertised_after_parity(pre_tool_use_native):
    result = subprocess.run([str(pre_tool_use_native), "capabilities"],
                            capture_output=True, check=True)
    assert b"mir-project-hooks-pre-tool-use-v1\n" in result.stdout


@pytest.mark.parametrize("record", HELPER_ABSENCE_RECORDS, ids=lambda r: r["id"])
def test_native_policy_without_retired_helpers(record, tmp_path, pre_tool_use_native):
    # Re-exercise retired diagnostics against the unmodified reference with helpers.
    # Native still receives the original helper-free setup.
    expected = replay(with_reference_helpers(record), tmp_path / "reference")
    assert replay(record, tmp_path / "native", pre_tool_use_native) == expected, record["id"]


@pytest.mark.parametrize("case", ["parse-invalid", "deny-suggest-no-helper"])
def test_native_telemetry_failure_preserves_policy(case, tmp_path, pre_tool_use_native):
    record = copy.deepcopy(next(r for r in RECORDS if r["case"] == case))
    # A file at the log directory makes telemetry creation fail, even as root.
    record["setup"]["project/.mir/runtime"] = {"base64": "", "mode": 0o644}
    expected = replay(with_reference_helpers(record), tmp_path / "reference")
    assert replay(record, tmp_path / "native", pre_tool_use_native) == expected
    assert not any(name.endswith("hook-invocations.jsonl") for name in expected["delta"])
