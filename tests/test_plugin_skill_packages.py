"""Dual-runtime plugin packaging and single-provider regressions."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mir.core.capabilities.manager import _validate_plugin
from scripts.verify_codex_sync import PLUGIN_SKILLS, validate_plugin_skill_providers
from scripts.verify_plugin_cli_activation import _validate_installed_path

ROOT = Path(__file__).resolve().parents[1]


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_common_skills_have_one_namespaced_provider() -> None:
    providers: dict[str, str] = {}
    for plugin_name, expected_skills in PLUGIN_SKILLS.items():
        skills_root = ROOT / "plugins" / plugin_name / "skills"
        actual = {path.parent.name for path in skills_root.glob("*/SKILL.md")}
        assert actual == expected_skills
        for skill in actual:
            assert skill not in providers
            providers[skill] = plugin_name

    assert len(providers) == 13
    assert not (ROOT / ".claude" / "skills").exists()
    assert not (ROOT / ".agents" / "skills").exists()


def test_dual_runtime_manifests_share_one_skill_tree() -> None:
    for plugin_name in PLUGIN_SKILLS:
        plugin_root = ROOT / "plugins" / plugin_name
        claude = _json(plugin_root / ".claude-plugin" / "plugin.json")
        codex = _json(plugin_root / ".codex-plugin" / "plugin.json")
        assert claude["name"] == codex["name"] == plugin_name
        assert claude["version"] == codex["version"] == "0.9.0"
        assert codex["skills"] == "./skills/"
        assert isinstance(codex["interface"]["defaultPrompt"], list)
        assert 1 <= len(codex["interface"]["defaultPrompt"]) <= 3
        assert "interface" not in claude
        assert len(list(plugin_root.glob("skills/*/SKILL.md"))) == len(
            PLUGIN_SKILLS[plugin_name]
        )
        assert not any(path.is_symlink() for path in plugin_root.rglob("*"))


def test_marketplaces_publish_identical_plugin_names() -> None:
    claude = _json(ROOT / ".claude-plugin" / "marketplace.json")
    codex = _json(ROOT / ".agents" / "plugins" / "marketplace.json")
    expected = set(PLUGIN_SKILLS)
    assert {item["name"] for item in claude["plugins"]} == expected
    assert {item["name"] for item in codex["plugins"]} == expected

    failures: list[str] = []
    validate_plugin_skill_providers(failures)
    assert failures == []


def test_repository_has_no_tracked_worktree_symlinks() -> None:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    tracked = [Path(raw.decode()) for raw in completed.stdout.split(b"\0") if raw]
    assert [path for path in tracked if (ROOT / path).is_symlink()] == []

    index = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    stale_symlink_entries = []
    for row in index:
        mode, _, _, relative = row.split(maxsplit=3)
        path = ROOT / relative
        if mode == "120000" and (path.is_symlink() or (path.exists() and not path.is_dir())):
            stale_symlink_entries.append(relative)
    assert stale_symlink_entries == []


def test_plugin_packages_are_self_contained_in_isolated_copy(tmp_path: Path) -> None:
    for plugin_name in PLUGIN_SKILLS:
        isolated = tmp_path / plugin_name
        shutil.copytree(ROOT / "plugins" / plugin_name, isolated)
        assert _validate_plugin(isolated, plugin_name)
        text = "\n".join(path.read_text() for path in isolated.rglob("*.md"))
        assert "archive/skills/" not in text
        assert "memory_gc_runner.py" not in text


def test_activation_path_must_be_a_real_copy_inside_the_runtime_home(
    tmp_path: Path,
) -> None:
    runtime_home = tmp_path / "runtime-home"
    installed = runtime_home / "plugins" / "mir-core"
    installed.mkdir(parents=True)
    (installed / "plugin.json").write_text("{}\n", encoding="utf-8")

    assert _validate_installed_path(installed, runtime_home) == installed.resolve()

    outside = tmp_path / "provider-copy" / "mir-core"
    outside.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="outside the isolated runtime home"):
        _validate_installed_path(outside, runtime_home)

    linked = runtime_home / "plugins" / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlinked installed path"):
        _validate_installed_path(linked, runtime_home)


def test_manifest_versions_match_repository_release() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version == "0.9.0"
    for plugin_name in PLUGIN_SKILLS:
        plugin_root = ROOT / "plugins" / plugin_name
        assert _json(plugin_root / ".claude-plugin" / "plugin.json")["version"] == version
        assert _json(plugin_root / ".codex-plugin" / "plugin.json")["version"] == version


def test_runtime_marketplace_manifest_shapes_are_distinct() -> None:
    claude = _json(ROOT / ".claude-plugin" / "marketplace.json")
    codex = _json(ROOT / ".agents" / "plugins" / "marketplace.json")
    assert isinstance(claude["owner"], dict)
    assert all(isinstance(entry["source"], str) for entry in claude["plugins"])
    assert "interface" in codex
    assert all(entry["source"]["source"] == "local" for entry in codex["plugins"])
    assert all(
        set(entry["policy"]) == {"installation", "authentication"}
        for entry in codex["plugins"]
    )
