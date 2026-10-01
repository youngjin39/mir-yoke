"""Common dispatch safety and optional extension contracts."""

import json

import pytest

from tools.mir_executor import dispatch
from tools.mir_executor.codex_mcp_client import CodexMcpResult
from tools.mir_executor.tests.test_dispatch import _cleanup, _make_repo


def config(repo, **values):
    path = repo / "config/mir-executor.local.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(values))


def test_common_glob_allowlist():
    assert dispatch._path_allowed("src/example.py", ["src/*.py"])
    assert not dispatch._path_allowed("other/example.py", ["src/*.py"])


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_common_timeout_validation(value, tmp_path):
    with pytest.raises(ValueError):
        dispatch.build_codex_mcp_runner(tmp_path, "task", timeout_seconds=value)
    with pytest.raises(ValueError):
        dispatch.build_claude_runner(tmp_path, timeout_seconds=value)


def test_common_workspace_sandbox_and_metadata(tmp_path):
    repo = _make_repo(tmp_path)
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call_codex(self, **kwargs):
            calls.append(kwargs)
            return CodexMcpResult(
                "done", "thread", {"usage": {"inputTokens": 12}, "model": "actual"}
            )

    runner = dispatch.build_codex_mcp_runner(repo, "task", model="requested", client_factory=Client)
    outcome = dispatch.run_dispatch(repo, "meta", codex_runner=runner)
    try:
        assert calls[0]["sandbox"] == "workspace-write"
        assert outcome.tokens_used == (("input_tokens", 12),)
        assert outcome.model_id == "actual"
        assert outcome.stdout == "done"
    finally:
        _cleanup(outcome)


def test_common_secure_redacted_artifacts(tmp_path):
    repo = _make_repo(tmp_path)
    outcome = dispatch.run_dispatch(
        repo,
        "safe",
        brief_text="token=sk-" + "x" * 40,
        codex_runner=lambda *_: dispatch.CodexAttempt(0),
    )
    try:
        target = dispatch.persist_dispatch_artifacts(outcome.worktree, repo, tmp_path / "artifacts")
        brief = target / "brief.md"
        assert "sk-" + "x" * 40 not in brief.read_text()
        assert brief.stat().st_mode & 0o777 == 0o600
        assert (outcome.worktree.path / ".mir-dispatch/brief.md").stat().st_mode & 0o777 == 0o600
    finally:
        _cleanup(outcome)


def test_common_unknown_verifier_fails_closed(tmp_path):
    repo = _make_repo(tmp_path)
    outcome = dispatch.run_dispatch(
        repo, "unknown", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )
    try:
        gate = dispatch.evaluate_merge_gate(
            outcome.worktree,
            allowlist=[],
            expect_changes=False,
            verification_commands=["touch unsafe"],
        )
        assert gate.reason == "unknown-verifier:touch unsafe"
    finally:
        _cleanup(outcome)


def test_common_named_verifier_and_reviewed_no_diff(tmp_path):
    repo = _make_repo(tmp_path)
    config(repo, verifiers={"pass": ["true"]})
    outcome = dispatch.run_dispatch(
        repo, "review", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )
    result = dispatch.finalize_dispatch(
        outcome.worktree,
        repo,
        outcome,
        allowlist=[],
        verification_commands=["pass"],
        expect_changes=False,
    )
    try:
        assert result.action == "reviewed"
        assert result.merged_files == []
    finally:
        if outcome.worktree.path.exists():
            _cleanup(outcome)


def test_common_required_review_fails_closed(tmp_path):
    repo = _make_repo(tmp_path)
    config(repo, verifiers={"pass": ["true"]}, require_review=True)
    outcome = dispatch.run_dispatch(
        repo, "review-required", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )
    try:
        result = dispatch.finalize_dispatch(
            outcome.worktree,
            repo,
            outcome,
            allowlist=[],
            verification_commands=["pass"],
            expect_changes=False,
        )
        assert result.reason == "reviewer-missing"
    finally:
        _cleanup(outcome)


def test_common_reviewer_read_only(tmp_path):
    repo = _make_repo(tmp_path)
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call_codex(self, **kwargs):
            calls.append(kwargs)
            return CodexMcpResult('{"verdict":"pass","reason":"ok","findings":[]}', "review", {})

    outcome = dispatch.run_dispatch(
        repo, "read-review", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )
    try:
        reviewer = dispatch.build_codex_review_runner(repo, client_factory=Client)
        assert reviewer(outcome.worktree, []).passed
        assert calls[0]["sandbox"] == "read-only"
    finally:
        _cleanup(outcome)


def test_common_agent_route_api(tmp_path):
    route = dispatch.AgentRoute(
        "review", "codex", "m", "high", "def", "sha", "instructions", "read-only"
    )
    assert not dispatch.agent_route_expects_changes(route)
    with pytest.raises(ValueError):
        dispatch.resolve_agent_route(tmp_path, "missing")


def test_common_failure_preserves_metadata(tmp_path):
    repo = _make_repo(tmp_path)
    attempt = dispatch.CodexAttempt(124, tokens_used=(("output_tokens", 3),), model_id="m")
    outcome = dispatch.run_dispatch(repo, "failed-meta", codex_runner=lambda *_: attempt)
    try:
        assert outcome.exit_code == 124
        assert outcome.tokens_used == attempt.tokens_used
        assert outcome.model_id == "m"
    finally:
        _cleanup(outcome)


def test_common_verifier_environment_filters_credentials(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    config(repo, verifiers={"pass": ["true"]})
    outcome = dispatch.run_dispatch(
        repo, "verify-env", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )
    original = dispatch.subprocess.run
    environments = []
    monkeypatch.setenv("OPENAI_API_KEY", "credential")

    def run(argv, **kwargs):
        if argv == ["true"]:
            environments.append(kwargs.get("env"))
        return original(argv, **kwargs)

    monkeypatch.setattr(dispatch.subprocess, "run", run)
    try:
        gate = dispatch.evaluate_merge_gate(
            outcome.worktree, allowlist=[], expect_changes=False, verification_commands=["pass"]
        )
        assert gate.approved
        assert environments[0] is not None
        assert "OPENAI_API_KEY" not in environments[0]
    finally:
        _cleanup(outcome)


def test_common_claude_route_api(tmp_path, monkeypatch):
    route = dispatch.AgentRoute("agent", "claude", "sonnet", "high", "def", "sha", "body")
    calls = []

    def run(argv, cwd, env, timeout):
        calls.append(argv)
        return dispatch.subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(dispatch, "_run_guarded", run)
    repo = _make_repo(tmp_path)
    outcome = dispatch.run_dispatch(
        repo, "claude-route", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )
    try:
        runner = dispatch.build_claude_runner(
            repo, agent_route=route, model="sonnet", reasoning_effort="high"
        )
        runner(outcome.worktree, 1)
        assert calls[0][1:7] == ["--agent", "agent", "--model", "sonnet", "--effort", "high"]
    finally:
        _cleanup(outcome)


def test_common_reviewed_no_diff_rechecks_review_mutation(tmp_path):
    repo = _make_repo(tmp_path)
    config(repo, verifiers={"pass": ["true"]})
    outcome = dispatch.run_dispatch(
        repo, "review-dirty", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )

    def reviewer(wt, paths):
        (wt.path / "pkg/mod.py").write_text("changed by reviewer")
        return dispatch.ReviewEvidence(True, "ok", "")

    try:
        result = dispatch.finalize_dispatch(
            outcome.worktree,
            repo,
            outcome,
            allowlist=[],
            verification_commands=["pass"],
            expect_changes=False,
            reviewer=reviewer,
        )
        assert result.action == "blocked"
        assert result.reason == "dispatch-dirty"
    finally:
        if outcome.worktree.path.exists():
            _cleanup(outcome)


def test_common_run_artifacts_root(tmp_path):
    repo = _make_repo(tmp_path)
    outcome = dispatch.run_dispatch(
        repo,
        "rooted",
        artifacts_root=tmp_path / "artifacts",
        codex_runner=lambda *_: dispatch.CodexAttempt(0),
    )
    try:
        assert (tmp_path / "artifacts/rooted/dispatch-events.jsonl").exists()
    finally:
        _cleanup(outcome)


def test_common_reviewed_cleanup_failure_keeps_review_verdict(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    config(repo, verifiers={"pass": ["true"]})
    outcome = dispatch.run_dispatch(
        repo, "review-cleanup", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )

    def cleanup(wt):
        raise OSError("cleanup failed")

    monkeypatch.setattr(dispatch, "cleanup_worktree", cleanup)
    try:
        result = dispatch.finalize_dispatch(
            outcome.worktree,
            repo,
            outcome,
            allowlist=[],
            verification_commands=["pass"],
            expect_changes=False,
        )
        assert result.action == "reviewed-but-cleanup-failed"
    finally:
        _cleanup(outcome)


def test_common_long_review_evidence_remains_valid_json(tmp_path):
    repo = _make_repo(tmp_path)
    config(repo, verifiers={"pass": ["true"]})
    outcome = dispatch.run_dispatch(
        repo, "long-review", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )
    content = "x" * 20_000 + " token=private-value"
    try:
        result = dispatch.finalize_dispatch(
            outcome.worktree,
            repo,
            outcome,
            allowlist=[],
            verification_commands=["pass"],
            expect_changes=False,
            reviewer=lambda *_: dispatch.ReviewEvidence(True, "ok", content),
        )
        assert result.action == "reviewed"
        artifact = repo / "tasks/dispatch/long-review/reviewer.json"
        payload = json.loads(artifact.read_text())
        assert payload["content"].startswith("x" * 20_000)
        assert "private-value" not in payload["content"]
    finally:
        if outcome.worktree.path.exists():
            _cleanup(outcome)


@pytest.mark.parametrize("filename", ["status.json", "events.jsonl"])
def test_common_long_structured_artifacts_remain_valid_json(tmp_path, filename):
    repo = _make_repo(tmp_path)
    outcome = dispatch.run_dispatch(
        repo, "long-artifact", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )
    try:
        source = outcome.worktree.path / ".mir-dispatch" / filename
        source.write_text(json.dumps({"detail": "x" * 20_000 + " token=private-value"}) + "\n")
        artifact_dir = dispatch.persist_dispatch_artifacts(outcome.worktree, repo)
        payload = json.loads((artifact_dir / filename).read_text())
        assert payload["detail"].startswith("x" * 20_000)
        assert "private-value" not in payload["detail"]
    finally:
        _cleanup(outcome)


@pytest.mark.parametrize("filename", ["status.json", "events.jsonl"])
def test_common_nested_secret_redaction_preserves_json(tmp_path, filename):
    path = tmp_path / filename
    original = {"nested": [{"content": "API_KEY=private-value"}], "count": 2}
    dispatch._secure_write(path, json.dumps(original) + "\n")
    payload = json.loads(path.read_text())
    assert payload["count"] == 2
    assert payload["nested"][0]["content"] == "API_KEY=[REDACTED]"


def test_common_worktree_structured_status_redacts_values(tmp_path):
    from tools.mir_executor.worktree import _write_json

    path = tmp_path / "status.json"
    _write_json(path, {"nested": [{"content": "x" * 20_000 + " API_KEY=private-value"}]})
    payload = json.loads(path.read_text())
    assert payload["nested"][0]["content"] == "x" * 20_000 + " API_KEY=[REDACTED]"
    assert path.stat().st_mode & 0o777 == 0o600
