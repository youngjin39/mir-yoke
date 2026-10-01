"""Durable dispatch options and integrity checks for executor resume."""

import hashlib
import json
import sqlite3
import subprocess

import pytest

from tools.mir_executor import cli
from tools.mir_executor.jobs import JobRecord, JobRegistry


def make_job(root, **kwargs):
    return JobRecord(
        job_id="resume-v2", change_id="dispatch-synthetic", category="unit",
        family=None, repo_root=str(root), codex_args=["task"], timeout_seconds=600,
        status="failed", **kwargs,
    )


def original_database(path):
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE jobs (
        job_id TEXT PRIMARY KEY, change_id TEXT NOT NULL, category TEXT NOT NULL,
        family TEXT, repo_root TEXT NOT NULL, codex_args TEXT NOT NULL,
        timeout_seconds INTEGER NOT NULL, status TEXT NOT NULL, exit_code INTEGER,
        stdout TEXT, stderr TEXT, duration_seconds REAL, started_at TEXT NOT NULL,
        completed_at TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0)""")
    connection.execute(
        "INSERT INTO jobs (job_id, change_id, category, repo_root, codex_args, "
        "timeout_seconds, status, started_at) VALUES (?,?,?,?,?,?,?,?)",
        ("resume-v2", "old", "unit", "/tmp", "[]", 600, "failed", ""),
    )
    connection.commit()
    connection.close()


def test_dispatch_options_migrate_and_roundtrip(tmp_path):
    db = tmp_path / "jobs.db"
    original_database(db)
    registry = JobRegistry(db)
    assert registry.get("resume-v2").dispatch_options_json is None
    options = '{"verify_cmds":["unit"]}'
    job = make_job(tmp_path, dispatch_options_json=options)
    job.job_id = "new-job"
    registry.insert(job)
    assert registry.get("new-job").dispatch_options_json == options
    registry.close()


def test_dispatch_options_read_only_legacy(tmp_path):
    db = tmp_path / "jobs.db"
    original_database(db)
    registry = JobRegistry(db, read_only=True)
    assert registry.get("resume-v2").dispatch_options_json is None
    registry.close()
    connection = sqlite3.connect(db)
    assert "dispatch_options_json" not in {
        row[1] for row in connection.execute("PRAGMA table_info(jobs)")
    }
    connection.close()


def prepare_resume(tmp_path, change_id=None):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    brief = tmp_path / "brief.json"
    brief.write_text('{"expanded_goal":"task"}')
    options = {
        "dispatch_brief": str(brief),
        "brief_sha256": hashlib.sha256(brief.read_bytes()).hexdigest(),
        "allow_paths": ["src/"], "verify_cmds": ["unit", "lint"],
        "expect_changes": False, "change_id": change_id, "category": "integration",
        "model": "saved-model", "reasoning_effort": "high",
        "max_codex_attempts": 1, "execution_backend": "claude",
        "artifacts_dir": str(tmp_path / "artifacts"),
        "finalize_lock_timeout": 17.0, "stall_timeout": 45.0,
    }
    registry = JobRegistry(tmp_path / "tasks/jobs.db")
    registry.insert(make_job(
        tmp_path, dispatch_brief_path=str(brief),
        dispatch_options_json=json.dumps(options),
    ))
    registry.close()
    args = cli._build_parser().parse_args(
        ["resume", "--repo-root", str(tmp_path), "--job-id", "resume-v2"]
    )
    return brief, options, args


@pytest.mark.parametrize("change_id", [None, "real-ledger-change"])
def test_resume_restores_verification_and_dispatch_options(tmp_path, monkeypatch, change_id):
    brief, options, args = prepare_resume(tmp_path, change_id)
    calls = []
    monkeypatch.setattr(cli, "_handle_dispatch", lambda *a: calls.append(a) or 0)
    assert cli._handle_resume(args) == 0
    restored, root, codex_args = calls[0]
    assert root == tmp_path
    assert codex_args == ["task"]
    assert restored.dispatch_brief == brief
    for key, value in options.items():
        if key not in {"dispatch_brief", "brief_sha256", "artifacts_dir"}:
            assert getattr(restored, key) == value
    assert restored.artifacts_dir == tmp_path / "artifacts"
    # Missing verify IDs previously caused finalize to fail with no-verification-commands.
    assert restored.verify_cmds == ["unit", "lint"]
    assert restored.change_id == change_id


def test_resume_changed_brief_refused_before_hook_or_dispatch(tmp_path, monkeypatch, capsys):
    brief, _, args = prepare_resume(tmp_path)
    brief.write_text('{"expanded_goal":"different"}')
    calls = []
    monkeypatch.setattr(cli, "invoke_hook", lambda *a: calls.append(a))
    monkeypatch.setattr(cli, "emit_job_event", lambda *a, **kw: calls.append(a))
    monkeypatch.setattr(cli, "_handle_dispatch", lambda *a: calls.append(a) or 0)
    assert cli._handle_resume(args) == 1
    assert calls == []
    assert "brief" in capsys.readouterr().err.lower()
    registry = JobRegistry(tmp_path / "tasks/jobs.db")
    job = registry.get("resume-v2")
    assert job.status == "failed"
    assert job.resume_count == 0
    registry.close()
