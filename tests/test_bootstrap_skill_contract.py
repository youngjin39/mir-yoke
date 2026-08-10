from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_ARCHITECT = "spec-architect"


def _load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_minimal_starter_does_not_require_spec_architect() -> None:
    bootstrap = (ROOT / "BOOTSTRAP.md").read_text(encoding="utf-8")
    capability = _load_json("config/capability-sources.json")
    assert SPEC_ARCHITECT in capability["plugins"]["mir-core"]["skills"]
    assert all(
        "mir-core" in pack["plugins"]
        for pack in capability["profiles"]["packs"].values()
    )
    assert "specification tree" in bootstrap
    assert "does not require" in bootstrap
    assert "mir-core:spec-architect" not in bootstrap

    example = _load_json("config/repos/example.json")
    assert SPEC_ARCHITECT in example["active_skills"]

    manifest = _load_json("config/repo-agent-management.json")
    templates = manifest["templates"]
    assert templates, "management templates must not be empty"
    missing = [
        template_id
        for template_id, template in templates.items()
        if SPEC_ARCHITECT not in template["default_skill_pack"]["core"]
    ]
    assert missing == [], f"templates missing {SPEC_ARCHITECT} from core: {missing}"
