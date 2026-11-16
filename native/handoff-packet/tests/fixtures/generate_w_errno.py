"""Capture CPython 3.12 Windows operation errors and the pinned B30 receipt read."""

import argparse
import ast
import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import stat
import subprocess
import sys
import sysconfig
from pathlib import Path

PIN = "a61c3013dc382989c321577bb93dd937d11884fd"


def operation_records(scratch):
    """Only stdlib operations; no live repository package or native output is used."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
                       ctypes.wintypes.DWORD, ctypes.c_void_p, ctypes.wintypes.DWORD,
                       ctypes.wintypes.DWORD, ctypes.wintypes.HANDLE]
    create.restype = ctypes.wintypes.HANDLE
    kernel.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    records = []

    def observe(operation, case, path, destination):
        actions = {
            "open": lambda: path.open("rb").close(),
            "read": path.read_bytes,
            "write": lambda: path.write_bytes(b"new"),
            "create": lambda: path.open("xb").close(),
            "stat": path.stat, "lstat": path.lstat,
            "scandir": lambda: list(os.scandir(path)),
            "listdir": lambda: os.listdir(path),
            "mkdir": path.mkdir, "rmdir": path.rmdir, "unlink": path.unlink,
            "rename": lambda: path.rename(destination),
            "replace": lambda: path.replace(destination),
            "chmod": lambda: path.chmod(stat.S_IWRITE),
            "readlink": path.readlink,
            "symlink": lambda: os.symlink("target", path),
        }
        record = dict(operation=operation, case=case)
        try:
            actions[operation]()
        except OSError as error:
            def filename(value):
                return None if value is None else str(value).replace(str(scratch), "<tmp>")
            raw = error.winerror
            if raw is None:
                # Measure the equivalent failing Win32 open: CRT exceptions have
                # errno only. Never infer a raw Win32 code from that errno.
                access = 0x80000000 if operation in ("open", "read") else 0x40000000
                disposition = {"open": 3, "read": 3, "write": 2, "create": 1}[operation]
                handle = create(str(path), access, 3, None, disposition, 0x80, None)
                if handle not in (None, ctypes.c_void_p(-1).value):
                    kernel.CloseHandle(handle)
                    raise AssertionError("CRT failure must also fail its raw-code probe") from error
                raw = ctypes.get_last_error()
            record.update(exception=type(error).__name__, errno=error.errno,
                          winerror=error.winerror, raw_code=raw, strerror=error.strerror,
                          filename=filename(error.filename), filename2=filename(error.filename2),
                          message=str(error).replace(repr(str(scratch))[1:-1], "<tmp>"))
        else:
            record["outcome"] = "success"
        records.append(record)

    operations = ("open", "read", "write", "create", "stat", "lstat", "scandir", "listdir",
                  "mkdir", "rmdir", "unlink", "rename", "replace", "chmod", "readlink", "symlink")
    for operation in operations:
        for case in ("missing", "missing-parent", "not-directory", "directory", "readonly",
                     "sharing", "exists", "nonempty"):
            root = scratch / "operations" / operation / case
            root.mkdir(parents=True)
            path, destination = root / "source", root / "destination"
            handle = None
            if case == "missing-parent":
                path = root / "absent" / "source"
            elif case == "not-directory":
                (root / "file").write_bytes(b"file")
                path = root / "file" / "source"
            elif case in ("directory", "nonempty"):
                path.mkdir()
                if case == "nonempty":
                    (path / "child").write_bytes(b"child")
            elif case not in ("missing",):
                path.write_bytes(b"synthetic")
                if case == "exists":
                    destination.write_bytes(b"existing")
                elif case == "readonly":
                    path.chmod(stat.S_IREAD)
                elif case == "sharing":
                    handle = create(str(path), 0x80000000, 0, None, 3, 0, None)
                    assert handle not in (None, ctypes.c_void_p(-1).value), ctypes.get_last_error()
            try:
                observe(operation, case, path, destination)
            finally:
                if handle is not None:
                    assert kernel.CloseHandle(handle), ctypes.get_last_error()
                if case == "readonly" and path.exists():
                    path.chmod(stat.S_IWRITE)
    for operation in operations:
        assert any(r["operation"] == operation and "exception" in r for r in records)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        parser.error("capture requires Windows CPython 3.12; never derive from Mac")
    if not sys.flags.isolated or not sys.flags.utf8_mode or not sys.flags.dont_write_bytecode:
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
                   python=sys.version, platform=sys.platform, records=records, receipt=receipt,
                   operations=operation_records(scratch))
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
