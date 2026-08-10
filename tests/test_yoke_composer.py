from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mir.core.distribution.catalog import provider_files
from mir.core.distribution.composer import (
    CompositionError,
    apply_plan,
    create_plan,
    install_provider,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy_provider(target: Path) -> Path:
    for relative, source in provider_files(ROOT).items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return target


def test_should_return_create_actions_without_writing_when_empty_target_is_planned(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()

    plan = create_plan(ROOT, target, profile="minimal")

    assert {item["action"] for item in plan["files"]} == {"create"}
    assert {item["target"] for item in plan["files"]} == {
        "AGENTS.md",
        "CLAUDE.md",
        "HARNESS.md",
        "README.md",
    }
    assert list(target.iterdir()) == []


def test_should_create_files_and_local_receipt_when_clean_plan_is_applied(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    plan = create_plan(ROOT, target, profile="code")

    result = apply_plan(ROOT, target, plan)

    assert result["status"] == "applied"
    assert (target / "HARNESS.md").is_file()
    assert (target / ".claude/hooks/mir-safety.py").is_file()
    assert (target / ".mir/local-state.json").is_file()
    assert list((target / ".mir/yoke-receipts").glob("*.json"))


def test_should_reject_apply_without_overwriting_when_target_conflicts(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    harness = target / "HARNESS.md"
    harness.write_text("repository-owned\n", encoding="utf-8")
    plan = create_plan(ROOT, target, profile="minimal")

    assert any(item["action"] == "conflict" for item in plan["files"])
    with pytest.raises(CompositionError, match="conflict"):
        apply_plan(ROOT, target, plan)
    assert harness.read_text(encoding="utf-8") == "repository-owned\n"


def test_should_install_multiple_content_addressed_providers_without_active_alias(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"

    first = install_provider(ROOT, home)
    second = install_provider(ROOT, home)

    assert first == second
    assert first.parent == home / "providers"
    assert (first / "provider.json").is_file()
    assert not (home / "active").exists()
    receipt = json.loads((first / "provider.json").read_text())
    assert receipt["content_digest"] == first.name


def test_should_keep_two_provider_versions_when_source_content_changes(tmp_path: Path) -> None:
    source = _copy_provider(tmp_path / "source")
    home = tmp_path / "home"

    first = install_provider(source, home)
    (source / "VERSION").write_text("0.9.1-test\n", encoding="utf-8")
    second = install_provider(source, home)

    assert first != second
    assert {path.name for path in (home / "providers").iterdir()} == {
        first.name,
        second.name,
    }
    assert not (home / "active").exists()


def test_should_reject_apply_when_provider_changes_after_plan(tmp_path: Path) -> None:
    source = _copy_provider(tmp_path / "source")
    target = tmp_path / "target"
    target.mkdir()
    plan = create_plan(source, target)
    (source / "VERSION").write_text("changed\n", encoding="utf-8")

    with pytest.raises(CompositionError, match="provider source changed"):
        apply_plan(source, target, plan)

    assert list(target.iterdir()) == []


def test_should_roll_back_created_files_when_receipt_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    plan = create_plan(ROOT, target)

    def fail_receipt(*_args, **_kwargs) -> None:
        raise OSError("synthetic receipt failure")

    monkeypatch.setattr("mir.core.distribution.composer.atomic_write_json", fail_receipt)
    with pytest.raises(OSError, match="synthetic receipt failure"):
        apply_plan(ROOT, target, plan)

    assert not (target / "HARNESS.md").exists()
    assert not (target / ".mir/local-state.json").exists()
