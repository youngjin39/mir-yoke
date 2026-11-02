"""Capture Python JobRegistry rows, schemas, errors and cancel output."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import pathlib
import sqlite3
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor import cli, cli_jobs  # noqa: E402
from tools.mir_executor.jobs import JobRecord, JobRegistry  # noqa: E402

OPTIONAL = [
    "target_agent",
    "execution_backend",
    "resolved_model",
    "resolved_reasoning_effort",
    "agent_definition_path",
    "agent_definition_sha256",
    "identity_json",
    "dispatch_options_json",
    "ai_run_metadata",
    "dispatch_brief_path",
    "allow_harness_self_modify",
    "resume_count",
    "last_resumed_at",
]


def snapshot(connection):
    connection.row_factory = sqlite3.Row
    return {
        "columns": [list(row) for row in connection.execute("PRAGMA table_info(jobs)")],
        "rows": [dict(row) for row in connection.execute("SELECT * FROM jobs ORDER BY job_id")],
        "sweeps": [list(row) for row in connection.execute("SELECT * FROM artifact_sweeps")],
    }


def generate():
    cases = []
    with tempfile.TemporaryDirectory(dir=os.environ.get("MIR_NATIVE_TEST_SCRATCH")) as directory:
        path = pathlib.Path(directory) / "jobs.db"
        registry = JobRegistry(path)
        schema = registry._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='jobs'"
        ).fetchone()[0]
        registry.close()
        path.unlink()
        shapes = [[], OPTIONAL] + [[column] for column in OPTIONAL]
        for removed in shapes:
            connection = sqlite3.connect(path)
            connection.execute(schema)
            connection.execute(
                "INSERT INTO jobs (job_id,change_id,category,repo_root,codex_args,"
                "timeout_seconds,status,started_at) VALUES "
                "('legacy','c','unit','fixture-root','[]',60,'running','then')"
            )
            for column in removed:
                connection.execute(f"ALTER TABLE jobs DROP COLUMN {column}")
            connection.commit()
            initial = "\n".join(connection.iterdump())
            connection.close()
            registry = JobRegistry(path)
            cases.append(
                {"removed": removed, "initial": initial, "expected": snapshot(registry._conn)}
            )
            registry.close()
            path.unlink()
        registry = JobRegistry(path)
        record = dataclasses.asdict(
            JobRecord(
                job_id="job",
                change_id="change",
                category="unit",
                family=None,
                repo_root="fixture-root",
                codex_args=["token=private", "\ud55c\U0001f600"],
                timeout_seconds=60,
                status="running",
                started_at="2026-01-01T00:00:00Z",
                ai_run_metadata={"z": [1, True, 1e-7, 1e16, -0.0], "a": "\ud55c"},
                stdout="api_key=private",
                stderr='"password": "private value"',
            )
        )
        operations = [
            {"op": "insert", "record": record},
            {"op": "insert", "record": record, "error": "IntegrityError"},
            {
                "op": "update_route_metadata",
                "job_id": "job",
                "execution_backend": "codex",
                "resolved_model": "fixture-model",
                "resolved_reasoning_effort": "medium",
            },
            {
                "op": "update_ai_run_metadata",
                "job_id": "job",
                "metadata": {"z": 1, "a": "\U0001f600"},
            },
            {
                "op": "update_status",
                "job_id": "job",
                "status": "completed",
                "exit_code": 7,
                "stdout": "password=secret bearer abc",
                "stderr": "x" * 16400,
                "duration_seconds": 1.25,
                "completed_at": "done",
            },
            {"op": "cancel", "job_id": "job"},
            {"op": "cancel", "job_id": "absent"},
            {"op": "mark_resumed", "job_id": "job", "resumed_at": "again"},
            {"op": "mark_resumed", "job_id": "job", "resumed_at": "again-twice"},
            {"op": "mark_resumed", "job_id": "absent", "resumed_at": "no-op"},
            {"op": "update_status", "job_id": "absent", "status": "failed"},
            {"op": "update_status", "job_id": "job", "status": "failed", "stdout": "keep"},
            {
                "op": "update_status",
                "job_id": "job",
                "status": "running",
                "clear_existing_result": True,
            },
            {"op": "update_ai_run_metadata", "job_id": "job", "metadata": None},
            {
                "op": "update_route_metadata",
                "job_id": "job",
                "execution_backend": None,
                "resolved_model": None,
                "resolved_reasoning_effort": None,
            },
            {
                "op": "record_artifact_sweep",
                "job_id": "job",
                "path": "artifacts",
                "files": 2,
                "size_bytes": 10,
                "swept_at": "now",
            },
        ]
        for operation in operations:
            args = {k: v for k, v in operation.items() if k not in ("op", "error")}
            if operation["op"] == "insert":
                args = {"job": JobRecord(**args["record"])}
            try:
                result = getattr(registry, operation["op"])(**args)
                assert "error" not in operation
                operation["result"] = result
            except sqlite3.IntegrityError:
                assert operation.get("error") == "IntegrityError"
            operation["expected"] = snapshot(registry._conn)
        registry.close()
        cancel = []
        for job in ("job", "absent-'\ud55c"):
            out, err = io.StringIO(), io.StringIO()
            import argparse

            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli_jobs._handle_cancel(
                    cli, argparse.Namespace(repo_root=path.parent, jobs_db=path, job_id=job)
                )
            cancel.append(
                {"job_id": job, "stdout": out.getvalue(), "stderr": err.getvalue(), "code": code}
            )
        from tools.mir_executor.jobs import sanitize_persisted_text

        texts = [
            "",
            "ordinary text",
            '"api_key": "value with spaces"',
            "password: 'value'",
            "Bearer opaque",
            "sk-proj-abcdefghijklmnop",
            "ghp_abcdefghijklmnopqrstuvwxyz",
            "xoxb-abcdefghijklmnop",
            "AKIAABCDEFGHIJKLMNOP",
            "AIzaabcdefghijklmnopqrstuvwxyz",
            "-----BEGIN PRIVATE KEY-----\nbody\n-----END PRIVATE KEY-----",
            "-----BEGIN RSA PRIVATE KEY-----unterminated",
            "max_tokens: 4096",
            "\u0301token=abc",
            "\u0130OKEN=abc",
            "token\u001c=\u001cvalue",
            "\ud55c\U0001f600" * 8300,
            "\u212aey token=private",
            "authorization=Basic abc",
            "sk_\u017f\u0130\u0131\u212aabcdefghijklmno",
        ]
        return {
            "migrations": cases,
            "operations": operations,
            "cancel": cancel,
            "sanitize": [
                {"input": text, "expected": sanitize_persisted_text(text)} for text in texts
            ],
        }


if __name__ == "__main__":
    pathlib.Path(__file__).with_name("executor_registry.json").write_text(
        json.dumps(generate(), ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
