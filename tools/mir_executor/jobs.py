"""
jobs.py
-------
sqlite-backed JobRegistry for your-harness Executor background jobs.

ADR: docs/decisions/p2-4-l4-background-jobs-2026-05-10.md §4.1–§4.2

Schema v1 (tasks/jobs.db):
    jobs(job_id, change_id, category, family, repo_root, codex_args, dispatch_brief_path,
         resume_count, last_resumed_at,
         timeout_seconds, status, exit_code, stdout, stderr,
         duration_seconds, started_at, completed_at, cancel_requested)

Thread safety: single sqlite3 connection with check_same_thread=False + threading.Lock
for serialized write access (reads are lock-free; sqlite supports concurrent reads).

BORROWED-FROM: codex-plugin-cc background job pattern (structure, not code).
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import threading
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class JobRecord:
    """Mirrors the jobs table row.

    Fields:
        job_id: UUID4 hex string (primary key).
        change_id: tdd.json change entry id.
        category: tdd.json category (unit / integration / …).
        family: family slug or None.
        repo_root: absolute path to repository root.
        codex_args: argument list passed to Codex CLI.
        dispatch_brief_path: persisted DispatchBrief JSON path, if present.
        resume_count: number of successful/attempted resume launches for this job row.
        last_resumed_at: last UTC timestamp when resume was requested.
        timeout_seconds: subprocess timeout.
        status: running / completed / cancelled / failed.
        exit_code: Codex exit code (None while running).
        stdout: captured stdout text (None while running).
        stderr: captured stderr text (None while running).
        duration_seconds: wall-clock seconds (None while running).
        started_at: ISO8601 UTC timestamp string.
        completed_at: ISO8601 UTC timestamp string or None.
        cancel_requested: True if cancel has been requested.
    """

    job_id: str
    change_id: str
    category: str
    family: str | None
    repo_root: str
    codex_args: list[str]
    timeout_seconds: int
    status: str  # running / completed / cancelled / failed
    dispatch_brief_path: str | None = None
    resume_count: int = 0
    last_resumed_at: str | None = None
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    duration_seconds: float | None = None
    started_at: str = ""
    completed_at: str | None = None
    cancel_requested: bool = False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class JobRegistry:
    """sqlite-backed job registry.

    All writes are serialized via a threading.Lock.
    Reads bypass the lock (default DELETE journal; Lock serializes writes within one process).

    Usage:
        registry = JobRegistry(pathlib.Path("tasks/jobs.db"))
        registry.insert(JobRecord(...))
        job = registry.get(job_id)
        registry.update_status(job_id, "completed", exit_code=0, ...)
        registry.cancel(job_id)
        jobs = registry.list_jobs(status_filter="running")
    """

    def __init__(self, db_path: pathlib.Path) -> None:
        """Open (or create) the sqlite database and ensure the schema exists."""
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """CREATE TABLE IF NOT EXISTS jobs + index — idempotent."""
        ddl = """
        CREATE TABLE IF NOT EXISTS jobs (
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
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        """
        with self._lock:
            with self._conn:
                self._conn.executescript(ddl)
                columns = {
                    row["name"]
                    for row in self._conn.execute("PRAGMA table_info(jobs)").fetchall()
                }
                if "dispatch_brief_path" not in columns:
                    self._conn.execute("ALTER TABLE jobs ADD COLUMN dispatch_brief_path TEXT")
                if "resume_count" not in columns:
                    self._conn.execute(
                        "ALTER TABLE jobs ADD COLUMN resume_count INTEGER NOT NULL DEFAULT 0"
                    )
                if "last_resumed_at" not in columns:
                    self._conn.execute("ALTER TABLE jobs ADD COLUMN last_resumed_at TEXT")

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def insert(self, job: JobRecord) -> None:
        """Insert a new JobRecord row.  Raises sqlite3.IntegrityError on duplicate job_id."""
        sql = """
        INSERT INTO jobs (
            job_id, change_id, category, family, repo_root, codex_args, dispatch_brief_path,
            resume_count, last_resumed_at, timeout_seconds, status, exit_code, stdout, stderr,
            duration_seconds, started_at, completed_at, cancel_requested
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        params = (
            job.job_id,
            job.change_id,
            job.category,
            job.family,
            job.repo_root,
            json.dumps(job.codex_args),
            job.dispatch_brief_path,
            job.resume_count,
            job.last_resumed_at,
            job.timeout_seconds,
            job.status,
            job.exit_code,
            job.stdout,
            job.stderr,
            job.duration_seconds,
            job.started_at,
            job.completed_at,
            1 if job.cancel_requested else 0,
        )
        with self._lock:
            with self._conn:
                self._conn.execute(sql, params)

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        exit_code: int | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        duration_seconds: float | None = None,
        completed_at: str | None = None,
    ) -> None:
        """UPDATE status + optional result fields for the given job_id.

        Only supplied (non-None) keyword args overwrite existing columns.
        If no row with job_id exists, this is a no-op (caller uses get() to verify).
        """
        sets = ["status = ?"]
        params: list = [status]

        if exit_code is not None:
            sets.append("exit_code = ?")
            params.append(exit_code)
        if stdout is not None:
            sets.append("stdout = ?")
            params.append(stdout)
        if stderr is not None:
            sets.append("stderr = ?")
            params.append(stderr)
        if duration_seconds is not None:
            sets.append("duration_seconds = ?")
            params.append(duration_seconds)
        if completed_at is not None:
            sets.append("completed_at = ?")
            params.append(completed_at)

        params.append(job_id)
        sql = f"UPDATE jobs SET {', '.join(sets)} WHERE job_id = ?"  # noqa: S608
        with self._lock:
            with self._conn:
                self._conn.execute(sql, params)

    def cancel(self, job_id: str) -> bool:
        """Set cancel_requested=1 for job_id.  Returns True if row was found, False otherwise."""
        sql = "UPDATE jobs SET cancel_requested = 1 WHERE job_id = ?"
        with self._lock:
            with self._conn:
                cur = self._conn.execute(sql, (job_id,))
                return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> JobRecord | None:
        """Return the JobRecord for job_id, or None if not found."""
        sql = "SELECT * FROM jobs WHERE job_id = ?"
        row = self._conn.execute(sql, (job_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_jobs(self, status_filter: str | None = None) -> list[JobRecord]:
        """Return all jobs, optionally filtered by status.

        Args:
            status_filter: one of running / completed / cancelled / failed, or None for all.
        """
        if status_filter is None:
            rows = self._conn.execute("SELECT * FROM jobs ORDER BY started_at DESC").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY started_at DESC", (status_filter,)
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JobRecord:
        """Convert a sqlite3.Row to a JobRecord."""
        return JobRecord(
            job_id=row["job_id"],
            change_id=row["change_id"],
            category=row["category"],
            family=row["family"],
            repo_root=row["repo_root"],
            codex_args=json.loads(row["codex_args"]),
            dispatch_brief_path=row["dispatch_brief_path"],
            resume_count=row["resume_count"],
            last_resumed_at=row["last_resumed_at"],
            timeout_seconds=row["timeout_seconds"],
            status=row["status"],
            exit_code=row["exit_code"],
            stdout=row["stdout"],
            stderr=row["stderr"],
            duration_seconds=row["duration_seconds"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            cancel_requested=bool(row["cancel_requested"]),
        )

    def mark_resumed(self, job_id: str, *, resumed_at: str) -> None:
        """Increment resume_count and stamp last_resumed_at for a resumed job."""
        sql = """
        UPDATE jobs
        SET resume_count = COALESCE(resume_count, 0) + 1,
            last_resumed_at = ?,
            status = 'running'
        WHERE job_id = ?
        """
        with self._lock:
            with self._conn:
                self._conn.execute(sql, (resumed_at, job_id))

    def close(self) -> None:
        """Close the underlying sqlite3 connection."""
        self._conn.close()
