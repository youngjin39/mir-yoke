"""Compare verifier process bytes with the unchanged Python reference."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mir.core.adoption.runtime import create_runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / "native/handoff-packet"
META = {"source_url": "https://example.invalid/provider.git", "source_commit": "a" * 40,
        "constraints_sha256": "b" * 64}
pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo unavailable")


@pytest.fixture(scope="module")
def binary():
    command = ["cargo", "build", "--release", "--locked", "--bin", "runtime-verify"]
    if os.environ.get("MIR_HANDOFF_CARGO_OFFLINE") == "1":
        command.append("--offline")
    subprocess.run(command, cwd=CRATE, check=True)
    target = Path(os.environ.get("CARGO_TARGET_DIR", "target"))
    if not target.is_absolute():
        target = CRATE / target
    return target / "release" / ("runtime-verify.exe" if os.name == "nt" else "runtime-verify")


@pytest.fixture
def closure(tmp_path):
    root = tmp_path / "runtime with spaces \ud55c"
    (root / "bin").mkdir(parents=True)
    (root / "bin/tool").write_bytes(b"#!/bin/sh\nexit 0\n")
    (root / "bin/tool").chmod(0o755)
    (root / "library").mkdir()
    (root / "library/module.py").write_bytes(b"VALUE = 1\n")
    (root / "z\U0001f600.txt").write_bytes(bytes(range(256)))
    manifest = root / "runtime-manifest.json"
    create_runtime_manifest(root, manifest, **META)
    return root, manifest


def pair(binary, root, manifest, metadata=None):
    argv = ["--runtime-root", str(root), "--manifest", str(manifest)]
    for key, value in (META if metadata is None else metadata).items():
        argv.extend(["--" + key.replace("_", "-"), value])
    env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(ROOT / "src"))
    reference = [sys.executable, "-c", "import sys; from mir.cli.runtime_manifest import main; "
                 "sys.exit(main(['verify', *sys.argv[1:]]))", *argv]
    outputs = [subprocess.run(command, capture_output=True, timeout=15, env=env)
               for command in (reference, [str(binary), *argv])]
    return [(p.stdout, p.stderr, p.returncode) for p in outputs]


CASES = ["valid", "digest", "added", "deleted", "mode", "metadata-url", "metadata-commit",
         "metadata-constraints", "malformed", "schema", "schema-bool", "schema-float",
         "entries", "missing-entries", "entry-extra", "entry-order", "entry-mode-float",
         "transient", "missing-manifest", "missing-root", "outside", "precedence",
         "directory-manifest", "directory-suffix", "manifest-link", "symlink", "symlink-drift",
         "directory-link", "dangling-link", "unreadable", "unreadable-directory"]


@pytest.mark.parametrize("case", CASES)
def test_runtime_verify_bytes(binary, closure, tmp_path, case):
    root, manifest = closure
    metadata = dict(META)
    document = json.loads(manifest.read_text())
    if case == "digest":
        (root / "library/module.py").write_bytes(b"VALUE = 2\n")
    elif case == "added":
        (root / "new").write_bytes(b"new")
    elif case == "deleted":
        (root / "bin/tool").unlink()
    elif case == "mode":
        (root / "bin/tool").chmod(0o444)
    elif case.startswith("metadata-"):
        key = {"url": "source_url", "commit": "source_commit",
               "constraints": "constraints_sha256"}[case.removeprefix("metadata-")]
        metadata[key] = "different"
    elif case == "malformed":
        manifest.write_text("{")
    elif case in {"schema", "schema-bool", "schema-float"}:
        document["schema_version"] = {"schema": 2, "schema-bool": True, "schema-float": 1.0}[case]
    elif case == "entries":
        document["entries"] = {}
    elif case == "missing-entries":
        del document["entries"]
    elif case == "entry-extra":
        document["entries"][0]["extra"] = True
    elif case == "entry-order":
        document["entries"].reverse()
    elif case == "entry-mode-float":
        for entry in document["entries"]:
            entry["mode"] = float(entry["mode"])
    elif case == "transient":
        for directory in ["__pycache__", ".pytest_cache", ".ruff_cache"]:
            (root / directory).mkdir()
            (root / directory / "ignored").write_bytes(b"ignore")
        for name in ["a.pyc", "b.pyo"]:
            (root / name).write_bytes(b"ignore")
    elif case == "missing-manifest":
        manifest.unlink()
    elif case == "missing-root":
        root = tmp_path / "absent"
    elif case == "outside":
        outside = tmp_path / "outside.json"
        outside.write_bytes(manifest.read_bytes())
        manifest = outside
    elif case == "precedence":
        metadata["source_commit"] = "different"
        document["entries"] = None
        (root / "new").write_bytes(b"different")
    elif case == "directory-manifest":
        manifest.unlink()
        manifest.mkdir()
    elif case == "directory-suffix":
        (root / "directory.pyc").mkdir()
        (root / "directory.pyc/file").write_bytes(b"ignored directory")
    elif case == "manifest-link":
        alias = root / "manifest-alias.json"
        try:
            alias.symlink_to(manifest.name)
        except OSError:
            pytest.skip("symlink privilege unavailable")
        create_runtime_manifest(root, manifest, **META)
        manifest = alias
    elif case in {"symlink", "symlink-drift", "directory-link", "dangling-link"}:
        link = root / "link"
        target = "library" if case == "directory-link" else "bin/tool"
        if case == "dangling-link":
            target = "absent"
        try:
            link.symlink_to(target, target_is_directory=case == "directory-link")
        except OSError:
            pytest.skip("symlink privilege unavailable")
        create_runtime_manifest(root, manifest, **META)
        if case == "symlink-drift":
            link.unlink()
            link.symlink_to("library/module.py")
    elif case in {"unreadable", "unreadable-directory"}:
        if os.name == "nt":
            pytest.skip("POSIX permission boundary")
        path = root / ("library/module.py" if case == "unreadable" else "library")
        path.chmod(0)
    if case in {"schema", "schema-bool", "schema-float", "entries", "missing-entries",
                "entry-extra", "entry-order", "entry-mode-float", "precedence"}:
        manifest.write_text(json.dumps(document))
    try:
        reference, native = pair(binary, root, manifest, metadata)
        assert reference[0] == b""
        assert reference[2] in {0, 2}
        if os.name == "nt" and case in {
            "manifest-link", "symlink", "symlink-drift", "directory-link", "dangling-link"
        }:
            assert native == (b"", b"", 64)
        else:
            assert native == reference, case
    finally:
        if case in {"unreadable", "unreadable-directory"}:
            path.chmod(0o755)


@pytest.mark.parametrize("args", [[], ["--help"], ["--unknown", "x"]])
def test_runtime_verify_unsupported_args(binary, args):
    result = subprocess.run([str(binary), *args], capture_output=True, timeout=10)
    assert (result.stdout, result.stderr, result.returncode) == (b"", b"", 64)


def test_runtime_verify_unsupported_encoding(binary, closure):
    root, manifest = closure
    manifest.write_bytes(b"\xff")
    _, native = pair(binary, root, manifest)
    assert native == (b"", b"", 64)


@pytest.mark.parametrize("body", ["[]", "null", "true", '{"schema_version": 1}',
                                  '{"schema_version": 1, "source_url": null}',
                                  '\ufeff{}', '{"schema_version": 2, "entries": {}}'])
def test_runtime_verify_document_shapes(binary, closure, body):
    root, manifest = closure
    manifest.write_text(body, encoding="utf-8")
    reference, native = pair(binary, root, manifest)
    assert reference[2] == 2
    assert native == reference


@pytest.mark.parametrize("mutation", ["boolean-mode", "null-entry", "unicode-target"])
def test_runtime_verify_entry_shapes(binary, closure, mutation):
    root, manifest = closure
    if mutation == "unicode-target":
        try:
            (root / "link").symlink_to("absent \ud55c target")
        except OSError:
            pytest.skip("symlink privilege unavailable")
        create_runtime_manifest(root, manifest, **META)
    else:
        document = json.loads(manifest.read_text())
        if mutation == "boolean-mode":
            document["entries"][0]["mode"] = True
        else:
            document["entries"][0] = None
        manifest.write_text(json.dumps(document))
    try:
        reference, native = pair(binary, root, manifest)
        if os.name == "nt" and mutation == "unicode-target":
            assert native == (b"", b"", 64)
        else:
            assert native == reference
    finally:
        (root / "bin/tool").chmod(0o755)


@pytest.mark.parametrize("body", ['{"entries": NaN}', '{"entries": Infinity}',
                                  '{"entry": "\\ud800"}', '[' * 150 + ']' * 150])
def test_runtime_verify_unsupported_json(binary, closure, body):
    root, manifest = closure
    manifest.write_text(body)
    _, native = pair(binary, root, manifest)
    assert native == (b"", b"", 64)


def test_runtime_verify_version(binary):
    result = subprocess.run([str(binary), "--version"], capture_output=True, timeout=10)
    assert (result.stdout, result.stderr, result.returncode) == (
        b"runtime-verify 0.1.0\n", b"", 0)


@pytest.mark.skipif(os.name == "nt", reason="POSIX special files")
def test_runtime_verify_unsupported_special_file(binary, closure):
    root, manifest = closure
    os.mkfifo(root / "pipe")
    argv = ["--runtime-root", str(root), "--manifest", str(manifest)]
    for key, value in META.items():
        argv.extend(["--" + key.replace("_", "-"), value])
    result = subprocess.run([str(binary), *argv], capture_output=True, timeout=10)
    assert (result.stdout, result.stderr, result.returncode) == (b"", b"", 64)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink loop")
def test_runtime_verify_unsupported_symlink_loop(binary, closure):
    root, manifest = closure
    manifest.unlink()
    manifest.symlink_to(manifest.name)
    _, native = pair(binary, root, manifest)
    assert native == (b"", b"", 64)


@pytest.mark.parametrize("name", ["tool.exe", "tool.bat", "tool.cmd", "tool.com",
                                  "tool.EXE", "tool.BAT", "tool.CMD", "tool.COM", ".exe"])
@pytest.mark.parametrize("readonly", [False, True])
def test_runtime_verify_executable_suffix_modes(binary, closure, name, readonly):
    root, manifest = closure
    executable = root / name
    executable.write_bytes(b"runtime executable")
    if readonly:
        executable.chmod(0o444)
    try:
        create_runtime_manifest(root, manifest, **META)
        reference, native = pair(binary, root, manifest)
        assert reference == (b"", b"", 0)
        assert native == reference
    finally:
        executable.chmod(0o644)


@pytest.mark.parametrize("name,target", [("link.exe", "data.txt"), ("link.EXE", "data.txt"),
                                        ("link.bat", "data.txt"), ("link.cmd", "data.txt"),
                                        ("link.com", "data.txt"), ("link.txt", "tool.exe")])
def test_runtime_verify_symlink_suffix_modes(binary, closure, name, target):
    root, manifest = closure
    (root / target).write_bytes(b"symlink target")
    try:
        (root / name).symlink_to(target)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    create_runtime_manifest(root, manifest, **META)
    reference, native = pair(binary, root, manifest)
    assert reference == (b"", b"", 0)
    assert native == ((b"", b"", 64) if os.name == "nt" else reference)


def test_runtime_verify_unsupported_empty_home(binary, closure, monkeypatch):
    root, manifest = closure
    monkeypatch.chdir(root.parent)
    monkeypatch.setenv("USERPROFILE" if os.name == "nt" else "HOME", "")
    reference, native = pair(binary, Path("~") / root.name, manifest)
    assert reference[2] == 2
    assert native == (b"", b"", 64)


@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize("metadata_matches", [False, True])
def test_runtime_verify_link_fallback_precedence(binary, closure, absolute, metadata_matches):
    root, manifest = closure
    target = root / "library/module.py"
    try:
        (root / "link").symlink_to(target if absolute else "library/module.py")
    except OSError:
        pytest.skip("symlink privilege unavailable")
    create_runtime_manifest(root, manifest, **META)
    metadata = dict(META)
    if not metadata_matches:
        metadata["source_commit"] = "different"
    reference, native = pair(binary, root, manifest, metadata)
    assert reference[2] == (0 if metadata_matches else 2)
    if os.name == "nt" and metadata_matches:
        assert native == (b"", b"", 64)
    else:
        assert native == reference
