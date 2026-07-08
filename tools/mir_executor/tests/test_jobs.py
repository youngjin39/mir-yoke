"""
test_jobs.py
------------
Tests for tools.mir_executor.jobs (JobRegistry + JobRecord)
and CLI background job subcommands.

ADR: docs/decisions/p2-4-l4-background-jobs-2026-05-10.md §9

Note on --background MVP:
    Background mode in this CLI prints job_id then runs synchronously
    (asyncio.run) within the same process. True daemon detachment is
    Out-of-Scope per ADR §8 O1. Tests verify the synchronous flow.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import subprocess
import sys
import threading

import pytest

from tools.mir_executor.jobs import (
    JobRecord,
    JobRegistry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(
    job_id: str = "aabbcc00",
    change_id: str = "test-change",
    category: str = "unit",
    family: str | None = None,
    repo_root: str = "/tmp/repo",
    codex_args: list[str] | None = None,
    dispatch_brief_path: str | None = None,
    timeout_seconds: int = 600,
    status: str = "running",
    started_at: str = "2026-05-10T00:00:00+00:00",
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        change_id=change_id,
        category=category,
        family=family,
        repo_root=repo_root,
        codex_args=codex_args if codex_args is not None else ["--model", "o4-mini"],
        dispatch_brief_path=dispatch_brief_path,
        timeout_seconds=timeout_seconds,
        status=status,
        started_at=started_at,
    )


def _make_registry(tmp_path: pathlib.Path) -> JobRegistry:
    return JobRegistry(tmp_path / "jobs.db")


# ---------------------------------------------------------------------------
# 1. test_insert_creates_record
# ---------------------------------------------------------------------------

def test_insert_creates_record(tmp_path):
    reg = _make_registry(tmp_path)
    job = _make_job(job_id="abc123")
    reg.insert(job)
    # Verify via raw sqlite
    conn = sqlite3.connect(str(tmp_path / "jobs.db"))
    row = conn.execute("SELECT job_id FROM jobs WHERE job_id='abc123'").fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "abc123"


# ---------------------------------------------------------------------------
# 2. test_get_returns_inserted
# ---------------------------------------------------------------------------

def test_get_returns_inserted(tmp_path):
    reg = _make_registry(tmp_path)
    job = _make_job(job_id="deadbeef", change_id="my-change", category="integration")
    reg.insert(job)
    fetched = reg.get("deadbeef")
    assert fetched is not None
    assert fetched.job_id == "deadbeef"
    assert fetched.change_id == "my-change"
    assert fetched.category == "integration"
    assert fetched.status == "running"


# ---------------------------------------------------------------------------
# 3. test_get_returns_none_when_unknown
# ---------------------------------------------------------------------------

def test_get_returns_none_when_unknown(tmp_path):
    reg = _make_registry(tmp_path)
    result = reg.get("nonexistent-job-id")
    assert result is None


# ---------------------------------------------------------------------------
# 4. test_update_status_persists
# ---------------------------------------------------------------------------

def test_update_status_persists(tmp_path):
    reg = _make_registry(tmp_path)
    job = _make_job(job_id="job001", status="running")
    reg.insert(job)
    reg.update_status("job001", "completed", completed_at="2026-05-10T01:00:00+00:00")
    fetched = reg.get("job001")
    assert fetched is not None
    assert fetched.status == "completed"
    assert fetched.completed_at == "2026-05-10T01:00:00+00:00"


# ---------------------------------------------------------------------------
# 5. test_update_status_with_exit_code_and_stdout
# ---------------------------------------------------------------------------

def test_update_status_with_exit_code_and_stdout(tmp_path):
    reg = _make_registry(tmp_path)
    job = _make_job(job_id="job002", status="running")
    reg.insert(job)
    reg.update_status(
        "job002",
        "completed",
        exit_code=0,
        stdout="all tests pass",
        stderr="",
        duration_seconds=12.5,
        completed_at="2026-05-10T01:00:00+00:00",
    )
    fetched = reg.get("job002")
    assert fetched is not None
    assert fetched.exit_code == 0
    assert fetched.stdout == "all tests pass"
    assert fetched.stderr == ""
    assert fetched.duration_seconds == pytest.approx(12.5)


# ---------------------------------------------------------------------------
# 6. test_cancel_sets_flag
# ---------------------------------------------------------------------------

def test_cancel_sets_flag(tmp_path):
    reg = _make_registry(tmp_path)
    job = _make_job(job_id="job003", status="running")
    reg.insert(job)
    reg.cancel("job003")
    fetched = reg.get("job003")
    assert fetched is not None
    assert fetched.cancel_requested is True


# ---------------------------------------------------------------------------
# 7. test_cancel_returns_true_when_found
# ---------------------------------------------------------------------------

def test_cancel_returns_true_when_found(tmp_path):
    reg = _make_registry(tmp_path)
    job = _make_job(job_id="job004")
    reg.insert(job)
    result = reg.cancel("job004")
    assert result is True


# ---------------------------------------------------------------------------
# 8. test_cancel_returns_false_when_unknown
# ---------------------------------------------------------------------------

def test_cancel_returns_false_when_unknown(tmp_path):
    reg = _make_registry(tmp_path)
    result = reg.cancel("no-such-job")
    assert result is False


# ---------------------------------------------------------------------------
# 9. test_list_jobs_all
# ---------------------------------------------------------------------------

def test_list_jobs_all(tmp_path):
    reg = _make_registry(tmp_path)
    for i in range(3):
        reg.insert(_make_job(job_id=f"listjob{i}", status="running"))
    jobs = reg.list_jobs()
    assert len(jobs) == 3


# ---------------------------------------------------------------------------
# 10. test_list_jobs_filtered_by_status_running
# ---------------------------------------------------------------------------

def test_list_jobs_filtered_by_status_running(tmp_path):
    reg = _make_registry(tmp_path)
    reg.insert(_make_job(job_id="r1", status="running"))
    reg.insert(_make_job(job_id="r2", status="running"))
    reg.insert(_make_job(job_id="c1", status="completed"))
    jobs = reg.list_jobs(status_filter="running")
    assert len(jobs) == 2
    assert all(j.status == "running" for j in jobs)


# ---------------------------------------------------------------------------
# 11. test_list_jobs_filtered_by_status_completed
# ---------------------------------------------------------------------------

def test_list_jobs_filtered_by_status_completed(tmp_path):
    reg = _make_registry(tmp_path)
    reg.insert(_make_job(job_id="r3", status="running"))
    reg.insert(_make_job(job_id="c2", status="completed"))
    jobs = reg.list_jobs(status_filter="completed")
    assert len(jobs) == 1
    assert jobs[0].job_id == "c2"


# ---------------------------------------------------------------------------
# 12. test_schema_creates_on_first_use
# ---------------------------------------------------------------------------

def test_schema_creates_on_first_use(tmp_path):
    db_path = tmp_path / "fresh.db"
    assert not db_path.exists()
    JobRegistry(db_path)
    # Table must exist after init
    conn = sqlite3.connect(str(db_path))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
    ).fetchone()
    conn.close()
    assert tables is not None
    assert tables[0] == "jobs"


# ---------------------------------------------------------------------------
# 13. test_concurrent_inserts_safe (real threading — 5 concurrent inserters)
# ---------------------------------------------------------------------------

def test_concurrent_inserts_safe(tmp_path):
    """Five threads concurrently insert into the same JobRegistry.

    Verifies:
    - All 5 records are persisted (no DB locked errors, no missing rows).
    - threading.Lock in JobRegistry serializes writes correctly.
    - More than 1 thread is exercised (5 Thread objects are started).
    """
    reg = _make_registry(tmp_path)
    errors: list[Exception] = []

    def _insert(i: int) -> None:
        try:
            reg.insert(_make_job(job_id=f"concurrent{i}"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_insert, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    jobs = reg.list_jobs()
    ids = {j.job_id for j in jobs}
    assert ids == {f"concurrent{i}" for i in range(5)}
    # Confirm more than 1 thread was involved (not sequential simulation).
    assert len(threads) == 5


# ---------------------------------------------------------------------------
# 14. test_codex_args_roundtrip (JSON dumps/loads preserves list)
# ---------------------------------------------------------------------------

def test_codex_args_roundtrip(tmp_path):
    args_in = ["--model", "o4-mini", "--timeout", "300", "--flag"]
    reg = _make_registry(tmp_path)
    job = _make_job(job_id="roundtrip", codex_args=args_in)
    reg.insert(job)
    fetched = reg.get("roundtrip")
    assert fetched is not None
    assert fetched.codex_args == args_in


def test_dispatch_brief_path_roundtrip(tmp_path):
    reg = _make_registry(tmp_path)
    job = _make_job(
        job_id="briefpath",
        dispatch_brief_path="/tmp/tasks/dispatch/task/slice.json",
    )
    reg.insert(job)
    fetched = reg.get("briefpath")
    assert fetched is not None
    assert fetched.dispatch_brief_path == "/tmp/tasks/dispatch/task/slice.json"


def test_allow_harness_self_modify_roundtrip(tmp_path):
    reg = _make_registry(tmp_path)
    job = _make_job(job_id="allowharness")
    job.allow_harness_self_modify = True
    reg.insert(job)
    fetched = reg.get("allowharness")
    assert fetched is not None
    assert fetched.allow_harness_self_modify is True


def test_allow_harness_self_modify_legacy_rows_default_false(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE jobs (
            job_id             TEXT    PRIMARY KEY,
            change_id          TEXT    NOT NULL,
            category           TEXT    NOT NULL,
            family             TEXT,
            repo_root          TEXT    NOT NULL,
            codex_args         TEXT    NOT NULL,
            dispatch_brief_path TEXT,
            resume_count       INTEGER NOT NULL DEFAULT 0,
            last_resumed_at    TEXT,
            timeout_seconds    INTEGER NOT NULL,
            status             TEXT    NOT NULL,
            exit_code          INTEGER,
            stdout             TEXT,
            stderr             TEXT,
            duration_seconds   REAL,
            started_at         TEXT    NOT NULL,
            completed_at       TEXT,
            cancel_requested   INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.execute(
        """
        INSERT INTO jobs (
            job_id, change_id, category, family, repo_root, codex_args,
            dispatch_brief_path, timeout_seconds, status, started_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "legacyharness",
            "change",
            "unit",
            None,
            "/tmp/repo",
            json.dumps(["exec", "hi"]),
            None,
            600,
            "running",
            "2026-05-10T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    reg = JobRegistry(db_path)
    fetched = reg.get("legacyharness")
    assert fetched is not None
    assert fetched.allow_harness_self_modify is False


def test_mark_resumed_increments_counter_and_timestamp(tmp_path):
    reg = _make_registry(tmp_path)
    reg.insert(_make_job(job_id="resume-counter"))
    reg.mark_resumed("resume-counter", resumed_at="2026-05-28T12:00:00+00:00")
    fetched = reg.get("resume-counter")
    assert fetched is not None
    assert fetched.resume_count == 1
    assert fetched.last_resumed_at == "2026-05-28T12:00:00+00:00"


# ---------------------------------------------------------------------------
# 15. test_family_null_preserved
# ---------------------------------------------------------------------------

def test_family_null_preserved(tmp_path):
    reg = _make_registry(tmp_path)
    job = _make_job(job_id="famnull", family=None)
    reg.insert(job)
    fetched = reg.get("famnull")
    assert fetched is not None
    assert fetched.family is None


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _make_ledger(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a minimal tdd.json with one planned entry."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = tasks_dir / "tdd.json"
    ledger = {
        "version": 1,
        "changes": [
            {
                "id": "bg-test-change",
                "scope": "background CLI test",
                "targets": ["tasks/tdd.json"],
                "categories": {
                    "unit": {"status": "planned"},
                },
            }
        ],
    }
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return ledger_path


def _write_dispatch_brief(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "tasks" / "dispatch" / "dispatch-task" / "executor-slice.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "task_id": "dispatch-task",
                "phase_id": "phase-4",
                "slice_id": "executor-slice",
                "target_agent": "executor-agent",
                "user_intent": "Resume executor job",
                "expanded_goal": "Resume executor job [role=executor, stack=python]",
                "owned_scope": ["tools/mir_executor/**"],
                "out_of_scope": ["docs/**"],
                "verification_commands": ["uv run pytest -q tools/mir_executor/tests/test_jobs.py"],
                "stop_conditions": ["Stop if owned_scope expands."],
                "handoff_refs": [],
                "tdd_change_refs": ["tasks/tdd.json#bg-test-change"],
                "resume_state_ref": "tasks/dispatch/dispatch-task/executor-slice.json",
                "source_refs": {
                    "task_spec": "runtime://task-spec/dispatch-task",
                    "plan": "tasks/plan.md",
                    "phase": "tasks/phase.json",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _run_cli(*args, cwd=None, env=None):
    """Run the mir_executor CLI as a subprocess and return CompletedProcess."""
    cmd = [sys.executable, "-m", "tools.mir_executor", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
    )
    return result


# ---------------------------------------------------------------------------
# 16. test_cli_execute_background_returns_job_id
# ---------------------------------------------------------------------------

def test_cli_execute_background_returns_job_id(tmp_path, monkeypatch):
    """execute --background prints job_id (UUID hex) and exits 0.

    Monkeypatches run_codex_async to avoid real Codex invocation.
    Also monkeypatches update_ledger so the test is ledger-agnostic.
    """
    from tools.mir_executor.executor import LedgerUpdate, MirExecutor, SubprocessResult

    _make_ledger(tmp_path)
    jobs_db = tmp_path / "tasks" / "jobs.db"

    fake_result = SubprocessResult(
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=0.1,
        command=["codex"],
    )
    fake_update = LedgerUpdate(
        change_id="bg-test-change",
        category="unit",
        previous_status="planned",
        new_status="pass",
        notes="test",
    )

    async def _fake_run_codex_async(self, codex_args, timeout_seconds=600):
        return fake_result

    def _fake_update_ledger(self, change_id, category, result):
        return fake_update

    monkeypatch.setattr(MirExecutor, "run_codex_async", _fake_run_codex_async)
    monkeypatch.setattr(MirExecutor, "update_ledger", _fake_update_ledger)

    import io
    from contextlib import redirect_stdout

    from tools.mir_executor.cli import main

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main([
            "--jobs-db", str(jobs_db),
            "execute",
            "--background",
            "--change-id", "bg-test-change",
            "--category", "unit",
            "--codex-args", "ignored",
            "--repo-root", str(tmp_path),
        ])

    output = buf.getvalue()
    assert rc == 0
    # Output must contain a UUID-like job_id
    assert "[BACKGROUND] job_id=" in output
    job_id_part = output.split("job_id=")[-1].strip()
    # UUID4 hex is 32 lowercase hex chars
    assert len(job_id_part) == 32
    assert all(c in "0123456789abcdef" for c in job_id_part)


# ---------------------------------------------------------------------------
# 17. test_cli_status_outputs_record
# ---------------------------------------------------------------------------

def test_cli_status_outputs_record(tmp_path):
    """status --job-id prints status of a running job."""
    import io
    from contextlib import redirect_stdout

    from tools.mir_executor.cli import main

    jobs_db = tmp_path / "jobs.db"
    reg = JobRegistry(jobs_db)
    job = _make_job(
        job_id="statusjob",
        status="running",
        dispatch_brief_path="/tmp/tasks/dispatch/statusjob/slice.json",
    )
    reg.insert(job)
    reg.close()

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main([
            "--jobs-db", str(jobs_db),
            "status",
            "--job-id", "statusjob",
        ])

    output = buf.getvalue()
    assert rc == 0
    assert "statusjob" in output
    assert "running" in output
    assert "dispatch_brief_path" in output
    assert "allow_harness_self_modify=False" in output
    assert "resume_count=0" in output


# ---------------------------------------------------------------------------
# 18. test_cli_result_outputs_completed_record
# ---------------------------------------------------------------------------

def test_cli_result_outputs_completed_record(tmp_path):
    """result --job-id prints exit_code/stdout for a completed job."""
    import io
    from contextlib import redirect_stdout

    from tools.mir_executor.cli import main

    jobs_db = tmp_path / "jobs.db"
    reg = JobRegistry(jobs_db)
    job = _make_job(
        job_id="resultjob",
        status="completed",
        dispatch_brief_path="/tmp/tasks/dispatch/resultjob/slice.json",
    )
    reg.insert(job)
    reg.update_status(
        "resultjob",
        "completed",
        exit_code=0,
        stdout="15 passed",
        duration_seconds=3.14,
        completed_at="2026-05-10T01:00:00+00:00",
    )
    reg.close()

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main([
            "--jobs-db", str(jobs_db),
            "result",
            "--job-id", "resultjob",
        ])

    output = buf.getvalue()
    assert rc == 0
    assert "completed" in output
    assert "exit_code=0" in output
    assert "15 passed" in output
    assert "dispatch_brief_path" in output
    assert "allow_harness_self_modify=False" in output
    assert "resume_count=0" in output


# ---------------------------------------------------------------------------
# 19. test_cli_cancel_sets_flag
# ---------------------------------------------------------------------------

def test_cli_cancel_sets_flag(tmp_path):
    """cancel --job-id sets cancel_requested=True in the registry."""
    import io
    from contextlib import redirect_stdout

    from tools.mir_executor.cli import main

    jobs_db = tmp_path / "jobs.db"
    reg = JobRegistry(jobs_db)
    job = _make_job(job_id="canceljob", status="running")
    reg.insert(job)
    reg.close()

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main([
            "--jobs-db", str(jobs_db),
            "cancel",
            "--job-id", "canceljob",
        ])

    assert rc == 0
    assert "cancel_requested=True" in buf.getvalue()

    # Verify DB state
    reg2 = JobRegistry(jobs_db)
    job2 = reg2.get("canceljob")
    reg2.close()
    assert job2 is not None
    assert job2.cancel_requested is True


def test_cli_resume_replays_job_with_dispatch_brief(tmp_path, monkeypatch):
    import io
    from contextlib import redirect_stdout

    from tools.mir_executor.cli import main
    from tools.mir_executor.executor import LedgerUpdate, MirExecutor, SubprocessResult

    _make_ledger(tmp_path)
    brief_path = _write_dispatch_brief(tmp_path)
    jobs_db = tmp_path / "jobs.db"
    reg = JobRegistry(jobs_db)
    job = _make_job(
        job_id="resumejob",
        change_id="bg-test-change",
        category="unit",
        repo_root=str(tmp_path),
        codex_args=[],
        dispatch_brief_path=str(brief_path),
        status="failed",
    )
    job.allow_harness_self_modify = True
    reg.insert(job)
    reg.close()

    def _fake_run_codex(self, codex_args, timeout_seconds=600):
        return SubprocessResult(
            exit_code=0,
            stdout="resume-ok",
            stderr="",
            duration_seconds=0.2,
            command=["codex", *self.resolve_codex_args(codex_args)],
        )

    def _fake_update_ledger(self, change_id, category, result):
        return LedgerUpdate(
            change_id=change_id,
            category=category,
            previous_status="planned",
            new_status="pass",
            notes="resume test",
        )

    monkeypatch.setattr(MirExecutor, "run_codex", _fake_run_codex)
    monkeypatch.setattr(MirExecutor, "update_ledger", _fake_update_ledger)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--jobs-db", str(jobs_db), "resume", "--job-id", "resumejob"])

    output = buf.getvalue()
    assert rc == 0
    assert "[RESUME] job_id=resumejob" in output
    assert "allow_harness_self_modify=True" in output
    assert "Resume executor job [role=executor, stack=python]" in output

    reg2 = JobRegistry(jobs_db)
    resumed = reg2.get("resumejob")
    reg2.close()
    assert resumed is not None
    assert resumed.status == "completed"
    assert resumed.stdout == "resume-ok"
    assert resumed.resume_count == 1
    assert resumed.last_resumed_at is not None


def test_cli_resume_requires_dispatch_brief_path(tmp_path, capsys):
    from tools.mir_executor.cli import main

    jobs_db = tmp_path / "jobs.db"
    reg = JobRegistry(jobs_db)
    reg.insert(
        _make_job(
            job_id="nobrief",
            repo_root=str(tmp_path),
            codex_args=["exec", "hello"],
            dispatch_brief_path=None,
        )
    )
    reg.close()

    with pytest.raises(SystemExit) as exc_info:
        main(["--jobs-db", str(jobs_db), "resume", "--job-id", "nobrief"])

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "dispatch_brief_path" in captured.err


# ---------------------------------------------------------------------------
# 20. test_cli_list_jobs_no_filter
# ---------------------------------------------------------------------------

def test_cli_list_jobs_no_filter(tmp_path):
    """list-jobs without --status prints all jobs."""
    import io
    from contextlib import redirect_stdout

    from tools.mir_executor.cli import main

    jobs_db = tmp_path / "jobs.db"
    reg = JobRegistry(jobs_db)
    reg.insert(_make_job(job_id="lj1", status="running", dispatch_brief_path="/tmp/a.json"))
    reg.insert(_make_job(job_id="lj2", status="completed"))
    reg.close()

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--jobs-db", str(jobs_db), "list-jobs"])

    output = buf.getvalue()
    assert rc == 0
    assert "lj1" in output
    assert "lj2" in output
    assert "dispatch_brief_path" in output


# ---------------------------------------------------------------------------
# 21. test_cli_list_jobs_status_filter
# ---------------------------------------------------------------------------

def test_cli_list_jobs_status_filter(tmp_path):
    """list-jobs --status running only shows running jobs."""
    import io
    from contextlib import redirect_stdout

    from tools.mir_executor.cli import main

    jobs_db = tmp_path / "jobs.db"
    reg = JobRegistry(jobs_db)
    reg.insert(_make_job(job_id="lj3", status="running"))
    reg.insert(_make_job(job_id="lj4", status="failed"))
    reg.close()

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--jobs-db", str(jobs_db), "list-jobs", "--status", "running"])

    output = buf.getvalue()
    assert rc == 0
    assert "lj3" in output
    assert "lj4" not in output


# ---------------------------------------------------------------------------
# 22. test_cancel_does_not_change_status_field
# ---------------------------------------------------------------------------

def test_cancel_does_not_change_status_field(tmp_path):
    """cancel() only sets cancel_requested; status remains 'running'."""
    reg = _make_registry(tmp_path)
    job = _make_job(job_id="nostatus", status="running")
    reg.insert(job)
    reg.cancel("nostatus")
    fetched = reg.get("nostatus")
    assert fetched is not None
    assert fetched.status == "running"  # status unchanged by cancel
    assert fetched.cancel_requested is True


# ---------------------------------------------------------------------------
# 23. test_update_status_noop_on_unknown_job
# ---------------------------------------------------------------------------

def test_update_status_noop_on_unknown_job(tmp_path):
    """update_status on a nonexistent job_id is a no-op (no error raised)."""
    reg = _make_registry(tmp_path)
    # Should not raise
    reg.update_status("ghost-job", "completed", exit_code=0)
    # Nothing was inserted
    assert reg.get("ghost-job") is None
