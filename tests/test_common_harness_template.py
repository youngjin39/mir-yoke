from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "common-harness"


def test_should_provide_only_the_bounded_common_harness_sources() -> None:
    files = {
        path.relative_to(TEMPLATE).as_posix()
        for path in TEMPLATE.rglob("*")
        if path.is_file()
    }

    assert files == {
        "harness_a.toml",
        "scripts/memory-sync.sh",
        "scripts/mir.sh",
        "tasks/handoffs/session-handoff-LATEST.md",
    }
    assert not any(path.startswith(("src/mir/", "tools/", "plugins/")) for path in files)


def test_should_define_a_rehydratable_project_local_memory_index() -> None:
    config = tomllib.loads((TEMPLATE / "harness_a.toml").read_text(encoding="utf-8"))
    memory = config["memory"]

    assert memory["required"] is True
    assert memory["backend"] == "sqlite_fts5"
    assert memory["db_path"] == ".mir/memory.db"
    assert memory["vector_mode"] == "off"
    assert memory["external_archives"] == [
        {
            "slug": "project-harness",
            "root": ".",
            "mode": "indexed",
            "glob_include": [
                "PROJECT.md",
                "HARNESS.md",
                "docs/**/*.md",
                "tasks/**/*.md",
            ],
        }
    ]


def test_should_pin_external_mir_and_confine_its_runtime_state() -> None:
    wrapper = (TEMPLATE / "scripts/mir.sh").read_text(encoding="utf-8")
    sync = (TEMPLATE / "scripts/memory-sync.sh").read_text(encoding="utf-8")

    assert "git+https://github.com/youngjin39/mir-yoke@{{MIR_YOKE_REVISION}}" in wrapper
    for variable in (
        "HOME",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "TMPDIR",
        "UV_CACHE_DIR",
        "UV_TOOL_DIR",
        "UV_PYTHON_INSTALL_DIR",
    ):
        assert f"export {variable}=" in wrapper
    assert "src/mir" not in wrapper
    assert "scripts/mir.sh context sync --db .mir/memory.db --project-root ." in sync


def test_should_leave_a_cold_resume_handoff_before_product_planning() -> None:
    handoff = (TEMPLATE / "tasks/handoffs/session-handoff-LATEST.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(handoff.split())

    assert "Product planning and implementation have not started" in normalized
    assert "context_pull" in handoff
    assert "memory_init" in handoff
    assert "memory_sync" in handoff
    assert "memory_doctor" in handoff
