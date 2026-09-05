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
        assert "agent-guided" in body, relative
        assert "not a universal installer" in body, relative


# @spec CR-001 CR-003 QR-004
def test_should_state_harness_managed_central_capability_supply_without_consumer_control() -> None:
    phrase = "harness-managed central capability supply system for independently owned repositories"
    for relative in (
        "CLAUDE.md",
        "README.md",
        "ARCHITECTURE.md",
        "docs/decisions/adr-86-mir-harness-managed-repository-maintenance.md",
    ):
        body = re.sub(
            r"\s+", " ", (ROOT / relative).read_text(encoding="utf-8").lower()
        )
        assert phrase in body, relative
        assert "no standing authority" in body or "consumer authority" in body, relative

    with (ROOT / ".mir/repo-profile.toml").open("rb") as stream:
        profile = tomllib.load(stream)
    assert phrase in profile["repo"]["purpose"].lower()
    assert profile["repo"]["repository_type"] == "public_harness_template"


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
    assert repository["management_mode"] == "harness-managed"
    assert "may manage Yoke directly" in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "fleet_management" not in repository
    local_profile = ROOT / ".mir/repo-profile.toml"
    with local_profile.open("rb") as stream:
        profile = tomllib.load(stream)
    assert profile["repo"]["path"] == "."
    assert profile["repo"]["repository_type"] == "public_harness_template"
    assert profile["repo"]["rollout_class"] == "repository_owned"
    assert profile["repo"]["overlay_archetype"] == "public_template"
    assert re.fullmatch(r"[0-9a-f]{40}", profile["repo"]["profile_base_commit"])
    assert "T" in profile["repo"]["profile_verified_at"]
    assert profile["boundaries"]["live_runtime"] == []
    assert ".mir/capability-lock.json" not in profile["paths"]["protected_paths"]


def test_should_not_declare_repository_runtime_agents_or_orchestration() -> None:
    repository = json.loads(
        (ROOT / "config/repos/mir-yoke.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        (ROOT / "config/repo-agent-management.schema.json").read_text(encoding="utf-8")
    )

    assert repository["active_agents"] == []
    assert repository["active_skills"] == []
    assert repository["orchestration_profile"] == "none"
    orchestration = schema["$defs"]["repository"]["properties"][
        "orchestration_profile"
    ]
    assert "none" in orchestration["enum"]


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
