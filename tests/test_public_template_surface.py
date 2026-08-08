from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# @spec CR-002 CR-003 FR-007
def test_should_remove_central_control_executables_when_building_public_payload() -> None:
    prohibited = (
        "scripts/notify_discord.py",
        "scripts/verify_self_stop.py",
        "scripts/verify_template_applied_state.py",
        "tools/profile_compiler/specialist_deploy.py",
        "tools/harness_consistency/parity.py",
        "config/parity-classes.json",
        "config/parity-manifest.json",
        "config/parity-manifest.schema.json",
    )
    assert all(not (ROOT / relative).exists() for relative in prohibited)


# @spec CR-002 CR-003 FR-007
def test_should_run_local_validation_without_notification_when_tagged() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8").lower()
    assert "verify_release_readiness.py" in workflow
    for forbidden in ("discord", "webhook", "notify_fleet", "mir_fleet"):
        assert forbidden not in workflow


# @spec CR-006 IR-001 QR-004
def test_should_expose_no_private_absolute_path_when_public_surfaces_are_scanned() -> None:
    forbidden = (
        "/" + "Volumes/",
        "/" + "Users/",
        "09." + "Mini_Harness",
        "T7 " + "Shield",
    )
    candidates = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    for relative in candidates:
        path = ROOT / relative
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert all(token not in body for token in forbidden), relative
