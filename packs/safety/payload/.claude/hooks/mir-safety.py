#!/usr/bin/env python3
"""Small repository-owned safety adapter for explicit opt-in use."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

_PATCH_PATH = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
_ENV_PATH = re.compile(r"(^|/)\.env(?:\.[A-Za-z0-9_-]+)?$")
_DESTRUCTIVE = (
    re.compile(r"\brm\s+(?:-[rRfF]+\s+)+/(?:\s|$)"),
    re.compile(r"\bgit\s+push\s+(?:--force|-f)\b.*\b(?:main|master)\b"),
)
_CREDENTIAL_PATTERNS = (
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("openai-token", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)
_MAX_SCAN_BYTES = 1_000_000


def changed_paths(event: dict[str, object]) -> list[str]:
    """Normalize direct file and patch-shaped tool payloads into relative paths."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    values: set[str] = set()
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            values.add(value.strip())
    for key in ("patch", "input"):
        value = tool_input.get(key)
        if isinstance(value, str):
            values.update(match.strip() for match in _PATCH_PATH.findall(value))
    return sorted(values)


def evaluate_path(raw: str) -> dict[str, str]:
    """Return a finding class without exposing repository content."""
    normalized = raw.replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        return {"decision": "block", "reason": "path-outside-repository"}
    if path.parts and path.parts[0] == ".git":
        return {"decision": "block", "reason": "git-internal-path"}
    if _ENV_PATH.search(normalized) or (path.parts and path.parts[0] in {"secrets", "credentials"}):
        return {"decision": "block", "reason": "protected-secret-path"}
    return {"decision": "allow", "reason": "repository-path"}


def scan_text(text: str) -> str | None:
    for label, pattern in _CREDENTIAL_PATTERNS:
        if pattern.search(text):
            return label
    return None


def _tool_text(event: dict[str, object]) -> str:
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    return "\n".join(value for value in tool_input.values() if isinstance(value, str))


def _git_changed_paths(root: Path) -> list[str]:
    commands = (
        ["git", "diff", "--name-only", "-z"],
        ["git", "diff", "--cached", "--name-only", "-z"],
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
    )
    values: set[str] = set()
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            continue
        values.update(
            entry
            for entry in completed.stdout.decode("utf-8", errors="replace").split("\0")
            if entry
        )
    return sorted(values)


def evaluate_event(event: dict[str, object], *, post: bool = False) -> dict[str, str]:
    for relative in changed_paths(event):
        finding = evaluate_path(relative)
        if finding["decision"] == "block":
            return finding
    text = _tool_text(event)
    finding = scan_text(text)
    if finding is not None:
        return {"decision": "block", "reason": finding}
    if event.get("tool_name") == "Bash" and any(pattern.search(text) for pattern in _DESTRUCTIVE):
        return {"decision": "block", "reason": "direct-destructive-command"}
    if not post:
        return {"decision": "allow", "reason": "preflight-clear"}

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd())).resolve()
    paths = changed_paths(event) or _git_changed_paths(root)
    for relative in paths:
        if evaluate_path(relative)["decision"] == "block":
            continue
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return {"decision": "block", "reason": "path-outside-repository"}
        if not candidate.is_file() or candidate.stat().st_size > _MAX_SCAN_BYTES:
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        finding = scan_text(content)
        if finding is not None:
            return {"decision": "block", "reason": finding}
    return {"decision": "allow", "reason": "postflight-clear"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("[mir-safety] invalid hook payload", file=sys.stderr)
        return 2
    if not isinstance(event, dict):
        print("[mir-safety] hook payload must be an object", file=sys.stderr)
        return 2
    result = evaluate_event(event, post="--post" in argv)
    if result["decision"] == "block":
        print(f"[mir-safety] blocked: {result['reason']}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
