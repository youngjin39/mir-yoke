"""Startup context remains task-blind and non-duplicative."""

from pathlib import Path

from scripts.build_session_upfront_context import build_upfront_context


def test_upfront_context_keeps_safety_inventory_without_repeating_pull_command(
    tmp_path: Path,
) -> None:
    profile_dir = tmp_path / ".mir"
    profile_dir.mkdir()
    profile_dir.joinpath("repo-profile.toml").write_text(
        """
[repo]
slug = "fixture"
display_name = "Fixture"
repository_type = "test"

[paths]
protected_paths = [".env", ".mir/memory.db*"]
generated_paths = ["AGENTS.md", "**/AGENTS.md", ".codex/**"]

[preserve]
agent_memory_paths = [".mir/memory.db"]

[boundaries]
secrets = [".env"]
live_runtime = []
data_sensitivity = "low"
release_window = "anytime"

[gates]
requires_phase_gate = false
""".strip()
        + "\n",
        encoding="utf-8",
    )

    rendered = build_upfront_context(tmp_path)

    assert "repository: Fixture (fixture, test)" in rendered
    assert "protected_paths: .env, .mir/memory.db*" in rendered
    assert "generated_paths: AGENTS.md, **/AGENTS.md, .codex/**" in rendered
    assert "Context depth on demand" not in rendered
    assert rendered.endswith("=== END REPOSITORY CONTEXT ===")
