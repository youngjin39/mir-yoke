"""Isolated WT-SPAWN oracle; run with python -I and the pinned reference archive."""

import argparse
import hashlib
import importlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

PIN = "b13c568b994616809946cbaa512f832d608a7dd0"
ARCHIVE_SHA256 = "a9dee34ffa560608ab5688678aa2789bab8889d3ccdc4ffc7a2f8f3f0864b4c4"


def capture(args):
    if not sys.flags.isolated:
        raise RuntimeError("python -I is required")
    if os.name != "nt" and not args.allow_non_windows:
        raise RuntimeError("Windows capture required; --allow-non-windows is smoke-only")
    archive = args.archive.resolve(strict=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise RuntimeError("reference archive digest mismatch")
    # A new directory prevents overwriting any existing target or following its links.
    root = args.scratch.resolve() / "capture"
    root.mkdir(parents=True, exist_ok=False)
    source = root / "reference"
    source.mkdir()
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if not (member.isfile() or member.isdir()):
                raise RuntimeError("non-regular archive member")
            if not (source / member.name).resolve().is_relative_to(source):
                raise RuntimeError("archive path escapes synthetic root")
        bundle.extractall(source, filter="data")
    home = root / "home"
    home.mkdir()
    repo = root / "repo"
    (repo / "config").mkdir(parents=True)
    tmp = root / "tmp"
    tmp.mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    env.update(HOME=str(home), USERPROFILE=str(home), TMP=str(tmp), TEMP=str(tmp),
               TMPDIR=str(tmp), PATH="")
    os.chdir(root)
    os.environ.clear()
    os.environ.update(env)
    tempfile.tempdir = str(tmp)
    # Keep only the interpreter's standard-library paths, never site-packages/cwd.
    sys.path[:] = [str(source)] + [
        p for p in sys.path
        if p and pathlib.Path(p).resolve().is_relative_to(pathlib.Path(sys.base_prefix).resolve())
        and "site-packages" not in pathlib.Path(p).parts
    ]
    dispatch = importlib.import_module("tools.mir_executor.dispatch")
    origins = {}
    for name, module in list(sys.modules.items()):
        if name == "tools" or name.startswith("tools."):
            paths = ([module.__file__] if getattr(module, "__file__", None)
                     else list(module.__path__))
            for path in paths:
                if not pathlib.Path(path).resolve().is_relative_to(source):
                    raise RuntimeError(f"non-isolated reference module: {name}")
            origins[name] = [str(pathlib.Path(p).relative_to(source)) for p in paths]
    denied = root / "denied.exe"
    malformed = root / "malformed.exe"
    malformed.write_bytes(b"WT-SPAWN malformed executable\n")
    malformed.chmod(0o755)
    sid = None
    icacls = None
    if os.name == "nt":
        system = pathlib.Path(env["SystemRoot"]) / "System32"
        who = subprocess.run([str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
                             capture_output=True, text=True, check=True)
        import csv

        sid = "*" + next(csv.reader([who.stdout.strip()]))[1]
        icacls = str(system / "icacls.exe")
        shutil.copyfile(sys.executable, denied)
        subprocess.run([icacls, str(denied), "/deny", sid + ":(X)"],
                       capture_output=True, check=True)
    else:
        denied.write_bytes(b"#!/bin/sh\nexit 0\n")
        denied.chmod(0o644)

    def normalize(text):
        # Replace repr-escaped Windows separators before the literal spelling.
        for spelling in (repr(str(root))[1:-1], str(root), root.as_posix()):
            text = text.replace(spelling, "{ROOT}")
        drive = root.drive
        if drive:
            text = text.replace(drive, "{DRIVE}")
        return text

    records = []
    try:
        for name, program in [("missing", "mir-e7-nonexistent-verifier"),
                              ("permission-denied", str(denied)),
                              ("malformed", str(malformed))]:
            config = {"verifiers": {"probe": [program]}, "verifier_env": "isolated",
                      "child_env_extra_keys": ["SystemRoot", "WINDIR"]}
            (repo / "config/mir-executor.local.json").write_text(json.dumps(config))
            wt = SimpleNamespace(main_repo_root=repo, path=repo, base_commit="base")
            # Only Git preparation is replaced. The pinned gate, environment context,
            # subprocess.run and OS failure/exception propagation execute unchanged.
            with (patch.object(dispatch, "_git", return_value=SimpleNamespace(stdout="code.txt\0")),
                  patch.object(dispatch, "_dispatch_nonruntime_status", return_value=""),
                  patch.object(dispatch, "_isolated_verification_worktree",
                               return_value=nullcontext(repo))):
                try:
                    result = dispatch.evaluate_merge_gate(
                        wt, allowlist=["code.txt"], verification_commands=["probe"],
                        source_commit="synthetic", verify_timeout=5)
                except OSError as exc:
                    record = {"case": name, "class": type(exc).__name__, "errno": exc.errno,
                              "winerror": getattr(exc, "winerror", None),
                              "text": normalize(str(exc)),
                              "filename": normalize(str(exc.filename)) if exc.filename else None}
                else:
                    raise RuntimeError(f"{name} did not raise an OS spawn exception: {result!r}")
            records.append(record)
    finally:
        if icacls:
            subprocess.run([icacls, str(denied), "/remove:d", sid],
                           capture_output=True, check=True)
    result = {"reference_pin": PIN, "archive_sha256": ARCHIVE_SHA256,
              "platform": sys.platform, "python": sys.version.split()[0],
              "modules": origins, "records": records,
              "excluded": ["Git preparation", "Git cleanup precedence", "native behaviour"]}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, required=True)
    parser.add_argument("--scratch", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--allow-non-windows", action="store_true")
    capture(parser.parse_args())


if __name__ == "__main__":
    main()
