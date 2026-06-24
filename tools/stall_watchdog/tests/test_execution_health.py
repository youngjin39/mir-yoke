"""Tests for ADR-59 L2 unified execution-health monitor in scan.py."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.stall_watchdog.scan import scan_codex_events, scan_job_registry


def _write_events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _make_db(path: Path, jobs: list[dict]) -> None:
    """Create a minimal jobs.db with the given rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            change_id TEXT NOT NULL,
            category TEXT NOT NULL,
            family TEXT,
            repo_root TEXT NOT NULL DEFAULT '',
            codex_args TEXT NOT NULL DEFAULT '[]',
            dispatch_brief_path TEXT,
            resume_count INTEGER NOT NULL DEFAULT 0,
            last_resumed_at TEXT,
            timeout_seconds INTEGER NOT NULL,
            status TEXT NOT NULL,
            exit_code INTEGER,
            stdout TEXT,
            stderr TEXT,
            duration_seconds REAL,
            started_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0
        )"""
    )
    for job in jobs:
        conn.execute(
            "INSERT INTO jobs (job_id, change_id, category, repo_root, codex_args, "
            "timeout_seconds, status, started_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                job["job_id"],
                job["change_id"],
                job.get("category", "unit"),
                job.get("repo_root", "/tmp"),
                "[]",
                job["timeout_seconds"],
                job["status"],
                job["started_at"],
            ),
        )
    conn.commit()
    conn.close()


_NOW = datetime(2026, 6, 22, 10, 0, 0, tzinfo=UTC)


def test_hang_exit_142(tmp_path: Path):
    events_file = tmp_path / "events.jsonl"
    _write_events(
        events_file,
        [
            {
                "ts": "2026-06-22T09:58:00Z",
                "pid": 1,
                "exit_code": 142,
                "signal": None,
                "duration_s": 120.0,
                "error_sig": None,
            }
        ],
    )
    verdicts = scan_codex_events(events_file)
    hangs = [v for v in verdicts if v.verdict == "HANG"]
    assert len(hangs) == 1
    assert hangs[0].recommendation == "ESCALATE_HUMAN"
    assert hangs[0].source == "codex_events"


def test_hang_exit_124(tmp_path: Path):
    events_file = tmp_path / "events.jsonl"
    _write_events(
        events_file,
        [
            {
                "ts": "2026-06-22T09:58:00Z",
                "pid": 1,
                "exit_code": 124,
                "signal": None,
                "duration_s": 120.0,
                "error_sig": None,
            }
        ],
    )
    verdicts = scan_codex_events(events_file)
    hangs = [v for v in verdicts if v.verdict == "HANG"]
    assert len(hangs) == 1
    assert hangs[0].recommendation == "ESCALATE_HUMAN"
    assert hangs[0].source == "codex_events"


def test_hang_signal_sig14(tmp_path: Path):
    events_file = tmp_path / "events.jsonl"
    _write_events(
        events_file,
        [
            {
                "ts": "2026-06-22T09:58:00Z",
                "pid": 2,
                "exit_code": 0,
                "signal": "SIG14",
                "duration_s": 120.0,
                "error_sig": None,
            }
        ],
    )
    verdicts = scan_codex_events(events_file)
    hangs = [v for v in verdicts if v.verdict == "HANG"]
    assert len(hangs) == 1
    assert hangs[0].recommendation == "ESCALATE_HUMAN"


def test_spinning_same_error_sig_three_times(tmp_path: Path):
    sig = "aabbccddeeff"
    events_file = tmp_path / "events.jsonl"
    _write_events(
        events_file,
        [
            {
                "ts": "T1",
                "pid": 1,
                "exit_code": 1,
                "signal": None,
                "duration_s": 5.0,
                "error_sig": sig,
            },
            {
                "ts": "T2",
                "pid": 2,
                "exit_code": 1,
                "signal": None,
                "duration_s": 5.0,
                "error_sig": sig,
            },
            {
                "ts": "T3",
                "pid": 3,
                "exit_code": 1,
                "signal": None,
                "duration_s": 5.0,
                "error_sig": sig,
            },
        ],
    )
    verdicts = scan_codex_events(events_file)
    spinning = [v for v in verdicts if v.verdict == "SPINNING"]
    assert len(spinning) == 1
    assert spinning[0].recommendation == "ESCALATE_HUMAN"
    assert spinning[0].source == "codex_events"


def test_no_spinning_when_only_two(tmp_path: Path):
    sig = "aabbccddeeff"
    events_file = tmp_path / "events.jsonl"
    _write_events(
        events_file,
        [
            {
                "ts": "T1",
                "pid": 1,
                "exit_code": 1,
                "signal": None,
                "duration_s": 5.0,
                "error_sig": sig,
            },
            {
                "ts": "T2",
                "pid": 2,
                "exit_code": 1,
                "signal": None,
                "duration_s": 5.0,
                "error_sig": sig,
            },
        ],
    )
    verdicts = scan_codex_events(events_file)
    spinning = [v for v in verdicts if v.verdict == "SPINNING"]
    assert spinning == []


def test_duration_anomaly_spike(tmp_path: Path):
    events_file = tmp_path / "events.jsonl"
    _write_events(
        events_file,
        [
            {
                "ts": "T1",
                "pid": 1,
                "exit_code": 0,
                "signal": None,
                "duration_s": 60.0,
                "error_sig": None,
            },
            {
                "ts": "T2",
                "pid": 2,
                "exit_code": 0,
                "signal": None,
                "duration_s": 60.0,
                "error_sig": None,
            },
            {
                "ts": "T3",
                "pid": 3,
                "exit_code": 0,
                "signal": None,
                "duration_s": 300.0,
                "error_sig": None,
            },
        ],
    )
    verdicts = scan_codex_events(events_file)
    anomalies = [v for v in verdicts if v.verdict == "DURATION_ANOMALY"]
    assert len(anomalies) == 1
    assert anomalies[0].recommendation == "ESCALATE_HUMAN"


def test_no_duration_anomaly_normal(tmp_path: Path):
    events_file = tmp_path / "events.jsonl"
    _write_events(
        events_file,
        [
            {
                "ts": "T1",
                "pid": 1,
                "exit_code": 0,
                "signal": None,
                "duration_s": 60.0,
                "error_sig": None,
            },
            {
                "ts": "T2",
                "pid": 2,
                "exit_code": 0,
                "signal": None,
                "duration_s": 65.0,
                "error_sig": None,
            },
        ],
    )
    verdicts = scan_codex_events(events_file)
    anomalies = [v for v in verdicts if v.verdict == "DURATION_ANOMALY"]
    assert anomalies == []


def test_no_duration_anomaly_short_baseline(tmp_path: Path):
    events_file = tmp_path / "events.jsonl"
    _write_events(
        events_file,
        [
            {
                "ts": "T1",
                "pid": 1,
                "exit_code": 0,
                "signal": None,
                "duration_s": 5.0,
                "error_sig": None,
            },
            {
                "ts": "T2",
                "pid": 2,
                "exit_code": 0,
                "signal": None,
                "duration_s": 5.0,
                "error_sig": None,
            },
            {
                "ts": "T3",
                "pid": 3,
                "exit_code": 0,
                "signal": None,
                "duration_s": 9000.0,
                "error_sig": None,
            },
        ],
    )
    verdicts = scan_codex_events(events_file)
    anomalies = [v for v in verdicts if v.verdict == "DURATION_ANOMALY"]
    assert anomalies == []


def test_absent_events_file(tmp_path: Path):
    verdicts = scan_codex_events(tmp_path / "no-events.jsonl")
    assert verdicts == []


def test_job_registry_hang_past_timeout(tmp_path: Path):
    db = tmp_path / "jobs.db"
    started = (_NOW - timedelta(seconds=200)).isoformat()
    _make_db(
        db,
        [
            {
                "job_id": "j1",
                "change_id": "c1",
                "timeout_seconds": 120,
                "status": "running",
                "started_at": started,
            }
        ],
    )
    verdicts = scan_job_registry(db, _NOW)
    hangs = [v for v in verdicts if v.verdict == "HANG"]
    assert len(hangs) == 1
    assert hangs[0].source == "job_registry"
    assert hangs[0].recommendation == "ESCALATE_HUMAN"
    assert "j1" in hangs[0].detail


def test_job_registry_no_hang_within_timeout(tmp_path: Path):
    db = tmp_path / "jobs.db"
    started = (_NOW - timedelta(seconds=30)).isoformat()
    _make_db(
        db,
        [
            {
                "job_id": "j2",
                "change_id": "c2",
                "timeout_seconds": 120,
                "status": "running",
                "started_at": started,
            }
        ],
    )
    verdicts = scan_job_registry(db, _NOW)
    hangs = [v for v in verdicts if v.verdict == "HANG"]
    assert hangs == []


def test_job_registry_absent_db(tmp_path: Path):
    verdicts = scan_job_registry(tmp_path / "no.db", _NOW)
    assert verdicts == []
