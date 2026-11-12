"""E02b pinned-reference records and real private-host process parity.

Regenerate with --write --scratch pointing to disposable synthetic fixture storage.
The script exports ba6aa95 src/ itself; records never come from native output.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PIN = "ba6aa95673deefcb5f418b3fe9f3007f9b22e62a"
FIXTURE = ROOT / "native/handoff-packet/tests/fixtures/stage-e02b-install.json"
TARGET = "x86_64-unknown-linux-gnu"
BODY = b'#!/bin/sh\nprintf "mir-project-hooks-v1\\nmir-project-hooks-compact-v1\\n"\n'
NAMES = ["bootstrap-gate", "runtime-verify", "executor-query", "delegation-gate", "project-hooks"]
MODES = [
    "valid",
    "existing",
    "replace",
    "bad-hash",
    "wrong-size",
    "truncated",
    "missing",
    "linked-target",
    "linked-parent",
    "readonly-parent",
    "local",
    "empty-local",
    "bad-provider",
    "missing-provider",
    "disabled",
    "unsupported",
    "url-leading-space",
    "url-leading-tab",
    "url-embedded-tab",
    "url-embedded-newline",
]
HOOKS = [
    "valid",
    "check",
    "bad-schema",
    "bad-identity",
    "no-pin",
    "disabled",
    "unsupported",
    "bad-hash",
    "probe-failed",
    "bad-receipt",
    "linked-receipt",
    "bool-schema",
    "broken-receipt",
    "missing-plugins",
    "list-metadata",
    "missing-receipt",
    "nonexec",
    "probe-cr",
    "probe-timeout",
    "probe-delayed-descendant",
    "probe-pipe",
    "probe-large",
    "root-dotdot",
    "receipt-utf16",
    "receipt-utf32",
    "receipt-surrogate",
    "receipt-surrogate16",
    "receipt-surrogate32",
    "receipt-surrogate8",
    "null-plugins",
]
CASES = [(name, mode) for name in NAMES for mode in MODES] + [("hooks", m) for m in HOOKS]


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix="e02b-") as folder:
        yield Path(folder).resolve()


def snapshot(root):
    result = {}
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            p = Path(parent) / name
            info = p.lstat()
            entry = {"mode": stat.S_IMODE(info.st_mode)}
            if p.is_symlink():
                entry = {"link": os.readlink(p).replace(str(root.parent), "<tmp>")}
            elif p.is_file():
                entry["hex"] = p.read_bytes().hex()
            else:
                entry["dir"] = True
            result[p.relative_to(root).as_posix()] = entry
    return result


def setup(tmp, name, mode):
    root = tmp / "project"
    root.mkdir()
    source = tmp / "artifact"
    body = b"#!/bin/sh\nexit 1\n" if mode == "probe-failed" else BODY
    if mode == "probe-cr":
        body = b'#!/bin/sh\nprintf "mir-project-hooks-v1\\rmir-project-hooks-compact-v1\\r"\n'
    if mode == "probe-timeout":
        body = b"#!/bin/sh\nexec sleep 3\n"
    if mode == "probe-delayed-descendant":
        body = (
            b'#!/bin/sh\n(/bin/sleep 0.05; '
            b'printf "mir-project-hooks-v1\\nmir-project-hooks-compact-v1\\n") &\nexit 0\n'
        )
    if mode == "probe-pipe":
        body = (
            b'#!/bin/sh\nif [ -p /dev/stdout ]; then '
            b'printf "mir-project-hooks-v1\\nmir-project-hooks-compact-v1\\n"; fi\n'
        )
    if mode == "probe-large":
        body = (
            b"#!/bin/sh\npad='" + b"x" * 1024 + b"'\ni=0\n"
            b'while [ "$i" -lt 256 ]; do printf "%s\\n" "$pad"; '
            b'printf "%s\\n" "$pad" >&2; i=$((i+1)); done\n'
            b'printf "mir-project-hooks-v1\\nmir-project-hooks-compact-v1\\n"\n'
        )
    source.write_bytes(body)
    pin = {"url": str(source), "size": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    binary_name = "project-hooks" if name == "hooks" else name
    destination = root / ".mir/bin" / binary_name
    if mode.startswith("receipt-"):
        destination.parent.mkdir(parents=True)
        destination.write_bytes(body)
        destination.chmod(0o755)
        receipt = destination.parent / "project-hooks.json"
        text = json.dumps({"path": ".mir/bin/project-hooks", "sha256": pin["sha256"]})
        if mode == "receipt-surrogate":
            text = '{"path": "\\ud800"}'
        if mode in {"receipt-surrogate16", "receipt-surrogate32", "receipt-surrogate8"}:
            text = '{"path": "' + chr(0xD800) + '"}'
        encoding = {
            "receipt-utf16": "utf-16", "receipt-utf32": "utf-32",
            "receipt-surrogate16": "utf-16", "receipt-surrogate32": "utf-32",
        }.get(mode, "utf-8")
        receipt.write_bytes(text.encode(encoding, errors="surrogatepass"))
    if mode in {
        "existing",
        "replace",
        "linked-target",
        "readonly-parent",
        "check",
        "bad-receipt",
        "broken-receipt",
        "nonexec",
    }:
        destination.parent.mkdir(parents=True)
        destination.write_bytes(
            body if mode in {"existing", "check", "bad-receipt", "nonexec"} else b"old\n"
        )
        destination.chmod(0o755 if mode != "replace" else 0o700)
    if mode == "nonexec":
        destination.chmod(0o600)
    if mode == "readonly-parent":
        destination.parent.chmod(0o500)
    if mode == "linked-target":
        destination.unlink()
        destination.symlink_to(source)
    if mode == "linked-parent":
        (tmp / "outside").mkdir()
        (root / ".mir").mkdir()
        (root / ".mir/bin").symlink_to(tmp / "outside")
    if mode == "bad-hash":
        pin["sha256"] = "0" * 64
    if mode == "wrong-size":
        pin["size"] += 1
    if mode == "truncated":
        source.write_bytes(body[:5])
    if mode == "missing":
        source.unlink()
    if mode == "empty-local":
        source.write_bytes(b"")
    metadata = {
        "schema_version": 2 if mode == "bad-schema" else 1,
        "provider_revision": "bad" if mode == "bad-identity" else "a" * 40,
        "plugins": {"mir-lifecycle-hooks": {}},
        "native_artifacts": {
            binary_name: {
                "plugin": "mir-lifecycle-hooks",
                "install_path": "bin/" + binary_name,
                "targets": {} if mode == "no-pin" else {TARGET: pin},
            }
        },
    }
    if mode.startswith("url-"):
        pin["url"] = {
            "url-leading-space": " file://" + str(source),
            "url-leading-tab": "\tfile://" + str(source),
            "url-embedded-tab": "fi\tle://" + str(source),
            "url-embedded-newline": "fi\nle://" + str(source),
        }[mode]
    if mode == "null-plugins":
        metadata["plugins"] = None
    if mode == "bool-schema":
        metadata["schema_version"] = True
    if mode == "missing-plugins":
        del metadata["plugins"]
    if mode == "list-metadata":
        metadata = []
    provider = tmp / "provider"
    (provider / ".mir").mkdir(parents=True)
    lock = provider / ".mir/capability-lock.json"
    lock.write_text("{" if mode == "bad-provider" else json.dumps(metadata))
    if mode == "missing-provider":
        lock.unlink()
    if mode in {"check", "bad-receipt", "linked-receipt", "broken-receipt", "nonexec"}:
        destination.parent.mkdir(parents=True, exist_ok=True)
        receipt = destination.parent / "project-hooks.json"
        receipt.write_text(
            json.dumps(
                {"path": ".mir/bin/project-hooks", "sha256": pin["sha256"]}
                if mode in {"check", "nonexec"}
                else {}
            )
        )
        if mode == "broken-receipt":
            receipt.write_text("{")
        if mode == "linked-receipt":
            receipt.unlink()
            receipt.symlink_to(source)
    request = {
        "operation": "project-hooks" if name == "hooks" else "install-artifact",
        "root": str(root),
        "name": binary_name,
        "target": None if mode == "unsupported" else TARGET,
        "source_root": str(provider),
        "metadata": metadata,
        "pin": pin,
        "disabled": mode == "disabled",
        "action": "check"
        if mode in {"check", "bad-receipt", "broken-receipt", "missing-receipt", "nonexec"}
        or mode.startswith("receipt-")
        else "install",
    }
    if mode == "root-dotdot":
        (root / "nested").mkdir()
        request["root"] = str(root / "nested/..")
    if mode in {"local", "empty-local"}:
        request["local_source"] = str(source)
    return request, root


def observe(tmp, name, mode, binary=None):
    request, root = setup(tmp, name, mode)
    if binary:
        process = subprocess.run(
            [str(binary)], input=json.dumps(request).encode(), capture_output=True, timeout=10
        )
        code, stdout, stderr = process.returncode, process.stdout, process.stderr
    else:
        from mir.cli import _adoption_native as adoption
        from mir.cli import project_hooks as hooks

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
            mock.patch.object(adoption.native, "host_target", return_value=request["target"]),
            mock.patch.dict(
                os.environ, {"MIR_CAPABILITY_NATIVE_ARTIFACTS": "0" if request["disabled"] else "1"}
            ),
        ):
            if name == "hooks":
                with mock.patch.object(hooks.resources, "files", return_value=tmp / "resource"):
                    resource = tmp / "resource/resources"
                    resource.mkdir(parents=True)
                    (resource / "project-hooks-provider.json").write_text(
                        json.dumps(request["metadata"])
                    )
                    code = hooks.main([request["action"], "--project-root", request["root"]])
            else:
                result = adoption._install(
                    root,
                    source_root=Path(request["source_root"]),
                    name=name,
                    local_source=Path(request["local_source"])
                    if "local_source" in request
                    else None,
                )
                print(json.dumps(result, separators=(",", ":"), sort_keys=True))
                code = 0
        stdout, stderr = stdout.getvalue().encode(), stderr.getvalue().encode()
    result = {
        "code": code,
        "stdout": stdout.decode().replace(str(tmp), "<tmp>"),
        "stderr": stderr.decode().replace(str(tmp), "<tmp>"),
        "tree": snapshot(root),
    }
    # Permission-restricted fixtures must be removable under ordinary user credentials.
    for parent, _dirs, _ in os.walk(root, followlinks=False):
        Path(parent).chmod(0o755)
    return result


@pytest.mark.parametrize(("name", "mode"), CASES)
def test_native_matches_pinned_record(tmp_path, name, mode):
    binary = Path(
        os.environ.get(
            "MIR_E02B_BINARY", ROOT / "native/handoff-packet/target/debug/adoption-install"
        )
    )
    records = json.loads(FIXTURE.read_text())
    assert observe(tmp_path, name, mode, binary) == records[name + ":" + mode]


def test_silent_decline_before_effects(tmp_path):
    binary = Path(
        os.environ.get(
            "MIR_E02B_BINARY", ROOT / "native/handoff-packet/target/debug/adoption-install"
        )
    )
    result = subprocess.run(
        [str(binary)],
        input=json.dumps({"operation": "unknown", "root": str(tmp_path / "new")}).encode(),
        capture_output=True,
    )
    assert (result.returncode, result.stdout, result.stderr) == (64, b"", b"")
    assert not (tmp_path / "new").exists()


def write_records(scratch):
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        workspace = Path(folder)
        archive = subprocess.run(
            ["git", "archive", PIN, "src"], cwd=ROOT, capture_output=True, check=True
        )
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(workspace, filter="data")
        env = {
            **os.environ,
            "PYTHONPATH": str(workspace / "src"),
            "HOME": str(workspace / "home"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        (workspace / "home").mkdir()
        records = {}
        for name, mode in CASES:
            case = workspace / "case"
            case.mkdir()
            process = subprocess.run(
                [sys.executable, __file__, "--observe", name, mode, str(case)],
                env=env,
                capture_output=True,
                check=True,
            )
            records[name + ":" + mode] = json.loads(process.stdout)
            shutil.rmtree(case)
        FIXTURE.write_text(json.dumps(records, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--observe":
        print(json.dumps(observe(Path(sys.argv[4]), sys.argv[2], sys.argv[3])))
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument("--write", action="store_true", required=True)
        parser.add_argument("--scratch", type=Path, required=True)
        args = parser.parse_args()
        write_records(args.scratch)
