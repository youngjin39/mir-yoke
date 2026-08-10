"""The Python coordinator emits the compact, safety-complete profile."""

import tomllib
from pathlib import Path

from mir.cli.bootstrap import _repo_profile_text


def test_setup_profile_tracks_canonical_and_generated_surfaces(tmp_path: Path) -> None:
    profile = tomllib.loads(
        _repo_profile_text(
            tmp_path,
            "sample-project",
            "code_app",
            "Build a portable sample application.",
            ["python", "sqlite"],
        )
    )

    assert ".mir/memory.db*" in profile["paths"]["protected_paths"]
    assert "config/adopter-boundary.json" in profile["paths"]["protected_paths"]
    assert "config/adopter-payload.json" in profile["paths"]["protected_paths"]
    assert ".mir/bootstrap-receipt.json" in profile["paths"]["protected_paths"]
    assert ".mir/capability-lock.json" in profile["paths"]["protected_paths"]
    assert ".mir/cli-runtime-lock.json" not in profile["paths"]["protected_paths"]
    assert "profiles/**" in profile["paths"]["protected_paths"]
    assert "playwright/.auth/**" in profile["paths"]["protected_paths"]
    assert "state/**" in profile["paths"]["protected_paths"]
    assert "logs/**" in profile["paths"]["protected_paths"]
    assert "AGENTS.md" in profile["paths"]["generated_paths"]
    assert ".codex/**" in profile["paths"]["generated_paths"]
    assert profile["preserve"]["agent_memory_paths"] == [".mir/memory.db"]
    assert profile["gates"]["requires_memory_store"] is True
    assert profile["gates"]["requires_global_capabilities"] is True
    assert profile["repo"]["purpose"] == "Build a portable sample application."
    assert profile["repo"]["technology_stack"] == ["python", "sqlite"]
    assert profile["repo"]["path"] == str(tmp_path.resolve())
    assert profile["repo"]["repository_type"] == "code_app"
    assert profile["repo"]["overlay_archetype"] == "product_adopter"
    assert profile["paths"]["code_paths"] == ["app/", "apps/", "packages/"]
    assert Path(profile["repo"]["path"]).is_absolute()
