"""Frozen acquisition boundary; no installer delivery entry point is invoked."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures/user_runtime_install"
MUTANTS = ["parent-path", "symlink-ancestor", "nonregular-source", "receipt-sorting",
           "receipt-newline", "claude-required", "codex-required"]


def test_cli_record_program_name():
    corpus = json.loads((FIXTURES / "admission-receipts.json").read_text())
    for name, record in corpus["records"].items():
        if name.startswith("cli-") and record["stderr"]:
            assert record["stderr"].startswith("usage: install_user_runtime_agents.py "), name
            assert "\ninstall_user_runtime_agents.py: error: " in record["stderr"], name


@pytest.mark.parametrize("mutant", [None, *MUTANTS])
def test_frozen_installer_corpus(tmp_path, mutant):
    output = tmp_path / "actual.json"
    command = [sys.executable, "-I", str(FIXTURES / "capture_admission_receipts.py"),
               "--scratch", str(tmp_path), "--output", str(output)]
    if mutant:
        command += ["--mutant", mutant]
    subprocess.run(command, check=True, timeout=20, cwd=tmp_path,
                   env={**os.environ, "HOME": str(tmp_path), "TMPDIR": str(tmp_path)})
    expected = json.loads((FIXTURES / "admission-receipts.json").read_text())
    actual = json.loads(output.read_text())
    differences = {name for name, value in actual["records"].items()
                   if value != expected["records"][name]}
    if mutant is None:
        assert actual == expected
    else:
        # Reject through observable behavior, never through the mutation label/metadata.
        witness = {
            "parent-path": "relative-2", "symlink-ancestor": "home-6",
            "nonregular-source": "source-directory", "receipt-sorting": "receipt-claude",
            "receipt-newline": "receipt-claude", "claude-required": "cli-missing-claude",
            "codex-required": "cli-missing-codex",
        }[mutant]
        assert witness in differences, f"corpus did not distinguish {mutant} at {witness}"
