"""Capture CPython 3.12 Windows CRT errors and the pinned B30 receipt read."""

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

PIN = "a61c3013dc382989c321577bb93dd937d11884fd"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        parser.error("capture requires Windows CPython 3.12; never derive from Mac")
    if not sys.flags.isolated or not sys.flags.utf8_mode:
        parser.error("run with -I -B -X utf8")
    repo = Path(__file__).resolve().parents[4]
    source = subprocess.check_output(
        ["git", "show", f"{PIN}:src/mir/cli/project_hooks.py"], cwd=repo
    ).decode("utf-8")
    selected = [n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name in ("_path", "_check")]
    assert len(selected) == 2
    scratch, output = args.scratch.resolve(), args.output.resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ.update(HOME=str(scratch), USERPROFILE=str(scratch))
    os.chdir(scratch)
    # Execute only these pinned stdlib-only functions. No mir package is imported.
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    dlls = Path(sys.base_prefix).resolve() / "DLLs"
    sys.path[:] = [str(scratch), str(stdlib), str(dlls)]
    for module in list(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if filename and not filename.startswith("<"):
            path = Path(filename).resolve()
            assert path == Path(__file__).resolve() or (
                (path.is_relative_to(stdlib) or path.is_relative_to(dlls))
                and "site-packages" not in path.parts
            ), f"non-isolated import: {path}"
    namespace = dict(Path=Path, json=json, os=os)
    assert not any(n == "mir" or n.startswith("mir.") for n in sys.modules)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(scratch / "reference.py"),
                 "exec"), namespace)
    records = {}
    for code in (2, 3, 5, 32, 183):
        mapped = OSError(0, "", None, code)
        error = OSError(mapped.errno, os.strerror(mapped.errno))
        records[str(code)] = dict(
            errno=error.errno, message=str(error), exception=type(error).__name__
        )
    project = scratch / "project"
    project.mkdir(exist_ok=True)
    assert not list(project.iterdir()), "receipt scenario requires an empty synthetic project"
    try:
        namespace["_check"](project, ".mir/bin/project-hooks.exe", {"sha256": "0" * 64})
    except OSError as error:
        receipt = dict(exception=type(error).__name__, message=str(error).replace(
            repr(str(scratch))[1:-1], "<tmp>"
        ))
        assert error.errno == 2 and error.winerror is None
    else:
        raise AssertionError("empty project must fail before native verification")
    assert not any(n == "mir" or n.startswith("mir.") for n in sys.modules)
    payload = dict(reference_pin=PIN, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                   python=sys.version, platform=sys.platform, records=records, receipt=receipt)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
