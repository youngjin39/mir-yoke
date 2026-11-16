"""Capture pinned receipt exceptions on the executing OS; stdlib, no live imports."""

import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

PIN = "5f8f69f94e09b64c5e4d07d329ed17797c35e6cb"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[4]
    source = subprocess.check_output(
        ["git", "show", f"{PIN}:src/mir/cli/bootstrap.py"], cwd=repo
    ).decode("utf-8")
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == "_atomic_write_json")
    function = ast.get_source_segment(source, node)
    args.scratch.mkdir(parents=True, exist_ok=True)
    scratch = args.scratch.resolve()
    # Execute only the pinned function, with stdlib globals; no mir package imports.
    script = '''import json, os, pathlib, sys, sysconfig, tempfile
root = pathlib.Path.cwd().resolve()
stdlib = pathlib.Path(sysconfig.get_path("stdlib"))
sys.path[:] = [str(root), str(stdlib), str(stdlib / "lib-dynload")]
Path = pathlib.Path
assert not any(n == "mir" or n.startswith("mir.") for n in sys.modules)
'''+function+'''
records = {}
for name in ("destination_directory", "parent_file"):
    with tempfile.TemporaryDirectory(dir=root) as work:
        base = Path(work)
        target = base / "receipt"
        if name == "destination_directory":
            target.mkdir()
        else:
            (base / "file").write_text("old", encoding="utf-8")
            target = base / "file/child/receipt"
        try:
            _atomic_write_json(target, {})
        except OSError as error:
            records[name] = type(error).__name__
        else:
            raise AssertionError("receipt write must fail")
        assert not list(base.glob(".receipt.*"))
        if name == "destination_directory":
            assert target.is_dir() and not list(target.iterdir())
        else:
            assert (base / "file").read_bytes() == b"old"
with tempfile.TemporaryDirectory(dir=root) as work:
    path = Path(work) / "receipt"
    path.write_bytes(b"a\\r\\nb\\rc\\n\\\\r\\\\n")
    observation = path.read_text(encoding="utf-8")
    assert observation == "a\\nb\\nc\\n\\\\r\\\\n"
print(json.dumps(dict(reference_pin=PIN, platform=sys.platform,
                     exceptions=records, observation=observation), sort_keys=True))
'''.replace("reference_pin=PIN", f"reference_pin={PIN!r}")
    env = dict(os.environ, HOME=str(scratch), USERPROFILE=str(scratch), TMPDIR=str(scratch))
    result = subprocess.run([sys.executable, "-I", "-c", script], cwd=scratch,
                            env=env, capture_output=True, check=True)
    assert not result.stderr, result.stderr
    record = json.loads(result.stdout)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
