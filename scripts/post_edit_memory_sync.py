"""PostToolUse adapter that re-indexes tracked durable memory after relevant edits."""

from __future__ import annotations

import json
import re
import shutil
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
    for field in ("patch", "input", "content"):
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
    uv = shutil.which("uv")
    if uv is None:
        print("[mir-memory] durable edit was not indexed: uv is unavailable", file=sys.stderr)
        return 1
    completed = subprocess.run(
        [
            uv,
            "run",
            "--project",
            str(root),
            "mir",
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
