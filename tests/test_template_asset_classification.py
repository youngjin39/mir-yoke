from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from tools.template_assets import AssetManifestError, classify_tracked_files, load_manifest

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
