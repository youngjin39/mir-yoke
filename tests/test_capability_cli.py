"""Capability provider lifecycle and CLI contract tests."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mir.cli import capability as capability_cli
from mir.core.capabilities import CapabilityError, CapabilityManager, load_capability_config

ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 40


class CopyGit:
    def __init__(self, source: Path = ROOT, commit: str = SHA_A) -> None:
        self.source = source
        self.commit = commit

    def resolve(self, url: str, ref: str) -> str:
        return self.commit

    def export(
        self,
        url: str,
        ref: str,
        commit: str,
        paths: list[str],
        destination: Path,
    ) -> None:
        destination.mkdir(parents=True)
        for relative in paths:
            source = self.source / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)


def make_project(tmp_path: Path, name: str = "project") -> Path:
    project = tmp_path / name
    (project / "config").mkdir(parents=True)
    shutil.copy2(
        ROOT / "config" / "capability-sources.json",
        project / "config" / "capability-sources.json",
    )
    for filename in ("CLAUDE.md", "AGENTS.md"):
        (project / filename).write_text(f"# {filename}\n", encoding="utf-8")
    for directory in (".ai-harness", "tasks", ".claude/agents"):
        (project / directory).mkdir(parents=True, exist_ok=True)
    return project


def runtime_runner(active: Path):
    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        entries = [
            {
                "name": plugin.name,
                "enabled": True,
                "installedPath": str(plugin),
            }
            for plugin in sorted((active / "plugins").iterdir())
        ]
        payload: object = entries if Path(args[0]).name == "claude" else {"installed": entries}
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    return run


def test_profiles_are_canonical_and_have_distinct_inventories() -> None:
    config = load_capability_config(ROOT / "config" / "capability-sources.json")
    assert set(config.packs) == {
        "code_app",
        "hybrid_pipeline",
        "infra_runtime",
        "content_workspace",
    }
    inventories = {(pack.plugins, pack.agents) for pack in config.packs.values()}
    assert len(inventories) == 4
    assert config.resolve_profile("hybrid")[0] == "hybrid_pipeline"
    assert config.resolve_profile("infra")[0] == "infra_runtime"


def test_sync_materializes_exact_lock_and_requires_restart(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active"),
        which=lambda executable: f"/fake/{executable}",
    )

    dry_run = manager.sync("code_app")
    assert dry_run["dry_run"] is True
    assert not (project / ".mir" / "capability-lock.json").exists()
    assert not capability_home.exists()

    applied = manager.sync("code_app", apply=True)
    assert applied["registration_status"] == "restart-required"
    lock = json.loads((project / ".mir" / "capability-lock.json").read_text())
    assert lock["source"]["commit"] == SHA_A
    assert set(lock["plugins"]) == {"mir-core", "mir-code"}
    assert set(lock["agents"]) == set(manager.config.packs["code_app"].agents)
    assert lock["registration"] == {"status": "restart-required"}
    assert "materialized_root" not in lock
    assert all((project / path).is_file() for path in lock["agents"])
    assert (capability_home / "active" / "plugins" / "mir-core").is_dir()

    status = manager.status()
    assert status["ready"] is False
    assert status["activation"]["status"] == "restart-required"


def test_check_is_read_only_for_project_and_capability_home(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        git=CopyGit(),
    )
    result = manager.check("hybrid_pipeline")
    assert result["dry_run"] is True
    assert result["ready_to_apply"] is True
    assert not (project / ".mir" / "capability-lock.json").exists()
    assert not capability_home.exists()


def test_finalize_requires_runtime_path_hash_evidence(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    base = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active"),
        which=lambda executable: f"/fake/{executable}",
    )
    base.sync("content_workspace", apply=True)

    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active"),
        which=lambda executable: f"/fake/{executable}",
    )
    assert manager.finalize()["ready_to_finalize"] is True
    finalized = manager.finalize(apply=True, after_restart=True)
    assert finalized["activation"]["status"] == "active"
    assert manager.status()["ready"] is True


def test_claude_plugin_id_is_normalized_for_runtime_evidence(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"

    def claude_id_runner(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        entries = [
            {
                "id": f"{plugin.name}@mir-yoke",
                "enabled": True,
                "installPath": str(plugin),
            }
            for plugin in sorted((capability_home / "active" / "plugins").iterdir())
        ]
        payload: object = entries if Path(args[0]).name == "claude" else {"installed": entries}
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        git=CopyGit(),
        command_runner=claude_id_runner,
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("content_workspace", apply=True)

    assert manager.finalize()["ready_to_finalize"] is True


def test_sync_apply_fails_ready_when_supported_clis_are_missing(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    manager = CapabilityManager(
        project,
        capability_home=tmp_path / "home",
        user_home=tmp_path / "user",
        git=CopyGit(),
        which=lambda executable: None,
    )
    with pytest.raises(CapabilityError, match="registration failed"):
        manager.sync("code_app", apply=True)
    lock = json.loads((project / ".mir" / "capability-lock.json").read_text())
    assert lock["registration"]["status"] == "registration-failed"
    assert manager.status()["ready"] is False


def test_cli_accepts_bootstrap_argument_order(monkeypatch, tmp_path: Path, capsys) -> None:
    calls: list[tuple[str | None, bool]] = []

    class FakeManager:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def sync(self, profile: str | None, *, apply: bool) -> dict[str, object]:
            calls.append((profile, apply))
            return {"operation": "sync", "dry_run": not apply}

    monkeypatch.setattr(capability_cli, "CapabilityManager", FakeManager)
    exit_code = capability_cli.main(
        [
            "sync",
            "--profile",
            "hybrid_pipeline",
            "--project-root",
            str(tmp_path),
            "--apply",
            "--json",
        ]
    )
    assert exit_code == 0
    assert calls == [("hybrid_pipeline", True)]
    assert json.loads(capsys.readouterr().out)["dry_run"] is False
