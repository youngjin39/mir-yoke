"""Fail-closed capability source, collision, and consumer tests."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from test_capability_cli import CopyGit, make_project, runtime_runner

from mir.core.capabilities import CapabilityConfigError, CapabilityError, CapabilityManager
from mir.core.capabilities.config import load_capability_config
from mir.core.capabilities.manager import (
    GitClient,
    _tree_digest,
    _validate_marketplaces,
    _validate_plugin,
)

ROOT = Path(__file__).resolve().parents[1]


def mutated_config(tmp_path: Path, mutation) -> Path:
    payload = json.loads((ROOT / "config" / "capability-sources.json").read_text())
    mutation(payload)
    path = tmp_path / "capability-sources.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def use_schema2_capability_source(project: Path) -> None:
    path = project / "config" / "capability-sources.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    payload["plugins"].pop("mir-lifecycle-hooks")
    payload.pop("active_package_digest_acknowledgements")
    payload.pop("commands")
    payload.pop("project_integrations")
    payload["agents"].pop("provider_local")
    for pack in payload["profiles"]["packs"].values():
        pack.pop("commands")
        pack["plugins"].remove("mir-lifecycle-hooks")
    path.write_text(json.dumps(payload), encoding="utf-8")


def schema1_capability_source_payload() -> dict[str, object]:
    """The fixed public schema-1 shape, reconstructed without Git history."""
    current = json.loads((ROOT / "config" / "capability-sources.json").read_text())
    legacy_plugins = ("mir-core", "mir-code", "mir-content")
    current["schema_version"] = 1
    current["plugins"] = {
        name: {
            "path": current["plugins"][name]["path"],
            "skills": current["plugins"][name]["skills"],
        }
        for name in legacy_plugins
    }
    current.pop("plugin_component_policy")
    current.pop("active_package_digest_acknowledgements")
    current.pop("commands")
    current.pop("project_integrations")
    current["agents"].pop("provider_local")
    for pack in current["profiles"]["packs"].values():
        pack["plugins"] = [name for name in pack["plugins"] if name in legacy_plugins]
        pack.pop("commands")
    current["required_project_paths"] = [
        "CLAUDE.md",
        "AGENTS.md",
        ".ai-harness",
        "tasks",
        "config",
        ".claude/agents",
        "scripts/generate_codex_derivatives.sh",
    ]
    current["policy"]["activation_required_runtimes"] = ["codex-cli-desktop"]
    return current


def test_previous_public_schema1_capability_source_remains_readable(tmp_path: Path) -> None:
    path = tmp_path / "capability-sources.json"
    path.write_text(json.dumps(schema1_capability_source_payload()), encoding="utf-8")

    config = load_capability_config(path)

    assert config.source_schema_version == 1
    assert set(config.plugin_kinds.values()) == {"skills"}
    assert config.plugin_hooks == {}
    assert config.commands == {}
    assert config.project_integrations == {}
    assert config.required_runtimes == ("codex-cli-desktop",)
    assert all(not pack.commands for pack in config.packs.values())


def test_schema1_capability_source_cannot_admit_hook_packages(tmp_path: Path) -> None:
    legacy = schema1_capability_source_payload()
    legacy["plugins"]["mir-core"]["package_kind"] = "skills-hooks"
    legacy["plugins"]["mir-core"]["hooks"] = ["SessionStart"]
    path = tmp_path / "capability-sources.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    with pytest.raises(CapabilityConfigError, match="metadata must contain only"):
        load_capability_config(path)


def downgrade_lock_to_genuine_legacy_consumer(
    manager: CapabilityManager,
) -> dict[str, object]:
    lock = json.loads(manager.lock_path.read_text(encoding="utf-8"))
    legacy_plugins = {
        name: {"path": metadata["path"], "sha256": metadata["sha256"]}
        for name, metadata in lock["plugins"].items()
        if name != "mir-lifecycle-hooks"
    }
    lock["schema_version"] = 1
    lock["plugins"] = legacy_plugins
    lock.pop("consumer_binding")
    lock.pop("marketplaces")
    lock.pop("commands")
    manager.lock_path.write_text(json.dumps(lock), encoding="utf-8")
    return {
        "commit": lock["source"]["commit"],
        "plugins": {name: metadata["sha256"] for name, metadata in legacy_plugins.items()},
        "profile": lock["profile"],
    }


def downgrade_to_genuine_legacy_consumer(manager: CapabilityManager) -> None:
    registry = json.loads(manager.registry_path.read_text(encoding="utf-8"))
    registry["schema_version"] = 1
    registry.pop("active_plugins")
    registry["consumers"] = {
        str(manager.project_root): downgrade_lock_to_genuine_legacy_consumer(manager)
    }
    manager.registry_path.write_text(json.dumps(registry), encoding="utf-8")
    manager.consumer_bindings_path.unlink()


def test_legacy_consumers_enroll_bindings_one_at_a_time_without_registry_deadlock(
    tmp_path: Path,
) -> None:
    capability_home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    runner = runtime_runner(capability_home / "active", codex_home)
    projects = [make_project(tmp_path, name) for name in ("first", "second")]
    managers = [
        CapabilityManager(
            project,
            capability_home=capability_home,
            user_home=tmp_path / "user",
            codex_home=codex_home,
            git=CopyGit(),
            command_runner=runner,
            which=lambda executable: f"/fake/{executable}",
        )
        for project in projects
    ]
    for manager in managers:
        manager.sync("code_app", apply=True)

    registry = json.loads(managers[0].registry_path.read_text(encoding="utf-8"))
    registry["schema_version"] = 1
    registry.pop("active_plugins")
    registry["consumers"] = {
        str(manager.project_root): downgrade_lock_to_genuine_legacy_consumer(manager)
        for manager in managers
    }
    managers[0].registry_path.write_text(json.dumps(registry), encoding="utf-8")
    managers[0].consumer_bindings_path.unlink()

    managers[0].sync("code_app", apply=True)
    first_registry = json.loads(managers[0].registry_path.read_text(encoding="utf-8"))
    first_bindings = json.loads(managers[0].consumer_bindings_path.read_text(encoding="utf-8"))[
        "consumers"
    ]
    first_key, second_key = (str(manager.project_root) for manager in managers)
    assert set(first_bindings) == {first_key}
    assert "binding" in first_registry["consumers"][first_key]
    assert "binding" not in first_registry["consumers"][second_key]

    managers[1].sync("code_app", apply=True)
    bindings = json.loads(managers[1].consumer_bindings_path.read_text(encoding="utf-8"))[
        "consumers"
    ]
    registry = json.loads(managers[1].registry_path.read_text(encoding="utf-8"))
    assert set(bindings) == {first_key, second_key}
    assert all("binding" in entry for entry in registry["consumers"].values())


@pytest.mark.parametrize("mutation", ["partial", "mismatched", "invented"])
def test_partial_or_invented_legacy_enrollment_state_is_rejected(
    tmp_path: Path, mutation: str
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "home"
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
    downgrade_to_genuine_legacy_consumer(manager)
    registry = json.loads(manager.registry_path.read_text(encoding="utf-8"))
    consumer_key = str(manager.project_root)
    if mutation == "partial":
        registry["consumers"].pop(consumer_key)
    elif mutation == "mismatched":
        registry["consumers"][consumer_key]["plugins"]["mir-core"] = "0" * 64
    else:
        lock = json.loads(manager.lock_path.read_text(encoding="utf-8"))
        lock["agents"] = {}
        manager.lock_path.write_text(json.dumps(lock), encoding="utf-8")
    manager.registry_path.write_text(json.dumps(registry), encoding="utf-8")

    with pytest.raises(CapabilityError, match="current consumer enrollment is invalid"):
        manager.sync("code_app", apply=True)


def test_schema4_sync_requires_update_for_legacy_lock_missing_selected_plugin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "home"
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
    manager.sync("code_app", apply=True)
    downgrade_to_genuine_legacy_consumer(manager)
    lock = json.loads(manager.lock_path.read_text(encoding="utf-8"))
    registry = json.loads(manager.registry_path.read_text(encoding="utf-8"))
    old_commit = "b" * 40
    lock["source"]["commit"] = old_commit
    registry["active_commit"] = old_commit
    registry["consumers"][str(project)]["commit"] = old_commit
    active_receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
    active_receipt["commit"] = old_commit
    manager.lock_path.write_text(json.dumps(lock), encoding="utf-8")
    manager.registry_path.write_text(json.dumps(registry), encoding="utf-8")
    manager.active_receipt_path.write_text(json.dumps(active_receipt), encoding="utf-8")
    commands.clear()

    exported = False
    original_export = manager.git.export

    def export_must_not_run(*args: object, **kwargs: object) -> None:
        nonlocal exported
        exported = True
        raise AssertionError("sync exported an incompatible old provider")

    monkeypatch.setattr(manager.git, "export", export_must_not_run)
    message = (
        "capability source update required before sync: the current lock lacks newly "
        "selected plugins (mir-lifecycle-hooks); run 'mir capability update --apply'"
    )
    with pytest.raises(CapabilityError, match=re.escape(message)):
        manager.sync("code_app", apply=True)
    assert exported is False
    assert commands == []

    monkeypatch.setattr(manager.git, "export", original_export)
    result = manager.update("code_app", apply=True)
    assert result["applied"] is True
    upgraded = json.loads(manager.lock_path.read_text(encoding="utf-8"))
    assert "mir-lifecycle-hooks" in upgraded["plugins"]


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


@pytest.mark.parametrize(
    "required_runtimes",
    [
        [],
        ["unknown-runtime"],
        ["codex-cli-desktop", "codex-cli-desktop"],
        ["claude-code"],
        ["codex-cli-desktop"],
        ["codex-cli-desktop", "claude-code"],
    ],
)
def test_activation_required_runtimes_reject_invalid_policy(
    tmp_path: Path, required_runtimes: list[str]
) -> None:
    config = mutated_config(
        tmp_path,
        lambda value: value["policy"].update(activation_required_runtimes=required_runtimes),
    )
    with pytest.raises(CapabilityConfigError):
        load_capability_config(config)


@pytest.mark.parametrize("replacement", ["directory", "symlink"])
def test_capability_home_identity_change_blocks_state_and_runtime_use(
    tmp_path: Path, replacement: str
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
    manager.sync("content_workspace", apply=True)
    preserved_home = tmp_path / "preserved-capability-home"
    capability_home.rename(preserved_home)
    redirected = tmp_path / "redirected-capability-home"
    redirected.mkdir()
    if replacement == "directory":
        capability_home.mkdir()
    else:
        capability_home.symlink_to(redirected, target_is_directory=True)
    before = {
        name: (preserved_home / name).read_bytes()
        for name in ("active.json", "consumers.json", "consumer-bindings.json")
    }
    commands.clear()

    with pytest.raises(CapabilityError, match="capability home"):
        manager.status("content_workspace")
    with pytest.raises(CapabilityError, match="capability home"):
        manager.sync("content_workspace", apply=True)
    with pytest.raises(CapabilityError, match="capability home"):
        manager.attest("claude-code", [], apply=True)
    with pytest.raises(CapabilityError, match="capability home"):
        manager.finalize(apply=True, after_restart=True)

    assert commands == []
    assert not (redirected / ".apply.lock").exists()
    assert not (capability_home / ".apply.lock").exists()
    assert {name: (preserved_home / name).read_bytes() for name in before} == before


def test_capability_source_declares_the_reviewed_active_hook_package() -> None:
    config = load_capability_config(ROOT / "config" / "capability-sources.json")

    assert config.plugin_kinds["mir-lifecycle-hooks"] == "skills-hooks"
    assert config.plugin_hooks == {"mir-lifecycle-hooks": ("SessionStart",)}
    assert config.provider_local_agents == (".claude/agents/template-sync-validator.md",)
    assert config.component_policy["admitted_package_kinds"] == ["skills", "skills-hooks"]
    assert config.component_policy["reserved_active_package_kinds"] == ["mcp"]
    acknowledgement = config.active_digest_acknowledgements["mir-lifecycle-hooks"]
    assert acknowledgement == _tree_digest(ROOT / "plugins" / "mir-lifecycle-hooks")


@pytest.mark.parametrize("mutation", ["missing", "selected", "unknown"])
def test_provider_local_agents_are_explicit_and_not_distributed(
    tmp_path: Path, mutation: str
) -> None:
    def mutate(value: dict[str, object]) -> None:
        if mutation == "missing":
            value["agents"].pop("provider_local")
        elif mutation == "selected":
            value["agents"]["provider_local"] = [
                value["profiles"]["packs"]["code_app"]["agents"][0]
            ]
        else:
            value["agents"]["provider_local"] = [".claude/agents/not-declared.md"]

    path = mutated_config(tmp_path, mutate)

    with pytest.raises(CapabilityConfigError, match="provider_local|allowlist"):
        load_capability_config(path)


@pytest.mark.parametrize("kind", [None, "hooks", "mcp", "mixed", "agents"])
def test_plugin_package_kind_is_explicit_and_fail_closed(tmp_path: Path, kind: str | None) -> None:
    def mutate(value: dict[str, object]) -> None:
        plugin = value["plugins"]["mir-core"]
        if kind is None:
            plugin.pop("package_kind")
        else:
            plugin["package_kind"] = kind

    config = mutated_config(tmp_path, mutate)
    with pytest.raises(CapabilityConfigError, match="package_kind"):
        load_capability_config(config)


def test_active_component_policy_is_exact_and_cannot_be_relaxed_locally(
    tmp_path: Path,
) -> None:
    config = mutated_config(
        tmp_path,
        lambda value: value["plugin_component_policy"].update(
            admitted_package_kinds=["skills", "hooks"]
        ),
    )
    with pytest.raises(CapabilityConfigError, match="plugin_component_policy"):
        load_capability_config(config)


def test_plugin_metadata_rejects_undeclared_component_fields(tmp_path: Path) -> None:
    config = mutated_config(
        tmp_path,
        lambda value: value["plugins"]["mir-core"].update(hooks=["pre-tool-use"]),
    )
    with pytest.raises(CapabilityConfigError, match="metadata must contain only"):
        load_capability_config(config)


def test_active_hook_package_requires_an_exact_digest_acknowledgement(
    tmp_path: Path,
) -> None:
    missing = mutated_config(
        tmp_path,
        lambda value: value.pop("active_package_digest_acknowledgements"),
    )
    with pytest.raises(CapabilityConfigError, match="digest acknowledgement"):
        load_capability_config(missing)

    stale = mutated_config(
        tmp_path,
        lambda value: value["active_package_digest_acknowledgements"].update(
            {"mir-lifecycle-hooks": "0" * 64}
        ),
    )
    assert (
        load_capability_config(stale).active_digest_acknowledgements["mir-lifecycle-hooks"]
        == "0" * 64
    )


def test_active_hook_package_rejects_undeclared_hook_files(tmp_path: Path) -> None:
    plugin = tmp_path / "mir-lifecycle-hooks"
    shutil.copytree(ROOT / "plugins" / "mir-lifecycle-hooks", plugin)
    (plugin / "hooks" / "notes.txt").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(CapabilityError, match="shared hook content rejected"):
        _validate_plugin(plugin, "mir-lifecycle-hooks", package_kind="skills-hooks")


@pytest.mark.parametrize("runtime", ["claude", "codex"])
def test_active_hook_package_rejects_duplicate_default_hook_registration(
    tmp_path: Path, runtime: str
) -> None:
    plugin = tmp_path / "mir-lifecycle-hooks"
    shutil.copytree(ROOT / "plugins" / "mir-lifecycle-hooks", plugin)
    manifest = plugin / f".{runtime}-plugin" / "plugin.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["hooks"] = "./hooks/hooks.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CapabilityError, match="manifest keys rejected"):
        _validate_plugin(plugin, "mir-lifecycle-hooks", package_kind="skills-hooks")


@pytest.mark.parametrize("runtime", ["claude", "codex"])
def test_active_hook_package_rejects_undeclared_manifest_files(
    tmp_path: Path, runtime: str
) -> None:
    plugin = tmp_path / "mir-lifecycle-hooks"
    shutil.copytree(ROOT / "plugins" / "mir-lifecycle-hooks", plugin)
    (plugin / f".{runtime}-plugin" / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(CapabilityError, match="shared hook manifest content rejected"):
        _validate_plugin(plugin, "mir-lifecycle-hooks", package_kind="skills-hooks")


@pytest.mark.parametrize(
    ("relative_path", "field", "credential"),
    [
        (
            ".claude-plugin/plugin.json",
            "homepage",
            "https://user:secret@example.invalid/plugin",
        ),
        (
            ".claude-plugin/plugin.json",
            "homepage",
            "https://token@example.invalid/plugin",
        ),
        (
            "skills/runtime-continuity/SKILL.md",
            None,
            "-----BEGIN PRIVATE KEY-----\nprivate\n-----END PRIVATE KEY-----",
        ),
        (
            ".codex-plugin/plugin.json",
            "description",
            "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
        ),
        (
            ".claude-plugin/plugin.json",
            "description",
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        ),
        (
            ".claude-plugin/plugin.json",
            "description",
            "gho_abcdefghijklmnopqrstuvwxyz0123456789",
        ),
        (
            ".codex-plugin/plugin.json",
            "description",
            "AKIAABCDEFGHIJKLMNOP",
        ),
        (
            "skills/runtime-continuity/SKILL.md",
            None,
            "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
        ),
    ],
)
def test_active_hook_package_rejects_credential_bearing_content(
    tmp_path: Path, relative_path: str, field: str | None, credential: str
) -> None:
    plugin = tmp_path / "mir-lifecycle-hooks"
    shutil.copytree(ROOT / "plugins" / "mir-lifecycle-hooks", plugin)
    target = plugin / relative_path
    if field is None:
        target.write_text(f"{target.read_text(encoding='utf-8')}\n{credential}\n", encoding="utf-8")
    else:
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload[field] = credential
        target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CapabilityError, match="credential-bearing content rejected"):
        _validate_plugin(plugin, "mir-lifecycle-hooks", package_kind="skills-hooks")


def test_stale_active_hook_digest_blocks_runtime_registration(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    config_path = project / "config" / "capability-sources.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["active_package_digest_acknowledgements"]["mir-lifecycle-hooks"] = "0" * 64
    config_path.write_text(json.dumps(payload), encoding="utf-8")
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

    with pytest.raises(CapabilityError, match="digest acknowledgement is stale"):
        manager.sync("code_app", apply=True)
    assert commands == []


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
    codex_home = tmp_path / "codex-home"
    manager = CapabilityManager(
        project,
        capability_home=tmp_path / "home",
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(commit="a" * 40),
        command_runner=runtime_runner(tmp_path / "home" / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("content_workspace", apply=True)
    agent = project / ".claude" / "agents" / "main-orchestrator.md"
    agent.write_text("user-owned divergence\n", encoding="utf-8")
    manager.git.commit = "b" * 40
    with pytest.raises(CapabilityError, match="diverged"):
        manager.update("content_workspace", apply=True)
    assert agent.read_text() == "user-owned divergence\n"


def test_initial_sync_refuses_an_existing_unlocked_agent(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    agent = project / ".claude" / "agents" / "main-orchestrator.md"
    agent.write_text("project-owned customization\n", encoding="utf-8")
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

    with pytest.raises(CapabilityError, match="refusing overwrite"):
        manager.sync("content_workspace", apply=True)

    assert agent.read_text(encoding="utf-8") == "project-owned customization\n"
    assert not (project / ".mir" / "capability-lock.json").exists()


def test_should_reject_unsafe_or_unknown_command_mapping(tmp_path: Path) -> None:
    unsafe_path = mutated_config(
        tmp_path,
        lambda value: value["commands"]["allowlist"].update({"../commands/escape.md": "design"}),
    )
    with pytest.raises(CapabilityConfigError, match="command path"):
        load_capability_config(unsafe_path)

    unknown_skill = mutated_config(
        tmp_path,
        lambda value: value["commands"]["allowlist"].update(
            {".claude/commands/analyze-design.md": "missing-skill"}
        ),
    )
    with pytest.raises(CapabilityConfigError, match="unknown skill"):
        load_capability_config(unknown_skill)


def test_should_keep_hook_and_mcp_delivery_target_local(tmp_path: Path) -> None:
    relaxed = mutated_config(
        tmp_path,
        lambda value: value["project_integrations"]["hooks"].update(delivery="host-plugin"),
    )

    with pytest.raises(CapabilityConfigError, match="target-local hook and MCP"):
        load_capability_config(relaxed)

    missing_projection = mutated_config(
        tmp_path,
        lambda value: value["required_project_paths"].remove(".codex/hooks.json"),
    )
    with pytest.raises(CapabilityConfigError, match="managed hook and MCP projections"):
        load_capability_config(missing_projection)


def test_should_keep_schema2_sources_readable_without_managed_commands(
    tmp_path: Path,
) -> None:
    def downgrade(value: dict[str, object]) -> None:
        value["schema_version"] = 2
        value["plugins"].pop("mir-lifecycle-hooks")
        value.pop("active_package_digest_acknowledgements")
        value.pop("commands")
        value.pop("project_integrations")
        value["agents"].pop("provider_local")
        for pack in value["profiles"]["packs"].values():
            pack.pop("commands")
            pack["plugins"].remove("mir-lifecycle-hooks")

    legacy = mutated_config(tmp_path, downgrade)
    config = load_capability_config(legacy)

    assert config.source_schema_version == 2
    assert config.commands == {}
    assert all(pack.commands == () for pack in config.packs.values())


def test_should_refuse_remote_update_when_managed_command_diverges(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    codex_home = tmp_path / "codex-home"
    capability_home = tmp_path / "home"
    manager = CapabilityManager(
        project,
        capability_home=capability_home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(commit="a" * 40),
        command_runner=runtime_runner(capability_home / "active", codex_home),
        which=lambda executable: f"/fake/{executable}",
    )
    manager.sync("content_workspace", apply=True)
    command = project / ".claude" / "commands" / "analyze-design.md"
    command.write_text("project-owned divergence\n", encoding="utf-8")
    manager.git.commit = "b" * 40

    with pytest.raises(CapabilityError, match="command.*diverged"):
        manager.update("content_workspace", apply=True)
    assert command.read_text(encoding="utf-8") == "project-owned divergence\n"


def test_should_refuse_existing_command_symlink_on_first_sync(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    outside = tmp_path / "outside-command.md"
    outside.write_text("consumer owned\n", encoding="utf-8")
    command = project / ".claude" / "commands" / "analyze-design.md"
    command.parent.mkdir(parents=True)
    command.symlink_to(outside)
    capability_home = tmp_path / "home"
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

    preview = manager.sync("code_app")
    assert preview["command_changes"][".claude/commands/analyze-design.md"] == "diverged"
    assert preview["ready_to_apply"] is False
    with pytest.raises(CapabilityError, match="command diverged"):
        manager.sync("code_app", apply=True)
    assert command.is_symlink()
    assert outside.read_text(encoding="utf-8") == "consumer owned\n"


def test_should_reject_unsafe_project_target_from_tampered_lock(tmp_path: Path) -> None:
    manager = CapabilityManager(
        make_project(tmp_path),
        capability_home=tmp_path / "home",
        user_home=tmp_path / "user",
        git=CopyGit(),
    )

    with pytest.raises(CapabilityError, match="project target path is unsafe"):
        manager._project_target("../outside.md")


def test_adr89_should_advance_provider_and_leave_peer_local_integration_pending(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    runner = runtime_runner(home / "active", codex_home)
    first = CapabilityManager(
        make_project(tmp_path, "first"),
        capability_home=home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(commit="a" * 40),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    second = CapabilityManager(
        make_project(tmp_path, "second"),
        capability_home=home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(commit="a" * 40),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    first.sync("infra_runtime", apply=True)
    second.sync("infra_runtime", apply=True)
    second_lock_before = second.lock_path.read_bytes()
    first.git.commit = "b" * 40
    result = first.update("infra_runtime", apply=True)

    assert result["applied"] is True
    registry = json.loads((home / "consumers.json").read_text())
    assert registry["active_commit"] == "b" * 40
    assert second.lock_path.read_bytes() == second_lock_before
    assert second.status()["consumer"]["integration"] == "pending-local-update"

    first_lock_before = first.lock_path.read_bytes()
    second.git.commit = "c" * 40
    catch_up = second.update("infra_runtime", apply=True)

    assert catch_up["required_commit"] == "b" * 40
    assert json.loads((home / "consumers.json").read_text())["active_commit"] == "b" * 40
    assert first.lock_path.read_bytes() == first_lock_before
    assert json.loads(second.lock_path.read_text())["source"]["commit"] == "b" * 40
    assert second.status()["consumer"]["integration"] == "active"


def test_adr89_pending_peer_catchup_uses_receipt_bound_candidate_config(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    runner = runtime_runner(home / "active", codex_home)
    source_b = tmp_path / "provider-b"
    shutil.copytree(ROOT, source_b)
    source_config = source_b / "config" / "capability-sources.json"
    payload = json.loads(source_config.read_text(encoding="utf-8"))
    payload["profiles"]["packs"]["code_app"]["plugins"].append("mir-content")
    source_config.write_text(json.dumps(payload), encoding="utf-8")
    first = CapabilityManager(
        make_project(tmp_path, "first"),
        capability_home=home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(commit="a" * 40),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    second = CapabilityManager(
        make_project(tmp_path, "second"),
        capability_home=home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(commit="a" * 40),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    first.sync("code_app", apply=True)
    second.sync("code_app", apply=True)
    first.git.source = source_b
    first.git.commit = "b" * 40

    first.update("code_app", apply=True)
    assert "mir-content" in json.loads((home / "consumers.json").read_text())["active_plugins"]

    second.git.commit = "c" * 40
    second.update("code_app", apply=True)

    lock = json.loads(second.lock_path.read_text(encoding="utf-8"))
    assert lock["source"]["commit"] == "b" * 40
    assert "mir-content" in lock["plugins"]


def test_adr89_rollback_restores_provider_with_its_prior_bound_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    runner = runtime_runner(home / "active", codex_home)
    source_b = tmp_path / "provider-b"
    shutil.copytree(ROOT, source_b, ignore=shutil.ignore_patterns(".git", ".venv"))
    source_config = source_b / "config" / "capability-sources.json"
    payload = json.loads(source_config.read_text(encoding="utf-8"))
    payload["commands"]["allowlist"][".claude/commands/analyze-design.md"] = "mir-core:verify"
    source_config.write_text(json.dumps(payload), encoding="utf-8")
    first = CapabilityManager(
        make_project(tmp_path, "first"),
        capability_home=home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(commit="a" * 40),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    second = CapabilityManager(
        make_project(tmp_path, "second"),
        capability_home=home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(commit="a" * 40),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    first.sync("code_app", apply=True)
    second.sync("code_app", apply=True)
    before_active = _tree_digest(home / "active")
    before_registry = first.registry_path.read_bytes()
    before_first_lock = first.lock_path.read_bytes()
    before_second_lock = second.lock_path.read_bytes()
    first.git.source = source_b
    first.git.commit = "b" * 40

    def fail_candidate_derivative(*, raise_on_error: bool = True) -> bool:
        if raise_on_error:
            raise CapabilityError("forced derivative failure")
        return True

    monkeypatch.setattr(first, "_regenerate_agent_derivatives", fail_candidate_derivative)

    with pytest.raises(CapabilityError, match="local rollback was complete"):
        first.update("code_app", apply=True)

    assert _tree_digest(home / "active") == before_active
    assert first.registry_path.read_bytes() == before_registry
    assert first.lock_path.read_bytes() == before_first_lock
    assert second.lock_path.read_bytes() == before_second_lock


def test_provider_integrity_does_not_read_peer_local_lock_state(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    codex_home = tmp_path / "codex-home"
    runner = runtime_runner(home / "active", codex_home)
    first = CapabilityManager(
        make_project(tmp_path, "first"),
        capability_home=home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    second = CapabilityManager(
        make_project(tmp_path, "second"),
        capability_home=home,
        user_home=tmp_path / "user",
        codex_home=codex_home,
        git=CopyGit(),
        command_runner=runner,
        which=lambda executable: f"/fake/{executable}",
    )
    first.sync("content_workspace", apply=True)
    second.sync("content_workspace", apply=True)
    registry = json.loads(first.registry_path.read_text(encoding="utf-8"))
    first_key = str(first.project_root)
    registry["consumers"][first_key]["plugins"]["mir-core"] = "0" * 64
    first.registry_path.write_text(json.dumps(registry), encoding="utf-8")

    lock = json.loads(first.lock_path.read_text(encoding="utf-8"))
    consumer = registry["consumers"][first_key]
    assert first._consumer_integrity(lock, consumer, ["mir-core", "mir-content"]) is False
    assert second.status()["provider_ready"] is True


def test_fake_registry_consumer_blocks_status_apply_and_rollback_registration(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "home"
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
    manager.sync("code_app", apply=True)
    assert (manager.consumer_bindings_path.stat().st_mode & 0o777) == 0o600
    receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
    registry = json.loads(manager.registry_path.read_text(encoding="utf-8"))
    content_digest = receipt["materialized_plugins"]["mir-content"]
    receipt["plugins"]["mir-content"] = content_digest
    registry["active_plugins"]["mir-content"] = content_digest
    registry["consumers"][str(tmp_path / "nonexistent-consumer")] = {
        "commit": receipt["commit"],
        "plugins": {"mir-content": content_digest},
    }
    manager.active_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manager.registry_path.write_text(json.dumps(registry), encoding="utf-8")
    commands.clear()

    assert manager.status()["provider_ready"] is False
    assert manager.status()["consumer"]["integration"] == "active"
    with pytest.raises(CapabilityError, match="global consumer registry is invalid"):
        manager.sync("code_app", apply=True)
    assert manager._rollback_runtime_registration(["mir-core", "mir-code"], receipt) is False
    assert not any(args[1:3] in (["plugin", "install"], ["plugin", "add"]) for args in commands)


def test_minimal_forged_existing_consumer_lock_is_not_authentic(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "home"
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
    manager.sync("code_app", apply=True)
    receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
    registry = json.loads(manager.registry_path.read_text(encoding="utf-8"))
    content_digest = receipt["materialized_plugins"]["mir-content"]
    forged_root = tmp_path / "forged-consumer"
    (forged_root / ".mir").mkdir(parents=True)
    (forged_root / ".mir" / "capability-lock.json").write_text(
        json.dumps(
            {
                "source": {"commit": receipt["commit"]},
                "plugins": {"mir-content": {"sha256": content_digest}},
            }
        ),
        encoding="utf-8",
    )
    receipt["plugins"]["mir-content"] = content_digest
    registry["active_plugins"]["mir-content"] = content_digest
    registry["consumers"][str(forged_root)] = {
        "commit": receipt["commit"],
        "plugins": {"mir-content": content_digest},
    }
    manager.active_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manager.registry_path.write_text(json.dumps(registry), encoding="utf-8")
    commands.clear()

    assert manager.status()["provider_ready"] is False
    with pytest.raises(CapabilityError, match="global consumer registry is invalid"):
        manager.sync("code_app", apply=True)
    assert manager._rollback_runtime_registration(["mir-core", "mir-code"], receipt) is False
    assert not any(args[1:3] in (["plugin", "install"], ["plugin", "add"]) for args in commands)


def test_complete_forged_consumer_binding_cannot_enlarge_registry_union(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "home"
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
    manager.sync("code_app", apply=True)
    receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
    registry = json.loads(manager.registry_path.read_text(encoding="utf-8"))
    content_digest = receipt["materialized_plugins"]["mir-content"]
    forged_root = tmp_path / "forged-bound-consumer"
    (forged_root / ".mir").mkdir(parents=True)
    invented_binding = "0" * 64
    (forged_root / ".mir" / "capability-lock.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "source": {
                    "url": manager.config.source_url,
                    "ref": manager.config.source_ref,
                    "commit": receipt["commit"],
                },
                "consumer_binding": invented_binding,
                "plugins": {
                    "mir-content": {
                        "path": manager.config.plugins["mir-content"],
                        "package_kind": manager.config.plugin_kinds["mir-content"],
                        "sha256": content_digest,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    receipt["plugins"]["mir-content"] = content_digest
    registry["active_plugins"]["mir-content"] = content_digest
    registry["consumers"][str(forged_root)] = {
        "commit": receipt["commit"],
        "plugins": {"mir-content": content_digest},
        "binding": invented_binding,
    }
    manager.active_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manager.registry_path.write_text(json.dumps(registry), encoding="utf-8")
    commands.clear()

    assert manager.status()["active_integrity"] is False
    with pytest.raises(CapabilityError, match="global consumer registry is invalid"):
        manager.sync("code_app", apply=True)
    assert manager._rollback_runtime_registration(["mir-core", "mir-code"], receipt) is False
    assert not any(args[1:3] in (["plugin", "install"], ["plugin", "add"]) for args in commands)


@pytest.mark.parametrize("mutation", ["missing", "world-readable", "symlink"])
def test_current_consumer_binding_ledger_mutation_blocks_status_apply_and_rollback(
    tmp_path: Path, mutation: str
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "home"
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
    manager.sync("code_app", apply=True)
    receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
    if mutation == "missing":
        manager.consumer_bindings_path.unlink()
    elif mutation == "world-readable":
        os.chmod(manager.consumer_bindings_path, 0o644)
    else:
        outside = tmp_path / "outside-bindings.json"
        outside.write_text("{}\n", encoding="utf-8")
        manager.consumer_bindings_path.unlink()
        manager.consumer_bindings_path.symlink_to(outside)
    commands.clear()

    if mutation == "missing":
        status = manager.status()
        assert status["provider_ready"] is True
        assert status["consumer"]["integration"] == "invalid"
    else:
        with pytest.raises(CapabilityError, match="consumer binding ledger"):
            manager.status()
    with pytest.raises(CapabilityError, match="consumer enrollment|binding ledger"):
        manager.sync("code_app", apply=True)
    assert manager._rollback_runtime_registration(["mir-core", "mir-code"], receipt) is False
    assert not any(args[1:3] in (["plugin", "install"], ["plugin", "add"]) for args in commands)


@pytest.mark.parametrize("unsafe_kind", ["symlink", "file"])
def test_project_mir_lock_parent_must_be_a_real_project_directory(
    tmp_path: Path, unsafe_kind: str
) -> None:
    project = make_project(tmp_path)
    mir_path = project / ".mir"
    if unsafe_kind == "symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        mir_path.symlink_to(outside, target_is_directory=True)
    else:
        mir_path.write_text("not a directory\n", encoding="utf-8")
    manager = CapabilityManager(
        project,
        capability_home=tmp_path / "home",
        user_home=tmp_path / "user",
        codex_home=tmp_path / "codex-home",
        git=CopyGit(),
        command_runner=runtime_runner(tmp_path / "home" / "active", tmp_path / "codex-home"),
        which=lambda executable: f"/fake/{executable}",
    )

    with pytest.raises(CapabilityError, match="project .mir capability state path is unsafe"):
        manager.sync("content_workspace", apply=True)


@pytest.mark.parametrize("unsafe_kind", ["non-plugin", "symlink", "executable"])
def test_materialized_plugin_rejects_unsafe_content(tmp_path: Path, unsafe_kind: str) -> None:
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
        _validate_plugin(plugin, "mir-core", package_kind="skills")


@pytest.mark.parametrize("kind", ["hooks", "mcp", "mixed"])
def test_plugin_validator_has_no_generic_active_component_path(tmp_path: Path, kind: str) -> None:
    plugin = tmp_path / "mir-core"
    shutil.copytree(ROOT / "plugins" / "mir-core", plugin)

    with pytest.raises(CapabilityError, match="unsupported plugin package_kind"):
        _validate_plugin(plugin, "mir-core", package_kind=kind)


@pytest.mark.parametrize(
    "component",
    [
        "hooks",
        "mcpServers",
        "apps",
        "scripts",
        "agents",
        "commands",
        "permissions",
        "policy",
        "runtimePolicy",
    ],
)
def test_skill_package_manifest_rejects_active_or_runtime_specific_components(
    tmp_path: Path, component: str
) -> None:
    plugin = tmp_path / "mir-core"
    shutil.copytree(ROOT / "plugins" / "mir-core", plugin)
    manifest_path = plugin / ".claude-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[component] = "./forbidden"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CapabilityError, match=component):
        _validate_plugin(plugin, "mir-core", package_kind="skills")


def test_skill_package_version_is_safe_before_runtime_install(tmp_path: Path) -> None:
    plugin = tmp_path / "mir-core"
    shutil.copytree(ROOT / "plugins" / "mir-core", plugin)
    for runtime in ("claude", "codex"):
        manifest_path = plugin / f".{runtime}-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = "../../escape"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CapabilityError, match="version"):
        _validate_plugin(plugin, "mir-core", package_kind="skills")


def test_new_receipt_cannot_downgrade_away_all_materialized_digest_binding(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "home"
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
    receipt_path = capability_home / "active.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("marketplaces")
    receipt.pop("materialized_plugins")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    unselected = (
        capability_home / "active" / "plugins" / "mir-content" / "skills" / "knowledge" / "SKILL.md"
    )
    unselected.write_text(unselected.read_text(encoding="utf-8") + "\nmutation\n")

    assert manager.status()["active_integrity"] is False


@pytest.mark.parametrize(
    ("lock_bound", "receipt_bound", "expected"),
    [
        (False, False, True),
        (False, True, True),
        (True, True, True),
        (True, False, False),
    ],
)
def test_legacy_and_bound_marketplace_evidence_compatibility_matrix(
    tmp_path: Path, lock_bound: bool, receipt_bound: bool, expected: bool
) -> None:
    project = make_project(tmp_path)
    use_schema2_capability_source(project)
    capability_home = tmp_path / "home"
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
    receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
    if not lock_bound:
        lock["schema_version"] = 1
        lock.pop("marketplaces")
    if not receipt_bound:
        receipt["schema_version"] = 1
        receipt.pop("marketplaces")
        receipt.pop("materialized_plugins")
    manager.active_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert manager._active_integrity(lock, ["mir-core", "mir-code"]) is expected


def test_schema2_state_cannot_downgrade_by_removing_both_binding_fields(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "home"
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
    receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
    lock["schema_version"] = 2
    receipt["schema_version"] = 2
    lock.pop("marketplaces")
    receipt.pop("marketplaces")
    receipt.pop("materialized_plugins")
    manager.active_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    marketplace = manager.active_path / ".agents" / "plugins" / "marketplace.json"
    payload = json.loads(marketplace.read_text(encoding="utf-8"))
    payload["interface"]["displayName"] = "Tampered but structurally valid"
    marketplace.write_text(json.dumps(payload), encoding="utf-8")

    assert manager._active_integrity(lock, ["mir-core", "mir-code"]) is False


def test_should_reject_simultaneous_state_schema_downgrade_under_schema3(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "home"
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
    receipt = json.loads(manager.active_receipt_path.read_text(encoding="utf-8"))
    registry = json.loads(manager.registry_path.read_text(encoding="utf-8"))
    lock["schema_version"] = 1
    lock.pop("marketplaces")
    receipt["schema_version"] = 1
    receipt.pop("marketplaces")
    receipt.pop("materialized_plugins")
    registry["schema_version"] = 1
    registry.pop("active_plugins")
    manager.active_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manager.registry_path.write_text(json.dumps(registry), encoding="utf-8")

    assert manager._active_integrity(lock, ["mir-core", "mir-code"]) is False


def test_should_report_missing_managed_integration_files(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    manager = CapabilityManager(
        project,
        capability_home=tmp_path / "home",
        user_home=tmp_path / "user",
        git=CopyGit(),
    )
    required = (
        "config/project-hooks.json",
        ".claude/settings.json",
        ".codex/hooks.json",
        ".codex/config.toml",
    )

    assert manager._missing_project_paths() == []
    for relative in required:
        (project / relative).unlink()
    assert set(manager._missing_project_paths()) >= set(required)


def test_schema1_lock_does_not_bypass_current_skill_manifest_validation(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    use_schema2_capability_source(project)
    active = tmp_path / "home" / "active"
    active.mkdir(parents=True)
    shutil.copytree(ROOT / ".claude-plugin", active / ".claude-plugin")
    shutil.copytree(ROOT / ".agents" / "plugins", active / ".agents" / "plugins")
    shutil.copytree(ROOT / "plugins", active / "plugins")
    plugin = active / "plugins" / "mir-core"
    legacy_lock = {
        "schema_version": 1,
        "plugins": {"mir-core": {"sha256": _tree_digest(plugin)}},
    }
    manager = CapabilityManager(
        project,
        capability_home=tmp_path / "home",
        user_home=tmp_path / "user",
    )

    assert manager._active_integrity(legacy_lock, ["mir-core"]) is True

    manifest_path = plugin / ".claude-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["permissions"] = {"allow": ["Bash(*)"]}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    legacy_lock["plugins"]["mir-core"]["sha256"] = _tree_digest(plugin)

    assert manager._active_integrity(legacy_lock, ["mir-core"]) is False
    manager.lock_path.parent.mkdir(parents=True)
    manager.lock_path.write_text(json.dumps(legacy_lock), encoding="utf-8")
    with pytest.raises(CapabilityError, match="failed current validation"):
        manager.attest("codex-cli-desktop", [], apply=False)
    with pytest.raises(CapabilityError, match="failed current validation"):
        manager.finalize()


@pytest.mark.parametrize("runtime", ["claude", "codex"])
def test_marketplace_inventory_rejects_nonlocal_plugin_redirect(
    tmp_path: Path, runtime: str
) -> None:
    checkout = tmp_path / "checkout"
    shutil.copytree(ROOT / ".claude-plugin", checkout / ".claude-plugin")
    shutil.copytree(ROOT / ".agents" / "plugins", checkout / ".agents" / "plugins")
    shutil.copytree(ROOT / "plugins", checkout / "plugins")
    if runtime == "claude":
        marketplace_path = checkout / ".claude-plugin" / "marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["source"] = "https://example.invalid/plugin.git"
    else:
        marketplace_path = checkout / ".agents" / "plugins" / "marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["source"] = {
            "source": "git",
            "url": "https://example.invalid/plugin.git",
        }
    marketplace_path.write_text(json.dumps(marketplace), encoding="utf-8")
    config = load_capability_config(ROOT / "config" / "capability-sources.json")

    with pytest.raises(CapabilityError, match="marketplace"):
        _validate_marketplaces(checkout, config)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "version", "name", "unknown-field", "policy"]
)
def test_marketplace_inventory_and_version_are_exact(tmp_path: Path, mutation: str) -> None:
    checkout = tmp_path / "checkout"
    shutil.copytree(ROOT / ".claude-plugin", checkout / ".claude-plugin")
    shutil.copytree(ROOT / ".agents" / "plugins", checkout / ".agents" / "plugins")
    shutil.copytree(ROOT / "plugins", checkout / "plugins")
    marketplace_path = checkout / ".claude-plugin" / "marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    if mutation == "missing":
        marketplace["plugins"].pop()
    elif mutation == "duplicate":
        marketplace["plugins"].append(dict(marketplace["plugins"][0]))
    elif mutation == "version":
        marketplace["plugins"][0]["version"] = "999.0.0"
    elif mutation == "name":
        marketplace["name"] = "unexpected-marketplace"
    elif mutation == "unknown-field":
        marketplace["plugins"][0]["permissions"] = {"allow": ["Bash(*)"]}
    else:
        codex_path = checkout / ".agents" / "plugins" / "marketplace.json"
        codex = json.loads(codex_path.read_text(encoding="utf-8"))
        codex["plugins"][0]["policy"]["authentication"] = "NONE"
        codex_path.write_text(json.dumps(codex), encoding="utf-8")
    marketplace_path.write_text(json.dumps(marketplace), encoding="utf-8")
    config = load_capability_config(ROOT / "config" / "capability-sources.json")

    with pytest.raises(CapabilityError, match="marketplace"):
        _validate_marketplaces(checkout, config)


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
