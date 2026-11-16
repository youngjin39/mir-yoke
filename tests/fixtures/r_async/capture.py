"""Freeze only the reachable import result, never synthesize worker dependencies."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PIN = "5906400250462673691bbb72b66db91d0cb4e556"
MODULE = "mir.core.engine.async_adapter"
FILES = (
    "mir/__init__.py", "mir/core/__init__.py", "mir/core/engine/__init__.py",
    "mir/core/engine/async_adapter.py",
)
PROBE = r'''
import importlib
import json
import pathlib
import sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path[:] = [str(root)] + [p for p in sys.path if "site-packages" not in p]
def verify():
    for name, module in sys.modules.items():
        if name == "mir" or name.startswith("mir."):
            assert pathlib.Path(module.__file__).resolve().is_relative_to(root), name
importlib.import_module("mir.core.engine")
verify()  # Verify package provenance before executing the adapter.
try:
    module = importlib.import_module("mir.core.engine.async_adapter")
except Exception as exc:
    result = {"status": "error", "type": type(exc).__name__, "message": str(exc),
              "name": getattr(exc, "name", None)}
else:
    result = {"status": "imported", "callable": callable(module.run_provider)}
verify()
result["registered"] = "mir.core.engine.async_adapter" in sys.modules
print(json.dumps(result, sort_keys=True))
'''


def observe(source: Path, scratch: Path) -> dict:
    """Run without editable-package resolution, a live HOME, or database access."""
    scratch.mkdir(parents=True, exist_ok=True)
    home = scratch / "home"
    home.mkdir(exist_ok=True)
    env = {**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    run = subprocess.run(
        [sys.executable, "-I", "-c", PROBE, str(source.resolve())],
        cwd=scratch, env=env, capture_output=True, text=True, check=True, timeout=30,
    )
    assert run.stderr == "", run.stderr
    return json.loads(run.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.scratch.resolve() / "reference" / "src"
    for relative in FILES:
        content = subprocess.check_output(
            ["git", "show", f"{PIN}:src/{relative}"], cwd=args.repo,
        )
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    result = observe(source, args.scratch.resolve() / "probe")
    # The synthetic tree deliberately contains no worker or contract implementation.
    assert result["name"] == "mir.core.worker", result
    args.output.write_text(json.dumps({"reference_pin": PIN, "import": result}, indent=2) + "\n")


if __name__ == "__main__":
    main()
