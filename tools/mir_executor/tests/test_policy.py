"""Tests for ADR-61 sub-agent policy loading."""

from __future__ import annotations

import json
import pathlib

from tools.mir_executor.policy import POLICY_ENV_VAR, load_sub_agent_policy


def _write_policy(repo_root: pathlib.Path, data: object) -> pathlib.Path:
    policy_path = repo_root / "config" / "sub-agent-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps(data), encoding="utf-8")
    return policy_path


def test_force_codex_default(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(tmp_path, {"mode": "force_codex", "per_project": {}})

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "force_codex"
    assert policy.per_project == {}


def test_force_claude_policy_mode_is_accepted(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(tmp_path, {"mode": "force_claude", "per_project": {}})

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "force_claude"
    assert policy.per_project == {}


def test_missing_config_file_resolves_to_force_codex(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "force_codex"
    assert policy.per_project == {}


def test_malformed_json_resolves_to_force_codex(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    policy_path = tmp_path / "config" / "sub-agent-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("{", encoding="utf-8")

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "force_codex"
    assert policy.per_project == {}


def test_unknown_mode_value_resolves_to_force_codex(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(tmp_path, {"mode": "unknown", "per_project": {"mir": "select"}})

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "force_codex"
    assert policy.per_project == {}


def test_per_project_mode_returns_per_project_map(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    per_project = {"your-harness": "force_codex", "example": "select"}
    _write_policy(tmp_path, {"mode": "per_project", "per_project": per_project})

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "per_project"
    assert policy.per_project == per_project


def test_user_policy_overlay_takes_precedence_when_present(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    _write_policy(tmp_path, {"mode": "force_codex", "per_project": {}})
    overlay = tmp_path / "user-policy.json"
    overlay_per_project = {"your-harness": "select"}
    overlay.write_text(
        json.dumps({"mode": "per_project", "per_project": overlay_per_project}),
        encoding="utf-8",
    )
    monkeypatch.setenv(POLICY_ENV_VAR, str(overlay))

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "per_project"
    assert policy.per_project == overlay_per_project
