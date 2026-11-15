"""Pinned offline oracle; run with CPython 3.12.13 -I and explicit scratch/output."""
import argparse
import hashlib
import importlib
import json
import locale
import os
import platform
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

PIN = "603912f530e88e1dfdbf7de1e56f852a9c40cb94"
REPO = Path(__file__).resolve().parents[4]


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args()
    if not sys.flags.isolated or platform.python_version() != "3.12.13":
        parser.error("CPython 3.12.13 -I required")
    output = args.output.resolve()
    repository = args.repo.resolve()
    root = args.scratch.resolve()
    root.mkdir(parents=True, exist_ok=False)
    sources = root / "sources"
    names = ["__init__", "worktree", "codex_mcp_client", "local_hooks", "redaction"]
    hashes = {}
    for name in names:
        relative = f"tools/mir_executor/{name}.py"
        data = subprocess.run(["git", "-C", str(repository), "show", f"{PIN}:{relative}"],
                              check=True, capture_output=True).stdout
        target = sources / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[relative] = hashlib.sha256(data).hexdigest()
    # tools is a namespace package in the pinned tree; retain that structure.
    os.chdir(root)
    os.environ.update(HOME=str(root), USERPROFILE=str(root))
    sys.path[:] = [str(sources), *[p for p in sys.path if "site-packages" not in p]]
    module = importlib.import_module("tools.mir_executor.worktree")
    for name, loaded in tuple(sys.modules.items()):
        if name == "tools" or name.startswith("tools."):
            filename = getattr(loaded, "__file__", None)
            if filename and not Path(filename).resolve().is_relative_to(sources):
                raise RuntimeError(f"non-isolated import: {name}: {filename}")
            for path in getattr(loaded, "__path__", []):
                if not Path(path).resolve().is_relative_to(sources):
                    raise RuntimeError(f"non-isolated package: {name}: {path}")
    (root / "blocked").write_text("keep", encoding="utf-8")
    (root / "directory").mkdir()
    records = {}
    cases = {
        "mkdir_collision": (root / "blocked", lambda p: p.mkdir(parents=True, exist_ok=True)),
        "blocked_parent": (root / "blocked/child", lambda p: p.mkdir(parents=True, exist_ok=True)),
        "read_directory": (root / "directory", module._read_json_object),
        "status_directory": (root / "directory", lambda p: module.write_status(
            SimpleNamespace(status_path=p), "complete")),
    }
    assert module._read_json_object(root / "absent") == {}
    for name, (path, operation) in cases.items():
        try:
            operation(path)
        except OSError as error:
            records[name] = {"class": type(error).__name__, "errno": error.errno,
                             "winerror": getattr(error, "winerror", None),
                             "text": str(error).replace(str(root).replace("\\", "\\\\"), "<ROOT>")}
        else:
            raise RuntimeError(f"expected OS refusal: {name}")
    output.write_text(json.dumps({
        "pin": PIN, "sources": hashes, "python": sys.version,
        "platform": platform.platform(), "os": os.name, "locale": locale.setlocale(locale.LC_ALL),
        "encoding": locale.getencoding(), "stdout_encoding": sys.stdout.encoding,
        "records": records,
    }, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
