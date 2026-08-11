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
        "Build and verify the project-specific harness and Project Agent Kit first.",
        "Initialize a new Git repository and create the verified initial commit.",
        "Do not start product planning or implementation yet.",
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


def test_should_not_publish_a_legacy_target_writing_console_entrypoint() -> None:
    project = tomllib.loads(_read("pyproject.toml"))["project"]
    module_entrypoint = _read("src/mir/cli/__main__.py")

    assert "scripts" not in project
    assert "exposes no public CLI" in module_entrypoint


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


def test_should_limit_optional_consumer_tools_to_marketplaces_and_plugins() -> None:
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
