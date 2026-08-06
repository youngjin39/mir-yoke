#!/usr/bin/env python3
"""Install Mir plugins in isolated homes and verify both CLI inventory schemas."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAMES = ("mir-core", "mir-code", "mir-content")


def _run(argv: list[str], environment: dict[str, str]) -> str:
    completed = subprocess.run(
        argv,
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise RuntimeError(f"plugin command failed ({argv[0]}): {detail}")
    return completed.stdout


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _entries(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("installed"), list):
        return [item for item in payload["installed"] if isinstance(item, dict)]
    raise RuntimeError("plugin list returned an unsupported JSON shape")


def _name(entry: dict[str, object]) -> str | None:
    for key in ("name", "id", "pluginId"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value.split("@", 1)[0]
    return None


def _path(entry: dict[str, object]) -> Path | None:
    for key in ("installPath", "installedPath", "installed_path", "path"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return Path(value)
    source = entry.get("source")
    if isinstance(source, dict) and isinstance(source.get("path"), str):
        return Path(source["path"])
    return None


def main() -> int:
    claude = shutil.which("claude")
    codex = shutil.which("codex")
    if claude is None or codex is None:
        raise SystemExit("Claude Code and Codex CLI are required for activation verification")

    with tempfile.TemporaryDirectory(prefix="mir-plugin-activation-") as raw_temp:
        temp = Path(raw_temp)
        environment = os.environ.copy()
        environment["HOME"] = str(temp / "home")
        environment["CODEX_HOME"] = str(temp / "codex")
        (temp / "home").mkdir()
        (temp / "codex").mkdir()

        _run([claude, "plugin", "marketplace", "add", str(ROOT), "--scope", "user"], environment)
        _run([codex, "plugin", "marketplace", "add", str(ROOT), "--json"], environment)
        for plugin in PLUGIN_NAMES:
            _run(
                [claude, "plugin", "install", f"{plugin}@mir-yoke", "--scope", "user"],
                environment,
            )
            _run([codex, "plugin", "add", f"{plugin}@mir-yoke", "--json"], environment)

        inventories = {
            "claude": _entries(json.loads(_run([claude, "plugin", "list", "--json"], environment))),
            "codex": _entries(json.loads(_run([codex, "plugin", "list", "--json"], environment))),
        }
        verified: dict[str, dict[str, str]] = {}
        for runtime, entries in inventories.items():
            runtime_result: dict[str, str] = {}
            for plugin in PLUGIN_NAMES:
                matches = [entry for entry in entries if _name(entry) == plugin]
                if len(matches) != 1 or matches[0].get("enabled") is not True:
                    raise RuntimeError(f"{runtime} did not report exactly one enabled {plugin}")
                installed = _path(matches[0])
                if installed is None or not installed.is_dir():
                    raise RuntimeError(f"{runtime} did not report a usable path for {plugin}")
                expected = _tree_digest(ROOT / "plugins" / plugin)
                actual = _tree_digest(installed)
                if actual != expected:
                    raise RuntimeError(f"{runtime} installed digest mismatch for {plugin}")
                runtime_result[plugin] = actual
            verified[runtime] = runtime_result

    print(json.dumps({"status": "ok", "verified": verified}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
