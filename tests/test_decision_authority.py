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
