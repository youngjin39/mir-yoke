"""PostToolUse adapter that re-indexes tracked durable memory after relevant edits."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_PATCH_PATH = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
_DURABLE_ROOTS = ("docs/", "tasks/", ".ai-harness/")
_GENERATED = {"docs/memory-map.md", "tasks/lessons.md"}


def _relative_candidate(root: Path, raw: object) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw.strip())
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        return None
    if relative in _GENERATED or not relative.endswith(".md"):
        return None
    if not relative.startswith(_DURABLE_ROOTS):
        return None
    return relative


def relevant_paths(payload: dict[str, object], root: Path) -> tuple[str, ...]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ()
    raw_paths: list[object] = [tool_input.get("file_path"), tool_input.get("path")]
    for field in ("command", "patch", "input", "content"):
        body = tool_input.get(field)
        if isinstance(body, str):
            raw_paths.extend(_PATCH_PATH.findall(body))
    selected = {
        relative
        for raw in raw_paths
        if (relative := _relative_candidate(root, raw)) is not None
    }
    return tuple(sorted(selected))


def main(argv: list[str]) -> int:
    root = Path(argv[0] if argv else ".").expanduser().resolve(strict=False)
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(payload, dict) or not relevant_paths(payload, root):
        return 0
    if not (root / "harness_a.toml").is_file() or not (root / ".mir/memory.db").is_file():
        print(
            "[mir-memory] durable edit was not indexed: bootstrap memory is not ready",
            file=sys.stderr,
        )
        return 1
    receipt_path = root / ".mir/bootstrap-receipt.json"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        cli = Path(
            os.path.abspath(Path(receipt["cli"]["executable"]).expanduser())
        )
        resolved_cli = cli.resolve(strict=True)
        expected_cli_hash = receipt["cli"]["sha256"]
        runtime_manifest_raw = receipt["cli"].get("runtime_manifest")
        runtime_manifest_hash = receipt["cli"].get("runtime_manifest_sha256")
        resolved_cli.relative_to(root)
    except ValueError:
        pass
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        print(
            "[mir-memory] durable edit was not indexed: external Mir CLI is unavailable",
            file=sys.stderr,
        )
        return 1
    else:
        print(
            "[mir-memory] durable edit was not indexed: Mir CLI must be outside the project",
            file=sys.stderr,
        )
        return 1
    if not resolved_cli.is_file() or not os.access(cli, os.X_OK):
        print(
            "[mir-memory] durable edit was not indexed: Mir CLI is not executable",
            file=sys.stderr,
        )
        return 1
    if (
        not isinstance(expected_cli_hash, str)
        or hashlib.sha256(cli.read_bytes()).hexdigest() != expected_cli_hash
    ):
        print(
            "[mir-memory] durable edit was not indexed: external Mir CLI hash changed",
            file=sys.stderr,
        )
        return 1
    if runtime_manifest_raw:
        runtime_root = cli.parent.parent
        runtime_manifest = Path(str(runtime_manifest_raw)).expanduser().resolve(
            strict=False
        )
        if (
            runtime_manifest != runtime_root / "runtime-manifest.json"
            or not runtime_manifest.is_file()
            or runtime_manifest.is_symlink()
            or not isinstance(runtime_manifest_hash, str)
            or hashlib.sha256(runtime_manifest.read_bytes()).hexdigest()
            != runtime_manifest_hash
        ):
            print(
                "[mir-memory] durable edit was not indexed: external Mir runtime changed",
                file=sys.stderr,
            )
            return 1
        verified = subprocess.run(
            [
                str(cli),
                "runtime-manifest",
                "verify",
                "--runtime-root",
                str(runtime_root),
                "--manifest",
                str(runtime_manifest),
                "--source-url",
                str(receipt["cli"].get("source_url", "")),
                "--source-commit",
                str(receipt["cli"].get("source_commit", "")),
                "--constraints-sha256",
                str(receipt["cli"].get("constraints_sha256", "")),
            ],
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        if verified.returncode != 0:
            print(
                "[mir-memory] durable edit was not indexed: external Mir runtime changed",
                file=sys.stderr,
            )
            return 1
    completed = subprocess.run(
        [
            str(cli),
            "context",
            "sync",
            "--db",
            str(root / ".mir/memory.db"),
        ],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown failure"
        print(f"[mir-memory] durable edit sync failed: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
