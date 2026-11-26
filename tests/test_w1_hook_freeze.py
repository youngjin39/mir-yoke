"""W1 reference completeness, provenance and exact launch-envelope replay."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from w1_golden import FIXTURES, ROOT, assert_replay, reference_source

MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
RECORDS = json.loads((FIXTURES / "records.json").read_text())
OWN = {
    "_lib/bootstrap-gate.sh",
    "_lib/invocation_log.sh",
    "_lib/run-python.sh",
    "_lib/tier_dispatch.sh",
    "compact-resume.sh",
    "mir-stop.sh",
    "post-compact.sh",
    "post-edit-check.sh",
    "post-edit-self-ingest.sh",
    "pre-commit-verification.sh",
    "pre-compact.sh",
    "pre-merge-gate.sh",
    "pre-tool-use.sh",
    "session-end.sh",
    "session-start.sh",
    "stop-failure-audit.sh",
    "sub-agent-policy-gate.sh",
    "tdd-guard.sh",
    "tdd-matrix-guard.py",
    "tdd-task-completed.sh",
    "tdd-task-created.sh",
    "user-prompt-submit.sh",
}
TEMPLATE = {
    "_lib/invocation_log.sh",
    "_lib/run-python.sh",
    "compact-resume.sh",
    "post-compact.sh",
    "pre-compact.sh",
}
WINDOWS = "plugins/mir-lifecycle-hooks/hooks/windows_hook.py"
FAMILIES = (
    {".claude/hooks/" + name for name in OWN}
    | {"templates/common-harness/.claude/hooks/" + name for name in TEMPLATE}
    | {WINDOWS, "bootstrap-native"}
)


def test_freeze_completeness_and_provenance():
    assert MANIFEST["schema"] == "mir.w1-hook-freeze@1"
    assert set(MANIFEST["families"]) == FAMILIES
    assert {r["family"] for r in RECORDS} == FAMILIES
    assert len({r["id"] for r in RECORDS}) == len(RECORDS)
    for family, ids in MANIFEST["families"].items():
        assert ids
        assert [r["id"] for r in RECORDS if r["family"] == family] == ids
    required_sources = FAMILIES - {"bootstrap-native"}
    assert required_sources <= MANIFEST["sources"].keys()
    assert all("__pycache__" not in Path(source).parts for source in MANIFEST["sources"])
    for source, digest in MANIFEST["sources"].items():
        assert hashlib.sha256(reference_source(source).read_bytes()).hexdigest() == digest, source
    for record in RECORDS:
        assert set(record["copies"]) <= MANIFEST["sources"].keys()
        assert set(record["expected"]) == {"exit", "stdout", "stderr", "delta", "deleted"}
    bootstrap = {
        r["case"] for r in RECORDS if r["family"] == ".claude/hooks/_lib/bootstrap-gate.sh"
    }
    assert {
        f"{mode}-{state}"
        for mode in ("greenfield", "adoption")
        for state in ("missing", "pending", "restart", "ready", "invalid")
    } <= bootstrap
    windows = {r["case"] for r in RECORDS if r["family"] == WINDOWS}
    assert {
        f"{name}-{event}-{tail}-{status}"
        for name, event in [
            ("runtime-continuity", "SessionStart"),
            ("handoff-packet", "UserPromptSubmit"),
            ("handoff-packet", "PreToolUse"),
            ("handoff-packet", "Stop"),
        ]
        for tail in (0, 3)
        for status in (2, 37, 64, 126, 127)
    } <= windows


@pytest.fixture(scope="session")
def bootstrap_native(tmp_path_factory):
    supplied = os.environ.get("W1_BOOTSTRAP_NATIVE")
    if supplied:
        path = Path(supplied)
        assert path.is_file()
        return path
    target = Path(os.environ.get("CARGO_TARGET_DIR", tmp_path_factory.mktemp("w1-target")))
    subprocess.run(
        [
            "cargo",
            "build",
            "--offline",
            "--locked",
            "--manifest-path",
            str(ROOT / "native/handoff-packet/Cargo.toml"),
            "--bin",
            "bootstrap-gate",
        ],
        env=dict(os.environ, CARGO_TARGET_DIR=str(target)),
        check=True,
        capture_output=True,
        timeout=180,
    )
    return target / "debug/bootstrap-gate"


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX reference envelopes; Windows shell lanes have separate tests"
)
@pytest.mark.parametrize("record", RECORDS, ids=lambda record: record["id"])
def test_frozen_reference_replay(record, tmp_path, request):
    native = request.getfixturevalue("bootstrap_native") if record["native"] else None
    assert_replay(record, tmp_path / "replay", native=native)


def test_tdd_ledger_freeze_provenance_and_inventory():
    from collections import Counter

    frozen = json.loads((FIXTURES / "tdd-ledger.json").read_text())
    assert frozen["schema"] == "mir.w1-tdd-ledger@1"
    for source, digest in frozen["sources"].items():
        assert hashlib.sha256(reference_source(source).read_bytes()).hexdigest() == digest
    records = frozen["records"]
    assert len({r["id"] for r in records}) == len(records)
    assert Counter(r["mode"] for r in records) == {
        "prewrite": 53, "precommit": 27, "precommit-merge": 13, "tdd-guard": 150,
    }
    for record in records:
        assert record["expected"]["delta"] == {}
        assert record["expected"]["deleted"] == []
        assert (record["usage"] == "unused-mode") == (record["mode"] == "precommit-merge")


def test_w5_tdd_retirement_freeze_provenance():
    frozen = json.loads((FIXTURES.parent / "w5-tdd.json").read_text())
    assert frozen["oracle"] == "abb0dd82:.claude/hooks/tdd-matrix-guard.py"
    assert hashlib.sha256(reference_source(".claude/hooks/tdd-matrix-guard.py").read_bytes()
                          ).hexdigest() == frozen["sha256"]
    records = frozen["records"]
    assert len(records) == len({r["id"] for r in records}) == 196
    for record in records:
        assert record["expected"]["delta"] == {}
        assert record["expected"]["deleted"] == []
        assert isinstance(record["oracle_stderr"], str)
