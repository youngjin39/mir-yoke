from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STARTER = ROOT / "starter"
SUPPORTED_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "HARNESS.md",
    "README.md",
}


def test_supported_starter_is_one_small_document_only_payload() -> None:
    files = {
        path.relative_to(STARTER).as_posix()
        for path in STARTER.rglob("*")
        if path.is_file()
    }

    assert files == SUPPORTED_FILES
    assert all((STARTER / relative).suffix == ".md" for relative in files)


def test_starter_routes_agents_to_one_local_contract() -> None:
    harness = (STARTER / "HARNESS.md").read_text(encoding="utf-8")
    claude = (STARTER / "CLAUDE.md").read_text(encoding="utf-8")
    agents = (STARTER / "AGENTS.md").read_text(encoding="utf-8")

    for heading in (
        "## Outcome and completion",
        "## Current state sources",
        "## Authority and safety",
        "## Work style",
        "## Verification",
    ):
        assert heading in harness
    assert "{{PROJECT_NAME}}" in harness
    assert "<Project" not in harness
    assert "HARNESS.md" in claude
    assert "HARNESS.md" in agents
    assert agents.startswith("<!-- Mir Yoke publication derivative.")
    assert "scripts/generate_codex_derivatives.sh" not in agents


def test_public_contract_names_the_minimal_support_boundary() -> None:
    root_docs = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in ("README.md", "BOOTSTRAP.md", "CLAUDE.md", "ARCHITECTURE.md")
    ).lower()

    assert "starter/" in root_docs
    assert "only supported consumer payload" in root_docs
    assert "does not require" in root_docs
    for optional in ("memory database", "plugin", "hook", "sub-agent"):
        assert optional in root_docs


def test_asset_manifest_classifies_the_minimal_starter() -> None:
    manifest = json.loads((ROOT / "config/template-assets.json").read_text())
    rules = {rule["id"]: rule for rule in manifest["rules"]}

    assert rules["minimal-starter"] == {
        "id": "minimal-starter",
        "classification": "starter",
        "include": ["starter/**"],
        "exclude": [],
        "reason": (
            "The only supported consumer payload: a small agent-adapted "
            "documentation baseline."
        ),
    }


def test_advanced_automation_spec_is_a_superseded_reference() -> None:
    index = __import__("yaml").safe_load((ROOT / "spec/index.yaml").read_text())
    state = (ROOT / "spec/STATE.md").read_text(encoding="utf-8")
    features = (ROOT / "spec/views/features.md").read_text(encoding="utf-8")

    assert index["status"] == "superseded-reference"
    assert index["superseded_by"] == "ADR-81"
    assert "not the current supported consumer contract" in state
    assert "Superseded reference snapshot" in features
