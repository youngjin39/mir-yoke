"""Tests for ADR-61 sub-agent policy loading."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

from tools.mir_executor import cli
from tools.mir_executor.policy import POLICY_ENV_VAR, load_sub_agent_policy

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


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
    assert cli._resolve_dispatch_backend(
        policy,
        requested_backend="claude",
        repo_slug=None,
    ) == "claude"


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

    assert policy.mode == "user_command_priority"
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


def test_resolve_category_prefers_primary_prefer_route(
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
                        "model": "single-model",
                        "reasoning_effort": "low",
                        "prefer": [
                            {
                                "model": " preferred-model ",
                                "reasoning_effort": " high ",
                            },
                            {
                                "model": "fallback-model",
                                "reasoning_effort": "medium",
                            },
                        ],
                    },
                },
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert policy.resolve_category("architecture") == {
        "model": "preferred-model",
        "reasoning_effort": "high",
    }


def test_resolve_category_uses_single_value_category_without_prefer(
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
                        "model": "single-model",
                        "reasoning_effort": "low",
                    },
                },
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert policy.resolve_category("unit") == {
        "model": "single-model",
        "reasoning_effort": "low",
    }


def test_resolve_category_uses_routing_default(
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
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert policy.resolve_category("unit") == {
        "model": "default-model",
        "reasoning_effort": "medium",
    }


def test_resolve_category_uses_flat_default(
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
                "default_model": "flat-model",
                "default_reasoning_effort": "flat-effort",
            },
        },
    )
    policy = load_sub_agent_policy(tmp_path)

    assert policy.resolve_category("unit") == {
        "model": "flat-model",
        "reasoning_effort": "flat-effort",
    }


def test_resolve_category_returns_none_when_absent(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(tmp_path, {"mode": "force_codex", "per_project": {}})
    policy = load_sub_agent_policy(tmp_path)

    assert policy.resolve_category("unit") == {
        "model": None,
        "reasoning_effort": None,
    }


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


def test_missing_config_file_resolves_to_select(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "select"
    assert policy.per_project == {}
    assert policy.routing == {}
    assert policy.monitoring == {}
    assert cli._resolve_dispatch_backend(
        policy,
        requested_backend="claude",
        repo_slug=None,
    ) == "claude"


def test_malformed_json_resolves_to_select(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    policy_path = tmp_path / "config" / "sub-agent-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("{", encoding="utf-8")

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "select"
    assert policy.per_project == {}
    assert policy.routing == {}
    assert policy.monitoring == {}
    assert cli._resolve_dispatch_backend(
        policy,
        requested_backend="claude",
        repo_slug=None,
    ) == "claude"


def test_unknown_mode_value_resolves_to_select(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(tmp_path, {"mode": "unknown", "per_project": {"mir": "select"}})

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "select"
    assert policy.per_project == {}
    assert policy.routing == {}
    assert policy.monitoring == {}


def test_per_project_mode_returns_per_project_map(
    tmp_path: pathlib.Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    per_project = {"mir-harness": "force_codex", "example": "select"}
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
    overlay_per_project = {"mir-harness": "select"}
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
    ) == ("gpt-5.5", "low", None)
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


def test_policy_resolve_cli_subcommand_prints_json(
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
                        "model": "cli-policy-model",
                        "reasoning_effort": "low",
                    },
                },
            },
        },
    )
    env = os.environ.copy()
    # A present empty overlay keeps the subprocess off the host's rendered policy (ADR-88);
    # a missing one would now fall back to that policy.
    empty_overlay = tmp_path / "empty-global-policy.json"
    empty_overlay.write_text("{}", encoding="utf-8")
    env[POLICY_ENV_VAR] = str(empty_overlay)
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    pythonpath = os.pathsep.join(
        [
            str(repo_root / "src"),
            str(repo_root),
            env.get("PYTHONPATH", ""),
        ]
    )
    env["PYTHONPATH"] = pythonpath

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mir",
            "policy",
            "resolve",
            "--category",
            "unit",
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "model": "cli-policy-model",
        "reasoning_effort": "low",
    }
    assert result.stderr == ""


def test_adr88_unset_env_falls_back_to_the_rendered_harness_policy(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Without MIR_SUB_AGENT_POLICY, routing still comes from the Harness-rendered JSON."""
    from tools.mir_executor import policy as policy_module

    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    _write_policy(tmp_path, {"mode": "force_codex", "per_project": {}})
    fallback = tmp_path / "rendered.json"
    fallback.write_text(
        json.dumps({"routing": {"default": {"model": "m", "reasoning_effort": "high"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(policy_module, "default_global_policy_path", lambda: fallback)

    policy = load_sub_agent_policy(tmp_path)

    assert policy.routing == {"default": {"model": "m", "reasoning_effort": "high"}}


def test_adr88_default_global_policy_path_is_the_rendered_harness_policy() -> None:
    import pwd

    from tools.mir_executor import policy as policy_module

    account_home = pathlib.Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert policy_module.DEFAULT_GLOBAL_POLICY_PATH == (
        account_home / ".mir" / "model-routing" / "sub-agent-policy.json"
    )


def test_adr88_missing_env_policy_file_falls_back_to_the_rendered_policy(
    tmp_path: pathlib.Path, monkeypatch, capsys
) -> None:
    """MIR_SUB_AGENT_POLICY naming a missing file must not route every category to null."""
    from tools.mir_executor import policy as policy_module

    missing = tmp_path / "retired" / "sub-agent-policy.global.json"
    monkeypatch.setenv(POLICY_ENV_VAR, str(missing))
    _write_policy(tmp_path, {"mode": "force_codex", "per_project": {}})
    rendered_route = {"model": "m", "reasoning_effort": "high"}
    fallback = tmp_path / "rendered.json"
    fallback.write_text(
        json.dumps({"routing": {"by_category": {"architecture": rendered_route}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(policy_module, "default_global_policy_path", lambda: fallback)

    policy = load_sub_agent_policy(tmp_path)

    route = policy.resolve_category("architecture")
    assert (route["model"], route["reasoning_effort"]) == ("m", "high")
    assert str(missing) in capsys.readouterr().err


def test_owner_decision_1a_repository_policy_follows_the_central_delegation_mode(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Owner decision 1-A: this repository states no mode; the central `delegation.mode` decides.

    The rendered global policy carries its switch only as `delegation.mode`, so a loader
    that reads just the top-level `mode` let a repository-local value decide the lane.
    """
    from tools.mir_executor import policy as policy_module

    local = json.loads((REPO_ROOT / "config" / "sub-agent-policy.json").read_text(encoding="utf-8"))
    assert "mode" not in local
    # Without a deployed lock (ADR-88), the rendered host policy is the fallback.
    repo_root = tmp_path / "repo"
    _write_policy(repo_root, local)
    central = tmp_path / "central.json"
    central.write_text(
        json.dumps({"delegation": {"mode": "user_command_priority", "default_backend": "codex"}}),
        encoding="utf-8",
    )
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    monkeypatch.setattr(policy_module, "default_global_policy_path", lambda: central)

    assert load_sub_agent_policy(repo_root).mode == "user_command_priority"

    central.write_text(json.dumps({"delegation": {"mode": "force_codex"}}), encoding="utf-8")
    assert load_sub_agent_policy(repo_root).mode == "force_codex"


def _write_lock(repo_root: pathlib.Path, policy: object) -> None:
    lock_path = repo_root / "config" / "model-routing.lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"policy": policy, "routes": {}}), encoding="utf-8")


def test_adr88_deployed_lock_policy_drives_routing_before_env_and_host_policy(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """ADR-88 amendment: the Harness-deployed lock `policy` wins; env/host JSON are fallbacks."""
    from tools.mir_executor import policy as policy_module

    _write_policy(tmp_path, {"per_project": {}, "monitoring": {"stall_timeout_seconds": 9}})
    lock_route = {"model": "lock-model", "reasoning_effort": "high"}
    _write_lock(
        tmp_path,
        {"delegation": {"mode": "force_codex"}, "routing": {"by_category": {"narrow": lock_route}}},
    )
    other = {
        "delegation": {"mode": "unrestricted"},
        "routing": {"by_category": {"narrow": {"model": "host-model", "reasoning_effort": "low"}}},
    }
    env_policy = tmp_path / "env.json"
    env_policy.write_text(json.dumps(other), encoding="utf-8")
    host_policy = tmp_path / "host.json"
    host_policy.write_text(json.dumps(other), encoding="utf-8")
    monkeypatch.setenv(POLICY_ENV_VAR, str(env_policy))
    monkeypatch.setattr(policy_module, "default_global_policy_path", lambda: host_policy)

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "force_codex"
    assert policy.resolve_category("narrow") == lock_route
    assert policy.monitoring_stall_timeout_seconds() == 9.0


def test_adr88_deployed_lock_alone_is_enough_for_a_new_repository(tmp_path: pathlib.Path) -> None:
    """A greenfield repository with only the deployed lock still routes from it."""
    _write_lock(
        tmp_path,
        {
            "delegation": {"mode": "user_command_priority"},
            "routing": {"default": {"model": "lock-model", "reasoning_effort": "medium"}},
        },
    )

    policy = load_sub_agent_policy(tmp_path)

    assert policy.mode == "user_command_priority"
    assert policy.resolve_category("unit") == {
        "model": "lock-model",
        "reasoning_effort": "medium",
    }


def test_adr88_this_repository_routes_from_its_deployed_lock() -> None:
    """The committed lock, not a host file, decides this repository's live routing."""
    lock_path = REPO_ROOT / "config" / "model-routing.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    policy = load_sub_agent_policy(REPO_ROOT)

    for category, expected in lock["policy"]["routing"]["by_category"].items():
        assert policy.resolve_category(category) == {
            "model": expected["model"],
            "reasoning_effort": expected["reasoning_effort"],
        }
    assert policy.mode == "user_command_priority"
