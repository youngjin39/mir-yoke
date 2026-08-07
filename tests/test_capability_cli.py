"""Capability provider lifecycle and CLI contract tests."""

from __future__ import annotations

import json
import shutil
import subprocess
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
    derivative = project / "scripts" / "generate_codex_derivatives.sh"
    derivative.parent.mkdir(parents=True)
    if real_derivatives:
        shutil.copy2(ROOT / "scripts" / "generate_codex_derivatives.sh", derivative)
        (project / ".claude" / "hooks" / "lib").mkdir(parents=True)
    else:
        derivative.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    return project


def runtime_runner(active: Path, codex_home: Path):
    installed: set[str] = set()

    def write_codex_state() -> None:
        codex_home.mkdir(parents=True, exist_ok=True)
        lines = [
            "[marketplaces.mir-yoke]",
            'source_type = "local"',
            f'source = "{active}"',
            "",
        ]
        for plugin in sorted(installed):
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
            installed.add(plugin)
            write_codex_state()
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps({"installedPath": str(cache), "pluginId": args[3]}),
                "",
            )
        if executable == "codex" and args[1:3] == ["plugin", "remove"]:
            installed.discard(args[3].split("@", 1)[0])
            write_codex_state()
            return subprocess.CompletedProcess(args, 0, "{}", "")
        if executable == "codex" and args[1:4] == ["plugin", "marketplace", "remove"]:
            installed.clear()
            write_codex_state()
            return subprocess.CompletedProcess(args, 0, "{}", "")

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
            if executable != "codex" or plugin.name in installed
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


def attest_both_runtimes(manager: CapabilityManager) -> None:
    skills = observed_skills(manager)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("CLAUDE_SESSION_ID", "claude-new-session")
        monkeypatch.setenv("CODEX_THREAD_ID", "codex-new-session")
        manager.attest("claude-code", skills, apply=True)
        manager.attest("codex-cli-desktop", skills, apply=True)


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
    attest_both_runtimes(manager)
    assert manager.finalize()["ready_to_finalize"] is True
    finalized = manager.finalize(apply=True, after_restart=True)
    assert finalized["activation"]["status"] == "active"
    assert manager.status()["ready"] is True


def test_claude_plugin_id_is_normalized_for_runtime_evidence(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    capability_home = tmp_path / "capability-home"
    codex_home = tmp_path / "codex-home"
    base_runner = runtime_runner(capability_home / "active", codex_home)

    def claude_id_runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if Path(args[0]).name != "claude" or args[1:3] != ["plugin", "list"]:
            return base_runner(args, **kwargs)
        entries = [
            {
                "id": f"{plugin.name}@mir-yoke",
                "enabled": True,
                "installPath": str(plugin),
            }
            for plugin in sorted((capability_home / "active" / "plugins").iterdir())
        ]
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


def test_source_path_is_not_an_installed_path_fallback() -> None:
    assert _installed_path({"source": {"path": "/provider/source"}}) is None


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
            apply=True,
        )
    with pytest.raises(CapabilityError, match="new runtime session"):
        manager.attest(
            "codex-cli-desktop",
            skills,
            apply=True,
        )

    monkeypatch.setenv("CODEX_THREAD_ID", "new-session")
    receipt = manager.attest("codex-cli-desktop", skills, apply=True)
    assert receipt["status"] == "attested"
    assert receipt["attestation_kind"] == "operator-observed-runtime-catalog"
    assert manager.finalize()["discovery"]["status"] == "incomplete"


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
    base_runner = runtime_runner(capability_home / "active", codex_home)

    def toggled_runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if fail:
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
    manager.sync("content_workspace", apply=True)
    marker = capability_home / "active" / "previous-provider-marker"
    marker.write_text("preserve\n", encoding="utf-8")
    tracked = [
        project / ".mir" / "capability-lock.json",
        capability_home / "consumers.json",
        capability_home / "active.json",
        project / ".claude" / "agents" / "main-orchestrator.md",
    ]
    before = {path: path.read_bytes() for path in tracked}

    fail = True
    with pytest.raises(CapabilityError, match="local rollback was incomplete"):
        manager.sync("content_workspace", apply=True)

    assert marker.read_text(encoding="utf-8") == "preserve\n"
    assert {path: path.read_bytes() for path in tracked} == before
    assert not (capability_home / ".active.previous").exists()


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


def test_cli_accepts_runtime_skill_attestation(monkeypatch, tmp_path: Path, capsys) -> None:
    calls: list[tuple[str, tuple[str, ...], bool]] = []

    class FakeManager:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def attest(
            self,
            runtime: str,
            observed_skills: list[str],
            *,
            apply: bool,
        ) -> dict[str, object]:
            calls.append((runtime, tuple(observed_skills), apply))
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
            "--apply",
            "--json",
        ]
    )
    assert exit_code == 0
    assert calls == [
        (
            "codex-cli-desktop",
            ("mir-core:design", "mir-core:verify"),
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
