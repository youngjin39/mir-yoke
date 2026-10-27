"""Codex derivative generator regressions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path, PureWindowsPath

import pytest

from scripts import verify_codex_sync

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("invalid", [False, True])
def test_should_emit_utf8_bytes_under_cp949_locale(tmp_path, invalid):
    source = tmp_path / "fixture—"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    copy_generators(scripts)
    (source / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
    if invalid:
        agent = source / ".claude/agents/invalid—.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\ndisallowedTools: 'Write, Edit'\n---\n", encoding="utf-8")
    command = [sys.executable, str(scripts / "generate_codex_derivatives.py")]
    baseline = subprocess.run(
        command, capture_output=True,
        env={**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "utf-8"},
    )
    legacy = subprocess.run(
        command, capture_output=True,
        env={**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp949"},
    )
    assert baseline.returncode == (2 if invalid else 0)
    assert legacy.returncode == baseline.returncode, legacy.stderr
    assert legacy.stdout == baseline.stdout
    assert legacy.stderr == baseline.stderr


def test_should_decode_git_output_as_utf8_under_cp949_locale(monkeypatch):
    from mir.core.capabilities.manager import GitClient

    monkeypatch.setattr(subprocess, "_text_encoding", lambda: "cp949")
    result = GitClient()._run([
        sys.executable, "-c", "import os; os.write(1, b'\\xe2\\x80\\x94\\xff')",
    ])
    assert result == "—\ufffd"


def test_should_decode_generator_output_as_utf8_under_cp949_locale(tmp_path, monkeypatch):
    from mir.core.capabilities.manager import CapabilityManager

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "generate_codex_derivatives.py").write_text(
        "import os\nos.write(1, b'\\xe2\\x80\\x94\\xff')\n", encoding="utf-8",
    )
    manager = CapabilityManager(
        tmp_path, capability_home=tmp_path / "capabilities", user_home=tmp_path / "user",
        codex_home=tmp_path / "codex",
    )
    monkeypatch.setattr(subprocess, "_text_encoding", lambda: "cp949")
    assert manager._regenerate_agent_derivatives()


def copy_generators(scripts: Path) -> None:
    for suffix in ("sh", "py"):
        shutil.copy2(ROOT / f"scripts/generate_codex_derivatives.{suffix}", scripts)


@pytest.fixture(params=["python", "wrapper"])
def generator(request):
    if request.param == "wrapper" and (sys.platform == "win32" or shutil.which("bash") is None):
        pytest.skip("Bash wrapper requires a POSIX host with Bash")

    def command(root):
        if request.param == "python":
            return [sys.executable, str(root / "scripts/generate_codex_derivatives.py")]
        return ["bash", str(root / "scripts/generate_codex_derivatives.sh")]

    return command


def test_should_generate_without_retired_hook_library_when_source_is_absent(tmp_path, generator):
    source = tmp_path / "source"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    copy_generators(scripts)
    (source / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
    output = tmp_path / "output"
    stale = output / ".codex/hooks/lib/obsolete.py"
    stale.parent.mkdir(parents=True)
    stale.write_text("# Obsolete generated helper\n", encoding="utf-8")
    result = subprocess.run(
        generator(scripts.parent),
        env={**os.environ, "CODEX_DERIVATION_OUTPUT_ROOT": str(output)},
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not (output / ".codex/hooks/lib").exists()
    manifest = json.loads((output / ".codex-sync/manifest.json").read_text(encoding="utf-8"))
    assert all(item["source"] != ".claude/hooks/lib" for item in manifest["mappings"])
    failures = []
    verify_codex_sync.validate_portable_hook_copy(
        failures, source_root=source, output_root=output,
    )
    assert failures == []


def test_generator_skips_non_agent_markdown_and_empty_targets(tmp_path: Path, generator) -> None:
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
        generator(ROOT),
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True, encoding="utf-8",
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
    for source_path in (ROOT / ".claude" / "agents").glob("*.md"):
        if source_path.name != "README.md":
            assert "\nmodel: " in source_path.read_text(encoding="utf-8")

    generated_orchestrator = (
        tmp_path / ".codex" / "agents" / "main-orchestrator.toml"
    ).read_text(encoding="utf-8")
    assert "## Specialist Scope-Pattern Routing (catalog routing ADR)" in generated_orchestrator
    assert '"filtered_files":0' in generated_orchestrator
    assert "## Post-Dispatch Evidence" in generated_orchestrator
    assert "Mir Yoke provides no daemon" in generated_orchestrator

    config = tomllib.loads((tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8"))
    config_text = (tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert config_text.startswith(
        "# GENERATED FILE: edit scripts/generate_codex_derivatives.sh or .mcp.json"
    )
    assert "approval_policy" not in config
    assert "sandbox_mode" not in config
    assert "sandbox_workspace_write" not in config
    assert "default_permissions" not in config
    assert "agents" not in config
    assert config["features"]["hooks"] is True
    assert "multi_agent" not in config["features"]
    assert "codex_hooks" not in config["features"]
    executor = tomllib.loads(
        (tmp_path / ".codex" / "agents" / "executor-agent.toml").read_text(encoding="utf-8")
    )
    reviewer = tomllib.loads(
        (tmp_path / ".codex" / "agents" / "codex-final-reviewer.toml").read_text(encoding="utf-8")
    )
    governance_reviewer = tomllib.loads(
        (tmp_path / ".codex" / "agents" / "fleet-doc-steward.toml").read_text(encoding="utf-8")
    )
    assert "sandbox_mode" not in executor
    assert reviewer["sandbox_mode"] == "read-only"
    assert governance_reviewer["sandbox_mode"] == "read-only"
    for agent_path in (tmp_path / ".codex" / "agents").glob("*.toml"):
        agent = tomllib.loads(agent_path.read_text(encoding="utf-8"))
        assert "model" not in agent
        assert "model_reasoning_effort" not in agent

    generated_agent_texts = {
        agent_path.name: agent_path.read_text(encoding="utf-8")
        for agent_path in (tmp_path / ".codex" / "agents").glob("*.toml")
    }
    for stale_contract in (
        "tool_search",
        "multi_agent_v1",
        "max_threads=6",
        "agents.max_depth",
        "Project-wide Claude control plane",
        "mcp__codex__codex",
        "codex-reply",
        "spawn_agent",
    ):
        assert all(
            stale_contract not in agent_text
            for agent_text in generated_agent_texts.values()
        ), stale_contract

    codex_readme = (tmp_path / ".codex" / "README.md").read_text(encoding="utf-8")
    assert "Use `/hooks`" in codex_readme
    assert "tool_input.command" in codex_readme
    assert "does not select `sandbox_mode`" in codex_readme
    assert "does not select `approval_policy`" in codex_readme
    assert "agent routing defaults" in codex_readme
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


def test_generator_derives_path_scoped_agents_and_manifest_entry(tmp_path: Path, generator) -> None:
    fixture = tmp_path / "fixture"
    scripts_dir = fixture / "scripts"
    scripts_dir.mkdir(parents=True)
    copy_generators(scripts_dir)
    (fixture / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
    (scripts_dir / "CLAUDE.md").write_text(
        "Read root CLAUDE.md before changing scripts.\n", encoding="utf-8"
    )

    completed = subprocess.run(
        generator(fixture),
        cwd=fixture,
        capture_output=True,
        text=True, encoding="utf-8",
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


def test_should_not_infer_read_only_sandbox_from_agent_name(tmp_path: Path, generator) -> None:
    fixture = tmp_path / "fixture"
    scripts_dir = fixture / "scripts"
    agent_dir = fixture / ".claude" / "agents"
    scripts_dir.mkdir(parents=True)
    agent_dir.mkdir(parents=True)
    copy_generators(scripts_dir)
    (fixture / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
    (agent_dir / "fleet-doc-steward.md").write_text(
        "---\n"
        "name: fleet-doc-steward\n"
        "description: Name-only fixture\n"
        "---\n\n"
        "Remain within the supplied scope.\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        generator(fixture),
        cwd=fixture,
        capture_output=True,
        text=True, encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    generated = tomllib.loads(
        (fixture / ".codex" / "agents" / "fleet-doc-steward.toml").read_text(
            encoding="utf-8"
        )
    )
    assert "sandbox_mode" not in generated


def test_generator_requires_exact_write_and_edit_tokens_for_read_only_sandbox(
    tmp_path: Path, generator) -> None:
    fixture = tmp_path / "fixture"
    scripts_dir = fixture / "scripts"
    agent_dir = fixture / ".claude" / "agents"
    scripts_dir.mkdir(parents=True)
    agent_dir.mkdir(parents=True)
    copy_generators(scripts_dir)
    (fixture / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
    for name, disallowed_tools in (
        ("writer-edit", "Writer, Edit"),
        ("write-notebook-edit", "Write, NotebookEdit"),
        ("quoted-edit-write", '"Edit, Bash, Write"'),
    ):
        (agent_dir / f"{name}.md").write_text(
            "---\n"
            f"name: {name}\n"
            "description: Exact-token fixture\n"
            f"disallowedTools: {disallowed_tools}\n"
            "---\n\n"
            "Remain within the supplied scope.\n",
            encoding="utf-8",
        )

    completed = subprocess.run(
        generator(fixture),
        cwd=fixture,
        capture_output=True,
        text=True, encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    for name in ("writer-edit", "write-notebook-edit", "quoted-edit-write"):
        generated = tomllib.loads(
            (fixture / ".codex" / "agents" / f"{name}.toml").read_text(
                encoding="utf-8"
            )
        )
        if name == "quoted-edit-write":
            assert generated["sandbox_mode"] == "read-only"
        else:
            assert "sandbox_mode" not in generated


def test_generator_rejects_invalid_patterned_frontmatter_before_agent_output(
    tmp_path: Path, generator) -> None:
    cases = (
        (
            "single-quoted-tools",
            "name: single-quoted-tools\n"
            "description: Invalid tools fixture\n"
            "disallowedTools: 'Write, Edit'\n",
            "disallowedTools",
        ),
        (
            "commented-tools",
            "name: commented-tools\n"
            "description: Invalid tools fixture\n"
            "disallowedTools: Write, Edit # read only\n",
            "disallowedTools",
        ),
        (
            "single-quoted-name",
            "name: 'single-quoted-name'\n"
            "description: Invalid name fixture\n",
            "name",
        ),
    )
    for fixture_name, frontmatter, invalid_field in cases:
        fixture = tmp_path / fixture_name
        scripts_dir = fixture / "scripts"
        agent_dir = fixture / ".claude" / "agents"
        scripts_dir.mkdir(parents=True)
        agent_dir.mkdir(parents=True)
        copy_generators(scripts_dir)
        (fixture / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
        (agent_dir / f"{fixture_name}.md").write_text(
            f"---\n{frontmatter}---\n\nRemain within the supplied scope.\n",
            encoding="utf-8",
        )

        completed = subprocess.run(
            generator(fixture),
            cwd=fixture,
            capture_output=True,
            text=True, encoding="utf-8",
            check=False,
        )

        assert completed.returncode != 0
        assert f"invalid {invalid_field} frontmatter value" in completed.stderr
        assert not any((fixture / ".codex" / "agents").glob("*.toml"))


def test_generator_validates_all_agent_sources_before_replacing_agent_output(
    tmp_path: Path, generator) -> None:
    fixture = tmp_path / "fixture"
    scripts_dir = fixture / "scripts"
    agent_dir = fixture / ".claude" / "agents"
    output_agent_dir = fixture / ".codex" / "agents"
    scripts_dir.mkdir(parents=True)
    agent_dir.mkdir(parents=True)
    output_agent_dir.mkdir(parents=True)
    copy_generators(scripts_dir)
    (fixture / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
    (agent_dir / "a-valid.md").write_text(
        "---\n"
        "name: a-valid\n"
        "description: Valid fixture\n"
        "disallowedTools: Write, Edit\n"
        "---\n\n"
        "Remain within the supplied scope.\n",
        encoding="utf-8",
    )
    (agent_dir / "z-invalid.md").write_text(
        "---\n"
        "name: z-invalid\n"
        "description: Invalid fixture\n"
        "disallowedTools: 'Write, Edit'\n"
        "---\n\n"
        "Remain within the supplied scope.\n",
        encoding="utf-8",
    )
    preserved = output_agent_dir / "preserved.toml"
    preserved.write_text('name = "preserved"\n', encoding="utf-8")

    completed = subprocess.run(
        generator(fixture),
        cwd=fixture,
        capture_output=True,
        text=True, encoding="utf-8",
        check=False,
    )

    assert completed.returncode != 0
    assert "invalid disallowedTools frontmatter value" in completed.stderr
    assert preserved.read_text(encoding="utf-8") == 'name = "preserved"\n'
    assert not (output_agent_dir / "a-valid.toml").exists()


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
        f"nested AGENTS derivative retains Claude-only path reference: {Path('src/AGENTS.md')}"
    ]


def test_verifier_rejects_legacy_raw_skill_provider(tmp_path: Path) -> None:
    raw_skill = tmp_path / ".agents" / "skills" / "example" / "SKILL.md"
    raw_skill.parent.mkdir(parents=True)
    raw_skill.write_text("# Example\n", encoding="utf-8")
    failures: list[str] = []

    verify_codex_sync.validate_plugin_skill_providers(failures, root=tmp_path)

    assert f"legacy raw skill provider remains: {Path('.agents/skills')}" in failures


def test_verifier_accepts_posix_source_marker_with_windows_relative_path(tmp_path, monkeypatch):
    source = tmp_path / "src/CLAUDE.md"
    source.parent.mkdir()
    source.write_text("# Fixture\n", encoding="utf-8")
    source.with_name("AGENTS.md").write_text(
        "<!-- GENERATED FILE: edit src/CLAUDE.md and rerun "
        "scripts/generate_codex_derivatives.sh -->\n\n# Fixture\n",
        encoding="utf-8",
    )
    relative_to = type(source).relative_to

    def windows_source_relative_to(path, *args):
        if path == source:
            return PureWindowsPath("src/CLAUDE.md")
        return relative_to(path, *args)

    monkeypatch.setattr(type(source), "relative_to", windows_source_relative_to)
    failures = []
    verify_codex_sync.validate_nested_instruction_derivatives(failures, root=tmp_path)
    assert failures == []


def test_should_validate_all_yoke_managed_runtime_surfaces() -> None:
    failures: list[str] = []

    verify_codex_sync.validate_managed_capability_surfaces(failures)

    assert failures == []


def test_generator_emits_real_portable_hook_library(tmp_path: Path, generator) -> None:
    source = tmp_path / "source"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    copy_generators(scripts)
    (source / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
    library = source / ".claude/hooks/lib"
    library.mkdir(parents=True)
    (library / "portable.py").write_text("# Portable fixture\n", encoding="utf-8")
    output = tmp_path / "output"
    env = {**os.environ, "CODEX_DERIVATION_OUTPUT_ROOT": str(output)}
    completed = subprocess.run(
        generator(source),
        cwd=source,
        env=env,
        capture_output=True,
        text=True, encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    target = output / ".codex" / "hooks" / "lib"
    assert target.is_dir()
    assert not target.is_symlink()
    failures: list[str] = []
    verify_codex_sync.validate_portable_hook_copy(
        failures, source_root=source, output_root=output
    )
    assert failures == []


@pytest.mark.parametrize("line_ending", ["\n", "\r\n"])
def test_generator_preserves_shell_body_and_frontmatter_rules(tmp_path, generator, line_ending):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    copy_generators(scripts)
    (tmp_path / "CLAUDE.md").write_bytes(
        line_ending.join(["---", "title: fixture", "---", "# Root", ""]).encode()
    )
    agents = tmp_path / ".claude/agents"
    agents.mkdir(parents=True)
    (agents / "sample.md").write_bytes(line_ending.join([
        "---", "name: sample", 'description: "A multiline', 'description"',
        "disallowedTools: Write, Edit", "---", "", '# Body with """', "last line",
    ]).encode())
    completed = subprocess.run(generator(tmp_path) + ["ignored-argument"],
                               capture_output=True, text=True, encoding="utf-8", check=False)
    assert completed.returncode == 0, completed.stderr
    body = (tmp_path / "AGENTS.md").read_bytes()
    if line_ending == "\r\n":
        assert b"---\r\ntitle: fixture\r\n" in body
    else:
        assert b"title: fixture" not in body
    agent = (tmp_path / ".codex/agents/sample.toml").read_bytes()
    assert b'description = "A multiline\ndescription"\n' in agent
    assert b'\\"""' in agent
    assert agent.endswith(b'last line\n"""\n')


def test_generator_missing_root_contract(tmp_path, generator):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    copy_generators(scripts)
    completed = subprocess.run(
        generator(tmp_path), capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 1
    assert completed.stderr == "ERROR: CLAUDE.md not found in repository root.\n"
    assert not (tmp_path / ".codex").exists()


@pytest.mark.parametrize("line_ending", ["\n", "\r\n"])
def test_generator_uses_adopter_catalog_and_optional_mcp(tmp_path, generator, line_ending):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    copy_generators(scripts)
    (tmp_path / "CLAUDE.md").write_text("# Fixture\n", encoding="utf-8")
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/repo-profile.toml").write_bytes(
        ('overlay_archetype = "product_adopter"' + line_ending).encode("utf-8"))
    (tmp_path / "config").mkdir()
    (tmp_path / "config/repo-agent-management.json").write_text(json.dumps({
        "catalog": {"agents": {"custom": {"source_path": "custom.md"}}}
    }), encoding="utf-8")
    (tmp_path / "custom.md").write_text(
        "---\nname: custom\ndescription: Custom\n---\nBody\n", encoding="utf-8")
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "fixture": {"command": "python3", "args": ["server.py", "--stdio"]},
        "no-args": {"command": "local"},
    }}), encoding="utf-8")
    completed = subprocess.run(
        generator(tmp_path), capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / ".codex/agents/custom.toml").is_file()
    config = tomllib.loads((tmp_path / ".codex/config.toml").read_text(encoding="utf-8"))
    assert config["mcp_servers"]["fixture"]["args"] == ["server.py", "--stdio"]
    assert config["mcp_servers"]["no-args"]["args"] == []
