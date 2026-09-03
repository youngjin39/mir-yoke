from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_ADR = ROOT / "docs/decisions/adr-78-public-template-identity-and-non-authority.md"
MINIMAL_ADR = ROOT / "docs/decisions/adr-81-minimal-starter-support-boundary.md"
PROJECT_AGENT_KIT_ADR = (
    ROOT / "docs/decisions/adr-83-project-agent-kit-recipe-and-supported-surfaces.md"
)
UPGRADE_ADR = (
    ROOT / "docs/decisions/adr-84-harness-upgrade-guidance-and-runtime-hygiene.md"
)
GLOBAL_POLICY_ADR = (
    ROOT / "docs/decisions/adr-85-global-policy-inheritance-and-agent-contracts.md"
)
ACTIVE_PLUGIN_ADR = (
    ROOT / "docs/decisions/adr-88-active-plugin-component-admission.md"
)
ROLE_PLUGIN_ADR = (
    ROOT / "docs/decisions/adr-90-role-plugins-and-common-hooks.md"
)
COMPOSITION_ADR = (
    ROOT / "docs/decisions/adr-82-product-planes-capability-packs-and-composition.md"
)


def _frontmatter(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


# @spec CR-001 CR-003 FR-008 QR-004
def test_should_make_adr_78_the_current_product_decision_when_indexed() -> None:
    metadata = _frontmatter(IDENTITY_ADR)
    index = (ROOT / "docs/decisions/INDEX.md").read_text(encoding="utf-8")

    assert metadata["status"] == "accepted"
    assert metadata["product_role"] == "public-template"
    assert metadata["provider_runtime"] == "none"
    assert metadata["standing_consumer_authority"] == "none"
    assert index.index("ADR-78") < index.index("ADR-77")


# @spec QR-001 QR-004
def test_should_make_adr_81_the_narrowest_support_decision_when_indexed() -> None:
    metadata = _frontmatter(MINIMAL_ADR)
    index = (ROOT / "docs/decisions/INDEX.md").read_text(encoding="utf-8")

    assert metadata["status"] == "accepted"
    assert metadata["supported_consumer_payload"] == "starter/"
    assert metadata["required_runtime"] == "none"
    assert index.index("ADR-81") < index.index("ADR-78")


def test_should_make_adr_83_the_current_supported_surface_decision() -> None:
    metadata = _frontmatter(PROJECT_AGENT_KIT_ADR)
    index = (ROOT / "docs/decisions/INDEX.md").read_text(encoding="utf-8")
    body = PROJECT_AGENT_KIT_ADR.read_text(encoding="utf-8")

    assert metadata["status"] == "accepted"
    assert metadata["amended"] == __import__("datetime").date(2026, 8, 11)
    assert metadata["supersedes"] == ["adr-82"]
    assert "2026-08-11 Owner Amendment" in body
    assert "required SQLite+FTS5 memory" in body
    assert "must not copy the full Mir package or CLI source" in body
    assert "post-release owner acceptance" in body
    assert index.index("ADR-83") < index.index("ADR-81")


def test_should_make_adr_84_the_current_upgrade_guidance_decision() -> None:
    metadata = _frontmatter(UPGRADE_ADR)
    index = (ROOT / "docs/decisions/INDEX.md").read_text(encoding="utf-8")
    guide = ROOT / "docs/operations/harness-engineering-upgrade.md"

    assert metadata["status"] == "accepted"
    assert metadata["amends"] == ["adr-74", "adr-83"]
    assert guide.is_file()
    assert index.index("ADR-84") < index.index("ADR-81")


def test_should_make_adr_85_the_current_runtime_policy_decision() -> None:
    metadata = _frontmatter(GLOBAL_POLICY_ADR)
    index = (ROOT / "docs/decisions/INDEX.md").read_text(encoding="utf-8")
    body = GLOBAL_POLICY_ADR.read_text(encoding="utf-8")
    amended = UPGRADE_ADR.read_text(encoding="utf-8")

    assert metadata["status"] == "accepted"
    assert metadata["amends"] == ["adr-09", "adr-84"]
    assert "operator-owned global policy" in body
    assert "Claude model frontmatter" in body
    assert "ADR-85 supersedes" in amended
    assert index.index("ADR-85") < index.index("ADR-84")


def test_should_make_adr_88_the_active_plugin_supply_boundary() -> None:
    metadata = _frontmatter(ACTIVE_PLUGIN_ADR)
    index = (ROOT / "docs/decisions/INDEX.md").read_text(encoding="utf-8")
    body = ACTIVE_PLUGIN_ADR.read_text(encoding="utf-8")

    assert metadata["status"] == "accepted"
    assert metadata["amends"] == ["adr-74", "adr-75", "adr-76", "adr-83", "adr-85"]
    assert "Any digest change invalidates the" in body
    assert "Target-local `config/project-hooks.json`" in body
    assert "`.mcp.json` remain the project integration sources" in body
    assert index.index("ADR-88") < index.index("ADR-87")


def test_should_make_adr_90_the_role_plugin_and_common_hook_authority() -> None:
    metadata = _frontmatter(ROLE_PLUGIN_ADR)
    index = (ROOT / "docs/decisions/INDEX.md").read_text(encoding="utf-8")
    body = ROLE_PLUGIN_ADR.read_text(encoding="utf-8")
    issue_draft = (
        ROOT / "docs/operations/codex-plugin-agents-commands-feature-request.md"
    ).read_text(encoding="utf-8")

    assert metadata["status"] == "accepted"
    assert metadata["amends"] == ["adr-88", "adr-89"]
    assert "previously copied into each repository" in body
    assert "mir-lifecycle-hooks" in body
    assert "does not mean that plugin hooks were removed" in body
    assert "Neither host currently has an MCP server registered" in body
    assert "https://github.com/openai/codex/issues/18308" in issue_draft
    assert "issuecomment-5527444139" in issue_draft
    assert "namespaced command aliases" in issue_draft
    assert index.index("ADR-90") < index.index("ADR-89")


def test_should_preserve_adr_82_only_as_an_inert_reference() -> None:
    metadata = _frontmatter(COMPOSITION_ADR)
    body = COMPOSITION_ADR.read_text(encoding="utf-8")

    assert metadata["status"] == "superseded"
    assert metadata["superseded_by"] == ["adr-83"]
    assert "reference-templates/advanced-composition/" in body
    assert "do not expose an active `yoke` command" in body


# @spec FR-008
def test_should_route_centralization_decisions_to_history_when_reading_current_authority() -> None:
    index = (ROOT / "docs/decisions/INDEX.md").read_text(encoding="utf-8")
    history = (ROOT / "docs/history/centralization/README.md").read_text(encoding="utf-8")

    assert "Current Authority" in index
    assert "Historical Decisions" in index
    assert "docs/history/centralization" in index
    for adr in ("ADR-26", "ADR-27", "ADR-48", "ADR-52", "ADR-54"):
        assert adr in history
