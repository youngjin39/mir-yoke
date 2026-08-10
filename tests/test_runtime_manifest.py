from __future__ import annotations

import json
from pathlib import Path

from mir.core.adoption.runtime import create_runtime_manifest, verify_runtime_manifest


def test_runtime_manifest_detects_installed_dependency_drift(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    executable = runtime / "bin/mir"
    dependency = runtime / "tools/mir/lib/python/site-packages/dependency.py"
    executable.parent.mkdir(parents=True)
    dependency.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    manifest = runtime / "runtime-manifest.json"

    create_runtime_manifest(
        runtime,
        manifest,
        source_url="https://github.com/example/mir-yoke.git",
        source_commit="a" * 40,
        constraints_sha256="b" * 64,
    )

    assert verify_runtime_manifest(runtime, manifest) == []
    document = json.loads(manifest.read_text(encoding="utf-8"))
    assert document["source_commit"] == "a" * 40
    assert any(entry["path"].endswith("dependency.py") for entry in document["entries"])
    dependency.write_text("VALUE = 2\n", encoding="utf-8")
    assert "runtime closure differs from manifest" in verify_runtime_manifest(runtime, manifest)
    assert "runtime manifest source evidence differs" in verify_runtime_manifest(
        runtime,
        manifest,
        source_commit="c" * 40,
    )


def test_runtime_manifest_tracks_symlink_targets_but_ignores_bytecode(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    target = runtime / "tools/python"
    link = runtime / "bin/python"
    cache = runtime / "tools/__pycache__/generated.pyc"
    target.parent.mkdir(parents=True)
    link.parent.mkdir(parents=True)
    cache.parent.mkdir(parents=True)
    target.write_text("runtime\n", encoding="utf-8")
    link.symlink_to("../tools/python")
    cache.write_bytes(b"transient")
    manifest = runtime / "runtime-manifest.json"

    create_runtime_manifest(
        runtime,
        manifest,
        source_url="https://github.com/example/mir-yoke.git",
        source_commit="a" * 40,
        constraints_sha256="b" * 64,
    )

    cache.write_bytes(b"changed transient bytecode")
    assert verify_runtime_manifest(runtime, manifest) == []
    link.unlink()
    link.symlink_to("../tools/other-python")
    assert "runtime closure differs from manifest" in verify_runtime_manifest(runtime, manifest)
