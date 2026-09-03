"""Capability provider lifecycle and CLI contract tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from mir.cli import capability as capability_cli
from mir.core.capabilities import CapabilityError, CapabilityManager, load_capability_config
from mir.core.capabilities.manager import _file_digest, _installed_path, _tree_digest

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


def make_project(tmp_path: Path, name: str = "project", *, real_derivatives: bool = False) -> Path:
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
    (project / "config" / "project-hooks.json").write_text("{}\n", encoding="utf-8")
    (project / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    (project / ".codex").mkdir(parents=True, exist_ok=True)
    (project / ".codex" / "hooks.json").write_text("{}\n", encoding="utf-8")
    (project / ".codex" / "config.toml").write_text("", encoding="utf-8")
    derivative = project / "scripts" / "generate_codex_derivatives.sh"
    derivative.parent.mkdir(parents=True)
    if real_derivatives:
        shutil.copy2(ROOT / "scripts" / "generate_codex_derivatives.sh", derivative)
        (project / ".claude" / "hooks" / "lib").mkdir(parents=True)
    else:
        derivative.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    return project


def use_schema2_capability_source(project: Path) -> None:
    path = project / "config" / "capability-sources.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    payload["plugins"].pop("mir-lifecycle-hooks")
    payload.pop("active_package_digest_acknowledgements")
    payload.pop("commands")
    payload.pop("project_integrations")
    for pack in payload["profiles"]["packs"].values():
        pack.pop("commands")
        pack["plugins"].remove("mir-lifecycle-hooks")
    path.write_text(json.dumps(payload), encoding="utf-8")


def runtime_runner(active: Path, codex_home: Path):
    installed = {"claude": set(), "codex": set()}

    def write_codex_state() -> None:
        codex_home.mkdir(parents=True, exist_ok=True)
        lines = [
            "[marketplaces.mir-yoke]",
            'source_type = "local"',
            f'source = "{active}"',
            "",
        ]
        for plugin in sorted(installed["codex"]):
            lines.extend(
                [
                    f'[plugins."{plugin}@mir-yoke"]',
                    "enabled = true",
                    "",
                ]
            )
        (codex_home / "config.toml").write_text("\n".join(lines), encoding="utf-8")

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        executable = Path(args[0]).name
        if executable == "codex" and args[1:4] == ["plugin", "marketplace", "add"]:
            write_codex_state()
            return subprocess.CompletedProcess(args, 0, "{}", "")
        if executable == "claude" and args[1:3] == ["plugin", "install"]:
            installed["claude"].add(args[3].split("@", 1)[0])
            return subprocess.CompletedProcess(args, 0, "{}", "")
        if executable == "claude" and args[1:3] == ["plugin", "uninstall"]:
            installed["claude"].discard(args[3].split("@", 1)[0])
            return subprocess.CompletedProcess(args, 0, "{}", "")
        if executable == "claude" and args[1:4] == ["plugin", "marketplace", "remove"]:
            installed["claude"].clear()
            return subprocess.CompletedProcess(args, 0, "{}", "")
        if executable == "codex" and args[1:3] == ["plugin", "add"]:
            plugin = args[3].split("@", 1)[0]
            manifest = json.loads(
                (active / "plugins" / plugin / ".codex-plugin" / "plugin.json").read_text()
            )
            cache = codex_home / "plugins" / "cache" / "mir-yoke" / plugin / manifest["version"]
            cache.parent.mkdir(parents=True, exist_ok=True)
            if cache.exists():
                shutil.rmtree(cache)
            shutil.copytree(active / "plugins" / plugin, cache)
            installed["codex"].add(plugin)
            write_codex_state()
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps({"installedPath": str(cache), "pluginId": args[3]}),
                "",
            )
        if executable == "codex" and args[1:3] == ["plugin", "remove"]:
            installed["codex"].discard(args[3].split("@", 1)[0])
            write_codex_state()
            return subprocess.CompletedProcess(args, 0, "{}", "")
        if executable == "codex" and args[1:4] == ["plugin", "marketplace", "remove"]:
            installed["codex"].clear()
            write_codex_state()
            return subprocess.CompletedProcess(args, 0, "{}", "")
        if executable not in installed:
            return subprocess.CompletedProcess(args, 0, "", "")

        entries = [
            {
                "name": plugin.name,
                "enabled": True,
                "installedPath": str(plugin),
                "version": json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())[
                    "version"
                ],
            }
            for plugin in sorted((active / "plugins").iterdir())
            if plugin.name in installed[executable]
        ]
        payload: object = entries if executable == "claude" else {"installed": entries}
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    return run


def runtime_with_real_derivatives(active: Path, codex_home: Path):
    fake_runtime = runtime_runner(active, codex_home)

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if Path(args[0]).name == "bash":
            actual_args = [shutil.which("bash") or "/bin/bash", *args[1:]]
            return subprocess.run(actual_args, **kwargs)  # type: ignore[arg-type]
        return fake_runtime(args, **kwargs)

    return run


def observed_skills(manager: CapabilityManager) -> list[str]:
    lock = json.loads(manager.lock_path.read_text(encoding="utf-8"))
    return sorted(
        f"{plugin}:{skill}"
        for plugin in lock["plugins"]
        for skill in manager.config.plugin_skills[plugin]
    )


def observed_hooks(manager: CapabilityManager) -> list[str]:
    lock = json.loads(manager.lock_path.read_text(encoding="utf-8"))
    return sorted(
        f"{plugin}:{hook}"
        for plugin in lock["plugins"]
        for hook in manager.config.plugin_hooks.get(plugin, ())
    )


def attest_both_runtimes(manager: CapabilityManager) -> None:
    skills = observed_skills(manager)
    hooks = observed_hooks(manager)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("CLAUDE_SESSION_ID", "claude-new-session")
        monkeypatch.setenv("CODEX_THREAD_ID", "codex-new-session")
        manager.attest("claude-code", skills, hooks, apply=True)
        manager.attest("codex-cli-desktop", skills, hooks, apply=True)


def attest_codex_runtime(manager: CapabilityManager) -> None:
    skills = observed_skills(manager)
    hooks = observed_hooks(manager)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("CODEX_THREAD_ID", "codex-new-session")
        manager.attest("codex-cli-desktop", skills, hooks, apply=True)


def test_profiles_are_canonical_and_have_distinct_inventories() -> None:
    config = load_capability_config(ROOT / "config" / "capability-sources.json")
    assert config.required_runtimes == ("claude-code", "codex-cli-desktop")
    assert set(config.packs) == {
        "code_app",
        "hybrid_pipeline",
        "infra_runtime",
        "content_workspace",
    }
    inventories = {(pack.plugins, pack.agents, pack.commands) for pack in config.packs.values()}
    assert len(inventories) == 4
    assert set(config.commands) == {
        ".claude/commands/analyze-design.md",
        ".claude/commands/audit-design-fit.md",
        ".claude/commands/develop-from-design.md",
        ".claude/commands/review-code.md",
        ".claude/commands/role-split-pipeline.md",
        ".claude/commands/verify-against-spec.md",
    }
    for pack in config.packs.values():
        assert pack.commands == tuple(config.commands)
        selected_skills = {
            f"{plugin}:{skill}"
            for plugin in pack.plugins
            for skill in config.plugin_skills[plugin]
        }
        assert {config.commands[path] for path in pack.commands} <= selected_skills
    assert config.resolve_profile("hybrid")[0] == "hybrid_pipeline"
    assert config.resolve_profile("infra")[0] == "infra_runtime"
    assert {
        "config/project-hooks.json",
        ".claude/settings.json",
        ".codex/hooks.json",
        ".codex/config.toml",
    } <= set(config.required_project_paths)


# @spec QR-003
def test_repository_lock_is_portable_and_matches_managed_trees() -> None:
    lock = json.loads((ROOT / ".mir" / "capability-lock.json").read_text(encoding="utf-8"))
    commit = lock["source"]["commit"]
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        check=False,
    )
    assert ancestry.returncode == 0
    assert str(ROOT) not in json.dumps(lock)
    assert "materialized_root" not in lock
    for metadata in lock["plugins"].values():
        assert _tree_digest(ROOT / metadata["path"]) == metadata["sha256"]
    for path, metadata in lock["agents"].items():
        source_bytes = subprocess.check_output(
            ["git", "show", f"{commit}:{path}"],
            cwd=ROOT,
        )
        assert hashlib.sha256(source_bytes).hexdigest() == metadata["sha256"]
        assert _file_digest(ROOT / path) == metadata["sha256"]


def test_manager_recovers_verified_external_provider_from_codex_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MIR_CAPABILITY_HOME", raising=False)
    project = make_project(tmp_path)
    bridge_home = tmp_path / "bridge-home"
    codex_home = bridge_home / ".codex"
    provider_home = tmp_path / "external" / "mir" / "capabilities"
    active = provider_home / "active"
    active.mkdir(parents=True)
    source_url = load_capability_config(
        project / "config" / "capability-sources.json"
    ).source_url
    (provider_home / "active.json").write_text(
        json.dumps(
            {
                "source_url": source_url,
                "materialized_root": str(active),
            }
        ),
        encoding="utf-8",
    )
    codex_home.mkdir(parents=True)
    (codex_home / "config.toml").write_text(
        "\n".join(
            [
                "[marketplaces.mir-yoke]",
                'source_type = "local"',
                f'source = "{active}"',
            ]
        ),
        encoding="utf-8",
    )

    manager = CapabilityManager(
        project,
        user_home=bridge_home,
        codex_home=codex_home,
    )

    assert manager.capability_home == provider_home.resolve()


def test_sync_materializes_exact_lock_and_requires_restart(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )

    dry_run = manager.sync("code_app")
    assert dry_run["dry_run"] is True
    assert not (project / ".mir" / "capability-lock.json").exists()
    assert not capability_home.exists()

    applied = manager.sync("code_app", apply=True)
    assert applied["registration_status"] == "restart-required"
    lock = json.loads((project / ".mir" / "capability-lock.json").read_text())
    assert lock["schema_version"] == 2
    assert lock["source"]["commit"] == SHA_A
    assert set(lock["plugins"]) == {"mir-core", "mir-code", "mir-lifecycle-hooks"}
    assert {metadata["package_kind"] for metadata in lock["plugins"].values()} == {
        "skills",
        "skills-hooks",
    }
    assert set(lock["agents"]) == set(manager.config.packs["code_app"].agents)
    assert set(lock["commands"]) == set(manager.config.packs["code_app"].commands)
    assert lock["registration"] == {"status": "restart-required"}
    assert set(lock["marketplaces"]) == {
        ".claude-plugin/marketplace.json",
        ".agents/plugins/marketplace.json",
    }
    receipt = json.loads((capability_home / "active.json").read_text())
    assert receipt["schema_version"] == 2
    assert receipt["marketplaces"] == lock["marketplaces"]
    assert set(receipt["plugins"]) == {"mir-core", "mir-code", "mir-lifecycle-hooks"}
    assert set(receipt["materialized_plugins"]) == set(manager.config.plugins)
    registry = json.loads((capability_home / "consumers.json").read_text())
    assert registry["schema_version"] == 2
    assert registry["active_plugins"] == receipt["plugins"]
    assert "materialized_root" not in lock
    assert all((project / path).is_file() for path in lock["agents"])
    assert all((project / path).is_file() for path in lock["commands"])
    assert (capability_home / "active" / "plugins" / "mir-core").is_dir()

    status = manager.status()
    assert status["ready"] is False
    assert status["activation"]["status"] == "restart-required"
    assert set(status["managed_surfaces"]) == {
        "agents",
        "skills",
        "commands",
        "hooks",
        "mcp_servers",
    }
    hook_surfaces = status["managed_surfaces"]["hooks"]
    assert hook_surfaces["delivery"] == "host-plugin-and-target-local-generated"
    assert hook_surfaces["global_plugins"] == {
        "mir-lifecycle-hooks": ["SessionStart"]
    }
    assert hook_surfaces["repository_coupled"]["delivery"] == (
        "target-local-generated"
    )
    assert (
        status["managed_surfaces"]["mcp_servers"]["plugin_package_kind"]
        == "reserved"
    )

    marketplace = capability_home / "active" / ".agents" / "plugins" / "marketplace.json"
    marketplace_payload = json.loads(marketplace.read_text(encoding="utf-8"))
    marketplace_payload["interface"]["displayName"] = "Tampered but structurally valid"
    marketplace.write_text(json.dumps(marketplace_payload), encoding="utf-8")
    assert manager.status()["active_integrity"] is False


def test_should_report_and_lock_commands_when_sync_applies(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )

    dry_run = manager.sync("hybrid_pipeline")
    assert set(dry_run["command_changes"]) == set(manager.config.commands)
    assert set(dry_run["command_skill_map"].values()) == {
        "mir-core:design",
        "mir-core:verify",
    }

    manager.sync("hybrid_pipeline", apply=True)
    lock = json.loads(manager.lock_path.read_text(encoding="utf-8"))
    for source_path, skill in manager.config.commands.items():
        assert lock["commands"][source_path]["codex_skill"] == skill
        assert _file_digest(project / source_path) == lock["commands"][source_path][
            "sha256"
        ]
    assert set(manager.status()["command_status"].values()) == {"unchanged"}

    command = next(iter(lock["commands"]))
    lock["commands"][command]["codex_skill"] = "mir-core:commit"
    manager.lock_path.write_text(json.dumps(lock), encoding="utf-8")
    assert manager.status()["command_status"][command] == "mapping-mismatch"
    with pytest.raises(CapabilityError, match="skill mapping diverged"):
        manager.update("hybrid_pipeline", apply=True)


def test_profile_materializes_only_its_selected_agent_pack(tmp_path: Path) -> None:
    project = make_project(tmp_path, real_derivatives=True)
    for source_path in load_capability_config(ROOT / "config" / "capability-sources.json").agents:
        target = project / source_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source_path, target)
    stale_codex_agent = project / ".codex" / "agents" / "stale-agent.toml"
    stale_codex_agent.parent.mkdir(parents=True)
    stale_codex_agent.write_text('name = "stale-agent"\n', encoding="utf-8")
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_with_real_derivatives(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )

    manager.sync("content_workspace", apply=True)

    selected = set(manager.config.packs["content_workspace"].agents)
    for source_path in manager.config.agents:
        assert (project / source_path).exists() is (source_path in selected)
    assert {path.stem for path in (project / ".codex" / "agents").glob("*.toml")} == {
        Path(source_path).stem for source_path in selected
    }


def test_should_keep_global_plugin_union_for_two_consumers(tmp_path: Path) -> None:
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    runner = runtime_runner(capability_home / "active", codex_home)
    first = CapabilityManager(
        make_project(tmp_path, "first"),
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    second = CapabilityManager(
        make_project(tmp_path, "second"),
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )

    first.sync("hybrid_pipeline", apply=True)
    second.sync("code_app", apply=True)

    expected = {"mir-core", "mir-code", "mir-content", "mir-lifecycle-hooks"}
    registry = json.loads(first.registry_path.read_text(encoding="utf-8"))
    receipt = json.loads(first.active_receipt_path.read_text(encoding="utf-8"))
    codex = tomllib.loads((codex_home / "config.toml").read_text(encoding="utf-8"))
    assert set(registry["active_plugins"]) == expected
    assert set(receipt["plugins"]) == expected
    assert {
        key.split("@", 1)[0] for key in codex["plugins"]
    } == expected
    assert first.status()["active_integrity"] is True
    assert second.status()["active_integrity"] is True


def test_should_serialize_concurrent_sync_before_preserving_both_consumers(
    tmp_path: Path,
) -> None:
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    runner = runtime_runner(capability_home / "active", codex_home)
    managers = (
        CapabilityManager(
            make_project(tmp_path, "first"),
            capability_home=capability_home,
            user_home=tmp_path / "user",
            codex_home=codex_home,
            git=CopyGit(),
            command_runner=runner,
            which=lambda executable: f"/fake/{executable}",
        ),
        CapabilityManager(
            make_project(tmp_path, "second"),
            capability_home=capability_home,
            user_home=tmp_path / "user",
            codex_home=codex_home,
            git=CopyGit(),
            command_runner=runner,
            which=lambda executable: f"/fake/{executable}",
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(managers[0].sync, "hybrid_pipeline", apply=True),
            executor.submit(managers[1].sync, "code_app", apply=True),
        )
        completed: list[int] = []
        rejected: list[int] = []
        for index, future in enumerate(futures):
            try:
                result = future.result()
            except CapabilityError as exc:
                assert "another capability apply is active" in str(exc)
                rejected.append(index)
            else:
                assert result["registration_status"] == "restart-required"
                completed.append(index)

    assert completed
    for index in rejected:
        retry_profile = "hybrid_pipeline" if index == 0 else "code_app"
        assert managers[index].sync(retry_profile, apply=True)[
            "registration_status"
        ] == "restart-required"

    registry = json.loads(managers[0].registry_path.read_text(encoding="utf-8"))
    assert len(registry["consumers"]) == 2
    assert set(registry["active_plugins"]) == {
        "mir-core",
        "mir-code",
        "mir-content",
        "mir-lifecycle-hooks",
    }


def test_should_restore_exact_plugin_set_when_profile_update_rolls_back(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    base_runner = runtime_runner(capability_home / "active", codex_home)
    fail_derivative_once = False

    def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal fail_derivative_once
        if Path(args[0]).name == "bash" and fail_derivative_once:
            fail_derivative_once = False
            return subprocess.CompletedProcess(args, 1, "", "forced derivative failure")
        return base_runner(args, **kwargs)

    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("code_app", apply=True)
    fail_derivative_once = True

    with pytest.raises(CapabilityError, match="local rollback was complete"):
        manager.sync("content_workspace", apply=True)

    codex = tomllib.loads((codex_home / "config.toml").read_text(encoding="utf-8"))
    assert {key.split("@", 1)[0] for key in codex["plugins"]} == {
        "mir-core",
        "mir-code",
        "mir-lifecycle-hooks",
    }


def test_rollback_rejects_inflated_schema2_prior_consumer_union_before_commands(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    base_runner = runtime_runner(capability_home / "active", codex_home)
    fail_derivative_once = False
    commands: list[list[str]] = []

    def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal fail_derivative_once
        commands.append(args)
        if Path(args[0]).name == "bash" and fail_derivative_once:
            fail_derivative_once = False
            return subprocess.CompletedProcess(args, 1, "", "forced derivative failure")
        return base_runner(args, **kwargs)

    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("code_app", apply=True)
    receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
    registry = json.loads(manager.registry_path.read_text(encoding="utf-8"))
    inflated_digest = receipt["materialized_plugins"]["mir-content"]
    receipt["plugins"]["mir-content"] = inflated_digest
    registry["active_plugins"]["mir-content"] = inflated_digest
    manager.active_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manager.registry_path.write_text(json.dumps(registry), encoding="utf-8")
    commands.clear()
    fail_derivative_once = True

    with pytest.raises(CapabilityError, match="local rollback was incomplete"):
        manager.sync("code_app", apply=True)

    assert not any(
        args[1:3] in (["plugin", "install"], ["plugin", "add"])
        and "mir-content@mir-yoke" in args
        for args in commands
    )


def test_apply_rejects_symlinked_codex_before_derivative_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    original_install = manager._install_and_verify
    outside = tmp_path / "outside-codex"

    def install_then_redirect(*args: object, **kwargs: object) -> dict[str, object]:
        result = original_install(*args, **kwargs)
        shutil.move(str(project / ".codex"), outside)
        (project / ".codex").symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(manager, "_install_and_verify", install_then_redirect)

    with pytest.raises(CapabilityError, match="local rollback was incomplete"):
        manager.sync("code_app", apply=True)

    assert ".codex/hooks.json" in manager._missing_project_paths()
    assert not (outside / "agents").exists()
    assert not (outside / "README.md").exists()


def test_apply_rejects_symlinked_codex_hooks_before_derivative_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    original_install = manager._install_and_verify
    outside = tmp_path / "outside-hooks"
    (project / ".codex" / "hooks").mkdir()

    def install_then_redirect(*args: object, **kwargs: object) -> dict[str, object]:
        result = original_install(*args, **kwargs)
        shutil.move(str(project / ".codex" / "hooks"), outside)
        (outside / "marker").write_text("preserve\n", encoding="utf-8")
        (project / ".codex" / "hooks").symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(manager, "_install_and_verify", install_then_redirect)

    with pytest.raises(CapabilityError, match="local rollback was incomplete"):
        manager.sync("code_app", apply=True)

    assert (outside / "marker").read_text(encoding="utf-8") == "preserve\n"
    assert not (outside / "lib").exists()


def test_apply_rejects_replaced_project_root_before_generator_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    commands: list[list[str]] = []
    base_runner = runtime_runner(capability_home / "active", codex_home)

    def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return base_runner(args, **kwargs)

    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    original_install = manager._install_and_verify
    replacement_lock = project / ".mir" / "capability-lock.json"

    def install_then_replace_root(*args: object, **kwargs: object) -> dict[str, object]:
        result = original_install(*args, **kwargs)
        project.rename(tmp_path / "original-project")
        project.mkdir()
        replacement_lock.parent.mkdir()
        replacement_lock.write_text("replacement sentinel\n", encoding="utf-8")
        return result

    monkeypatch.setattr(manager, "_install_and_verify", install_then_replace_root)

    with pytest.raises(CapabilityError, match="local rollback was incomplete"):
        manager.sync("code_app", apply=True)

    assert not any(Path(args[0]).name == "bash" for args in commands)
    assert replacement_lock.read_text(encoding="utf-8") == "replacement sentinel\n"


def test_should_restore_local_state_when_apply_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    interrupted = False

    def interrupt_once(*, raise_on_error: bool = True) -> bool:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return True

    monkeypatch.setattr(manager, "_regenerate_agent_derivatives", interrupt_once)

    with pytest.raises(KeyboardInterrupt):
        manager.sync("code_app", apply=True)

    assert not manager.active_path.exists()
    assert not manager.lock_path.exists()
    assert not manager.active_receipt_path.exists()
    assert not any((project / path).exists() for path in manager.config.commands)


# @spec CR-004 FR-005
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
    codex_home = tmp_path / "codex-home"
    runner = runtime_runner(capability_home / "active", codex_home)
    base = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    base.sync("content_workspace", apply=True)

    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    assert manager.finalize()["ready_to_finalize"] is False
    with pytest.raises(CapabilityError, match="runtime skill discovery"):
        manager.finalize(apply=True, after_restart=True)
    attest_codex_runtime(manager)
    assert manager.finalize()["ready_to_finalize"] is False
    discovery = manager.finalize()["discovery"]
    assert discovery["required_runtimes"] == ["claude-code", "codex-cli-desktop"]
    assert discovery["runtimes"]["claude-code"]["status"] == "missing"
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("CLAUDE_SESSION_ID", "claude-new-session")
        manager.attest(
            "claude-code",
            observed_skills(manager),
            observed_hooks(manager),
            apply=True,
        )
    assert manager.finalize()["ready_to_finalize"] is True
    finalized = manager.finalize(apply=True, after_restart=True)
    assert finalized["activation"]["status"] == "active"
    assert manager.status()["ready"] is True


def test_finalize_requires_fresh_observation_of_selected_plugin_hooks(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("content_workspace", apply=True)

    # Runtime installation/listing only proves registration, not hook execution.
    assert manager.finalize()["ready_to_finalize"] is False
    skills = observed_skills(manager)
    hooks = observed_hooks(manager)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("CODEX_THREAD_ID", "codex-new-session")
        with pytest.raises(CapabilityError, match="missing expected hooks"):
            manager.attest("codex-cli-desktop", skills, apply=True)
        codex_receipt = manager.attest("codex-cli-desktop", skills, hooks, apply=True)
        monkeypatch.setenv("CLAUDE_SESSION_ID", "claude-new-session")
        claude_receipt = manager.attest("claude-code", skills, hooks, apply=True)

    assert codex_receipt["attestation_kind"] == "operator-observed-runtime-catalog-and-hooks"
    assert claude_receipt["attestation_kind"] == "operator-observed-runtime-catalog-and-hooks"
    assert codex_receipt["missing_hooks"] == []
    receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
    discovery = receipt["discovery"][str(project)]
    assert discovery["codex-cli-desktop"]["observed_hooks"] == hooks
    assert discovery["claude-code"]["observed_hooks"] == hooks
    assert manager.finalize()["ready_to_finalize"] is True


def test_skills_only_legacy_attestation_does_not_require_hook_observations(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    use_schema2_capability_source(project)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("content_workspace", apply=True)
    skills = observed_skills(manager)
    assert observed_hooks(manager) == []

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("CODEX_THREAD_ID", "codex-new-session")
        manager.attest("codex-cli-desktop", skills, apply=True)
        monkeypatch.setenv("CLAUDE_SESSION_ID", "claude-new-session")
        manager.attest("claude-code", skills, apply=True)

    assert manager.finalize()["ready_to_finalize"] is True


def test_claude_plugin_id_is_normalized_for_runtime_evidence(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    base_runner = runtime_runner(capability_home / "active", codex_home)

    def claude_id_runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if Path(args[0]).name != "claude" or args[1:3] != ["plugin", "list"]:
            return base_runner(args, **kwargs)
        listed = base_runner(args, **kwargs)
        entries = json.loads(listed.stdout)
        for entry in entries:
            entry["id"] = f"{entry.pop('name')}@mir-yoke"
            entry["installPath"] = entry.pop("installedPath")
        return subprocess.CompletedProcess(args, 0, json.dumps(entries), "")

    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=claude_id_runner,
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("content_workspace", apply=True)

    attest_both_runtimes(manager)
    assert manager.finalize()["ready_to_finalize"] is True


def test_codex_source_path_without_persistent_install_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"

    def source_only_runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[1:3] != ["plugin", "list"]:
            return subprocess.CompletedProcess(args, 0, "{}", "")
        entries = [
            {
                "name": plugin.name,
                "enabled": True,
                "installed": True,
                "installPath": str(plugin),
                "source": {"source": "local", "path": str(plugin)},
                "version": "0.8.0",
            }
            for plugin in sorted((capability_home / "active" / "plugins").iterdir())
        ]
        payload: object = entries if Path(args[0]).name == "claude" else {"installed": entries}
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=tmp_path / "codex-home",
        git=CopyGit(),
        command_runner=source_only_runner,
        which=lambda executable: f"/fake/{executable}",
    )

    with pytest.raises(CapabilityError, match="runtime plugin registration failed"):
        manager.sync("content_workspace", apply=True)
    assert not manager.lock_path.exists()


def test_codex_hidden_cli_entry_cannot_bypass_persistent_enabled_set(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("content_workspace", apply=True)
    config_path = codex_home / "config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + '[plugins."mir-code@mir-yoke"]\n'
        + "enabled = true\n",
        encoding="utf-8",
    )

    status = manager.status()

    codex_evidence = status["activation"]["runtimes"]["codex-cli-desktop"]
    assert codex_evidence["verified"] is False
    assert codex_evidence["plugins"]["persistent-config"]["status"] == "enabled-set-mismatch"
    assert status["ready"] is False


def test_codex_probe_rejects_symlinked_cache_component(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("code_app", apply=True)
    cache_root = codex_home / "plugins" / "cache" / "mir-yoke"
    outside = tmp_path / "outside-cache"
    shutil.move(str(cache_root), outside)
    cache_root.symlink_to(outside, target_is_directory=True)
    lock = json.loads(manager.lock_path.read_text(encoding="utf-8"))

    evidence = manager._probe_runtime("codex", ["plugin", "list", "--json"], lock["plugins"])

    assert evidence["verified"] is False
    assert evidence["plugins"]["mir-core"]["status"] == "codex-plugin-cache-path-unsafe"


def test_codex_probe_rejects_parent_swapped_after_home_anchor(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_parent = tmp_path / "codex-parent"
    codex_home = codex_parent / "home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("code_app", apply=True)
    outside = tmp_path / "outside-codex-parent"
    shutil.move(str(codex_parent), outside)
    codex_parent.symlink_to(outside, target_is_directory=True)
    lock = json.loads(manager.lock_path.read_text(encoding="utf-8"))

    evidence = manager._probe_runtime("codex", ["plugin", "list", "--json"], lock["plugins"])

    assert evidence == {"verified": False, "reason": "codex-home-unsafe"}


def test_codex_probe_and_install_reject_replaced_home_identity(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("code_app", apply=True)
    lock = json.loads(manager.lock_path.read_text(encoding="utf-8"))
    codex_home.rename(tmp_path / "original-codex-home")
    codex_home.mkdir()

    probe = manager._probe_runtime("codex", ["plugin", "list", "--json"], lock["plugins"])
    install = manager._install_and_verify(
        manager._registration_plan(["mir-core", "mir-code"]),
        lock["plugins"],
    )

    assert probe == {"verified": False, "reason": "codex-home-unsafe"}
    assert install["install_attempts"]["codex-cli-desktop"]["status"] == "codex-home-unsafe"


def test_source_path_is_not_an_installed_path_fallback() -> None:
    assert _installed_path({"source": {"path": "/provider/source"}}) is None


def test_registration_plan_names_hook_trust_and_observation(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    manager = CapabilityManager(
        project,
        capability_home=tmp_path / "capability-home",
        user_home=tmp_path / "user",
        codex_home=tmp_path / "codex-home",
        git=CopyGit(),
        command_runner=lambda _command: subprocess.CompletedProcess([], 0, "", ""),
        which=lambda executable: f"/fake/{executable}",
    )

    next_step = manager._registration_plan(["mir-lifecycle-hooks"])["next_step"]

    assert "trust the exact installed hook digest" in next_step
    assert "observed hook" in next_step


def test_attest_requires_expected_skills_and_new_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_THREAD_ID", "install-session")
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("content_workspace", apply=True)
    skills = observed_skills(manager)

    with pytest.raises(CapabilityError, match="missing expected skills"):
        manager.attest(
            "codex-cli-desktop",
            skills[:-1],
            observed_hooks(manager),
            apply=True,
        )
    with pytest.raises(CapabilityError, match="new runtime session"):
        manager.attest(
            "codex-cli-desktop",
            skills,
            observed_hooks(manager),
            apply=True,
        )

    monkeypatch.setenv("CODEX_THREAD_ID", "new-session")
    receipt = manager.attest(
        "codex-cli-desktop", skills, observed_hooks(manager), apply=True
    )
    assert receipt["status"] == "attested"
    assert receipt["attestation_kind"] == "operator-observed-runtime-catalog-and-hooks"
    assert manager.finalize()["discovery"]["status"] == "incomplete"


@pytest.mark.parametrize("operation", ["attest", "finalize"])
def test_apply_attestation_and_finalization_revalidate_state_inside_apply_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, operation: str
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("content_workspace", apply=True)
    monkeypatch.setenv("CODEX_THREAD_ID", "new-session")
    if operation == "finalize":
        manager.attest(
            "codex-cli-desktop",
            observed_skills(manager),
            observed_hooks(manager),
            apply=True,
        )

    original_safety_check = manager._assert_project_lock_path_safe

    def corrupt_state_after_guard_is_acquired() -> None:
        original_safety_check()
        assert (capability_home / ".apply.lock").is_dir()
        receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
        receipt["commit"] = "b" * 40
        manager.active_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    monkeypatch.setattr(
        manager,
        "_assert_project_lock_path_safe",
        corrupt_state_after_guard_is_acquired,
    )

    if operation == "attest":
        with pytest.raises(CapabilityError, match="failed current validation"):
            manager.attest(
                "codex-cli-desktop",
                observed_skills(manager),
                observed_hooks(manager),
                apply=True,
            )
    else:
        with pytest.raises(CapabilityError, match="failed current validation"):
            manager.finalize(apply=True, after_restart=True)


def test_missing_claude_cli_prevents_successful_registration(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: None if executable == "claude" else f"/fake/{executable}",
    )

    with pytest.raises(CapabilityError, match="runtime plugin registration failed"):
        manager.sync("content_workspace", apply=True)


def test_sync_apply_fails_when_required_codex_cli_is_missing(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: None if executable == "codex" else f"/fake/{executable}",
    )

    with pytest.raises(CapabilityError, match="registration failed"):
        manager.sync("content_workspace", apply=True)


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
    assert not (project / ".mir" / "capability-lock.json").exists()
    assert not (tmp_path / "home" / "active").exists()
    assert manager.status()["ready"] is False


def test_failed_reregistration_restores_provider_agents_and_state(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    fail = False
    failed_commands: list[list[str]] = []
    base_runner = runtime_runner(capability_home / "active", codex_home)

    def toggled_runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if fail:
            failed_commands.append(args)
            return subprocess.CompletedProcess(args, 1, "", "forced failure")
        return base_runner(args, **kwargs)

    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=toggled_runner,
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("code_app", apply=True)
    receipt_path = capability_home / "active.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["schema_version"] = 1
    receipt["plugins"]["mir-content"] = receipt["materialized_plugins"]["mir-content"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert manager.status()["active_integrity"] is False
    marker = capability_home / "active" / "previous-provider-marker"
    marker.write_text("preserve\n", encoding="utf-8")
    tracked = [
        project / ".mir" / "capability-lock.json",
        capability_home / "consumers.json",
        capability_home / "active.json",
        project / ".claude" / "agents" / "main-orchestrator.md",
        project / ".claude" / "commands" / "analyze-design.md",
    ]
    before = {path: path.read_bytes() for path in tracked}

    fail = True
    with pytest.raises(CapabilityError, match="local rollback was incomplete"):
        manager.sync("code_app", apply=True)

    assert marker.read_text(encoding="utf-8") == "preserve\n"
    assert {path: path.read_bytes() for path in tracked} == before
    assert not (capability_home / ".active.previous").exists()
    assert not any(
        args[1:3] in (["plugin", "install"], ["plugin", "add"])
        and "mir-content@mir-yoke" in args
        for args in failed_commands
    )


def test_rollback_rejects_tampered_previous_marketplace_before_commands(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    fail = False
    failed_commands: list[list[str]] = []
    base_runner = runtime_runner(capability_home / "active", codex_home)

    def toggled_runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if fail:
            failed_commands.append(args)
            return subprocess.CompletedProcess(args, 1, "", "forced failure")
        return base_runner(args, **kwargs)

    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=toggled_runner,
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("code_app", apply=True)
    marketplace = capability_home / "active" / ".agents" / "plugins" / "marketplace.json"
    payload = json.loads(marketplace.read_text(encoding="utf-8"))
    payload["plugins"][0]["source"] = {
        "source": "git",
        "url": "https://example.invalid/plugin.git",
    }
    marketplace.write_text(json.dumps(payload), encoding="utf-8")

    fail = True
    with pytest.raises(CapabilityError, match="local rollback was incomplete"):
        manager.sync("code_app", apply=True)

    marketplace_adds = [
        args
        for args in failed_commands
        if "plugin" in args and "marketplace" in args and "add" in args
    ]
    assert len(marketplace_adds) == 2


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


def test_cli_accepts_runtime_skill_and_hook_attestation(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    calls: list[tuple[str, tuple[str, ...], tuple[str, ...], bool]] = []

    class FakeManager:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def attest(
            self,
            runtime: str,
            observed_skills: list[str],
            observed_hooks: list[str],
            *,
            apply: bool,
        ) -> dict[str, object]:
            calls.append((runtime, tuple(observed_skills), tuple(observed_hooks), apply))
            return {"operation": "attest", "dry_run": not apply}

    monkeypatch.setattr(capability_cli, "CapabilityManager", FakeManager)
    exit_code = capability_cli.main(
        [
            "attest",
            "--project-root",
            str(tmp_path),
            "--runtime",
            "codex-cli-desktop",
            "--observed-skill",
            "mir-core:design",
            "--observed-skill",
            "mir-core:verify",
            "--observed-hook",
            "mir-lifecycle-hooks:SessionStart",
            "--apply",
            "--json",
        ]
    )
    assert exit_code == 0
    assert calls == [
        (
            "codex-cli-desktop",
            ("mir-core:design", "mir-core:verify"),
            ("mir-lifecycle-hooks:SessionStart",),
            True,
        )
    ]
    assert json.loads(capsys.readouterr().out)["dry_run"] is False


def test_cli_rejects_operator_supplied_session_id() -> None:
    with pytest.raises(SystemExit) as exc:
        capability_cli.main(
            [
                "attest",
                "--runtime",
                "codex-cli-desktop",
                "--session-id",
                "forged-session",
            ]
        )
    assert exc.value.code == 2
