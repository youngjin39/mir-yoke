"""Contract for the portable reference-application profile skill."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "mir-core" / "skills" / "reference-app-profile" / "SKILL.md"

PROFILE_SECTIONS = (
    "Target",
    "Stack",
    "Permissions",
    "Signing and sandbox",
    "Integrations and endpoints",
    "Security policy",
    "Storage",
    "Updates",
    "Unknowns",
)


def test_reference_app_profile_skill_keeps_its_fixed_profile_sections() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert re.search(r"^name: reference-app-profile$", text, re.MULTILINE)
    profile = text.split("## Profile", 1)[1].split("## Report", 1)[0]
    headings = re.findall(r"^\d+\. ([^:]+):", profile, re.MULTILINE)
    assert tuple(headings) == PROFILE_SECTIONS


def test_should_extract_metadata_only_without_code_analysis_or_execution() -> None:
    text = SKILL.read_text(encoding="utf-8")
    bounds = text.split("## Bounds", 1)[1].split("## Targets", 1)[0]
    for requirement in (
        "No decompilation, disassembly or code tracing",
        "Do not launch",
        "Never bypass encryption, DRM",
        "never their values",
        "No active scanning",
    ):
        assert requirement in bounds


def test_should_label_every_claim_with_status_and_evidence() -> None:
    text = SKILL.read_text(encoding="utf-8")
    for status in ("Confirmed", "Inferred", "Unknown"):
        assert f"`{status}`" in text
    assert "command or path" in text
