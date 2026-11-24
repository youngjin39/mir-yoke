"""Replay frozen W1 launch envelopes; never regenerate expected results here."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "native/handoff-packet/tests/fixtures/w1"
# Deliberate tool allowlist, independent of the caller's PATH and home configuration.
TOOLS = (
    "bash",
    "sh",
    "cat",
    "dirname",
    "grep",
    "awk",
    "sed",
    "sort",
    "head",
    "find",
    "wc",
    "tr",
    "mkdir",
    "rm",
    "mv",
    "cp",
    "chmod",
    "date",
    "jq",
    "shasum",
    "cut",
    "tail",
    "basename",
    "readlink",
    "touch",
    "tee",
    "uname",
)


def reference_source(relative: str) -> Path:
    # The W1 Python launch envelope is historical after the native cutover.
    if relative == ".claude/hooks/post-edit-self-ingest.sh":
        return FIXTURES / "post-edit-self-ingest.reference.sh"
    if relative == ".claude/hooks/session-start.sh":
        return FIXTURES / "session-start.reference.sh"
    if relative in {"native/handoff-packet/Cargo.toml", "native/handoff-packet/Cargo.lock"}:
        return FIXTURES / Path(relative).name.replace(".", ".reference.", 1)
    return ROOT / relative


def expand(value: str, root: Path) -> str:
    for token, replacement in (
        ("@TMP@", str(root)),
        ("@REPO@", str(ROOT)),
        ("@PYTHON@", sys.executable),
    ):
        value = value.replace(token, replacement)
    return value


def normalize(data: bytes, root: Path) -> bytes:
    for value, token in ((str(root), "@TMP@"), (str(ROOT), "@REPO@"), (sys.executable, "@PYTHON@")):
        data = data.replace(value.encode(), token.encode())
    return data


def snapshot(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            result[str(path.relative_to(root))] = {
                "symlink": normalize(os.readlink(path).encode(), root).decode()
            }
        elif path.is_file():
            result[str(path.relative_to(root))] = {
                "base64": base64.b64encode(normalize(path.read_bytes(), root)).decode(),
                "mode": stat.S_IMODE(path.stat().st_mode),
            }
        elif path.is_dir():
            result[str(path.relative_to(root))] = {
                "directory": True,
                "mode": stat.S_IMODE(path.stat().st_mode),
            }
    return result


def install(files: dict, root: Path) -> None:
    for name, entry in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if "symlink" in entry:
            path.symlink_to(expand(entry["symlink"], root))
        elif "directory" in entry:
            path.mkdir(exist_ok=True)
            path.chmod(entry["mode"])
        else:
            data = base64.b64decode(entry["base64"])
            path.write_bytes(
                expand(data.decode("utf-8", errors="surrogateescape"), root).encode(
                    "utf-8", errors="surrogateescape"
                )
            )
            path.chmod(entry["mode"])


def prepare(root: Path) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    for name in ("tools", "home", "tmp", "project"):
        (root / name).mkdir(exist_ok=True)
    for name in TOOLS:
        candidates = [Path("/usr/bin") / name, Path("/bin") / name]
        source = next((p for p in candidates if p.is_file()), None)
        if source is None:
            raise RuntimeError(f"required fixture tool unavailable: {name}")
        (root / "tools" / name).symlink_to(source)
    # No real Git, network, global config, or system /tmp writes in a replay.
    for name, body in {
        "git": "exit 1\n",
        "mktemp": (
            'case "$1" in /tmp/*) set -- "$TMPDIR/${1##*/}" ;; esac\n'
            'exec /usr/bin/mktemp "$@"\n'
        ),
    }.items():
        path = root / "tools" / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
    env = {
        "PATH": str(root / "tools"),
        "HOME": str(root / "home"),
        "TMPDIR": str(root / "tmp"),
        "LC_ALL": "C",
        "TZ": "UTC",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "CLAUDE_PROJECT_DIR": str(root / "project"),
        "MIR_NATIVE_HOOKS": "0",
        "MIR_COMPACT_PYTHON_LAUNCHER": sys.executable,
    }
    return env


def stable_files(files: dict) -> dict:
    """Assert volatile field formats before substituting only those fields."""
    stable = {}
    for name, entry in files.items():
        entry = dict(entry)
        if "base64" in entry:
            raw = base64.b64decode(entry["base64"])
            if name.endswith("suggest_bypass.jsonl"):
                row = json.loads(raw)
                assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00", row["ts"])
                raw = raw.replace(row["ts"].encode(), b"@UTC@")
            if name.endswith("hook-invocations.jsonl"):
                rows = []
                for line in raw.splitlines():
                    row = json.loads(line)
                    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", row["ts"])
                    assert type(row["duration_ms"]) is int and row["duration_ms"] >= 0
                    row["ts"] = "@UTC@"
                    row["duration_ms"] = "@DURATION_MS@"
                    rows.append(json.dumps(row, separators=(",", ":")))
                raw = ("\n".join(rows) + "\n").encode()
            if re.search(r"/stop(?:-failure)?-\d{8}T\d{6}Z-\d+-[0-9a-f]{6}\.log$", name):
                name = re.sub(r"\d{8}T\d{6}Z-\d+-[0-9a-f]{6}", "@TIME@-@PID@-@RANDOM@", name)
                raw, count = re.subn(
                    rb"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00", b"@UTC@", raw
                )
                assert count == 1
            entry["base64"] = base64.b64encode(raw).decode()
        assert name not in stable, "normalization must not hide duplicate audit files"
        stable[name] = entry
    return stable


def run(record: dict, root: Path, *, native: Path | None = None) -> dict:
    env = prepare(root)
    install(record["setup"], root)
    # Source copies carry the exact original bytes and modes, not a reimplementation.
    for relative in record.get("copies", []):
        source = reference_source(relative)
        target = root / "project" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if record.get("native"):
        if native is None:
            raise RuntimeError("W1_BOOTSTRAP_NATIVE must name the built reference evaluator")
        target = root / "native-bootstrap-gate"
        shutil.copy2(native, target)
    env.update({key: expand(value, root) for key, value in record["env"].items()})
    before = snapshot(root / "project")
    result = subprocess.run(
        [expand(arg, root) for arg in record["argv"]],
        input=base64.b64decode(record["stdin"]),
        env=env,
        cwd=root / "project",
        capture_output=True,
        timeout=20,
        umask=0o022,
    )
    after = snapshot(root / "project")
    delta = {key: value for key, value in after.items() if before.get(key) != value}
    return {
        "exit": result.returncode,
        "stdout": base64.b64encode(normalize(result.stdout, root)).decode(),
        "stderr": base64.b64encode(normalize(result.stderr, root)).decode(),
        "delta": stable_files(delta),
        "deleted": sorted(before.keys() - after.keys()),
    }


def assert_replay(record: dict, root: Path, *, native: Path | None = None) -> None:
    assert run(record, root, native=native) == record["expected"], record["id"]
