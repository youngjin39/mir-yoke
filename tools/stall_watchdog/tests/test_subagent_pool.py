"""ADR-59 Phase-1 Step 4: sub-agent transcript pool coverage tests."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.stall_watchdog.scan import ScanConfig, scan_subagent_pool

_NOW = datetime(2026, 6, 22, 10, 0, 0, tzinfo=UTC)


def _ts(offset_sec: int) -> str:
    return (_NOW + timedelta(seconds=offset_sec)).isoformat().replace("+00:00", "Z")


def _make_entry(top, *, ts, content=None):
    obj = {"type": top, "timestamp": ts}
    if content is not None:
        obj["message"] = {"content": content}
    return json.dumps(obj)


def _write_output(path: Path, lines: list[str], mtime: datetime | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if mtime is not None:
        ts = mtime.timestamp()
        os.utime(path, (ts, ts))


def test_subagent_stall_detected(tmp_path: Path):
    """A sub-agent .output file with a stall tail yields is_stall=True."""
    tmp_root = tmp_path / "claude-fake"
    workspace = tmp_root / "-Volumes-T7-Shield-Project-05-Write-Score"
    session = workspace / "sess-abc-def"
    output_file = session / "tasks" / "agent0001.output"

    lines = [
        _make_entry("system", ts=_ts(-400)),
        _make_entry(
            "assistant",
            ts=_ts(-300),
            content=[{"type": "tool_use", "id": "t1"}],
        ),
        _make_entry("queue-operation", ts=_ts(-50)),
    ]
    _write_output(output_file, lines, mtime=_NOW - timedelta(seconds=50))

    config = ScanConfig(pool_root=tmp_path / "unused", threshold_seconds=180)
    verdicts = scan_subagent_pool(
        config,
        _NOW,
        {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"},
        tmp_root=tmp_root,
    )
    stalls = [v for v in verdicts if v.is_stall]
    assert len(stalls) == 1
    assert stalls[0].family_slug == "<example-family>"
    assert stalls[0].jsonl_path == output_file
    assert "agent0001" in stalls[0].session_uuid
    assert stalls[0].idle_seconds >= 180


def test_subagent_no_stall_below_threshold(tmp_path: Path):
    """A sub-agent file with a recent tool_use is below threshold."""
    tmp_root = tmp_path / "claude-fake"
    workspace = tmp_root / "-Volumes-T7-Shield-Project-09-Mini-Harness"
    session = workspace / "sess-xyz"
    output_file = session / "tasks" / "agent0002.output"

    lines = [
        _make_entry(
            "assistant",
            ts=_ts(-60),
            content=[{"type": "tool_use"}],
        ),
    ]
    _write_output(output_file, lines, mtime=_NOW - timedelta(seconds=60))

    config = ScanConfig(pool_root=tmp_path / "unused", threshold_seconds=180)
    verdicts = scan_subagent_pool(
        config,
        _NOW,
        {"-Volumes-T7-Shield-Project-09-Mini-Harness": "your-harness"},
        tmp_root=tmp_root,
    )
    assert len(verdicts) == 1
    assert verdicts[0].is_stall is False
    assert verdicts[0].skip_reason == "below_threshold"


def test_subagent_absent_tmp_root_returns_empty(tmp_path: Path):
    """Absent tmp_root is tolerated and returns empty list."""
    config = ScanConfig(pool_root=tmp_path / "unused", threshold_seconds=180)
    verdicts = scan_subagent_pool(
        config,
        _NOW,
        {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"},
        tmp_root=tmp_path / "does-not-exist",
    )
    assert verdicts == []


def test_subagent_unmapped_workspace_skipped(tmp_path: Path):
    """Unmapped workspace directories are silently skipped."""
    tmp_root = tmp_path / "claude-fake"
    workspace = tmp_root / "-some-unknown-workspace"
    session = workspace / "sess-abc"
    output_file = session / "tasks" / "agentX.output"
    lines = [
        _make_entry(
            "assistant",
            ts=_ts(-1000),
            content=[{"type": "tool_use"}],
        ),
    ]
    _write_output(output_file, lines, mtime=_NOW - timedelta(seconds=30))

    config = ScanConfig(pool_root=tmp_path / "unused", threshold_seconds=180)
    verdicts = scan_subagent_pool(config, _NOW, {}, tmp_root=tmp_root)
    assert verdicts == []


def test_subagent_stale_output_skipped_by_mtime(tmp_path: Path):
    """Output files older than recent_k_minutes are skipped."""
    tmp_root = tmp_path / "claude-fake"
    workspace = tmp_root / "-Volumes-T7-Shield-Project-05-Write-Score"
    session = workspace / "sess-old"
    output_file = session / "tasks" / "agent_old.output"
    lines = [
        _make_entry(
            "assistant",
            ts=_ts(-7200),
            content=[{"type": "tool_use"}],
        ),
    ]
    _write_output(output_file, lines, mtime=_NOW - timedelta(seconds=7200))

    config = ScanConfig(
        pool_root=tmp_path / "unused",
        threshold_seconds=180,
        recent_k_minutes=60,
    )
    verdicts = scan_subagent_pool(
        config,
        _NOW,
        {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"},
        tmp_root=tmp_root,
    )
    assert verdicts == []
