from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_ADR = ROOT / "docs/decisions/adr-78-public-template-identity-and-non-authority.md"
MINIMAL_ADR = ROOT / "docs/decisions/adr-81-minimal-starter-support-boundary.md"
PLANES_ADR = ROOT / "docs/decisions/adr-82-product-planes-capability-packs-and-composition.md"


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


def test_should_make_adr_82_the_current_composition_decision_when_indexed() -> None:
    metadata = _frontmatter(PLANES_ADR)
    index = (ROOT / "docs/decisions/INDEX.md").read_text(encoding="utf-8")

    assert metadata["status"] == "accepted"
    assert metadata["amends"] == ["adr-81"]
    assert index.index("ADR-82") < index.index("ADR-81")


# @spec FR-008
def test_should_route_centralization_decisions_to_history_when_reading_current_authority() -> None:
    index = (ROOT / "docs/decisions/INDEX.md").read_text(encoding="utf-8")
    history = (ROOT / "docs/history/centralization/README.md").read_text(encoding="utf-8")

    assert "Current Authority" in index
    assert "Historical Decisions" in index
    assert "docs/history/centralization" in index
    for adr in ("ADR-26", "ADR-27", "ADR-48", "ADR-52", "ADR-54"):
        assert adr in history
