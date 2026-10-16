"""Release metadata must describe one public template version."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    package = next(item for item in lock["package"] if item["name"] == project["project"]["name"])
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert version == project["project"]["version"] == package["version"]
    assert f"## [{version}]" in changelog
