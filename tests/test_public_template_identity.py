from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# @spec CR-001 CR-002 CR-003 QR-004
def test_should_publish_one_non_runtime_template_identity_when_root_contracts_are_read() -> None:
    claims = {
        "README.md": ("public", "template", "not an agent runtime", "no standing authority"),
        "CLAUDE.md": ("public", "template", "not an agent runtime", "no standing authority"),
        "ARCHITECTURE.md": ("public", "template", "no provider runtime", "no standing authority"),
        "docs/decisions/INDEX.md": (
            "public",
            "template",
            "no provider runtime",
            "no standing authority",
        ),
    }
    for relative, required in claims.items():
        body = re.sub(
            r"\s+",
            " ",
            (ROOT / relative).read_text(encoding="utf-8").lower(),
        )
        assert all(token in body for token in required), relative


# @spec CR-003 QR-004
def test_should_disable_fleet_identity_when_public_configuration_is_loaded() -> None:
    consistency = json.loads((ROOT / "config/harness-consistency.json").read_text())
    repository = json.loads((ROOT / "config/repos/mir-yoke.json").read_text())

    assert consistency["repo"] == {
        "slug": "mir-yoke",
        "repository_type": "public_harness_template",
        "role": "template_maintainer",
        "enforcement": {
            "tools_commit_gate": "lint_test",
            "tools_tdd_ledger": "changes_array",
        },
    }
    assert "fleet_manager" not in consistency["repo"]
    assert repository["repository_type"] == "public_harness_template"
    assert repository["adoption_mode"] == "explicit_local"
    assert repository["management_mode"] == "self-maintained-template"
    assert "fleet_management" not in repository
    local_profile = ROOT / ".mir/repo-profile.toml"
    if local_profile.exists():
        with local_profile.open("rb") as stream:
            profile = tomllib.load(stream)
        assert profile["repo"]["path"] == "."
        assert profile["repo"]["repository_type"] == "public_harness_template"
        assert profile["repo"]["overlay_archetype"] == "public_template"
        assert profile["boundaries"]["live_runtime"] == []


# @spec CR-002
def test_provider_has_no_runtime() -> None:
    absent = (
        "scripts/cron",
        "tools/stall_watchdog",
        ".github/workflows/daily_health.yml",
    )
    tracked = {
        line
        for line in __import__("subprocess")
        .check_output(["git", "ls-files"], cwd=ROOT, text=True)
        .splitlines()
        if (ROOT / line).is_file()
    }
    assert all(
        not any(path == relative or path.startswith(f"{relative}/") for path in tracked)
        for relative in absent
    )
    cli = (ROOT / "src/mir/cli/__init__.py").read_text(encoding="utf-8")
    assert all(token not in cli for token in ('"fleet"', '"rollout"', '"daemon"'))
