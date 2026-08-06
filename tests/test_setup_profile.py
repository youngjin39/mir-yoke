"""The Python coordinator emits the compact, safety-complete profile."""

import tomllib

from mir.cli.bootstrap import _repo_profile_text


def test_setup_profile_tracks_canonical_and_generated_surfaces() -> None:
    profile = tomllib.loads(_repo_profile_text("sample-project", "code_app"))

    assert ".mir/memory.db*" in profile["paths"]["protected_paths"]
    assert "AGENTS.md" in profile["paths"]["generated_paths"]
    assert ".codex/**" in profile["paths"]["generated_paths"]
    assert profile["preserve"]["agent_memory_paths"] == [".mir/memory.db"]
    assert profile["gates"]["requires_memory_store"] is True
    assert profile["gates"]["requires_global_capabilities"] is True
