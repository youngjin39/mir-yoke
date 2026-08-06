"""Fail-closed capability source, collision, and consumer tests."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from test_capability_cli import CopyGit, make_project, runtime_runner

from mir.core.capabilities import CapabilityConfigError, CapabilityError, CapabilityManager
from mir.core.capabilities.config import load_capability_config
from mir.core.capabilities.manager import GitClient, _validate_plugin

ROOT = Path(__file__).resolve().parents[1]


def mutated_config(tmp_path: Path, mutation) -> Path:
    payload = json.loads((ROOT / "config" / "capability-sources.json").read_text())
    mutation(payload)
    path = tmp_path / "capability-sources.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/youngjin39/mir-yoke.git",
        "https://token@github.com/youngjin39/mir-yoke.git",
        "https://user:secret@github.com/youngjin39/mir-yoke.git",
    ],
)
def test_source_url_rejects_non_https_and_credentials(tmp_path: Path, url: str) -> None:
    path = mutated_config(tmp_path, lambda value: value["source"].update(url=url))
    with pytest.raises(CapabilityConfigError):
        load_capability_config(path)


@pytest.mark.parametrize("path", ["../plugins/mir-core", "/plugins/mir-core", "C:/x", "plugins\\x"])
def test_plugin_paths_reject_traversal_and_platform_escapes(tmp_path: Path, path: str) -> None:
    config = mutated_config(
        tmp_path,
        lambda value: value["plugins"]["mir-core"].update(path=path),
    )
    with pytest.raises(CapabilityConfigError):
        load_capability_config(config)


def test_standalone_collision_fails_without_deleting_it(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    user_home = tmp_path / "user"
    collision = user_home / ".agents" / "skills" / "spec-architect"
    collision.mkdir(parents=True)
    (collision / "SKILL.md").write_text("existing\n", encoding="utf-8")
    manager = CapabilityManager(
        project,
        capability_home=tmp_path / "home",
        user_home=user_home,
        git=CopyGit(),
    )
    assert str(collision) in manager.status("code_app")["collisions"]
    with pytest.raises(CapabilityError, match="collision"):
        manager.sync("code_app", apply=True)
    assert (collision / "SKILL.md").read_text() == "existing\n"


def test_agent_divergence_refuses_remote_update(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    manager = CapabilityManager(
        project,
        capability_home=tmp_path / "home",
        user_home=tmp_path / "user",
        git=CopyGit(commit="a" * 40),
        command_runner=runtime_runner(tmp_path / "home" / "active"),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("content_workspace", apply=True)
    agent = project / ".claude" / "agents" / "main-orchestrator.md"
    agent.write_text("user-owned divergence\n", encoding="utf-8")
    manager.git.commit = "b" * 40
    with pytest.raises(CapabilityError, match="diverged"):
        manager.update("content_workspace", apply=True)
    assert agent.read_text() == "user-owned divergence\n"


def test_global_one_version_conflict_is_fail_closed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    first = CapabilityManager(
        make_project(tmp_path, "first"),
        capability_home=home,
        user_home=tmp_path / "user",
        git=CopyGit(commit="a" * 40),
        command_runner=runtime_runner(home / "active"),
        which=lambda executable: f"/fake/{executable}",
    )
    second = CapabilityManager(
        make_project(tmp_path, "second"),
        capability_home=home,
        user_home=tmp_path / "user",
        git=CopyGit(commit="a" * 40),
        command_runner=runtime_runner(home / "active"),
        which=lambda executable: f"/fake/{executable}",
    )
    first.sync("infra_runtime", apply=True)
    second.sync("infra_runtime", apply=True)
    first.git.commit = "b" * 40
    with pytest.raises(CapabilityError, match="another registered consumer"):
        first.update("infra_runtime", apply=True)
    registry = json.loads((home / "consumers.json").read_text())
    assert registry["active_commit"] == "a" * 40


@pytest.mark.parametrize("unsafe_kind", ["non-plugin", "symlink", "executable"])
def test_materialized_plugin_rejects_unsafe_content(
    tmp_path: Path, unsafe_kind: str
) -> None:
    plugin = tmp_path / "mir-core"
    shutil.copytree(ROOT / "plugins" / "mir-core", plugin)
    if unsafe_kind == "non-plugin":
        (plugin / "scripts").mkdir()
    elif unsafe_kind == "symlink":
        (plugin / "skills" / "linked").symlink_to(plugin / "skills" / "design")
    else:
        target = plugin / "skills" / "design" / "SKILL.md"
        target.chmod(0o755)
    with pytest.raises(CapabilityError):
        _validate_plugin(plugin, "mir-core")


@pytest.mark.parametrize(
    ("gitmodules", "listing", "expected"),
    [
        (".gitmodules\n", "", "submodule declaration"),
        ("", f"120000 blob {'1' * 40}\tplugins/mir-core/link\0", "symlink"),
        ("", f"100755 blob {'1' * 40}\tplugins/mir-core/run\0", "executable"),
    ],
)
def test_git_export_rejects_remote_link_submodule_and_executable_modes(
    tmp_path: Path, gitmodules: str, listing: str, expected: str
) -> None:
    sha = "a" * 40

    def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "rev-parse" in args:
            output = f"{sha}\n"
        elif ".gitmodules" in args:
            output = gitmodules
        elif "ls-tree" in args:
            output = listing
        else:
            output = ""
        return subprocess.CompletedProcess(args, 0, output, "")

    with pytest.raises(CapabilityError, match=expected):
        GitClient(runner).export(
            "https://example.com/source.git",
            "main",
            sha,
            ["plugins/mir-core"],
            tmp_path / "checkout",
        )
