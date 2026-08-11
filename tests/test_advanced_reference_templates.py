from __future__ import annotations

import ast
import hashlib
import json
import tomllib
from pathlib import Path

import jsonschema

from tools.template_assets import build_adopter_payload, classify_candidate_files, load_manifest

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = ROOT / "reference-templates/advanced-composition"
SOURCE_ROOT = REFERENCE_ROOT / "source"

EXPECTED_SOURCE_HASHES = {
    "config/capability-pack.schema.json": (
        "a00d246fa2533179b5947e1d5859b26d82b02a5ec362ad4fd6ba82e941378dec"
    ),
    "config/product-planes.json": (
        "df0bf369860c6849b976f79d417a38bdf72ae28b2c67a28d07cb0ffb5629412b"
    ),
    "config/product-planes.schema.json": (
        "807d76e534680c05bb759eda1b8764100d7b284d75112ea1d85dd934384eb973"
    ),
    "docs/bluebricks/composition.md": (
        "3e3d93b87ae132ea8bdd9840c6a5e337cc0f78a9bf97ac1f742c3fe4343637d1"
    ),
    "docs/bluebricks/distribution.md": (
        "f0cc252e5798a31b24ba245a21706f8c4a967afaaf4b8b81bfec41bdad769719"
    ),
    "packs/assurance/README.md": (
        "7646c58bd42cfcba8d8af08bfdbb9f162ee19b37613e9a3e8ff04701cb09c6ed"
    ),
    "packs/assurance/pack.json": (
        "e270e9ccaf86795127bd9167789712169077d95c47933f235e1fb93db72ab72f"
    ),
    "packs/assurance/payload/ASSURANCE.md": (
        "95df90f11dc40ebb6585431c82876051b6c3334f86c8d49515286d57ecf6bf82"
    ),
    "packs/assurance/payload/config/assurance.toml": (
        "cec4801bf0b01d6a1bfef967b633bdf6a62035e8144bfca10885063baf510853"
    ),
    "packs/collaboration/README.md": (
        "4b3d7535215921bc901ab7706c3f9caf3483a8b5896961d4817d6229055ccfe9"
    ),
    "packs/collaboration/pack.json": (
        "05c114a1f54570d9e7a0567ef5d7054bb4e0f1a3c0f27d611ba1a5890f73c904"
    ),
    "packs/collaboration/payload/COLLABORATION.md": (
        "dc73aea46b1408332d34ec2144e4062c838466d71f9b4d17da248dc01d6a1188"
    ),
    "packs/collaboration/payload/config/agent-roles.json": (
        "ae5a4cdf8ccaa7ba1027cd8c67976e603be1f9937520df16e56bad660075773d"
    ),
    "packs/memory/README.md": (
        "c2cd74906979b9e8fc3a34a40d344caf5c74356c03ae1bdb13bb89ed333193ef"
    ),
    "packs/memory/pack.json": (
        "aa0b9bd3605fbc237102133fd91c0ed41cd02e9621c50b825028f3ead00dd092"
    ),
    "packs/memory/payload/MEMORY.md": (
        "d064cf07e04e074a4f799e832aeaa8739842723d68d943bc24a0252c1e4f7ed5"
    ),
    "packs/memory/payload/config/memory.toml": (
        "2ba47cb59afe654c0825b300ea14b74cad9317eb05141c37f0aeead8b4f9e5c8"
    ),
    "packs/safety/README.md": (
        "cddd85ef25b88b637f5b92ee484ed308de957f50c89f1b5710ed0376bce58c1d"
    ),
    "packs/safety/pack.json": (
        "27114fc4ff93a25723bf50c22fdc5c1c451e73f00f12bcedaaf3636a1dcd87b7"
    ),
    "packs/safety/payload/.claude/hooks/mir-safety.py": (
        "85e228dca814f78657eedb76953df8db0e26d9cef36cebb1ab5a2716b4578007"
    ),
    "packs/safety/payload/.claude/settings.safety.example.json": (
        "b65aab42ebe3995d469cd61f1c6ad864f4df8d60242b976ec8d4dc6af6e91a26"
    ),
    "packs/safety/payload/SAFETY.md": (
        "22da506e80c359964814425a9674dc239ebe05c585781daf7bc5bcb8898b32ee"
    ),
    "packs/safety/payload/config/harness-policy.toml": (
        "11b4cb2de03cc9b9b6196af5a9404eaee9457d8ec460eb6c6858f1954c54aada"
    ),
    "profiles/assured.toml": (
        "af7d2c5503cec220218fb6ad34e8eae2622b915cc0b3e37249aa4527f2d08e71"
    ),
    "profiles/code.toml": (
        "0c45203cced491bde53fd972f837f5a9a58b8de75cb3d5761a59fb644def2969"
    ),
    "profiles/collaboration.toml": (
        "9f933f135749d939f9cfbe9e6a0f7fb63feedc2641c5b9f9def1dd444343a782"
    ),
    "profiles/content.toml": (
        "72f5335f9568d5cc652d0252c84d7eef11aa24d24548e47fa10b4185f9a7f813"
    ),
    "profiles/minimal.toml": (
        "1eb3879875db8608da1201cec6cfddab040884e338551d874126a1b9c31f10c1"
    ),
    "src/mir/cli/yoke.py": (
        "e264c26fbfb0cb6d1e056acaade759ee26a7b48e61c3ee553ecae6755f837b20"
    ),
    "src/mir/core/distribution/__init__.py": (
        "68ca6ea30d37cb8794679c9986606ab9f2582065bfa83fe1be0659bddc980e45"
    ),
    "src/mir/core/distribution/builder.py": (
        "b488af05123eef19af3b1edc642f08f947808ad03dc3f26eb30610a1f90a5ee0"
    ),
    "src/mir/core/distribution/catalog.py": (
        "0293789c8ff2c6e82249c790ef148a04218a11b37496ed6f1e390c4aa1675027"
    ),
    "src/mir/core/distribution/composer.py": (
        "a0d61a630c8bdbea75d3cd2189ce7290bd3d210bfdf81bc58dc99083b162def4"
    ),
}


def _reference_payload_paths() -> set[str]:
    prefix = REFERENCE_ROOT.relative_to(ROOT).as_posix()
    return {
        f"{prefix}/README.md",
        *(f"{prefix}/source/{relative}" for relative in EXPECTED_SOURCE_HASHES),
    }


def test_should_match_exact_adr_82_inventory_when_reference_template_is_inspected() -> None:
    actual_paths = {
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_ROOT.rglob("*")
        if path.is_file()
    }

    assert len(actual_paths) == 33
    assert actual_paths == set(EXPECTED_SOURCE_HASHES)
    assert {
        relative: hashlib.sha256((SOURCE_ROOT / relative).read_bytes()).hexdigest()
        for relative in actual_paths
    } == EXPECTED_SOURCE_HASHES


def test_should_validate_product_planes_and_packs_when_reference_schemas_are_used() -> None:
    plane_schema = json.loads(
        (SOURCE_ROOT / "config/product-planes.schema.json").read_text(encoding="utf-8")
    )
    pack_schema = json.loads(
        (SOURCE_ROOT / "config/capability-pack.schema.json").read_text(encoding="utf-8")
    )
    product_planes = json.loads(
        (SOURCE_ROOT / "config/product-planes.json").read_text(encoding="utf-8")
    )

    jsonschema.Draft202012Validator.check_schema(plane_schema)
    jsonschema.Draft202012Validator.check_schema(pack_schema)
    jsonschema.validate(product_planes, plane_schema)

    pack_paths = sorted(SOURCE_ROOT.glob("packs/*/pack.json"))
    assert [path.parent.name for path in pack_paths] == [
        "assurance",
        "collaboration",
        "memory",
        "safety",
    ]
    for pack_path in pack_paths:
        jsonschema.validate(json.loads(pack_path.read_text(encoding="utf-8")), pack_schema)


def test_should_parse_all_profiles_and_policy_files_when_reference_toml_is_loaded() -> None:
    toml_paths = sorted(SOURCE_ROOT.rglob("*.toml"))
    payloads = {
        path.relative_to(SOURCE_ROOT).as_posix(): tomllib.loads(
            path.read_text(encoding="utf-8")
        )
        for path in toml_paths
    }

    assert len(payloads) == 8
    assert all(payload["schema_version"] == 1 for payload in payloads.values())
    assert {
        payload["name"]
        for relative, payload in payloads.items()
        if relative.startswith("profiles/")
    } == {"assured", "code", "collaboration", "content", "minimal"}


def test_should_classify_reference_snapshot_once_when_asset_manifest_is_loaded() -> None:
    manifest = load_manifest(ROOT / "config/template-assets.json")
    classified = classify_candidate_files(ROOT, manifest)
    rules = {rule["id"]: rule for rule in manifest["rules"]}

    assert rules["advanced-composition-reference"] == {
        "id": "advanced-composition-reference",
        "classification": "reference",
        "include": ["reference-templates/**"],
        "exclude": [],
        "reason": (
            "Inactive ADR-82 composition source preserved at original relative paths for "
            "selective inspection and adaptation."
        ),
    }
    assert {classified[path] for path in _reference_payload_paths()} == {"reference"}


def test_should_remove_reference_snapshot_when_adopter_payload_is_built() -> None:
    manifest = load_manifest(ROOT / "config/template-assets.json")
    boundary = json.loads((ROOT / "config/adopter-boundary.json").read_text(encoding="utf-8"))
    payload = build_adopter_payload(ROOT, manifest, boundary)
    persisted = json.loads((ROOT / "config/adopter-payload.json").read_text(encoding="utf-8"))
    reference_paths = _reference_payload_paths()
    reference_files = {
        item["path"]: item
        for item in payload["files"]
        if item["path"] in reference_paths
    }

    assert payload == persisted
    assert set(reference_files) == reference_paths
    assert {item["classification"] for item in reference_files.values()} == {"reference"}
    assert {item["disposition"] for item in reference_files.values()} == {"remove"}


def test_should_parse_preserved_python_without_importing_when_reference_ast_is_checked() -> None:
    python_paths = sorted(SOURCE_ROOT.rglob("*.py"))

    assert {path.relative_to(SOURCE_ROOT).as_posix() for path in python_paths} == {
        "packs/safety/payload/.claude/hooks/mir-safety.py",
        "src/mir/cli/yoke.py",
        "src/mir/core/distribution/__init__.py",
        "src/mir/core/distribution/builder.py",
        "src/mir/core/distribution/catalog.py",
        "src/mir/core/distribution/composer.py",
    }
    for path in python_paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())


def test_should_keep_composition_surfaces_inactive_when_current_runtime_is_inspected() -> None:
    active_paths = (
        "yoke",
        "distribution",
        "packs",
        "profiles",
        "src/mir/cli/yoke.py",
        "src/mir/core/distribution",
    )
    assert all(not (ROOT / relative).exists() for relative in active_paths)

    dispatcher_paths = (ROOT / "src/mir/cli/__init__.py", ROOT / "src/mir/cli/__main__.py")
    dispatcher_strings = {
        node.value
        for path in dispatcher_paths
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "yoke" not in dispatcher_strings
    assert "mir.cli.yoke" not in dispatcher_strings

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "yoke" not in project["project"]["scripts"]
