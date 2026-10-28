"""Direct migration from the shipped 0.8.0 provider and schema-1 enrollment."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tarfile

import pytest
from test_capability_cli import ROOT, CopyGit, make_project, runtime_runner, write_acknowledgements

from mir.core.capabilities import CapabilityError, CapabilityManager
from mir.core.capabilities import manager as module
from mir.core.capabilities.manager import _consumer_key, _file_digest, _tree_digest


@pytest.fixture
def legacy_080(tmp_path):
    archive = subprocess.run(
        ["git", "archive", "26cf2a4"], cwd=ROOT, capture_output=True, check=True,
    ).stdout
    tree = tmp_path / "080"
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(tree, filter="data")
    commit = subprocess.run(
        ["git", "rev-parse", "26cf2a4"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    project = make_project(tmp_path, "Daily_Reward_Runner")
    config_path = project / "config/capability-sources.json"
    shutil.copy2(tree / "config/capability-sources.json", config_path)
    config = json.loads(config_path.read_text())
    home = tmp_path / "provider"
    active = home / "active"
    for relative in ["plugins", ".claude-plugin", ".agents/plugins"]:
        shutil.copytree(tree / relative, active / relative)
    plugins = {
        name: {"path": config["plugins"][name]["path"],
               "sha256": _tree_digest(active / config["plugins"][name]["path"])}
        for name in ("mir-core", "mir-code")
    }
    agents = {}
    for relative in config["profiles"]["packs"]["code_app"]["agents"]:
        shutil.copy2(tree / relative, project / relative)
        agents[relative] = {"project_path": relative, "sha256": _file_digest(tree / relative)}
    lock = {"schema_version": 1, "source": {**config["source"], "commit": commit},
            "profile": "code_app", "plugins": plugins, "agents": agents,
            "registration": {"status": "active"}, "synced_at": "2026-08-11T00:00:00Z"}
    (project / ".mir").mkdir()
    (project / ".mir/capability-lock.json").write_text(json.dumps(lock))
    key = _consumer_key(project)
    hashes = {name: value["sha256"] for name, value in plugins.items()}
    (home / "consumers.json").write_text(json.dumps({
        "schema_version": 1, "active_commit": commit,
        "consumers": {key: {"commit": commit, "plugins": hashes, "profile": "code_app"}},
    }))
    (home / "active.json").write_text(json.dumps({
        "schema_version": 1, "commit": commit, "source_url": config["source"]["url"],
        "plugins": hashes, "materialized_root": str(active),
        "activation": {key: {}}, "discovery": {key: {}}, "installation_sessions": {key: {}},
    }))
    target = tmp_path / "target"
    target_archive = subprocess.run(
        ["git", "archive", "HEAD"], cwd=ROOT, capture_output=True, check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(target_archive)) as bundle:
        bundle.extractall(target, filter="data")
    write_acknowledgements(project, {
        "mir-lifecycle-hooks": _tree_digest(target / "plugins/mir-lifecycle-hooks"),
    })
    commands = []
    base_runner = runtime_runner(active, tmp_path / "codex")

    def runner(args, **kwargs):
        commands.append(args)
        return base_runner(args, **kwargs)

    manager = CapabilityManager(
        project, capability_home=home, user_home=tmp_path / "user",
        codex_home=tmp_path / "codex", git=CopyGit(source=target), command_runner=runner,
        which=lambda name: f"/fake/{name}",
    )
    return manager, commands, target


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("windows", [False, True])
def test_update_real_080(legacy_080, monkeypatch, apply, windows):
    manager, commands, target = legacy_080
    if windows:
        monkeypatch.setattr(module, "sys_platform", lambda: "win32")
        monkeypatch.setattr(os.path, "normcase", lambda value: value.lower())
        # Host filesystem remains POSIX; emulate Windows case-insensitive lookup.
        registry = json.loads(manager.registry_path.read_text())
        registry["consumers"] = {str(manager.project_root).lower(): next(
            iter(registry["consumers"].values())
        )}
        manager.registry_path.write_text(json.dumps(registry))
        receipt = json.loads(manager.active_receipt_path.read_text())
        receipt["materialized_root"] = "\\\\?\\" + str(manager.active_path)
        manager.active_receipt_path.write_text(json.dumps(receipt))
    result = manager.update(apply=apply)
    assert set(result["plugins"]) == {"mir-core", "mir-code", "mir-lifecycle-hooks"}
    assert not any(
        "mir-mcp@mir-yoke" in command
        and ("install" in command or "add" in command)
        for command in commands
    )
    if not apply:
        assert result["ready_to_apply"]
        assert json.loads(manager.lock_path.read_text())["schema_version"] == 1
        return
    assert result["applied"]
    lock = json.loads(manager.lock_path.read_text())
    assert lock["schema_version"] == 2
    assert set(lock["plugins"]) == set(result["plugins"])
    assert json.loads(manager.registry_path.read_text())["schema_version"] == 3
    config = json.loads((manager.project_root / "config/capability-sources.json").read_text())
    assert config["schema_version"] == 5
    assert manager.status()["active_integrity"] is True

    fresh = make_project(manager.project_root.parent, "fresh")
    write_acknowledgements(fresh, {
        "mir-lifecycle-hooks": _tree_digest(target / "plugins/mir-lifecycle-hooks"),
    })
    fresh_home = manager.project_root.parent / "fresh-provider"
    fresh_manager = CapabilityManager(
        fresh, capability_home=fresh_home, user_home=manager.user_home,
        codex_home=manager.codex_home, git=CopyGit(source=target),
        command_runner=runtime_runner(fresh_home / "active", manager.codex_home),
        which=lambda name: f"/fake/{name}",
    )
    fresh_manager.sync("code_app", apply=True)
    fresh_lock = json.loads(fresh_manager.lock_path.read_text())
    for field in ("source", "profile", "plugins", "agents", "commands", "marketplaces"):
        assert lock[field] == fresh_lock[field]
    for relative in (*lock["agents"], *lock["commands"]):
        assert (manager.project_root / relative).read_bytes() == (fresh / relative).read_bytes()
    for relative in manager.config.provider_local_agents:
        assert (manager.project_root / relative).exists() == (fresh / relative).exists()


@pytest.mark.parametrize("mutation", ["partial", "invented", "digest", "receipt", "active-tree"])
def test_update_refuses_forged_080(legacy_080, mutation):
    manager, _, _ = legacy_080
    lock = json.loads(manager.lock_path.read_text())
    if mutation == "partial":
        manager.lock_path.unlink()
    elif mutation == "invented":
        lock["agents"] = {}
        manager.lock_path.write_text(json.dumps(lock))
    elif mutation == "digest":
        lock["plugins"]["mir-core"]["sha256"] = "0" * 64
        manager.lock_path.write_text(json.dumps(lock))
    elif mutation == "receipt":
        receipt = json.loads(manager.active_receipt_path.read_text())
        receipt["materialized_root"] = str(manager.project_root)
        manager.active_receipt_path.write_text(json.dumps(receipt))
    else:
        (manager.active_path / "plugins/mir-core/skills/commit/SKILL.md").write_text("forged")
    with pytest.raises(CapabilityError):
        manager.update(apply=True)
