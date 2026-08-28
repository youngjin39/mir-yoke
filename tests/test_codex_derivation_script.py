"""Codex derivative generator regressions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from scripts import verify_codex_sync

ROOT = Path(__file__).resolve().parents[1]


def test_generator_skips_non_agent_markdown_and_empty_targets(tmp_path: Path) -> None:
    stale_agent = tmp_path / ".codex" / "agents" / "stale-agent.toml"
    stale_agent.parent.mkdir(parents=True)
    stale_agent.write_text('name = "stale-agent"\n', encoding="utf-8")
    stale_live = tmp_path / ".agents" / "skills" / "spec-architect"
    stale_live.parent.mkdir(parents=True)
    stale_live.write_text("../../.claude/skills/spec-architect", encoding="utf-8")
    stale_staging = (
        tmp_path
        / ".codex-sync"
        / "staging"
        / ".agents"
        / "skills"
        / "spec-architect"
    )
    stale_staging.mkdir(parents=True)
    (stale_staging / "obsolete.txt").write_text("stale\n", encoding="utf-8")

    env = os.environ.copy()
    env["CODEX_DERIVATION_OUTPUT_ROOT"] = str(tmp_path)
    completed = subprocess.run(
        ["/bin/bash", "scripts/generate_codex_derivatives.sh"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads(
        (tmp_path / ".codex-sync" / "manifest.json").read_text(encoding="utf-8")
    )
    mappings = manifest["mappings"]
    assert all(mapping["source"] != ".claude/agents/README.md" for mapping in mappings)
    assert all(target != ".codex/agents/.toml" for item in mappings for target in item["targets"])
    assert "namespaced plugins" in manifest["notes"]

    claude_text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert claude_text in agents_text
    assert "## Codex closeout delta" not in agents_text
    assert "- Skills: `" not in agents_text
    assert "adopt it as your session contract" not in agents_text
    assert "## Codex Hook-Mirror Obligations" not in agents_text
    assert len(claude_text.splitlines()) <= 80
    assert len(agents_text.splitlines()) <= 90

    budgets = {
        entry["path"]: entry
        for entry in json.loads(
            (ROOT / "config" / "doc-size-guard.json").read_text(encoding="utf-8")
        )
    }
    assert len(claude_text.splitlines()) <= budgets["CLAUDE.md"]["max_lines"]
    assert len(agents_text.splitlines()) <= budgets["AGENTS.md"]["max_lines"]
    assert len(claude_text.encode()) <= budgets["CLAUDE.md"]["max_bytes"]
    assert len(agents_text.encode()) <= budgets["AGENTS.md"]["max_bytes"]

    assert not any(
        mapping["source"].startswith(".claude/skills/") for mapping in mappings
    )
    assert not (tmp_path / ".agents" / "skills").exists()
    assert not (tmp_path / ".codex-sync" / "staging" / ".agents" / "skills").exists()
    assert not stale_agent.exists()
    generated_agents = {
        path.stem for path in (tmp_path / ".codex" / "agents").glob("*.toml")
    }
    source_agents = {
        path.stem
        for path in (ROOT / ".claude" / "agents").glob("*.md")
        if path.name != "README.md"
    }
    assert generated_agents == source_agents

    generated_orchestrator = (
        tmp_path / ".codex" / "agents" / "main-orchestrator.toml"
    ).read_text(encoding="utf-8")
    assert "## Specialist Scope-Pattern Routing (catalog routing ADR)" in generated_orchestrator
    assert '"filtered_files":0' in generated_orchestrator
    assert "## Post-Dispatch Evidence" in generated_orchestrator
    assert "Mir Yoke provides no daemon" in generated_orchestrator

    config = tomllib.loads((tmp_path / ".codex" / "config.toml").read_text())
    assert "sandbox_mode" not in config
    assert "sandbox_workspace_write" not in config
    assert "default_permissions" not in config
    assert config["agents"]["max_concurrent_threads_per_session"] == 6
    assert "max_threads" not in config["agents"]
    assert config["features"]["hooks"] is True
    assert "codex_hooks" not in config["features"]
    executor = tomllib.loads(
        (tmp_path / ".codex" / "agents" / "executor-agent.toml").read_text()
    )
    reviewer = tomllib.loads(
        (tmp_path / ".codex" / "agents" / "codex-final-reviewer.toml").read_text()
    )
    governance_reviewer = tomllib.loads(
        (tmp_path / ".codex" / "agents" / "fleet-doc-steward.toml").read_text()
    )
    assert "sandbox_mode" not in executor
    assert reviewer["sandbox_mode"] == "read-only"
    assert governance_reviewer["sandbox_mode"] == "read-only"

    codex_readme = (tmp_path / ".codex" / "README.md").read_text(encoding="utf-8")
    assert "Use `/hooks`" in codex_readme
    assert "tool_input.command" in codex_readme
    assert "does not select `sandbox_mode`" in codex_readme
    assert "mechanically read-only reviewers" in codex_readme
    assert any(
        mapping["source"] == "scripts/generate_codex_derivatives.sh"
        and mapping["targets"] == [".codex/README.md"]
        for mapping in mappings
    )

    spec_architect_reference = (
        ROOT
        / "plugins"
        / "mir-core"
        / "skills"
        / "spec-architect"
        / "references"
        / "05-views.md"
    )
    assert spec_architect_reference.is_file()

    preserve = tomllib.loads((ROOT / ".mir-preserve.toml").read_text(encoding="utf-8"))
    for heading in preserve["claude_md_preserve"]["sections"]:
        assert heading in claude_text


def test_generator_derives_path_scoped_agents_and_manifest_entry(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    scripts_dir = fixture / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "generate_codex_derivatives.sh", scripts_dir)
    (fixture / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
    (scripts_dir / "CLAUDE.md").write_text(
        "Read root CLAUDE.md before changing scripts.\n", encoding="utf-8"
    )

    completed = subprocess.run(
        ["/bin/bash", "scripts/generate_codex_derivatives.sh"],
        cwd=fixture,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    generated = (scripts_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert generated.startswith(
        "<!-- GENERATED FILE: edit scripts/CLAUDE.md and rerun "
        "scripts/generate_codex_derivatives.sh -->\n\n"
    )
    assert "Read root AGENTS.md before changing scripts." in generated
    manifest = json.loads(
        (fixture / ".codex-sync" / "manifest.json").read_text(encoding="utf-8")
    )
    assert any(
        mapping["source"] == "scripts/CLAUDE.md"
        and mapping["targets"] == ["scripts/AGENTS.md"]
        and mapping["notes"] == "Path-scoped Codex instructions"
        for mapping in manifest["mappings"]
    )


def test_verifier_rejects_nested_agents_drift(tmp_path: Path) -> None:
    source = tmp_path / "src" / "CLAUDE.md"
    source.parent.mkdir(parents=True)
    source.write_text("Read root CLAUDE.md.\n", encoding="utf-8")
    source.with_name("AGENTS.md").write_text(
        "<!-- GENERATED FILE: edit src/CLAUDE.md and rerun "
        "scripts/generate_codex_derivatives.sh -->\n\n"
        "Read root CLAUDE.md.\n",
        encoding="utf-8",
    )
    failures: list[str] = []

    verify_codex_sync.validate_nested_instruction_derivatives(failures, root=tmp_path)

    assert failures == [
        "nested AGENTS derivative retains Claude-only path reference: src/AGENTS.md"
    ]


def test_verifier_rejects_legacy_raw_skill_provider(tmp_path: Path) -> None:
    raw_skill = tmp_path / ".agents" / "skills" / "example" / "SKILL.md"
    raw_skill.parent.mkdir(parents=True)
    raw_skill.write_text("# Example\n", encoding="utf-8")
    failures: list[str] = []

    verify_codex_sync.validate_plugin_skill_providers(failures, root=tmp_path)

    assert "legacy raw skill provider remains: .agents/skills" in failures


def test_generator_emits_real_portable_hook_library(tmp_path: Path) -> None:
    env = {**os.environ, "CODEX_DERIVATION_OUTPUT_ROOT": str(tmp_path)}
    completed = subprocess.run(
        ["/bin/bash", "scripts/generate_codex_derivatives.sh"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    target = tmp_path / ".codex" / "hooks" / "lib"
    assert target.is_dir()
    assert not target.is_symlink()
    failures: list[str] = []
    verify_codex_sync.validate_portable_hook_copy(
        failures, source_root=ROOT, output_root=tmp_path
    )
    assert failures == []
