"""Regression contracts merged into the fleet executor common base."""

import datetime
import json
import sqlite3

import pytest

from tools.mir_executor import jobs, policy, sweep
from tools.mir_executor.jobs import JobRecord, JobRegistry


def write_policy(root, data):
    path = root / "config/sub-agent-policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize("mode", ["obey_user", "user_command_priority"])
def test_common_canonical_mode(tmp_path, mode):
    write_policy(tmp_path, {"mode": mode})
    assert policy.load_sub_agent_policy(tmp_path).mode == "user_command_priority"


def test_common_optional_local_and_delegation_merge(tmp_path, monkeypatch):
    overlay = tmp_path / "global.json"
    overlay.write_text(
        json.dumps({"delegation": {"mode": "per_project", "default_backend": "claude"}})
    )
    monkeypatch.setenv(policy.POLICY_ENV_VAR, str(overlay))
    assert policy.load_sub_agent_policy(tmp_path).mode == "per_project"
    write_policy(
        tmp_path,
        {
            "mode": "force_codex",
            "delegation": {
                "resolution_order": ["default_backend"],
                "acceptance_evidence": {"diff": True},
            },
        },
    )
    resolved = policy.load_sub_agent_policy(tmp_path)
    assert resolved.default_backend == "claude"
    assert resolved.resolution_order() == ["default_backend"]
    assert resolved.acceptance_evidence() == {"diff": True}
    assert resolved.effective_delegation_mode() == "per_project"


def test_common_lock_path_seam(tmp_path, monkeypatch):
    lock = tmp_path / "custom-lock.json"
    lock.write_text(json.dumps({"policy": {"delegation": {"mode": "unrestricted"}}}))
    monkeypatch.setattr(policy, "model_routing_lock_path", lambda root: lock)
    assert policy.load_sub_agent_policy(tmp_path).mode == "unrestricted"


def test_common_unresolved_mode_warning(tmp_path, capsys):
    write_policy(tmp_path, {"mode": "typo"})
    resolved = policy.load_sub_agent_policy(tmp_path)
    assert resolved.unresolved_mode == "typo"
    assert "typo" in capsys.readouterr().err


def make_job(**overrides):
    return JobRecord(
        **(
            {
                "job_id": "a" * 32,
                "change_id": "x",
                "category": "unit",
                "family": None,
                "repo_root": "/tmp",
                "codex_args": [],
                "timeout_seconds": 30,
                "status": "completed",
                "completed_at": "2026-01-01T00:00:00+00:00",
            }
            | overrides
        )
    )


def test_common_nullable_metadata_and_legacy_read(tmp_path):
    db = tmp_path / "jobs.db"
    registry = JobRegistry(db)
    registry.insert(make_job(identity_json="{}", resolved_model="model"))
    assert registry.get("a" * 32).resolved_model == "model"
    registry.close()
    connection = sqlite3.connect(db)
    for column in [
        "identity_json",
        "resolved_model",
        "dispatch_brief_path",
        "resume_count",
        "last_resumed_at",
        "allow_harness_self_modify",
    ]:
        connection.execute(f"ALTER TABLE jobs DROP COLUMN {column}")
    connection.close()
    registry = JobRegistry(db, read_only=True)
    result = registry.get("a" * 32)
    assert result.identity_json is None
    assert result.resume_count == 0
    assert result.dispatch_brief_path is None
    registry.close()


def test_common_sanitized_persistence(tmp_path):
    registry = JobRegistry(tmp_path / "jobs.db")
    registry.insert(make_job(stdout="api_key=top-secret"))
    assert "top-secret" not in registry.get("a" * 32).stdout
    registry.update_status("a" * 32, "failed", stderr="Bearer secret-value")
    assert "secret-value" not in registry.get("a" * 32).stderr
    assert len(jobs.sanitize_persisted_text("z" * 20000)) <= 16384
    registry.close()


@pytest.mark.parametrize("method", ["mark_resumed", "update_status"])
def test_common_resume_clears_results(tmp_path, method):
    registry = JobRegistry(tmp_path / "jobs.db")
    registry.insert(
        make_job(stdout="old", stderr="old", exit_code=1, duration_seconds=2)
    )
    if method == "mark_resumed":
        registry.mark_resumed("a" * 32, resumed_at="2026-10-01")
    else:
        registry.update_status("a" * 32, "running", clear_existing_result=True)
    result = registry.get("a" * 32)
    assert (
        result.stdout,
        result.stderr,
        result.exit_code,
        result.duration_seconds,
        result.completed_at,
    ) == (None,) * 5
    registry.close()


def test_common_terminal_artifact_sweep(tmp_path):
    db = tmp_path / "jobs.db"
    registry = JobRegistry(db)
    registry.insert(make_job())
    registry.close()
    artifact = tmp_path / "tasks/dispatch" / ("a" * 32)
    artifact.mkdir(parents=True)
    (artifact / "output").write_text("123")
    now = datetime.datetime(2026, 10, 1, tzinfo=datetime.UTC)
    report = sweep.sweep_terminal_artifacts(tmp_path, db, now=now)
    assert report["expired"] == ["a" * 32]
    assert artifact.exists()
    report = sweep.sweep_terminal_artifacts(tmp_path, db, now=now, apply=True)
    assert report["removed"] == ["a" * 32]
    assert not artifact.exists()
    registry = JobRegistry(db)
    assert registry.has_artifact_sweep("a" * 32)
    assert registry._conn.execute(
        "SELECT files, bytes FROM artifact_sweeps"
    ).fetchone()[:] == (1, 3)
    registry.close()


def test_common_artifact_sweep_rejects_symlink_root(tmp_path):
    db = tmp_path / "jobs.db"
    registry = JobRegistry(db)
    registry.insert(make_job())
    registry.close()
    owner_dir = tmp_path / "owner"
    artifact = owner_dir / ("a" * 32)
    artifact.mkdir(parents=True)
    (artifact / "keep").write_text("owner content")
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks/dispatch").symlink_to(owner_dir, target_is_directory=True)
    now = datetime.datetime(2026, 10, 1, tzinfo=datetime.UTC)
    report = sweep.sweep_terminal_artifacts(tmp_path, db, now=now, apply=True)
    assert report["removed"] == []
    assert artifact.exists()


def test_common_ai_run_metadata_roundtrip(tmp_path):
    registry = JobRegistry(tmp_path / "jobs.db")
    registry.insert(make_job(ai_run_metadata={"model": "m", "input_tokens": 12}))
    assert registry.get("a" * 32).ai_run_metadata == {"model": "m", "input_tokens": 12}
    registry.update_ai_run_metadata("a" * 32, {"output_tokens": 4})
    assert registry.get("a" * 32).ai_run_metadata == {"output_tokens": 4}
    registry.close()


def test_common_delegation_project_evidence_accessors(tmp_path):
    write_policy(
        tmp_path,
        {
            "delegation": {
                "mode": "obey_user",
                "project_declaration": {"path": ".mir/repo-profile.toml"},
                "acceptance_evidence": {"required": ["filesystem", "diff", "tests"]},
            }
        },
    )
    resolved = policy.load_sub_agent_policy(tmp_path)
    assert resolved.delegation_mode() == "user_command_priority"
    assert resolved.project_declaration() == {"path": ".mir/repo-profile.toml"}
    assert resolved.acceptance_evidence_required() == ["filesystem", "diff", "tests"]
    assert resolved.delegation_resolution_order() == resolved.resolution_order()
    assert resolved.delegation_project_declaration() == resolved.project_declaration()


def test_common_local_artifact_retention_and_explicit_override(tmp_path):
    config = tmp_path / "config/mir-executor.local.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"artifact_retention_days": 7}))
    db = tmp_path / "jobs.db"
    registry = JobRegistry(db)
    registry.insert(make_job(completed_at="2026-09-20T00:00:00+00:00"))
    registry.close()
    artifact = tmp_path / "tasks/dispatch" / ("a" * 32)
    artifact.mkdir(parents=True)
    now = datetime.datetime(2026, 10, 1, tzinfo=datetime.UTC)
    local = sweep.sweep_terminal_artifacts(tmp_path, db, now=now)
    assert local["retention_days"] == 7
    assert local["expired"] == ["a" * 32]
    explicit = sweep.sweep_terminal_artifacts(tmp_path, db, now=now, retention_days=30)
    assert explicit["retention_days"] == 30
    assert explicit["expired"] == []


def test_common_update_route_metadata(tmp_path):
    registry = JobRegistry(tmp_path / "jobs.db")
    registry.insert(make_job())
    registry.update_route_metadata(
        "a" * 32,
        execution_backend="codex",
        resolved_model="m",
        resolved_reasoning_effort="high",
    )
    result = registry.get("a" * 32)
    assert (
        result.execution_backend,
        result.resolved_model,
        result.resolved_reasoning_effort,
    ) == (
        "codex",
        "m",
        "high",
    )
    registry.close()


def test_common_sweep_resume_attempt_history(tmp_path):
    db = tmp_path / "jobs.db"
    registry = JobRegistry(db)
    registry.insert(
        make_job(
            ai_run_metadata={
                "dispatch_ids": ["b" * 32, "c" * 32, "../owner", "invalid"],
                "dispatch_id": "d" * 32,
            }
        )
    )
    registry.close()
    dispatch_root = tmp_path / "tasks/dispatch"
    ids = ["a" * 32, "b" * 32, "c" * 32, "d" * 32]
    for attempt_id in [*ids, "invalid"]:
        directory = dispatch_root / attempt_id
        directory.mkdir(parents=True)
        (directory / "output").write_text(attempt_id)
    now = datetime.datetime(2026, 10, 1, tzinfo=datetime.UTC)
    report = sweep.sweep_terminal_artifacts(tmp_path, db, now=now, apply=True)
    assert report["removed"] == ids
    assert (dispatch_root / "invalid").exists()
    registry = JobRegistry(db)
    rows = registry._conn.execute("SELECT job_id, path FROM artifact_sweeps").fetchall()
    assert len(rows) == 4
    assert {row["job_id"] for row in rows} == {"a" * 32}
    assert {row["path"] for row in rows} == {str(dispatch_root / item) for item in ids}
    registry.close()


def test_common_artifact_sweep_evidence_is_path_specific(tmp_path):
    registry = JobRegistry(tmp_path / "jobs.db")
    registry.record_artifact_sweep("a" * 32, "/attempt/one", 1, 4, "now")
    assert registry.has_artifact_sweep("a" * 32)
    assert registry.has_artifact_sweep("a" * 32, path="/attempt/one")
    assert not registry.has_artifact_sweep("a" * 32, path="/attempt/two")
    registry.close()
