"""Tests for ADR-61 sub-agent policy loading."""

from __future__ import annotations

import json
import pathlib

import pytest

from tools.mir_executor import cli
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
    assert policy.routing == {}
    assert policy.monitoring == {}


def test_force_claude_policy_mode_is_accepted(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(tmp_path, {"mode": "force_claude", "per_project": {}})

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "force_claude"
    assert policy.per_project == {}
    assert policy.routing == {}
    assert policy.monitoring == {}


def test_loader_parses_routing_and_monitoring(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    routing = {
        "default": {"model": "gpt-5.5", "reasoning_effort": "high"},
        "by_category": {
            "unit": {"model": "gpt-5", "reasoning_effort": "low"},
            "e2e": "invalid",
        },
    }
    monitoring = {"stall_timeout_seconds": 42}
    _write_policy(
        tmp_path,
        {
            "mode": "obey_user",
            "per_project": {},
            "routing": routing,
            "monitoring": monitoring,
        },
    )

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "obey_user"
    assert policy.routing == routing
    assert policy.monitoring == monitoring
    assert policy.routing_default_model() == "gpt-5.5"
    assert policy.routing_default_reasoning_effort() == "high"
    assert policy.routing_for_category("unit") == {
        "model": "gpt-5",
        "reasoning_effort": "low",
    }
    assert policy.routing_for_category("e2e") == {}
    assert policy.monitoring_stall_timeout_seconds() == 42.0


def test_routing_rank_accessors_parse_ordered_string_lists(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(
        tmp_path,
        {
            "mode": "force_codex",
            "per_project": {},
            "routing": {
                "model_rank": [" top-model ", "", 7, "mid-model"],
                "effort_rank": [" xhigh ", None, "low"],
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert policy.routing_model_rank() == ["top-model", "mid-model"]
    assert policy.routing_effort_rank() == ["xhigh", "low"]


def test_routing_rank_accessors_return_empty_for_malformed_values(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(
        tmp_path,
        {
            "mode": "force_codex",
            "per_project": {},
            "routing": {
                "model_rank": "top-model",
                "effort_rank": ["", 7, None],
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert policy.routing_model_rank() == []
    assert policy.routing_effort_rank() == []


def test_routing_prefer_for_category_returns_empty_for_malformed_values(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(
        tmp_path,
        {
            "mode": "force_codex",
            "per_project": {},
            "routing": {
                "by_category": {
                    "unit": {
                        "model": "single-model",
                        "reasoning_effort": "low",
                        "prefer": "invalid",
                    },
                    "architecture": {"prefer": ["invalid", 7, None]},
                },
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert policy.routing_prefer_for_category("unit") == []
    assert policy.routing_prefer_for_category("architecture") == []
    assert cli._resolve_policy_runtime_options(
        policy,
        category="unit",
        model=None,
        reasoning_effort=None,
        stall_timeout=None,
    ) == ("single-model", "low", None)


def test_missing_routing_and_monitoring_sections_default_empty(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(tmp_path, {"mode": "select", "per_project": {}})

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "select"
    assert policy.routing == {}
    assert policy.monitoring == {}
    assert policy.routing_default_model() is None
    assert policy.routing_default_reasoning_effort() is None
    assert policy.routing_model_rank() == []
    assert policy.routing_effort_rank() == []
    assert policy.routing_by_category() == {}
    assert policy.routing_prefer_for_category("unit") == []
    assert policy.monitoring_stall_timeout_seconds() is None


def test_invalid_routing_and_monitoring_values_default_empty(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(
        tmp_path,
        {
            "mode": "force_claude",
            "per_project": {},
            "routing": ["invalid"],
            "monitoring": "invalid",
        },
    )

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "force_claude"
    assert policy.routing == {}
    assert policy.monitoring == {}


def test_missing_config_file_resolves_to_force_codex(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "force_codex"
    assert policy.per_project == {}
    assert policy.routing == {}
    assert policy.monitoring == {}


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
    assert policy.routing == {}
    assert policy.monitoring == {}


def test_unknown_mode_value_resolves_to_force_codex(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(tmp_path, {"mode": "unknown", "per_project": {"mir": "select"}})

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "force_codex"
    assert policy.per_project == {}
    assert policy.routing == {}
    assert policy.monitoring == {}


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


@pytest.mark.parametrize("mode", ["obey_user", "unrestricted"])
def test_obey_user_and_unrestricted_resolve_requested_backend(
    tmp_path: pathlib.Path,
    monkeypatch,
    mode: str,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(tmp_path, {"mode": mode, "per_project": {}})
    policy = load_sub_agent_policy(tmp_path)

    assert (
        cli._resolve_dispatch_backend(
            policy,
            requested_backend="claude",
            repo_slug=None,
        )
        == "claude"
    )
    assert (
        cli._resolve_dispatch_backend(
            policy,
            requested_backend="invalid",
            repo_slug=None,
        )
        == "codex"
    )
    assert (
        cli._resolve_dispatch_backend(
            policy,
            requested_backend=None,
            repo_slug=None,
        )
        == "codex"
    )


def test_policy_runtime_options_apply_category_then_default_and_preserve_cli_flags(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(
        tmp_path,
        {
            "mode": "force_codex",
            "per_project": {},
            "routing": {
                "default": {"model": "gpt-5.5", "reasoning_effort": "medium"},
                "by_category": {"unit": {"reasoning_effort": "low"}},
            },
            "monitoring": {"stall_timeout_seconds": 30},
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert cli._resolve_policy_runtime_options(
        policy,
        category="unit",
        model=None,
        reasoning_effort=None,
        stall_timeout=None,
    ) == ("gpt-5.5", "low", 30.0)
    assert cli._resolve_policy_runtime_options(
        policy,
        category="unit",
        model="cli-model",
        reasoning_effort="xhigh",
        stall_timeout=5,
    ) == ("cli-model", "xhigh", 5)


def test_policy_runtime_options_use_primary_prefer_route(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(
        tmp_path,
        {
            "mode": "force_codex",
            "per_project": {},
            "routing": {
                "default": {
                    "model": "default-model",
                    "reasoning_effort": "medium",
                },
                "by_category": {
                    "architecture": {
                        "prefer": [
                            {
                                "model": " top-model ",
                                "reasoning_effort": " xhigh ",
                            },
                            {
                                "model": "mid-model",
                                "reasoning_effort": "high",
                            },
                        ],
                    },
                },
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert policy.routing_prefer_for_category("architecture") == [
        {"model": "top-model", "reasoning_effort": "xhigh"},
        {"model": "mid-model", "reasoning_effort": "high"},
    ]
    assert cli._resolve_policy_runtime_options(
        policy,
        category="architecture",
        model=None,
        reasoning_effort=None,
        stall_timeout=None,
    ) == ("top-model", "xhigh", None)


def test_policy_runtime_options_keep_single_value_category_without_prefer(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(
        tmp_path,
        {
            "mode": "force_codex",
            "per_project": {},
            "routing": {
                "default": {
                    "model": "default-model",
                    "reasoning_effort": "medium",
                },
                "by_category": {
                    "unit": {
                        "model": "small-model",
                        "reasoning_effort": "low",
                    },
                },
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert cli._resolve_policy_runtime_options(
        policy,
        category="unit",
        model=None,
        reasoning_effort=None,
        stall_timeout=None,
    ) == ("small-model", "low", None)


def test_policy_runtime_options_prefer_wins_over_single_value_category(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(
        tmp_path,
        {
            "mode": "force_codex",
            "per_project": {},
            "routing": {
                "by_category": {
                    "architecture": {
                        "model": "single-model",
                        "reasoning_effort": "low",
                        "prefer": [
                            {
                                "model": "preferred-model",
                                "reasoning_effort": "high",
                            },
                        ],
                    },
                },
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert cli._resolve_policy_runtime_options(
        policy,
        category="architecture",
        model=None,
        reasoning_effort=None,
        stall_timeout=None,
    ) == ("preferred-model", "high", None)


def test_policy_runtime_options_cli_flags_override_prefer_route(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(
        tmp_path,
        {
            "mode": "force_codex",
            "per_project": {},
            "routing": {
                "by_category": {
                    "architecture": {
                        "prefer": [
                            {
                                "model": "preferred-model",
                                "reasoning_effort": "high",
                            },
                        ],
                    },
                },
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert cli._resolve_policy_runtime_options(
        policy,
        category="architecture",
        model="cli-model",
        reasoning_effort="cli-effort",
        stall_timeout=None,
    ) == ("cli-model", "cli-effort", None)
