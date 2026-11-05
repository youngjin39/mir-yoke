"""Explicit project-hook artifact supply from installed provider metadata."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mir.cli.__main__ import main
from mir.core.capabilities import native

TARGET = "aarch64-apple-darwin"
REVISION = "a" * 40
DATA = b"#!/bin/sh\nprintf 'mir-project-hooks-v1\\nmir-project-hooks-compact-v1\\n'\n"


@pytest.fixture
def provider(tmp_path, monkeypatch):
    from mir.cli import project_hooks

    resources = tmp_path / "resources"
    resources.mkdir()
    artifact = tmp_path / "artifact"
    artifact.write_bytes(DATA)
    metadata = {
        "schema_version": 1,
        "provider_revision": REVISION,
        "plugins": {"mir-lifecycle-hooks": {}},
        "native_artifacts": {"project-hooks": {
            "plugin": "mir-lifecycle-hooks",
            "install_path": "bin/project-hooks",
            "targets": {TARGET: {
                "url": artifact.as_uri(),
                "size": len(DATA),
                "sha256": hashlib.sha256(DATA).hexdigest(),
            }},
        }},
    }
    resource = resources / "project-hooks-provider.json"
    resource.write_text(json.dumps(metadata))
    monkeypatch.setattr(project_hooks.resources, "files", lambda package: tmp_path)
    monkeypatch.setattr(native, "host_target", lambda: TARGET)
    monkeypatch.delenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", raising=False)
    root = tmp_path / "project with spaces"
    root.mkdir()
    return root, resource, metadata


def invoke(root, operation="install"):
    return main(["project-hooks", operation, "--project-root", str(root)])


@pytest.mark.parametrize("operation", ["install", "check"])
def test_no_pin_is_explicit_degraded_and_writes_nothing(provider, capsys, operation):
    root, resource, metadata = provider
    metadata["native_artifacts"] = {}
    metadata["provider_revision"] = None
    resource.write_text(json.dumps(metadata))
    assert invoke(root, operation) == 1
    assert "degraded" in capsys.readouterr().out
    assert list(root.iterdir()) == []


def test_install_check_and_repeated_install_are_idempotent(provider, capsys):
    root, _, _ = provider
    assert invoke(root) == 0
    binary = root / ".mir/bin/project-hooks"
    receipt = root / ".mir/bin/project-hooks.json"
    assert json.loads(receipt.read_bytes()) == {
        "path": ".mir/bin/project-hooks", "sha256": hashlib.sha256(DATA).hexdigest(),
    }
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in [binary, receipt]}
    assert invoke(root, "check") == 0
    assert invoke(root) == 0
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns)
                      for path in [binary, receipt]}
    assert "ready" in capsys.readouterr().out


@pytest.mark.parametrize("failure", ["hash", "size", "revision", "wrong-path", "wrong-plugin"])
def test_invalid_provider_pin_does_not_write(provider, failure):
    root, resource, metadata = provider
    record = metadata["native_artifacts"]["project-hooks"]
    pin = record["targets"][TARGET]
    if failure == "hash":
        pin["sha256"] = "0" * 64
    elif failure == "size":
        pin["size"] += 1
    elif failure == "revision":
        metadata["provider_revision"] = "main"
    elif failure == "wrong-path":
        record["install_path"] = "bin/other"
    else:
        record["plugin"] = "unknown"
    resource.write_text(json.dumps(metadata))
    assert invoke(root) == 1
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("failure", ["binary", "receipt", "stale", "probe", "linked-parent"])
def test_check_requires_valid_binary_receipt_and_capability(provider, failure):
    root, resource, metadata = provider
    assert invoke(root) == 0
    binary = root / ".mir/bin/project-hooks"
    receipt = binary.with_suffix(".json")
    if failure == "binary":
        binary.unlink()
    elif failure == "receipt":
        receipt.unlink()
    elif failure == "stale":
        receipt.write_text(json.dumps({"path": ".mir/bin/project-hooks", "sha256": "0" * 64}))
    elif failure == "probe":
        binary.write_bytes(b"#!/bin/sh\nprintf 'other-capability\\n'\n")
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        metadata["native_artifacts"]["project-hooks"]["targets"][TARGET].update(
            sha256=digest, size=binary.stat().st_size,
        )
        resource.write_text(json.dumps(metadata))
        receipt.write_text(json.dumps({"path": ".mir/bin/project-hooks", "sha256": digest}))
    else:
        binary.parent.rename(root / "linked-bin")
        binary.parent.symlink_to(root / "linked-bin", target_is_directory=True)
    assert invoke(root, "check") == 1


def test_developer_lock_cannot_supply_artifacts(provider, tmp_path, monkeypatch):
    from mir.cli import project_hooks

    root, resource, metadata = provider
    (root / ".mir").mkdir()
    developer_lock = root / ".mir/capability-lock.json"
    developer_lock.write_text(json.dumps(metadata))
    checkout = tmp_path / "developer"
    (checkout / ".mir").mkdir(parents=True)
    (checkout / ".mir/capability-lock.json").write_text(json.dumps(metadata))
    monkeypatch.setattr(project_hooks, "__file__", str(checkout / "src/mir/cli/project_hooks.py"))
    metadata["native_artifacts"] = {}
    metadata["provider_revision"] = None
    resource.write_text(json.dumps(metadata))
    assert invoke(root) == 1
    developer_lock.write_text("invalid changed lock")
    assert invoke(root) == 1
    assert not (root / ".mir/bin").exists()


def test_wrong_capability_install_never_enables_receipt(provider):
    root, resource, metadata = provider
    artifact = resource.parent.parent / "artifact"
    data = b"#!/bin/sh\nprintf 'other-capability\\n'\n"
    artifact.write_bytes(data)
    metadata["native_artifacts"]["project-hooks"]["targets"][TARGET].update(
        size=len(data), sha256=hashlib.sha256(data).hexdigest(),
    )
    resource.write_text(json.dumps(metadata))
    assert invoke(root) == 1
    assert not (root / ".mir/bin/project-hooks.json").exists()


@pytest.mark.parametrize("target", [None, "x86_64-unknown-linux-gnu"])
def test_unsupported_or_unpublished_host_writes_nothing(provider, monkeypatch, target):
    root, _, _ = provider
    monkeypatch.setattr(native, "host_target", lambda: target)
    assert invoke(root) == 1
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("path", [".mir", ".mir/bin", ".mir/bin/project-hooks",
                                  ".mir/bin/project-hooks.json", "root-parent"])
def test_install_rejects_linked_placement_paths(provider, tmp_path, path):
    root, _, _ = provider
    outside = tmp_path / "outside"
    outside.mkdir()
    if path == "root-parent":
        link = tmp_path / "link"
        link.symlink_to(root.parent, target_is_directory=True)
        root = link / root.name
    else:
        link = root / path
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside, target_is_directory=True)
    assert invoke(root) == 1
    assert list(outside.iterdir()) == []


def test_disabled_install_writes_nothing(provider, monkeypatch):
    root, _, _ = provider
    monkeypatch.setenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", "0")
    assert invoke(root) == 1
    assert list(root.iterdir()) == []


def test_real_wheel_resource_without_checkout(tmp_path):
    """Build and install the production wheel into a separate, non-editable runtime."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is required for isolated wheel installation")
    source = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    def run(args, **kwargs):
        result = subprocess.run(
            [str(arg) for arg in args], env=environment, capture_output=True,
            text=True, timeout=90, **kwargs,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    wheels = tmp_path / "wheels"
    run([uv, "build", "--wheel", "--offline", "--out-dir", wheels], cwd=source)
    runtime = tmp_path / "runtime"
    run([uv, "venv", "--python", sys.executable, runtime])
    python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    wheel = next(wheels.glob("*.whl"))
    run([uv, "pip", "install", "--offline", "--python", python, wheel])
    target = tmp_path / "target"
    target.mkdir()
    code = """
import json, sys
from pathlib import Path
from importlib import resources
import mir.cli.project_hooks as command
source = Path(sys.argv[1]).resolve()
assert source not in Path(command.__file__).resolve().parents
data = resources.files('mir').joinpath('resources/project-hooks-provider.json').read_bytes()
assert json.loads(data) == json.loads(sys.argv[2])
original = Path.read_bytes
def deny_checkout(self):
    assert source not in self.resolve().parents, str(self)
    return original(self)
Path.read_bytes = deny_checkout
target = Path(sys.argv[3])
assert command.main(['install', '--project-root', str(target)]) == 1
assert command.main(['check', '--project-root', str(target)]) == 1
assert list(target.iterdir()) == []
"""
    result = run([
        python, "-c", code, source,
        (source / "config/project-hooks-provider.json").read_text(), target,
    ], cwd=tmp_path)
    assert "no published host pin" in result.stdout
