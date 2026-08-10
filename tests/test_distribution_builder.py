from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from mir.core.distribution.builder import DistributionError, build_distribution

ROOT = Path(__file__).resolve().parents[1]


def _digests(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.iterdir()
        if path.is_file()
    }


def test_should_build_core_and_pack_artifacts_when_distribution_is_requested(
    tmp_path: Path,
) -> None:
    report = build_distribution(ROOT, tmp_path / "dist", version="0.9.0-test")
    manifest = json.loads((tmp_path / "dist/manifest.json").read_text())

    assert report["artifact_count"] == 5
    assert {item["kind"] for item in manifest["artifacts"]} == {"core", "pack"}
    assert {item.get("pack") for item in manifest["artifacts"] if item["kind"] == "pack"} == {
        "safety",
        "memory",
        "collaboration",
        "assurance",
    }
    assert (tmp_path / "dist/SHA256SUMS").is_file()
    assert (tmp_path / "dist/provenance.json").is_file()


def test_should_keep_core_payload_to_four_markdown_files_when_archive_is_inspected(
    tmp_path: Path,
) -> None:
    build_distribution(ROOT, tmp_path, version="0.9.0-test")
    archive = tmp_path / "mir-yoke-core-0.9.0-test.tar.gz"

    with tarfile.open(archive, "r:gz") as stream:
        names = sorted(member.name for member in stream.getmembers() if member.isfile())

    assert names == ["AGENTS.md", "CLAUDE.md", "HARNESS.md", "README.md"]


def test_should_return_identical_digests_when_same_source_is_built_twice(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    build_distribution(ROOT, first, version="0.9.0-test")
    build_distribution(ROOT, second, version="0.9.0-test")

    assert _digests(first) == _digests(second)


def test_should_build_and_attest_artifacts_when_release_workflow_runs() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    validate = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")

    assert "id-token: write" in release
    assert "attestations: write" in release
    assert "uv run yoke build" in release
    assert "--require-clean" in release
    assert "actions/attest@v4" in release
    assert "actions/upload-artifact@v4" in release
    assert "starter_contract:" in validate
    assert "platform_regression:" in validate
    assert "github.event_name == 'workflow_dispatch'" in validate


def test_should_reject_dirty_source_when_clean_distribution_is_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mir.core.distribution.builder.source_is_clean", lambda _root: False)

    with pytest.raises(DistributionError, match="clean Git worktree"):
        build_distribution(ROOT, tmp_path, require_clean=True)
