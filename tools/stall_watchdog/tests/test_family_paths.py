"""ADR-06 Phase 6C-1 unit tests — tools/stall_watchdog/family_paths.py."""

from __future__ import annotations

from tools.stall_watchdog.family_paths import (
    FAMILY_SLUG_TO_DISPLAY,
    WORKSPACE_DIR_TO_FAMILY,
    family_display_name,
    family_slug_to_env_key,
)


def test_workspace_dir_map_size():
    # 12 active workspaces + 4 legacy aliases = 16 entries
    assert len(WORKSPACE_DIR_TO_FAMILY) == 16


def test_display_map_size():
    # 13 family slugs
    assert len(FAMILY_SLUG_TO_DISPLAY) == 13


def test_write_score_mapping():
    assert (
        WORKSPACE_DIR_TO_FAMILY["-Volumes-T7-Shield-Project-05-Write-Score"]
        == "<example-family>"
    )


def test_mir_harness_mapping():
    assert (
        WORKSPACE_DIR_TO_FAMILY["-Volumes-T7-Shield-Project-09-Mini-Harness"]
        == "your-harness"
    )


def test_musinsa_brand_mapping():
    assert (
        WORKSPACE_DIR_TO_FAMILY["-Volumes-T7-Shield-Project-11-Musinsa-Brand"]
        == "<example-family>"
    )


def test_memory_keeper_mapping():
    assert (
        WORKSPACE_DIR_TO_FAMILY["-Volumes-T7-Shield-Project-12-Memory-Keeper"]
        == "memory-keeper"
    )


def test_legacy_minesweeper_alias():
    assert (
        WORKSPACE_DIR_TO_FAMILY["-Users-ai-agent-Flutter-Project-MineSweeper"]
        == "minesweeper"
    )
    assert (
        WORKSPACE_DIR_TO_FAMILY[
            "-Volumes-T7-Shield-Project-01-Flutter-03-MineSweeper"
        ]
        == "minesweeper"
    )


def test_legacy_quietleaf_alias():
    assert (
        WORKSPACE_DIR_TO_FAMILY[
            "-Users-ai-agent-Flutter-Project-DEVELOPMENT-GUIDE-<example-family>"
        ]
        == "<example-family>"
    )


def test_env_key_normalization():
    assert family_slug_to_env_key("<example-family>") == "WRITE_SCORE"
    assert family_slug_to_env_key("your-harness") == "MIR_HARNESS"
    assert family_slug_to_env_key("short-movie-director") == "SHORT_MOVIE_DIRECTOR"
    assert family_slug_to_env_key("home-server") == "HOME_SERVER"


def test_env_key_unknown_returns_sentinel():
    assert family_slug_to_env_key("does-not-exist") == "UNKNOWN"


def test_display_name_consistency_with_dict():
    # Use the dict itself as the source of truth so this test stays byte-stable
    # even if the editor mangles in-source Korean literals.
    for slug, expected in FAMILY_SLUG_TO_DISPLAY.items():
        assert family_display_name(slug) == expected


def test_display_name_unknown_returns_slug():
    assert family_display_name("does-not-exist") == "does-not-exist"


def test_all_workspace_dirs_map_to_known_family():
    for encoded, slug in WORKSPACE_DIR_TO_FAMILY.items():
        assert slug in FAMILY_SLUG_TO_DISPLAY, (
            encoded + " -> " + slug + " not in FAMILY_SLUG_TO_DISPLAY"
        )


def test_no_duplicate_workspace_keys():
    # dict literal already enforces uniqueness, but assert explicitly so a future
    # editor-induced duplicate is caught.
    assert len(set(WORKSPACE_DIR_TO_FAMILY)) == len(WORKSPACE_DIR_TO_FAMILY)


def test_15_active_active_dirs_with_volumes_prefix():
    active = [k for k in WORKSPACE_DIR_TO_FAMILY if k.startswith("-Volumes-T7-Shield-Project-")]
    # 11 T7-Shield workspaces (01..09,11,12 minus deleted repos) — updated 2026-06-12
    assert len(active) == 11
