from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from tools.template_assets import (
    AssetManifestError,
    build_adopter_payload,
    classify_tracked_files,
    load_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


# @spec FR-003
def test_should_classify_every_tracked_surface_once_when_manifest_is_valid() -> None:
    manifest = load_manifest(ROOT / "config/template-assets.json")
    result = classify_tracked_files(ROOT, manifest)

    assert result["unclassified"] == []
    assert result["duplicate"] == []
    assert result["prohibited"] == []
    assert result["classified_count"] == result["tracked_count"]
    assert set(result["by_classification"]) == {
        "starter",
        "reference",
        "optional-consumer-tool",
        "template-maintainer-tool",
        "historical",
    }


# @spec FR-003
def test_should_fail_when_a_surface_has_no_or_multiple_classifications(tmp_path: Path) -> None:
    source = json.loads((ROOT / "config/template-assets.json").read_text())

    missing = copy.deepcopy(source)
    missing["rules"] = [rule for rule in missing["rules"] if rule["id"] != "root-metadata"]
    with pytest.raises(AssetManifestError, match="unclassified"):
        classify_tracked_files(ROOT, missing)

    duplicate = copy.deepcopy(source)
    duplicate["rules"].append(
        {
            "id": "duplicate-readme",
            "classification": "reference",
            "include": ["README.md"],
            "exclude": [],
            "reason": "Intentional invalid overlap for the contract test.",
        }
    )
    with pytest.raises(AssetManifestError, match="multiple"):
        classify_tracked_files(ROOT, duplicate)


# @spec FR-003 IR-001
def test_should_match_asset_schema_when_public_manifest_is_loaded() -> None:
    schema = json.loads((ROOT / "config/template-assets.schema.json").read_text())
    manifest = json.loads((ROOT / "config/template-assets.json").read_text())
    jsonschema.validate(manifest, schema)


# @spec FR-003
def test_should_return_nonstarter_classification_when_provider_sources_are_inspected() -> None:
    manifest = load_manifest(ROOT / "config/template-assets.json")
    rules = {rule["id"]: rule for rule in manifest["rules"]}

    starter_patterns = set(rules["minimal-starter"]["include"])
    legacy_patterns = set(rules["legacy-bootstrap-payload"]["include"])
    optional_patterns = set(rules["portable-plugin-provider"]["include"])

    assert {".agents/plugins/**", ".claude-plugin/**", "plugins/**"}.isdisjoint(
        starter_patterns
    )
    assert rules["legacy-bootstrap-payload"]["classification"] == "reference"
    assert "setup.sh" in legacy_patterns
    assert optional_patterns == {
        ".agents/plugins/**",
        ".claude-plugin/**",
        "plugins/**",
    }


# @spec FR-001 FR-003
def test_should_match_exact_adopter_payload_when_release_inventory_is_generated() -> None:
    manifest = load_manifest(ROOT / "config/template-assets.json")
    boundary = json.loads((ROOT / "config/adopter-boundary.json").read_text())
    payload = json.loads((ROOT / "config/adopter-payload.json").read_text())

    assert payload == build_adopter_payload(ROOT, manifest, boundary)
    adr_79 = next(
        item
        for item in payload["files"]
        if item["path"] == "docs/decisions/adr-79-agent-guided-platform-scope.md"
    )
    assert adr_79["classification"] == "reference"
    assert adr_79["disposition"] == "remove"


# @spec FR-001 FR-003
def test_should_remove_provider_state_and_preserve_adopter_runtime_when_payload_is_built() -> None:
    manifest = load_manifest(ROOT / "config/template-assets.json")
    boundary = json.loads((ROOT / "config/adopter-boundary.json").read_text())
    payload = build_adopter_payload(ROOT, manifest, boundary)
    dispositions = {item["path"]: item["disposition"] for item in payload["files"]}

    assert dispositions["src/mir/cli/bootstrap.py"] == "remove"
    assert dispositions["tests/test_bootstrap_cli.py"] == "remove"
    assert dispositions["tasks/plan.md"] == "remove"
    assert dispositions["config/repos/mir-yoke.json"] == "remove"
    assert dispositions["scripts/mir.sh"] == "remove"
    assert dispositions["config/adopter-boundary.json"] == "remove"
    assert dispositions["config/cli-runtime-constraints.txt"] == "remove"
    assert dispositions["starter/HARNESS.md"] == "preserve"
    assert dispositions[".claude/agents/template-sync-validator.md"] == "remove"
    assert dispositions[".codex/agents/template-sync-validator.toml"] == "remove"

    classifications = {
        item["path"]: item["classification"] for item in payload["files"]
    }
    assert classifications[".claude/agents/template-sync-validator.md"] == (
        "template-maintainer-tool"
    )
    assert classifications[".codex/agents/template-sync-validator.toml"] == (
        "template-maintainer-tool"
    )

    markers = set(boundary["provider_markers"])
    assert ".claude/agents/template-sync-validator.md" in markers
    assert ".codex/agents/template-sync-validator.toml" in markers

    sources = json.loads((ROOT / "config/capability-sources.json").read_text())
    for pack in sources["profiles"]["packs"].values():
        assert ".claude/agents/template-sync-validator.md" not in pack["agents"]
