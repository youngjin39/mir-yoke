"""Launch an admitted lifecycle hook without depending on Windows shell syntax."""

import os
import subprocess
import sys
from pathlib import Path

EVENTS = {
    "runtime-continuity": ("SessionStart",),
    "handoff-packet": ("UserPromptSubmit", "PreToolUse", "Stop"),
}


def unavailable(event: str) -> int:
    if event in ("PreToolUse", "Stop"):
        sys.stderr.buffer.write(
            f"mir-lifecycle-hooks: native handoff-packet unavailable for {event}\n".encode()
        )
    return 0


def main() -> int:
    args = sys.argv[1:]
    if len(args) not in (2, 5):
        return 1
    if args[2:] not in ([], [";", "exit", "$LASTEXITCODE"]):
        return 1
    if args[1] not in EVENTS.get(args[0], ()):
        return 1
    name, event = args[:2]
    root = Path(__file__).resolve().parents[1]
    binary = root / "bin" / (name + ".exe")
    if (os.environ.get("MIR_NATIVE_HOOKS") == "0" or binary.is_symlink()
            or not binary.is_file() or (os.name != "nt" and not os.access(binary, os.X_OK))):
        return unavailable(event)
    try:
        probe = subprocess.run([str(binary), "--mir-warmup"], stdin=subprocess.DEVNULL,
                               capture_output=True)
        if probe.returncode != 0:
            return unavailable(event)
        result = subprocess.run([str(binary)], capture_output=True)
    except OSError:
        return unavailable(event)
    if result.returncode in (64, 126, 127):
        return unavailable(event)
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
