from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "packs/safety/payload/.claude/hooks/mir-safety.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("mir_safety_pack", HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_should_extract_patch_paths_when_apply_patch_payload_is_normalized() -> None:
    hook = _load_hook()
    event = {
        "tool_name": "apply_patch",
        "tool_input": {"patch": "*** Update File: src/app.py\n*** Add File: docs/new.md\n"},
    }

    assert hook.changed_paths(event) == ["docs/new.md", "src/app.py"]


def test_should_block_secret_and_git_internal_paths_when_preflight_runs() -> None:
    hook = _load_hook()

    assert hook.evaluate_path(".env")["decision"] == "block"
    assert hook.evaluate_path(".git/config")["decision"] == "block"
    assert hook.evaluate_path("src/app.py")["decision"] == "allow"


def test_should_detect_credential_text_without_returning_secret_value() -> None:
    hook = _load_hook()
    secret = "ghp_" + "a" * 36

    finding = hook.scan_text(secret)

    assert finding == "github-token"
    assert secret not in finding


def test_should_contain_no_family_or_fleet_policy_when_payload_is_scanned() -> None:
    bodies = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "packs/safety/payload").rglob("*")
        if path.is_file() and path.suffix in {".json", ".md", ".py"}
    ).lower()

    assert "mir_family_slug" not in bodies
    assert "home-server" not in bodies
    assert "fleet" not in bodies


def test_should_ship_repository_owned_tracked_policy_separate_from_local_state() -> None:
    policy = ROOT / "packs/safety/payload/config/harness-policy.toml"
    planes = json.loads((ROOT / "config/product-planes.json").read_text())

    assert policy.is_file()
    assert 'owner = "consumer-repository"' in policy.read_text()
    assert planes["planes"]["project"]["optional_policy"] == "config/harness-policy.toml"
    assert planes["planes"]["local"]["state"] == ".mir/local-state.json"


def test_should_discover_tracked_and_untracked_changes_for_post_scan(tmp_path: Path) -> None:
    hook = _load_hook()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    tracked.write_text("after\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("new\n", encoding="utf-8")

    assert hook._git_changed_paths(tmp_path) == ["tracked.txt", "untracked.txt"]
