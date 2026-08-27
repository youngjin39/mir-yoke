from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "recipes" / "project-agent-kit"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_should_route_one_short_prompt_to_the_project_agent_kit_recipe() -> None:
    readme = _read("README.md")

    assert "recipes/project-agent-kit/" in readme
    for line in (
        "[Prepared project purpose and goals]",
        "Harness: https://github.com/youngjin39/mir-yoke",
        "Complete and verify the project-specific harness and Project Agent Kit first.",
        "Initialize a new Git repository and create the verified initial commit.",
        "Do not start development planning or product implementation yet.",
    ):
        assert line in readme


def test_should_define_the_recipe_as_guidance_not_a_consumer_payload() -> None:
    recipe = _read("recipes/project-agent-kit/README.md")

    assert "supported agent-guided recipe" in recipe
    assert "read-only reference" in recipe
    assert "one explicit empty target directory" in recipe
    assert "does not copy Mir Yoke's Git history" in recipe
    assert "`yoke plan`" in recipe
    assert "`yoke apply`" in recipe
    assert "READY_FOR_DEVELOPMENT_PLANNING" in recipe


def test_should_require_concrete_purpose_before_writing() -> None:
    readme = _read("README.md")
    recipe = _read("recipes/project-agent-kit/README.md")
    normalized_recipe = " ".join(recipe.split())

    assert "Replace the bracketed first line with concrete project purpose and goals" in readme
    assert "the bracketed placeholder in `prompt.txt` cannot remain" in normalized_recipe
    assert "stop before writing and ask for it" in normalized_recipe


def test_should_require_a_project_owned_brief_harness_and_dual_runtime_reviewer() -> None:
    recipe = _read("recipes/project-agent-kit/README.md")
    reviewer = _read("recipes/project-agent-kit/reviewer.md")

    for artifact in ("PROJECT.md", "HARNESS.md", "CLAUDE.md", "AGENTS.md"):
        assert artifact in recipe
    assert "harness/project-agent-kit.json" in recipe
    for requirement in (
        "<project-slug>-code-review",
        "<project-slug>-code-reviewer",
        "tools: Read, Glob, Grep",
        "disallowedTools: Write, Edit",
        'sandbox_mode = "read-only"',
        "one-way Claude-to-Codex generator",
        "scripts/generate_agent_derivatives.py",
        "parity check",
    ):
        assert requirement in reviewer


def test_should_require_the_bounded_common_harness_and_memory_commands() -> None:
    recipe = _read("recipes/project-agent-kit/README.md")
    verification = _read("recipes/project-agent-kit/verification.md")
    schema = json.loads(_read("recipes/project-agent-kit/project-agent-kit.schema.json"))

    assert schema["properties"]["schema_version"] == {"const": 3}
    assert "context_probe" in schema["properties"]["intent"]["required"]
    common = schema["properties"]["common_harness"]
    paths = common["properties"]["paths"]["properties"]
    commands = common["properties"]["commands"]["properties"]
    assert {name: value["const"] for name, value in paths.items()} == {
        "config": "harness_a.toml",
        "database": ".mir/memory.db",
        "handoff": "tasks/handoffs/session-handoff-LATEST.md",
        "mir_wrapper": "scripts/mir.sh",
        "memory_sync_wrapper": "scripts/memory-sync.sh",
        "memory_sync_hook": ".githooks/pre-commit",
        "lifecycle_sources": [
            "harness/project-hooks.json",
            "scripts/render-hook-configs.py",
            ".claude/hooks/_lib/invocation_log.sh",
            ".claude/hooks/_lib/run-python.sh",
            ".claude/hooks/pre-compact.sh",
            ".claude/hooks/post-compact.sh",
            ".claude/hooks/compact-resume.sh",
        ],
        "generated_hooks": [".claude/settings.json", ".codex/hooks.json"],
    }
    assert set(commands) == {
        "memory_init",
        "memory_sync",
        "memory_doctor",
        "context_pull",
        "hook_render",
        "hook_parity",
    }
    combined = f"{recipe}\n{verification}"
    for requirement in (
        "templates/common-harness/",
        "scripts/memory-sync.sh",
        ".mir/memory.db",
        "rehydratable",
        "`src/mir/`, `tools/`, or `plugins/`",
        "memory_init",
        "memory_sync",
        "memory_doctor",
        "context_pull",
        "PreCompact",
        "PostCompact",
        "SessionStart(source=compact)",
        "hook_render",
        "hook_parity",
        "nested working directory",
        "path containing spaces",
    ):
        assert requirement in combined


def test_should_require_task_scoped_context_pull_at_each_fresh_session() -> None:
    recipe = _read("recipes/project-agent-kit/README.md")
    normalized = " ".join(recipe.split())

    assert "fresh session" in normalized
    assert "task-scoped" in normalized
    assert "Generated `HARNESS.md`" in normalized
    assert (
        '`scripts/mir.sh context pull "<task query>" --db .mir/memory.db '
        "--project-root .`"
    ) in normalized
    assert "must not reuse `intent.context_probe`" in normalized


def test_should_require_a_real_git_pre_commit_gate_and_verified_initial_commit() -> None:
    recipe = _read("recipes/project-agent-kit/README.md")
    verification = _read("recipes/project-agent-kit/verification.md")
    combined = f"{recipe}\n{verification}"

    for requirement in (
        ".githooks/pre-commit",
        "core.hooksPath=.githooks",
        "PROJECT_AGENT_KIT_HOOK_PHASE=direct",
        "direct:0",
        "commit:0",
        "scripts/verify.sh",
        "lint",
        "build",
        "test",
        "git init -b main",
        "git config --get user.name",
        "git config --get user.email",
        "chore(harness): bootstrap project agent kit",
        "exactly one commit",
        "clean worktree",
    ):
        assert requirement in combined
    for forbidden_success in ("placeholder", "`true`", "echo skip"):
        assert forbidden_success in verification
    assert "no remote" in verification
    assert "no push" in verification
    assert "except the exact source URL and revision provenance" in verification
    assert "no global dependency was installed" in verification
    assert "target-local and ignored" in verification
    assert recipe.index("git init -b main") < recipe.index(
        "PROJECT_AGENT_KIT_HOOK_PHASE=direct"
    )
    assert recipe.index("PROJECT_AGENT_KIT_HOOK_PHASE=direct") < recipe.index(
        "stage only the Project Agent Kit foundation"
    )


def test_should_publish_optional_mir_without_the_legacy_yoke_composer() -> None:
    project = tomllib.loads(_read("pyproject.toml"))["project"]
    module_entrypoint = _read("src/mir/cli/__main__.py")
    command_registry = _read("src/mir/cli/__init__.py")

    assert project["scripts"] == {"mir": "mir.cli.__main__:main"}
    assert "Public ``mir`` command dispatcher" in module_entrypoint
    assert '"yoke"' not in command_registry


def test_should_keep_the_default_starter_small_and_remove_active_composition() -> None:
    starter_files = {
        path.relative_to(ROOT / "starter").as_posix()
        for path in (ROOT / "starter").rglob("*")
        if path.is_file()
    }
    assert starter_files == {"AGENTS.md", "CLAUDE.md", "HARNESS.md", "README.md"}

    candidate_files = {
        relative
        for relative in subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            text=True,
        ).splitlines()
        if (ROOT / relative).is_file()
    }
    for relative in (
        "packs",
        "profiles",
        "config/product-planes.json",
        "config/product-planes.schema.json",
        "config/capability-pack.schema.json",
        "src/mir/cli/yoke.py",
        "src/mir/core/distribution",
        "docs/bluebricks/composition.md",
        "docs/bluebricks/distribution.md",
    ):
        assert not any(
            candidate == relative or candidate.startswith(f"{relative}/")
            for candidate in candidate_files
        ), relative

    active_docs = "\n".join(
        _read(relative).lower()
        for relative in (
            "README.md",
            "BOOTSTRAP.md",
            "CLAUDE.md",
            "ARCHITECTURE.md",
            "docs/decisions/INDEX.md",
        )
    )
    for unsupported in ("yoke plan", "yoke apply", "product planes", "capability packs"):
        assert unsupported not in active_docs


def test_should_limit_optional_consumer_tools_to_explicit_adoption_surfaces() -> None:
    manifest = json.loads(_read("config/template-assets.json"))
    optional_patterns = {
        pattern
        for rule in manifest["rules"]
        if rule["classification"] == "optional-consumer-tool"
        for pattern in rule["include"]
    }

    assert optional_patterns == {
        ".agents/plugins/**",
        ".claude-plugin/**",
        "plugins/**",
        "templates/common-harness/**",
        "src/**",
        "tools/agent_loader/**",
        "tools/autonomous_loop/**",
        "tools/catalog_loader.py",
        "tools/hooks/**",
        "tools/mir_executor/**",
        "tools/plan_archive/**",
        "tools/run_orchestrator/**",
    }


def test_should_classify_the_supported_recipe_as_non_payload_guidance() -> None:
    manifest = json.loads(_read("config/template-assets.json"))
    rule = next(
        rule for rule in manifest["rules"] if rule["id"] == "project-agent-kit-recipe"
    )

    assert rule["classification"] == "reference"
    assert rule["include"] == ["recipes/**"]
    assert "Supported agent-guided procedure" in rule["reason"]
    assert "never copied as a consumer payload" in rule["reason"]
    assert (RECIPE / "project-agent-kit.schema.json").is_file()
