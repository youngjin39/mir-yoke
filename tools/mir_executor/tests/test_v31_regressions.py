"""Executor v3.1 compatibility and persistence regressions."""

import hashlib
import json
import os
import sqlite3

import pytest

from tools.mir_executor import cli, dispatch
from tools.mir_executor.executor import MirExecutor, SubprocessResult
from tools.mir_executor.jobs import JobRegistry
from tools.mir_executor.tests.test_common_policy_jobs import make_job
from tools.mir_executor.tests.test_executor import _make_ledger
from tools.mir_executor.tests.test_resume_v2 import prepare_resume


@pytest.mark.parametrize("backend,read_only,category", [
    ("codex", False, "implementation"),
    ("codex", True, "final_review"),
    ("claude", True, "implementation"),
])
def test_should_resolve_definition_when_local_hook_returns_none(
    tmp_path, backend, read_only, category,
):
    definition = tmp_path / ".claude/agents/executor-agent.md"
    definition.parent.mkdir(parents=True)
    text = (
        "---\nname: executor-agent\ndescription: Execute owned work.\n"
        f'model: "claude-model"\nexecution_backend: "{backend}"\n'
        + ('disallowedTools: "[Write, Edit]"\n' if read_only else "")
        + "---\n\nExecute only the owned scope.\n"
    )
    definition.write_text(text)
    lock = tmp_path / "config/model-routing.lock.json"
    lock.parent.mkdir()
    lock.write_text(json.dumps({
        "agent_criteria": {"executor-agent": {"category": category}}
        if category != "implementation" else {},
        "policy": {"routing": {"by_category": {
            category: {"model": "category-model", "reasoning_effort": "high"},
        }}},
    }))
    hooks = tmp_path / "tools/mir_executor/local.py"
    hooks.parent.mkdir(parents=True)
    hooks.write_text("def resolve_agent_route(root, name):\n    return None\n")
    route = dispatch.resolve_agent_route(tmp_path, "executor-agent")
    assert route.execution_backend == backend
    assert route.model == ("category-model" if backend == "codex" else "claude-model")
    assert route.reasoning_effort == ("high" if backend == "codex" else None)
    assert route.base_instructions == "Execute only the owned scope."
    assert route.definition_path == ".claude/agents/executor-agent.md"
    assert route.definition_sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert route.sandbox == ("read-only" if read_only else "workspace-write")


def test_should_warn_and_return_no_route_when_definition_missing(tmp_path, capsys):
    assert dispatch.resolve_agent_route(tmp_path, "missing") is None
    stderr = capsys.readouterr().err
    assert "warning" in stderr.lower()
    assert "missing" in stderr


@pytest.mark.parametrize("argument", [
    "OPENAI_API_KEY=very-secret " + "x" * 20000,
    "-----BEGIN PRIVATE KEY-----\nprivate-material\n-----END PRIVATE KEY-----",
])
def test_should_scrub_and_bound_persisted_job_arguments(tmp_path, argument):
    registry = JobRegistry(tmp_path / "jobs.db")
    try:
        registry.insert(make_job(codex_args=["exec", argument]))
        registry.update_status("a" * 32, "completed", stdout="password=hunter2 " + "y" * 20000)
        record = registry.get("a" * 32)
        assert record.codex_args[0] == "exec"
        assert len(record.codex_args[1]) <= 16384
        assert "very-secret" not in record.codex_args[1]
        assert "private-material" not in record.codex_args[1]
        assert "PRIVATE KEY-----" not in record.codex_args[1]
        assert "hunter2" not in record.stdout
        assert len(record.stdout) <= 16384
    finally:
        registry.close()


@pytest.mark.parametrize("existing", [False, True])
def test_should_protect_database_and_existing_sidecars(tmp_path, existing):
    db = tmp_path / "jobs.db"
    if existing:
        registry = JobRegistry(db)
        registry.close()
        db.chmod(0o644)
    sidecars = [tmp_path / ("jobs.db" + suffix) for suffix in ("-wal", "-shm", "-journal")]
    for path in sidecars:
        path.touch(mode=0o644)
        path.chmod(0o644)
    registry = JobRegistry(db)
    try:
        for path in [db, *sidecars]:
            if path.exists():
                assert os.stat(path).st_mode & 0o777 == 0o600
    finally:
        registry.close()


@pytest.mark.parametrize("timeout", [None, 37])
def test_should_persist_requested_timeout_in_dispatch_options(tmp_path, timeout):
    args = cli._build_parser(tmp_path).parse_args(["execute", "--dispatch"])
    args.timeout = timeout
    options = json.loads(cli._dispatch_options_json(args, None, None, None, "codex", None))
    assert options["timeout"] == timeout


@pytest.mark.parametrize("timeout", [None, 37])
def test_should_restore_requested_timeout_when_resuming(tmp_path, monkeypatch, timeout):
    _, options, args = prepare_resume(tmp_path)
    options["timeout"] = timeout
    with sqlite3.connect(tmp_path / "tasks/jobs.db") as connection:
        connection.execute(
            "UPDATE jobs SET dispatch_options_json=? WHERE job_id=?",
            (json.dumps(options), "resume-v2"),
        )
    calls = []
    monkeypatch.setattr(cli, "_handle_dispatch", lambda restored, *a: calls.append(restored) or 0)
    assert cli._handle_resume(args) == 0
    assert calls[0].timeout == timeout
    args.timeout = 53
    assert cli._handle_resume(args) == 0
    assert calls[1].timeout == 53


def test_should_preserve_ledger_verifier_id_when_recording_execution(tmp_path):
    ledger = _make_ledger(tmp_path, {"unit": {
        "status": "planned", "command": "unit-verifier", "evidence": "keep",
    }})
    result = SubprocessResult(0, "", "", 0.1, ["codex", "exec", "task with spaces"])
    MirExecutor(tmp_path).update_ledger("test-change-id", "unit", result)
    category = json.loads(ledger.read_text())["changes"][0]["categories"]["unit"]
    assert category["command"] == "unit-verifier"
    assert category["evidence"] == "keep"
    assert category["status"] == "pass"
    assert category["executed_argv"] == result.command


def test_should_use_codex_definition_when_agent_declares_codex(tmp_path):
    path = tmp_path / ".claude/agents/executor-agent.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nname: executor-agent\nmodel: inherit\nexecution_backend: codex\n"
        "effort: high\n---\nClaude body\n"
    )
    codex = tmp_path / ".codex/agents/executor-agent.toml"
    codex.parent.mkdir(parents=True)
    text = 'developer_instructions = "Codex body"\nsandbox_mode = "read-only"\n'
    codex.write_text(text)
    route = dispatch.resolve_agent_route(tmp_path, "executor-agent")
    assert route.base_instructions == "Codex body"
    assert route.sandbox == "read-only"
    assert route.reasoning_effort == "high"
    assert route.definition_path == ".codex/agents/executor-agent.toml"
    assert route.definition_sha256 == hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize(
    ("local_default", "expected"),
    [(None, "workspace-write"), ("danger-full-access", "danger-full-access")],
)
def test_should_not_widen_sandbox_from_codex_definition_without_local_opt_in(
    tmp_path, local_default, expected
):
    """Generated .codex/agents may declare danger-full-access; only local config may widen."""
    path = tmp_path / ".claude/agents/executor-agent.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: executor-agent\nexecution_backend: codex\n---\nbody\n")
    codex = tmp_path / ".codex/agents/executor-agent.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text('sandbox_mode = "danger-full-access"\n')
    if local_default is not None:
        (tmp_path / "config").mkdir(exist_ok=True)
        (tmp_path / "config/mir-executor.local.json").write_text(
            json.dumps({"codex_sandbox_default": local_default})
        )
    route = dispatch.resolve_agent_route(tmp_path, "executor-agent")
    assert route.sandbox == expected
