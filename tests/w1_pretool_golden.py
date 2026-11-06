"""Replay frozen PreToolUse envelopes; this module cannot capture expectations."""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from unittest.mock import patch

from w1_golden import FIXTURES, install, run

FROZEN = json.loads((FIXTURES / "pre-tool-use.json").read_text())
RECORDS = FROZEN["records"]
EXISTING = [
    r
    for r in json.loads((FIXTURES / "records.json").read_text())
    if r["family"] == ".claude/hooks/pre-tool-use.sh"
]

RETIRED_HELPERS = (
    ".claude/hooks/_lib/tier_dispatch.sh",
    ".claude/hooks/_lib/invocation_log.sh",
    ".claude/hooks/pre-commit-verification.sh",
)
HELPER_ABSENCE_RECORDS = []
for record in RECORDS:
    stderr = base64.b64decode(record["expected"]["stderr"])
    # Bootstrap exits before tier setup and telemetry; its policy is never retired.
    if (record.get("retired_native_reason") or record.get("native_engine_failure")
            or stderr.startswith(b"[BootstrapGate BLOCK]")):
        continue
    missing = []
    for helper in RETIRED_HELPERS:
        if helper in record.get("copies", []) or "project/" + helper in record["setup"]:
            continue
        if helper.endswith("tier_dispatch.sh") and record["case"] != "deny-suggest-no-helper":
            continue
        if (helper.endswith("pre-commit-verification.sh")
                and record["case"] != "commit-helper-missing"):
            continue
        missing.append(helper)
    if missing:
        record["retired_native_reason"] = (
            "Retired tool-presence diagnostic: " + ", ".join(missing)
            + "; native suggest is intrinsic, telemetry is always best effort, and "
            "pre-commit verification runs in process, as in the reference with helpers installed."
        )
        HELPER_ABSENCE_RECORDS.append(record)


def with_reference_helpers(record: dict) -> dict:
    """Install reference helpers without changing any frozen expected bytes."""
    envelope = copy.deepcopy(record)
    for helper in RETIRED_HELPERS:
        if helper not in envelope["copies"] and "project/" + helper not in envelope["setup"]:
            envelope["copies"].append(helper)
    return envelope


def replay(record: dict, root: Path, native: Path | None = None) -> dict:
    envelope = copy.deepcopy(record)
    if native is not None:
        envelope["argv"] = [str(native), "pre-tool-use"]
        if record.get("native_engine_failure") == "unsupported-project-path":
            # Replace the shell-helper status injection with an engine failure.
            envelope["env"]["CLAUDE_PROJECT_DIR"] = "@TMP@/project\n"

    def install_with_tool_overrides(files: dict, target: Path) -> None:
        # Never follow a prepared allowlist symlink when installing a fake tool.
        for name in files:
            path = target / name
            if name.startswith("tools/") and path.is_symlink():
                path.unlink()
        install(files, target)

    with patch("w1_golden.install", install_with_tool_overrides):
        return run(envelope, root)
