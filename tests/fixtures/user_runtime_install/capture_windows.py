"""Offline Windows oracle. Run with CPython 3.12.13 -I; all effects stay in scratch."""

import __future__  # noqa: F401 -- preload standalone reference dependencies

import argparse
import contextlib
import ctypes
import dataclasses  # noqa: F401 -- preload before restricting sys.path
import hashlib
import importlib.util
import io
import json
import locale
import os
import platform
import stat  # noqa: F401 -- preload reference dependency
import subprocess
import sys
import tempfile
import typing  # noqa: F401 -- preload reference dependency
from pathlib import Path

PIN = "0754c36a1bc5814d793984292aa9be6ae26d3001"
SOURCE = "scripts/install_user_runtime_agents.py"
GENERATOR = Path(__file__).resolve()


def inside(path, root):
    return path == root or root in path.parents


def audit(root):
    """No loaded third-party/live repository modules, including lazy imports."""
    stdlib = Path(os.__file__).resolve().parent
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename or filename.startswith("<"):
            continue
        path = Path(filename).resolve()
        if path == GENERATOR or inside(path, root):
            continue
        # Windows extension modules live in DLLs beside Lib, not inside Lib.
        extension = inside(path, Path(sys.base_prefix).resolve() / "DLLs")
        if (inside(path, stdlib) or extension) and not {
            "site-packages", "dist-packages"
        }.intersection(path.parts) and name.partition(".")[0] in sys.stdlib_module_names:
            continue
        raise RuntimeError(f"non-isolated import: {name}: {path}")


def win_api():
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetVolumePathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetVolumePathNameW.restype = wintypes.BOOL
    kernel.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR,
                                           wintypes.DWORD, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p,
                                           wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetVolumeInformationW.restype = wintypes.BOOL
    return kernel


def capture(repo, scratch):
    # Export ONLY the standalone pinned file. Never import the checkout's package.
    source = subprocess.run(["git", "-C", str(repo), "show", f"{PIN}:{SOURCE}"],
                            capture_output=True, check=True).stdout
    kernel = win_api()
    run = Path(tempfile.mkdtemp(prefix="installer-windows-", dir=scratch)).resolve()
    provider = run / "provider"
    script = provider / SOURCE
    script.parent.mkdir(parents=True)
    script.write_bytes(source)
    for name in ("home", "temp", "cases"):
        (run / name).mkdir()
    for name in ("HOME", "USERPROFILE"):
        os.environ[name] = str(run / "home")
    for name in ("TEMP", "TMP", "TMPDIR"):
        os.environ[name] = str(run / "temp")
    tempfile.tempdir = str(run / "temp")
    os.chdir(run)
    manifest = {"reference_pin": PIN, "source": SOURCE,
                "source_sha256": hashlib.sha256(source).hexdigest(),
                "generator_sha256": hashlib.sha256(GENERATOR.read_bytes()).hexdigest(),
                "python": sys.version, "os": platform.platform(),
                "windows": list(platform.win32_ver()), "architecture": platform.machine(),
                "locale": locale.setlocale(locale.LC_ALL, None),
                "filesystem_encoding": sys.getfilesystemencoding()}
    volume, filesystem = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(256)
    if not kernel.GetVolumePathNameW(str(run), volume, len(volume)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.GetVolumeInformationW(volume.value, None, 0, None, None, None,
                                        filesystem, len(filesystem)):
        raise ctypes.WinError(ctypes.get_last_error())
    manifest["filesystem"] = filesystem.value
    spec = importlib.util.spec_from_file_location("installer_windows_reference", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path[:] = [str(provider)]
    audit(run)
    spec.loader.exec_module(module)
    assert Path(module.__file__).resolve() == script
    audit(run)
    records, temporary_names, events = {}, [], []
    original_mkstemp = module.tempfile.mkstemp

    def mkstemp(*args, **kwargs):
        result = original_mkstemp(*args, **kwargs)
        temporary_names.append(result[1])
        return result

    module.tempfile.mkstemp = mkstemp

    def clean(value):
        if isinstance(value, module.Snapshot):
            return clean(dataclasses.asdict(value))
        if isinstance(value, bytes):
            return {"hex": value.hex()}
        if isinstance(value, Path):
            return clean(str(value))
        if isinstance(value, str):
            # Normalize only observed scratch prefixes and actual mkstemp results.
            for index, name in enumerate(temporary_names):
                token = str(Path(name).with_name(f"{{TEMP-{index}}}"))
                value = value.replace(name.replace("\\", "\\\\"),
                                      token.replace("\\", "\\\\")).replace(name, token)
            return value.replace(str(run).replace("\\", "\\\\"), "{ROOT}").replace(
                str(run), "{ROOT}").replace(run.as_posix(), "{ROOT}")
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        return value

    def error_record(error):
        result = {"class": type(error).__name__, "rendered": str(error)}
        for key in ("errno", "winerror", "strerror", "filename", "filename2"):
            result[key] = getattr(error, key, None)
        if error.__cause__ is not None:
            result["cause"] = error_record(error.__cause__)
        return result

    def traced(name, function):
        def call(*args, **kwargs):
            relative = args[1] if len(args) > 1 else None
            if isinstance(relative, (module.Snapshot, module.StaleFile)):
                relative = getattr(relative, "relative", getattr(relative, "target_relative", None))
            events.append({"operation": name, "phase": "begin",
                           "relative": str(relative) if isinstance(relative, Path) else None})
            try:
                result = function(*args, **kwargs)
            except BaseException as error:
                events.append({"operation": name, "phase": "error", "error": error_record(error)})
                raise
            events.append({"operation": name, "phase": "return"})
            return result
        return call

    for name in ("atomic_write", "remove_stale_file", "restore_snapshot", "remove_created_home"):
        setattr(module, name, traced(name, getattr(module, name)))

    def tree(root):
        result = {}
        for path in sorted(root.rglob("*")):
            details = path.lstat()
            result[path.relative_to(root).as_posix()] = {
                "type": "directory" if path.is_dir() else "file",
                "attributes": details.st_file_attributes,
                "bytes": None if path.is_dir() else path.read_bytes().hex()}
        return result

    def record(name, operation, root, function, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        events.clear()
        events.append({"operation": operation, "phase": "entry"})
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                value = function(*args)
                outcome = {"value": value, "error": None}
            except Exception as error:
                outcome = {"value": None, "error": error_record(error)}
        audit(run)
        records[name] = clean({"operation": operation, **outcome,
                               # Direct function boundary: no fabricated CLI exit status.
                               "exit": None, "stdout_hex": stdout.getvalue().encode().hex(),
                               "stderr_hex": stderr.getvalue().encode().hex(),
                               "trace": list(events), "tree": tree(root)})
        return outcome

    def case(name):
        root = run / "cases" / name
        root.mkdir()
        return root

    module.CONFIG_PATH.parent.mkdir()
    empty = {"agents": {"allowlist": []}, "commands": {"allowlist": {}},
             "profiles": {"packs": {}}}
    module.CONFIG_PATH.write_text(json.dumps(empty), encoding="utf-8")
    assert module.load_sources() == ([], []), "empty selection must have no candidates"
    root = case("admission")
    record("sources-empty", "load_sources", root, module.load_sources)
    module.CONFIG_PATH.unlink()
    missing = record("sources-missing", "load_sources", root, module.load_sources)
    assert missing["error"]["class"] == "SyncError"
    module.CONFIG_PATH.write_text(json.dumps(empty), encoding="utf-8")
    (root / "source.md").write_bytes(b"benign agent\r\n")
    record("source-regular", "regular_source", root, module.regular_source, root / "source.md")
    # regular_source requires paths relative to provider on its refusal path.
    record("source-missing", "regular_source", root, module.regular_source,
           provider / "missing.md")
    for name, home in (("relative", Path("relative")), ("root", Path(root.anchor))):
        record("home-" + name, "require_safe_home", root, module.require_safe_home, home)
    record("receipt-missing", "load_receipt", root, module.load_receipt, root, "claude")
    (root / module.RECEIPT_NAME).write_bytes(b"{")
    record("receipt-malformed", "load_receipt", root, module.load_receipt, root, "claude")
    record("receipt-bytes", "make_receipt", root, module.make_receipt, "claude", PIN, [])

    for failure in (False, True):
        root = case("rollback" if failure else "normal")
        plans = []
        for runtime in ("claude", "codex"):
            home = root / runtime
            (home / "agents").mkdir(parents=True)
            (home / "agents/old.md").write_bytes(b"old")
            (home / "agents/stale.md").write_bytes(b"stale")
            files = tuple(module.ManagedFile(f".{runtime}/agents/{name}", Path("agents") / name,
                                            b"new\r\n", module.sha256_bytes(b"new\r\n"))
                          for name in ("old.md", "Z.md", "a.md"))
            stale = (module.StaleFile(f".{runtime}/agents/stale.md", Path("agents/stale.md"),
                                     module.sha256_bytes(b"stale")),)
            plans.append(module.RuntimePlan(module.capture_home_identity(home), files, stale,
                                            module.make_receipt(runtime, PIN, list(files)), False))
        if not failure:
            record("snapshot-normal", "snapshot_plan", root, module.snapshot_plan, plans[0])
        # Real deny-delete handle: reference os.replace fails, then rolls back both homes.
        handle = None
        if failure:
            handle = kernel.CreateFileW(str(root / "codex/agents/old.md"), 0x80000000,
                                        1 | 2, None, 3, 0x80, None)
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
        try:
            outcome = record(root.name, "apply_transaction", root,
                             module.apply_transaction, tuple(plans))
        finally:
            if handle is not None and not kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())
        records[root.name]["input"] = clean([{
            "home": plan.identity.path, "created_home": plan.created_home,
            "files": [{"source": item.source_relative, "target": item.target_relative,
                       "content": item.content, "sha256": item.sha256} for item in plan.files],
            "stale": [{"source": item.source_relative, "target": item.target_relative,
                       "sha256": item.sha256} for item in plan.stale],
            "receipt": plan.receipt,
        } for plan in plans])
        if failure:
            assert outcome["error"] is not None, "deny-delete did not provoke reference failure"
            assert all((plan.identity.path / "agents/old.md").read_bytes() == b"old"
                       for plan in plans), "rollback did not restore original payloads"
        else:
            assert outcome["error"] is None, outcome
            identity = plans[0].identity
            record("target-absent", "target_bytes", root, module.target_bytes,
                   identity, Path("missing.md"))
            record("restore-new", "restore_snapshot", root, module.restore_snapshot,
                   identity, module.Snapshot(Path("agents/Z.md"), None, b"new\r\n"))
            record("restore-old", "restore_snapshot", root, module.restore_snapshot,
                   identity, module.Snapshot(Path("agents/old.md"), b"old", b"new\r\n"))
            record("stale-absent", "remove_stale_file", root, module.remove_stale_file,
                   identity, plans[0].stale[0])

    root = case("refusals")
    identity = module.capture_home_identity(root)
    (root / "file").write_bytes(b"foreign")
    record("target-nonregular", "safe_target", root, module.safe_target,
           root, Path("file/child"))
    record("stale-divergent", "remove_stale_file", root, module.remove_stale_file, identity,
           module.StaleFile(".claude/agents/file.md", Path("file"), module.sha256_bytes(b"old")))
    record("restore-foreign", "restore_snapshot", root, module.restore_snapshot, identity,
           module.Snapshot(Path("file"), b"old", b"new"))
    record("restore-absent", "restore_snapshot", root, module.restore_snapshot, identity,
           module.Snapshot(Path("missing"), None, b"new"))
    (root / "file").chmod(0o444)
    try:
        outcome = record("atomic-readonly", "atomic_write", root, module.atomic_write,
                         identity, Path("file"), b"new")
        assert outcome["error"] is not None, "read-only target unexpectedly replaced"
    finally:
        (root / "file").chmod(0o644)
    root = case("created-home")
    home = root / "home"
    home.mkdir()
    identity = module.capture_home_identity(home)
    plan = module.RuntimePlan(identity, (), (), b"receipt", True)
    record("cleanup-created-home", "remove_created_home", root, module.remove_created_home,
           plan, (module.Snapshot(Path(module.RECEIPT_NAME), None, b"receipt"),))
    root = case("os-errors")
    (root / "directory").mkdir()
    (root / "directory/child").write_bytes(b"child")
    (root / "file").write_bytes(b"file")
    for name, operation, function, args in (
        ("read-missing", "Path.read_bytes", (root / "missing").read_bytes, ()),
        ("mkdir-collision", "Path.mkdir", (root / "file").mkdir, ()),
        ("unlink-directory", "Path.unlink", (root / "directory").unlink, ()),
        ("rmdir-nonempty", "Path.rmdir", (root / "directory").rmdir, ()),
        ("replace-missing", "os.replace", os.replace, (root / "missing", root / "file")),
        ("fsync-invalid", "os.fsync", os.fsync, (-1,)),
    ):
        outcome = record(name, operation, root, function, *args)
        assert outcome["error"] is not None, name
    audit(run)
    return {"manifest": manifest, "records": records}


def main():
    if os.name != "nt" or sys.version_info[:3] != (3, 12, 13) or not sys.flags.isolated:
        raise SystemExit("Requires Windows CPython 3.12.13 with -I; no records written")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=GENERATOR.parents[3])
    args = parser.parse_args()
    repo, scratch, output = args.repo.resolve(), args.scratch.resolve(), args.output.resolve()
    if inside(scratch, repo) or inside(repo, scratch) or not inside(output, scratch):
        parser.error("scratch and repo must be separate; output must be under scratch")
    scratch.mkdir(parents=True, exist_ok=True)
    result = capture(repo, scratch)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                      encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
