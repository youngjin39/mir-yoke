"""Finite agent route policies compared with equivalent bridged local hooks."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

AGENT = runpy.run_path(str(Path(__file__).with_name("test_executor_agent_native_parity.py")))
P1 = runpy.run_path(str(Path(__file__).with_name("test_executor_target_policy_native_parity.py")))
binary = P1["binary"]
ORACLE = """
REQUESTED = None
_saved_pre_execute = pre_execute
def pre_execute(args, root):
    global REQUESTED
    REQUESTED = getattr(args, 'execution_backend', None)
    _saved_pre_execute(args, root)
def resolve_agent_route(root, name):
    import hashlib, re, tomllib
    from tools.mir_executor import cli, dispatch, policy
    rule = json.loads((root / 'route-rule.json').read_text())
    if rule.get('names') is not None and name not in rule['names']:
        return None
    if rule.get('name_filter', False) and not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name):
        return None
    source = rule['source']
    path = root / ('.claude/agents/' + name + '.md' if source == 'claude'
                   else '.codex/agents/' + name + '.toml')
    if not path.is_file():
        return None
    lock_path = policy.model_routing_lock_path(root)
    try:
        lock = policy._read_json_object(lock_path) if lock_path.is_file() else {}
    except (OSError, ValueError):
        if rule['invalid_lock'] == 'error':
            raise
        lock = {}
    criteria = lock.get('agent_criteria', {})
    if rule['criteria'] == 'defer' and name in criteria:
        return None
    category = criteria.get(name, {}).get('category')
    if rule['criteria'] == 'default':
        category = category or 'implementation'
    selected_policy = policy.load_sub_agent_policy(root)
    route = selected_policy.resolve_category(category) if category else {}
    if source == 'claude' and rule['criteria'] == 'declared' and category is not None:
        route = policy.load_sub_agent_policy(root).resolve_category(category)
    backend = ('codex' if rule['backend'] == 'codex' else cli._resolve_dispatch_backend(
        selected_policy,
        requested_backend=REQUESTED if rule.get('requested_backend') else None,
        repo_slug=cli._resolve_repo_policy_slug(root), repo_root=root))
    raw = path.read_bytes()
    instructions = dispatch._MCP_DISPATCH_BASE_INSTRUCTIONS
    sandbox = None
    if source == 'codex':
        definition = tomllib.loads(raw.decode())
        instructions = definition.get('developer_instructions', '')
        if rule['sandbox'] == 'double_opt_in':
            raw = path.read_text(encoding='utf-8').encode()
            instructions = definition['developer_instructions'].strip()
            sandbox = 'workspace-write'
            if (definition.get('sandbox_mode') == 'danger-full-access' and
                    cli.local_config(root).get('codex_sandbox_default') == 'danger-full-access'):
                sandbox = 'danger-full-access'
        elif definition.get('sandbox_mode') == 'read-only':
            sandbox = 'read-only'
    return dispatch.AgentRoute(name, backend, route.get('model'), route.get('reasoning_effort'),
        path.relative_to(root).as_posix(), hashlib.sha256(raw).hexdigest(), instructions, sandbox)
"""

RULES = [
    dict(
        source="claude", criteria="defer", backend="policy", sandbox="unset", invalid_lock="empty"
    ),
    dict(
        source="claude", criteria="defer", backend="policy", sandbox="unset", invalid_lock="error"
    ),
    dict(
        source="claude",
        criteria="declared",
        backend="policy",
        sandbox="unset",
        invalid_lock="empty",
        name_filter=True,
    ),
    dict(
        source="codex",
        criteria="declared",
        backend="policy",
        sandbox="read_only",
        invalid_lock="empty",
        requested_backend=True,
    ),
    dict(
        source="codex",
        criteria="default",
        backend="codex",
        sandbox="double_opt_in",
        invalid_lock="error",
        names=["offline-agent"],
    ),
]


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize(
    "case",
    [
        "plain",
        "criteria",
        "missing_lock",
        "missing_profile",
        "readonly",
        "wide",
        "wide_opt_in",
        "crlf",
        "invalid_lock",
        "object_lock",
        "filtered",
        "explicit",
        "resume",
    ],
)
def test_agent_route_matches_bridge(binary, tmp_path, rule, case):
    snapshots = []
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        environment, args = AGENT["seed_agent"](
            root, "claude" if case in ("explicit", "resume") else "codex"
        )
        generated = root / ".codex/agents/offline-agent.toml"
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_bytes(
            (
                'developer_instructions = "  Generated instructions.  "\n'
                'sandbox_mode = "'
                + (
                    "read-only"
                    if case == "readonly"
                    else "danger-full-access"
                    if case in ("wide", "wide_opt_in")
                    else "workspace-write"
                )
                + '"\n'
            )
            .replace("\n", "\r\n" if case == "crlf" else "\n")
            .encode()
        )
        if case == "missing_profile":
            (
                root
                / (
                    ".claude/agents/offline-agent.md"
                    if rule["source"] == "claude"
                    else ".codex/agents/offline-agent.toml"
                )
            ).unlink()
        if case in ("explicit", "resume"):
            (root / "offline-policy.json").write_text(
                json.dumps({"mode": "user_command_priority", "default_backend": "codex"})
            )
            if case == "explicit":
                args += ["--execution-backend", "claude"]
            else:
                args = AGENT["DISPATCH"]["resume"](root, "current")
                import sqlite3

                with sqlite3.connect(root / "tasks/jobs.db") as conn:
                    saved = json.loads(
                        conn.execute("SELECT dispatch_options_json FROM jobs").fetchone()[0]
                    )
                    saved["execution_backend"] = "claude"
                    conn.execute(
                        "UPDATE jobs SET execution_backend=?, dispatch_options_json=?",
                        ("claude", json.dumps(saved)),
                    )
        if case == "filtered":
            rule = dict(rule, names=["different-agent"])
        if case not in ("missing_lock", "explicit", "resume"):
            (root / "config/model-routing.lock.json").write_text(
                json.dumps(
                    {
                        "policy": {
                            "mode": "force_codex",
                            "routing": {
                                "default": {"model": "lock-model", "reasoning_effort": "low"}
                            },
                        },
                        "agent_criteria": {"offline-agent": {"category": "implementation"}}
                        if case == "criteria"
                        else {},
                    }
                )
            )
        if case in ("invalid_lock", "object_lock"):
            args += ["--model", "fallback-model", "--reasoning-effort", "low"]
            (root / "config/model-routing.lock.json").write_text(
                "{" if case == "invalid_lock" else "[]"
            )
        config_path = root / "config/mir-executor.local.json"
        config = json.loads(config_path.read_text())
        if case == "wide_opt_in":
            config["codex_sandbox_default"] = "danger-full-access"
        if not bridge:
            config["native_policy"] = {"version": 1, "agent_route": rule}
        config_path.write_text(json.dumps(config))
        (root / "route-rule.json").write_text(json.dumps(rule))
        if bridge:
            with (root / "tools/mir_executor/local.py").open("a") as stream:
                stream.write(ORACLE)
        result = P1["invoke"](binary, root, environment, args)
        snapshot = AGENT["DISPATCH"]["snapshot"](root, result)
        snapshot.pop("git_status")
        snapshot["provider_requests"] = (
            (root / "provider-requests").read_text().replace(str(root), "<root>")
            if (root / "provider-requests").exists()
            else ""
        )
        # Provider requests carry random worktree names, already masked by the
        # dispatch snapshot; compare their meaningful route parameters separately.
        requests = [json.loads(s) for s in snapshot.pop("provider_requests").splitlines()]
        snapshot["thread_route"] = [
            {k: r["params"].get(k) for k in ("model", "sandbox", "baseInstructions", "config")}
            for r in requests
            if r.get("method") == "thread/start"
        ]
        snapshot["claude_arguments"] = (
            json.loads((root / "provider-arguments").read_text())
            if (root / "provider-arguments").exists()
            else None
        )
        snapshots.append(snapshot)
        expected = (
            1 if case in ("invalid_lock", "object_lock") and rule["invalid_lock"] == "error" else 0
        )
        assert result.returncode == expected, result.stderr
    assert snapshots[0] == snapshots[1]


@pytest.mark.parametrize(
    "section",
    [
        None,
        True,
        {},
        dict(RULES[0], unknown=True),
        dict(RULES[0], requested_backend="yes"),
        dict(RULES[0], names=["../escape"]),
    ],
)
def test_agent_route_strict_validation(binary, tmp_path, section):
    root = tmp_path / "invalid"
    environment, args = AGENT["seed_agent"](root, "codex")
    config = root / "config/mir-executor.local.json"
    config.write_text(json.dumps({"native_policy": {"version": 1, "agent_route": section}}))
    result = P1["invoke"](binary, root, environment, args)
    assert result.returncode == 1
    assert b"native local policy configuration error" in result.stderr
    assert not (root / "provider-requests").exists()


def test_agent_route_duplicate_hook_fails_before_import(binary, tmp_path):
    root = tmp_path / "duplicate"
    environment, args = AGENT["seed_agent"](root, "codex")
    (root / "config/mir-executor.local.json").write_text(
        json.dumps({"native_policy": {"version": 1, "agent_route": RULES[0]}})
    )
    (root / "tools/mir_executor/local.py").write_text(
        'raise RuntimeError("unexpected import")\ndef resolve_agent_route(root, name): pass\n'
    )
    result = P1["invoke"](binary, root, environment, args)
    assert result.returncode == 1
    assert b"resolve_agent_route is also present in local.py" in result.stderr
    assert b"unexpected import" not in result.stderr
    assert not (root / "provider-requests").exists()


def test_agent_route_only_policy_keeps_home_root_mismatch_decline(binary, tmp_path):
    # Only target admission may admit a different target root natively; an
    # agent-route-only policy leaves that case to the Python executor.
    import subprocess

    root = tmp_path / "home"
    environment, args = AGENT["seed_agent"](root, "codex")
    (root / "config/mir-executor.local.json").write_text(
        json.dumps({"native_policy": {"version": 1, "agent_route": RULES[0]}})
    )
    other = tmp_path / "other"
    other.mkdir()
    subprocess.run(["git", "init", "--quiet", str(other)], check=True, capture_output=True)
    trace = tmp_path / "decline-trace"
    environment = dict(environment, MIR_EXECUTOR_DECLINE_TRACE=str(trace))
    result = P1["invoke"](binary, root, environment, [*args, "--repo-root", str(other)])
    assert result.returncode == 64, (result.stdout, result.stderr)
    assert b"execute home/root mismatch" in trace.read_bytes()
    assert not (root / "provider-requests").exists()
    assert not (other / "tasks/jobs.db").exists()
