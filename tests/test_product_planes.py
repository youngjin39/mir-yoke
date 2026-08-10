from __future__ import annotations

import json
import tomllib
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
PACK_IDS = {"safety", "memory", "collaboration", "assurance"}


def test_should_define_four_planes_when_product_manifest_is_loaded() -> None:
    manifest = json.loads((ROOT / "config/product-planes.json").read_text())
    schema = json.loads((ROOT / "config/product-planes.schema.json").read_text())

    jsonschema.validate(manifest, schema)
    assert set(manifest["planes"]) == {"source", "distribution", "project", "local"}
    assert manifest["planes"]["distribution"]["tracked"] is False
    assert manifest["planes"]["project"]["canonical_contract"] == "HARNESS.md"
    assert manifest["planes"]["local"]["root"] == ".mir"


def test_should_cover_existing_asset_classes_when_plane_axes_are_loaded() -> None:
    manifest = json.loads((ROOT / "config/product-planes.json").read_text())
    assets = json.loads((ROOT / "config/template-assets.json").read_text())

    assert set(manifest["asset_axes"]) == set(assets["classifications"])
    active_paths = {
        path
        for override in manifest["execution_overrides"]
        if override["execution_state"] == "active-maintainer"
        for path in override["paths"]
    }
    assert ".claude/settings.json" in active_paths
    assert ".claude/hooks/**" in active_paths
    assert ".codex/config.toml" in active_paths


def test_should_validate_each_pack_when_pack_catalog_is_loaded() -> None:
    schema = json.loads((ROOT / "config/capability-pack.schema.json").read_text())
    manifests = {}
    for path in sorted((ROOT / "packs").glob("*/pack.json")):
        payload = json.loads(path.read_text())
        jsonschema.validate(payload, schema)
        manifests[payload["id"]] = payload
        for pattern in payload["source_paths"]:
            assert list(ROOT.glob(pattern)), f"{payload['id']}: {pattern}"
        for asset in payload["adoption_assets"]:
            assert (ROOT / asset["source"]).is_file(), asset

    assert set(manifests) == PACK_IDS
    assert manifests["safety"]["support_level"] == "stable"
    assert all(item["execution_state"] == "opt-in" for item in manifests.values())
    release_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert all(item["version"] == release_version for item in manifests.values())


def test_should_reference_known_packs_when_profiles_are_loaded() -> None:
    known = {
        json.loads(path.read_text())["id"]
        for path in (ROOT / "packs").glob("*/pack.json")
    }
    profiles = sorted((ROOT / "profiles").glob("*.toml"))

    assert {path.stem for path in profiles} == {
        "minimal",
        "code",
        "content",
        "collaboration",
        "assured",
    }
    for path in profiles:
        profile = tomllib.loads(path.read_text())
        composition = profile["composition"]
        assert set(composition["default_packs"]) <= known
        assert set(composition["recommended_packs"]) <= known
        assert profile["policy"]["mandatory"] is False


def test_should_preserve_existing_platform_when_pack_sources_are_declared() -> None:
    preserved = {
        "src/mir/cli/bootstrap.py",
        "src/mir/cli/capability.py",
        "src/mir/cli/memory.py",
        ".claude/hooks/pre-tool-use.sh",
        "tools/mir_executor/cli.py",
        "plugins/mir-core/skills/spec-architect/SKILL.md",
    }
    declared = {
        match.relative_to(ROOT).as_posix()
        for manifest_path in (ROOT / "packs").glob("*/pack.json")
        for pattern in json.loads(manifest_path.read_text())["source_paths"]
        for match in ROOT.glob(pattern)
        if match.is_file()
    }

    assert all((ROOT / relative).is_file() for relative in preserved)
    assert preserved <= declared


def test_should_keep_collaboration_roles_runtime_neutral_when_adapters_are_loaded() -> None:
    roles = json.loads(
        (ROOT / "packs/collaboration/payload/config/agent-roles.json").read_text()
    )["roles"]

    assert set(roles) == {"control-plane", "executor", "reviewer"}
    for role in roles.values():
        assert set(role["runtime_adapters"]) == {"claude", "codex"}
        assert "claude" not in " ".join(role["responsibilities"])
    assert roles["control-plane"]["runtime_adapters"]["claude"]["delegated_tool"] == "Agent"
    assert (
        roles["control-plane"]["runtime_adapters"]["codex"]["delegated_tool"]
        == "spawn_agent"
    )
