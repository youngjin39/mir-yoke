"""Target-local optional evaluator delivery and adoption receipt contracts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from test_bootstrap_adoption_cli import _ready_project, _run

from mir.cli import bootstrap_adoption as adoption_cli
from mir.core.capabilities import native

DATA = b"#!/bin/sh\nprintf 'bootstrap-gate 1\\n'\n"
TARGET = "aarch64-apple-darwin"
RELATIVE = ".mir/bin/bootstrap-gate"


def _delivery():
    from mir.cli import _adoption_native

    return _adoption_native


def _provider(root: Path, *, target: str = TARGET) -> tuple[Path, dict]:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "artifact"
    source.write_bytes(DATA)
    lock = {
        "plugins": {"mir-lifecycle-hooks": {}},
        "native_artifacts": {
            "bootstrap-gate": {
                "plugin": "mir-lifecycle-hooks",
                "install_path": "bin/bootstrap-gate",
                "targets": {target: {
                    "url": source.as_uri(),
                    "size": len(DATA),
                    "sha256": hashlib.sha256(DATA).hexdigest(),
                }},
            },
        },
    }
    path = root / ".mir/capability-lock.json"
    path.parent.mkdir()
    path.write_text(json.dumps(lock))
    return path, lock


def _install(root: Path, provider: Path, **kwargs):
    return _delivery().install_evaluator(root, source_root=provider, **kwargs)


@pytest.fixture(autouse=True)
def _host(monkeypatch):
    monkeypatch.setattr(native, "host_target", lambda: TARGET)
    monkeypatch.delenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", raising=False)


@pytest.mark.parametrize("target", [TARGET, "x86_64-unknown-linux-gnu"])
def test_verified_artifact_installs_atomically_with_receipt_pin(tmp_path, monkeypatch, target):
    provider = tmp_path / "provider"
    _provider(provider, target=target)
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(native, "host_target", lambda: target)
    replace = os.replace
    replacements = []

    def observe(source, destination):
        source, destination = Path(source), Path(destination)
        assert source.parent == destination.parent
        assert source.stat().st_mode & 0o777 == 0o755
        replacements.append((source, destination))
        replace(source, destination)

    monkeypatch.setattr(os, "replace", observe)
    pin = _install(root, provider)
    binary = root / RELATIVE
    assert binary.read_bytes() == DATA
    assert binary.stat().st_mode & 0o777 == 0o755
    assert pin == {"path": RELATIVE, "sha256": hashlib.sha256(DATA).hexdigest()}
    assert len(replacements) == 1
    assert list(binary.parent.iterdir()) == [binary]


@pytest.mark.parametrize("failure", [
    "missing_lock", "malformed_lock", "list_lock", "null_lock", "linked_lock",
    "missing_record", "target",
    "digest", "size", "source", "source_symlink", "source_directory",
    "url", "fields", "disabled",
])
def test_unverified_artifact_keeps_shell_path(tmp_path, monkeypatch, failure):
    provider = tmp_path / "provider"
    path, lock = _provider(provider)
    pin = lock["native_artifacts"]["bootstrap-gate"]["targets"][TARGET]
    if failure == "missing_lock":
        path.unlink()
    elif failure == "malformed_lock":
        path.write_text("{")
    elif failure in {"list_lock", "null_lock"}:
        path.write_text("[]" if failure == "list_lock" else "null")
    elif failure == "linked_lock":
        original = provider / "original.json"
        path.rename(original)
        path.symlink_to(original)
    elif failure == "missing_record":
        lock["native_artifacts"].clear()
    elif failure == "target":
        lock["native_artifacts"]["bootstrap-gate"]["targets"].clear()
    elif failure == "digest":
        pin["sha256"] = "0" * 64
    elif failure == "size":
        pin["size"] -= 1
    elif failure == "source":
        (provider / "artifact").unlink()
    elif failure == "source_symlink":
        original = provider / "original"
        (provider / "artifact").rename(original)
        (provider / "artifact").symlink_to(original)
    elif failure == "source_directory":
        (provider / "artifact").unlink()
        (provider / "artifact").mkdir()
    elif failure == "url":
        pin["url"] = "file://remote/artifact"
    elif failure == "fields":
        pin["extra"] = True
    else:
        monkeypatch.setenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", "0")
    if failure not in {"missing_lock", "malformed_lock", "list_lock", "null_lock", "linked_lock"}:
        path.write_text(json.dumps(lock))
    root = tmp_path / "project"
    root.mkdir()
    assert _install(root, provider) is None
    assert not (root / RELATIVE).exists()
    assert not (root / ".mir/bin").exists()


@pytest.mark.parametrize("target", [None, "x86_64-pc-windows-msvc"])
@pytest.mark.parametrize("explicit", [False, True])
def test_unsupported_platform_never_installs(tmp_path, monkeypatch, target, explicit):
    provider = tmp_path / "provider"
    _provider(provider)
    monkeypatch.setattr(native, "host_target", lambda: target)
    root = tmp_path / "project"
    root.mkdir()
    options = {"local_source": provider / "artifact"} if explicit else {}
    assert _install(root, provider, **options) is None
    assert not (root / ".mir").exists()


@pytest.mark.parametrize("linked", [".mir", ".mir/bin", RELATIVE])
def test_linked_install_paths_preserve_external_files(tmp_path, linked):
    provider = tmp_path / "provider"
    _provider(provider)
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    if linked == RELATIVE:
        outside.write_bytes(b"preserve")
    else:
        outside.mkdir()
        (outside / "sentinel").write_bytes(b"preserve")
    destination = root / linked
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(outside, target_is_directory=outside.is_dir())
    assert _install(root, provider) is None
    assert destination.is_symlink()
    assert (outside / "sentinel" if outside.is_dir() else outside).read_bytes() == b"preserve"


def test_failed_replace_preserves_existing_binary_and_removes_temp(tmp_path, monkeypatch):
    provider = tmp_path / "provider"
    _provider(provider)
    root = tmp_path / "project"
    binary = root / RELATIVE
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"old binary")

    def fail(*args):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "replace", fail)
    assert _install(root, provider) is None
    assert binary.read_bytes() == b"old binary"
    assert list(binary.parent.iterdir()) == [binary]


@pytest.mark.parametrize("apply", [False, True])
def test_explicit_local_build_is_pinned_only_on_successful_apply(tmp_path, capsys, apply):
    root = tmp_path / "project"
    _ready_project(root)
    source = tmp_path / "local-bootstrap-gate"
    source.write_bytes(DATA)
    arguments = ["--native-evaluator", str(source)]
    if apply:
        arguments.append("--apply")
    assert _run(root, *arguments) == 0
    report = json.loads(capsys.readouterr().out)
    assert ("native_evaluator" in report) == apply
    assert (root / RELATIVE).exists() == apply
    if apply:
        receipt = json.loads((root / ".mir/bootstrap-receipt.json").read_text())
        assert receipt["native_evaluator"] == {
            "path": RELATIVE, "sha256": hashlib.sha256(DATA).hexdigest(),
        }
        assert RELATIVE in report["changed_paths"]


@pytest.mark.parametrize("source_kind", ["missing", "symlink", "directory"])
def test_invalid_explicit_source_adoption_still_succeeds_without_pin(
    tmp_path, capsys, source_kind,
):
    root = tmp_path / "project"
    _ready_project(root)
    source = tmp_path / "source"
    if source_kind == "symlink":
        original = tmp_path / "original"
        original.write_bytes(DATA)
        source.symlink_to(original)
    elif source_kind == "directory":
        source.mkdir()
    assert _run(root, "--apply", "--native-evaluator", str(source)) == 0
    report = json.loads(capsys.readouterr().out)
    assert "native_evaluator" not in report
    receipt = json.loads((root / ".mir/bootstrap-receipt.json").read_text())
    assert "native_evaluator" not in receipt
    assert not (root / RELATIVE).exists()


def test_unready_adoption_never_installs_local_build(tmp_path, capsys):
    root = tmp_path / "project"
    _ready_project(root)
    (root / "spec/gaps.yaml").write_text("gaps: [{id: unresolved}]\n")
    source = tmp_path / "source"
    source.write_bytes(DATA)
    assert _run(root, "--apply", "--native-evaluator", str(source)) == 2
    report = json.loads(capsys.readouterr().out)
    assert "native_evaluator" not in report
    assert not (root / RELATIVE).exists()


def test_default_cli_uses_provider_lock_and_pins_installed_bytes(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    _ready_project(root)
    provider = tmp_path / "provider"
    _provider(provider)
    for relative in adoption_cli._PACKAGED_CANONICAL:
        source = provider / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((adoption_cli._SOURCE_ROOT / relative).read_bytes())
    monkeypatch.setattr(adoption_cli, "_SOURCE_ROOT", provider)
    assert _run(root, "--apply") == 0
    report = json.loads(capsys.readouterr().out)
    receipt = json.loads((root / ".mir/bootstrap-receipt.json").read_text())
    assert receipt["native_evaluator"] == report["native_evaluator"] == {
        "path": RELATIVE, "sha256": hashlib.sha256(DATA).hexdigest(),
    }
    assert (root / RELATIVE).read_bytes() == DATA


def test_missing_provider_lock_clears_previous_receipt_pin(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    _ready_project(root)
    source = tmp_path / "local-build"
    source.write_bytes(DATA)
    assert _run(root, "--apply", "--native-evaluator", str(source)) == 0
    capsys.readouterr()
    provider = tmp_path / "provider"
    for relative in adoption_cli._PACKAGED_CANONICAL:
        path = provider / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((adoption_cli._SOURCE_ROOT / relative).read_bytes())
    monkeypatch.setattr(adoption_cli, "_SOURCE_ROOT", provider)
    assert _run(root, "--apply") == 0
    report = json.loads(capsys.readouterr().out)
    receipt = json.loads((root / ".mir/bootstrap-receipt.json").read_text())
    assert "native_evaluator" not in receipt
    assert "native_evaluator" not in report
    assert (root / RELATIVE).read_bytes() == DATA


@pytest.mark.parametrize("available", [False, True])
def test_runtime_verifier_reuses_verified_installer(tmp_path, available):
    provider = tmp_path / "provider"
    path, lock = _provider(provider)
    if available:
        record = lock["native_artifacts"].pop("bootstrap-gate")
        record["install_path"] = "bin/runtime-verify"
        lock["native_artifacts"]["runtime-verify"] = record
        path.write_text(json.dumps(lock))
    root = tmp_path / "project"
    root.mkdir()
    pin = _delivery().install_runtime_verifier(root, source_root=provider)
    if available:
        assert pin == {
            "path": ".mir/bin/runtime-verify", "sha256": hashlib.sha256(DATA).hexdigest(),
        }
        assert (root / pin["path"]).read_bytes() == DATA
    else:
        assert pin is None
        assert not (root / ".mir/bin").exists()


def test_runtime_verifier_supports_windows_artifact(tmp_path, monkeypatch):
    provider = tmp_path / "provider"
    target = "x86_64-pc-windows-msvc"
    path, lock = _provider(provider, target=target)
    record = lock["native_artifacts"].pop("bootstrap-gate")
    record["install_path"] = "bin/runtime-verify"
    lock["native_artifacts"]["runtime-verify"] = record
    path.write_text(json.dumps(lock))
    monkeypatch.setattr(native, "host_target", lambda: target)
    root = tmp_path / "project"
    root.mkdir()
    pin = _delivery().install_runtime_verifier(root, source_root=provider)
    assert pin == {
        "path": ".mir/bin/runtime-verify.exe", "sha256": hashlib.sha256(DATA).hexdigest(),
    }
    assert (root / pin["path"]).read_bytes() == DATA
