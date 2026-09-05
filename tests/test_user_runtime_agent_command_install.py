"""Regression coverage for explicit user-runtime agent and command sync."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_user_runtime_agents.py"
SOURCE_COMMIT = "a" * 40


def expected_paths() -> tuple[list[str], list[str]]:
    config = json.loads((ROOT / "config" / "capability-sources.json").read_text())
    agents = sorted(
        {
            agent
            for pack in config["profiles"]["packs"].values()
            for agent in pack["agents"]
        }
    )
    commands = sorted(
        {
            command
            for pack in config["profiles"]["packs"].values()
            for command in pack["commands"]
        }
    )
    codex_agents = [
        path.replace(".claude/agents/", ".codex/agents/").replace(".md", ".toml")
        for path in agents
    ]
    return agents + commands, codex_agents


def installer_module():
    spec = importlib.util.spec_from_file_location("user_runtime_installer", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_installer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    claude_home: Path,
    codex_home: Path,
    *extra: str,
    module=None,
) -> tuple[int, str, str]:
    module = module or installer_module()
    monkeypatch.setattr(module, "source_commit", lambda: SOURCE_COMMIT)
    result = module.main(
        [
            "--claude-home",
            str(claude_home),
            "--codex-home",
            str(codex_home),
            *extra,
        ]
    )
    captured = capsys.readouterr()
    return result, captured.out, captured.err


def test_dry_run_is_default_and_leaves_explicit_homes_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    claude_home = tmp_path / "claude-home"
    codex_home = tmp_path / "codex-home"

    result, stdout, stderr = run_installer(monkeypatch, capsys, claude_home, codex_home)

    assert result == 0, stderr
    report = json.loads(stdout)
    claude_paths, codex_paths = expected_paths()
    assert report["status"] == "dry_run"
    assert report["planned"]["claude"] == claude_paths
    assert report["planned"]["codex"] == codex_paths
    assert ".claude/agents/template-sync-validator.md" not in report["planned"]["claude"]
    assert ".codex/agents/template-sync-validator.toml" not in report["planned"]["codex"]
    assert "project-local files take precedence" in report["shadowing"]
    assert not claude_home.exists()
    assert not codex_home.exists()


def test_apply_records_file_digests_and_refuses_unmanaged_divergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    claude_home = tmp_path / "claude-home"
    codex_home = tmp_path / "codex-home"

    applied, _, stderr = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply"
    )

    assert applied == 0, stderr
    claude_receipt = json.loads(
        (claude_home / "mir-yoke-agent-command-receipt.json").read_text()
    )
    codex_receipt = json.loads(
        (codex_home / "mir-yoke-agent-command-receipt.json").read_text()
    )
    assert claude_receipt["source_commit"] == SOURCE_COMMIT
    assert set(claude_receipt["files"]) == set(expected_paths()[0])
    assert set(codex_receipt["files"]) == set(expected_paths()[1])
    target = claude_home / "agents" / "main-orchestrator.md"
    assert (
        claude_receipt["files"][".claude/agents/main-orchestrator.md"]["sha256"]
        == hashlib.sha256(target.read_bytes()).hexdigest()
    )

    target.write_text("user customization\n", encoding="utf-8")
    refused, _, stderr = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply"
    )

    assert refused != 0
    assert "diverged managed file" in stderr
    assert target.read_text(encoding="utf-8") == "user customization\n"


def test_refuses_symlinked_target_root_or_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    claude_home = tmp_path / "claude-home"
    claude_home.symlink_to(real_home, target_is_directory=True)
    codex_home = tmp_path / "codex-home"

    result, _, stderr = run_installer(monkeypatch, capsys, claude_home, codex_home)

    assert result != 0
    assert "symlinked target path" in stderr
    assert not codex_home.exists()


def test_refuses_unmanaged_existing_file_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    claude_home = tmp_path / "claude-home"
    codex_home = tmp_path / "codex-home"
    existing = claude_home / "agents" / "main-orchestrator.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("unmanaged\n", encoding="utf-8")

    result, _, stderr = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply"
    )

    assert result != 0
    assert "unmanaged existing file" in stderr
    assert existing.read_text(encoding="utf-8") == "unmanaged\n"


def test_refuses_non_regular_allowlisted_source(tmp_path: Path) -> None:
    provider = tmp_path / "provider"
    source = provider / ".claude" / "agents" / "sample.md"
    source.parent.mkdir(parents=True)
    source.symlink_to(provider / "payload.md")
    (provider / "payload.md").write_text("payload\n", encoding="utf-8")
    config = provider / "config" / "capability-sources.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "agents": {"allowlist": [".claude/agents/sample.md"]},
                "commands": {"allowlist": {}},
                "profiles": {
                    "packs": {
                        "test": {"agents": [".claude/agents/sample.md"], "commands": []}
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    module = installer_module()
    module.ROOT = provider
    module.CONFIG_PATH = config

    with pytest.raises(module.SyncError, match="source is not a regular file"):
        module.load_sources()


def test_dirty_provider_requires_clean_head(monkeypatch: pytest.MonkeyPatch) -> None:
    module = installer_module()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, " M source\n", ""),
    )

    with pytest.raises(module.SyncError, match="source is dirty"):
        module.source_commit()


def test_parser_does_not_offer_source_commit_override() -> None:
    module = installer_module()

    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--claude-home",
                "/private/claude",
                "--codex-home",
                "/private/codex",
                "--source-commit",
                SOURCE_COMMIT,
            ]
        )


def test_normalized_home_aliases_are_rejected_before_receipt_calculation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    claude_home = tmp_path / "shared-home"
    codex_home_alias = claude_home / "nested" / ".."

    result, _, stderr = run_installer(monkeypatch, capsys, claude_home, codex_home_alias)

    assert result != 0
    assert "must not overlap" in stderr
    assert not claude_home.exists()


@pytest.mark.parametrize(
    ("claude_relative", "codex_relative"),
    (("runtime", "runtime/codex"), ("runtime/claude", "runtime")),
)
def test_overlapping_runtime_homes_are_rejected_before_receipt_calculation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    claude_relative: str,
    codex_relative: str,
) -> None:
    claude_home = tmp_path / claude_relative
    codex_home = tmp_path / codex_relative

    result, _, stderr = run_installer(monkeypatch, capsys, claude_home, codex_home)

    assert result != 0
    assert "must not overlap" in stderr
    assert not (tmp_path / "runtime").exists()


def test_runtime_homes_with_the_same_physical_identity_overlap() -> None:
    module = installer_module()
    claude_home = module.HomeIdentity(
        Path("/runtime/ClaudeHome"), Path("/runtime/ClaudeHome"), 7, 9
    )
    codex_home = module.HomeIdentity(
        Path("/runtime/claudehome"), Path("/runtime/claudehome"), 7, 9
    )

    assert module.runtime_homes_overlap(claude_home, codex_home)


def test_case_insensitive_ancestor_aliases_are_rejected_without_created_home_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    probe = tmp_path / "CaseProbe"
    alias = tmp_path / "caseprobe"
    probe.mkdir()
    supported = alias.exists() and probe.samefile(alias)
    probe.rmdir()
    if not supported:
        pytest.skip("filesystem is case-sensitive")

    module = minimal_provider(tmp_path)
    claude_home = tmp_path / "CaseHome" / "a" / "claude"
    codex_home = tmp_path / "casehome"

    result, _, stderr = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply", module=module
    )

    assert result != 0
    assert "must not overlap" in stderr
    assert not (tmp_path / "CaseHome").exists()
    assert not (tmp_path / "casehome").exists()


def write_provider_config(
    provider: Path, agents: list[str], commands: list[str] | None = None
) -> None:
    commands = commands or []
    config = provider / "config" / "capability-sources.json"
    config.parent.mkdir(exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "agents": {"allowlist": agents},
                "commands": {"allowlist": {command: "test" for command in commands}},
                "profiles": {"packs": {"test": {"agents": agents, "commands": commands}}},
            }
        ),
        encoding="utf-8",
    )


def minimal_provider(tmp_path: Path):
    provider = tmp_path / "provider"
    agent = provider / ".claude" / "agents" / "retired.md"
    codex_agent = provider / ".codex" / "agents" / "retired.toml"
    agent.parent.mkdir(parents=True)
    codex_agent.parent.mkdir(parents=True)
    agent.write_text("agent\n", encoding="utf-8")
    codex_agent.write_text('name = "retired"\n', encoding="utf-8")
    write_provider_config(provider, [".claude/agents/retired.md"])
    module = installer_module()
    module.ROOT = provider
    module.CONFIG_PATH = provider / "config" / "capability-sources.json"
    return module


def test_allowlist_removal_plans_and_removes_only_prior_managed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = minimal_provider(tmp_path)
    claude_home = tmp_path / "claude-home"
    codex_home = tmp_path / "codex-home"
    first, _, _ = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply", module=module
    )
    assert first == 0
    write_provider_config(module.ROOT, [])

    result, stdout, stderr = run_installer(
        monkeypatch, capsys, claude_home, codex_home, module=module
    )

    assert result == 0, stderr
    report = json.loads(stdout)
    assert report["planned_removals"] == {
        "claude": [".claude/agents/retired.md"],
        "codex": [".codex/agents/retired.toml"],
    }
    assert (claude_home / "agents" / "retired.md").exists()
    unknown = claude_home / "agents" / "unknown.md"
    unknown.write_text("user-owned\n", encoding="utf-8")
    applied, _, _ = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply", module=module
    )
    assert applied == 0
    assert not (claude_home / "agents" / "retired.md").exists()
    assert not (codex_home / "agents" / "retired.toml").exists()
    assert unknown.read_text(encoding="utf-8") == "user-owned\n"


def test_allowlist_removal_refuses_diverged_prior_managed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = minimal_provider(tmp_path)
    claude_home = tmp_path / "claude-home"
    codex_home = tmp_path / "codex-home"
    first, _, _ = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply", module=module
    )
    assert first == 0
    (claude_home / "agents" / "retired.md").write_text("custom\n", encoding="utf-8")
    write_provider_config(module.ROOT, [])

    result, _, stderr = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply", module=module
    )

    assert result != 0
    assert "diverged stale managed file" in stderr
    assert (claude_home / "agents" / "retired.md").read_text(encoding="utf-8") == "custom\n"


def test_apply_rejects_replaced_home_identity(tmp_path: Path) -> None:
    module = installer_module()
    home = tmp_path / "home"
    home.mkdir()
    identity = module.capture_home_identity(home)
    home.rename(tmp_path / "replaced-home")
    home.mkdir()

    with pytest.raises(module.SyncError, match="runtime home changed during apply"):
        module.verified_target(identity, Path("agents") / "agent.md")


def runtime_state(home: Path) -> dict[str, bytes]:
    if not home.exists():
        return {}
    return {
        path.relative_to(home).as_posix(): path.read_bytes()
        for path in sorted(home.rglob("*"))
        if path.is_file()
    }


@pytest.mark.parametrize("failure_call", [2, 4], ids=["mid_claude", "during_codex"])
def test_apply_failure_rolls_back_both_runtime_homes_and_allows_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_call: int,
) -> None:
    module = minimal_provider(tmp_path)
    command_relative = ".claude/commands/retired.md"
    command = module.ROOT / command_relative
    command.parent.mkdir(parents=True)
    command.write_text("command-v1\n", encoding="utf-8")
    write_provider_config(module.ROOT, [".claude/agents/retired.md"], [command_relative])
    claude_home = tmp_path / "claude-home"
    codex_home = tmp_path / "codex-home"
    initial, _, initial_error = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply", module=module
    )
    assert initial == 0, initial_error
    before_claude = runtime_state(claude_home)
    before_codex = runtime_state(codex_home)

    (module.ROOT / ".claude" / "agents" / "retired.md").write_text(
        "agent-v2\n", encoding="utf-8"
    )
    (module.ROOT / ".codex" / "agents" / "retired.toml").write_text(
        'name = "retired-v2"\n', encoding="utf-8"
    )
    command.write_text("command-v2\n", encoding="utf-8")
    original_atomic_write = module.atomic_write
    calls = 0

    def fail_once(identity, relative, content):
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError("injected write failure")
        original_atomic_write(identity, relative, content)

    monkeypatch.setattr(module, "atomic_write", fail_once)
    failed, _, error = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply", module=module
    )

    assert failed != 0
    assert "rollback complete" in error
    assert runtime_state(claude_home) == before_claude
    assert runtime_state(codex_home) == before_codex

    monkeypatch.setattr(module, "atomic_write", original_atomic_write)
    retried, _, retry_error = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply", module=module
    )
    assert retried == 0, retry_error


def test_first_apply_failure_removes_created_homes_and_allows_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = minimal_provider(tmp_path)
    command_relative = ".claude/commands/retired.md"
    command = module.ROOT / command_relative
    command.parent.mkdir(parents=True)
    command.write_text("command\n", encoding="utf-8")
    write_provider_config(module.ROOT, [".claude/agents/retired.md"], [command_relative])
    claude_home = tmp_path / "claude-home"
    codex_home = tmp_path / "codex-home"
    original_atomic_write = module.atomic_write
    calls = 0

    def fail_mid_claude(identity, relative, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected first-apply failure")
        original_atomic_write(identity, relative, content)

    monkeypatch.setattr(module, "atomic_write", fail_mid_claude)
    failed, _, error = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply", module=module
    )

    assert failed != 0
    assert "rollback complete" in error
    assert not claude_home.exists()
    assert not codex_home.exists()

    monkeypatch.setattr(module, "atomic_write", original_atomic_write)
    retried, _, retry_error = run_installer(
        monkeypatch, capsys, claude_home, codex_home, "--apply", module=module
    )
    assert retried == 0, retry_error


def test_interrupt_during_apply_rolls_back_created_homes_and_reraises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = minimal_provider(tmp_path)
    claude_home = tmp_path / "claude-home"
    codex_home = tmp_path / "codex-home"
    original_atomic_write = module.atomic_write
    calls = 0

    def interrupt_on_second_write(identity, relative, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt()
        original_atomic_write(identity, relative, content)

    monkeypatch.setattr(module, "atomic_write", interrupt_on_second_write)

    with pytest.raises(KeyboardInterrupt):
        run_installer(monkeypatch, capsys, claude_home, codex_home, "--apply", module=module)

    assert not claude_home.exists()
    assert not codex_home.exists()
