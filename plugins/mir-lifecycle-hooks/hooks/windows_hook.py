"""Launch an admitted lifecycle hook without depending on Windows shell syntax."""

import subprocess
import sys
from pathlib import Path

REFERENCES = {
    "runtime-continuity": "hooks/runtime_continuity.py",
    "handoff-packet": "skills/runtime-continuity/scripts/handoff_packet.py",
}


def main() -> int:
    args = sys.argv[1:]
    if len(args) not in (2, 5):
        return 1
    if args[2:] not in ([], [";", "exit", "$LASTEXITCODE"]):
        return 1
    if REFERENCES.get(args[0]) != args[1]:
        return 1
    name, reference = args[:2]
    root = Path(__file__).resolve().parents[1]
    binary = root / "bin" / (name + ".exe")
    command = [str(binary)] if binary.is_file() else [sys.executable, str(root / reference)]
    return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
