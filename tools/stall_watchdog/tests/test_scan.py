"""ADR-06 Phase 6C-4 unit tests — tools/stall_watchdog/scan.py."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.stall_watchdog.scan import ScanConfig, scan_pool


def _make_entry(top, *, ts, content=None, session_id="s1"):
    obj = {"type": top, "timestamp": ts, "sessionId": session_id}
    if content is not None:
        obj["message"] = {"content": content}
    return json.dumps(obj)


def _write_jsonl(path: Path, lines: list[str], mtime: datetime | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if mtime is not None:
        ts = mtime.timestamp()
        os.utime(path, (ts, ts))


_NOW = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)
_NOW_ISO = _NOW.isoformat().replace("+00:00", "Z")


def _ts(offset_sec: int) -> str:
    return (_NOW + timedelta(seconds=offset_sec)).isoformat().replace("+00:00", "Z")


def test_stall_detected_assistant_tool_use(tmp_path: Path):
    pool = tmp_path / "pool"
    ws = pool / "-Volumes-T7-Shield-Project-05-Write-Score"
    jsonl = ws / "abc.jsonl"
    lines = [
        _make_entry("system", ts=_ts(-400)),
        _make_entry(
            "assistant",
            ts=_ts(-300),
            content=[{"type": "tool_use", "id": "t1"}],
        ),
        _make_entry("queue-operation", ts=_ts(-50)),
    ]
    _write_jsonl(jsonl, lines, mtime=_NOW - timedelta(seconds=50))

    config = ScanConfig(pool_root=pool, threshold_seconds=180)
    verdicts = scan_pool(
        config, _NOW, {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"}
    )
    stall = [v for v in verdicts if v.is_stall]
    assert len(stall) == 1
    assert stall[0].family_slug == "<example-family>"
    assert stall[0].session_uuid == "abc"
    assert stall[0].idle_seconds >= 180


def test_no_stall_when_session_continued(tmp_path: Path):
    """Next-turn assistant-text after tool_result = session_continued (not stall)."""
    pool = tmp_path / "pool"
    ws = pool / "-Volumes-T7-Shield-Project-05-Write-Score"
    jsonl = ws / "ok.jsonl"
    lines = [
        _make_entry(
            "assistant",
            ts=_ts(-300),
            content=[{"type": "tool_use"}],
        ),
        _make_entry(
            "user",
            ts=_ts(-250),
            content=[{"type": "tool_result"}],
        ),
        _make_entry(
            "assistant",
            ts=_ts(-100),
            content=[{"type": "text"}],
        ),
    ]
    _write_jsonl(jsonl, lines, mtime=_NOW - timedelta(seconds=100))

    config = ScanConfig(pool_root=pool, threshold_seconds=180)
    verdicts = scan_pool(
        config, _NOW, {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"}
    )
    assert len(verdicts) == 1
    assert verdicts[0].is_stall is False
    assert verdicts[0].skip_reason == "session_continued"


def test_no_stall_when_below_threshold(tmp_path: Path):
    pool = tmp_path / "pool"
    ws = pool / "-Volumes-T7-Shield-Project-05-Write-Score"
    jsonl = ws / "soon.jsonl"
    lines = [
        _make_entry(
            "assistant",
            ts=_ts(-60),
            content=[{"type": "tool_use"}],
        ),
    ]
    _write_jsonl(jsonl, lines, mtime=_NOW - timedelta(seconds=60))

    config = ScanConfig(pool_root=pool, threshold_seconds=180)
    verdicts = scan_pool(
        config, _NOW, {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"}
    )
    assert all(not v.is_stall for v in verdicts)
    assert verdicts[0].skip_reason == "below_threshold"


def test_unmapped_workspace_silent_skip(tmp_path: Path):
    pool = tmp_path / "pool"
    ws = pool / "-some-unmapped-workspace"
    jsonl = ws / "x.jsonl"
    lines = [
        _make_entry(
            "assistant",
            ts=_ts(-1000),
            content=[{"type": "tool_use"}],
        ),
    ]
    _write_jsonl(jsonl, lines, mtime=_NOW - timedelta(seconds=10))

    config = ScanConfig(pool_root=pool, threshold_seconds=180)
    verdicts = scan_pool(config, _NOW, {})
    assert verdicts == []


def test_stale_session_skipped_by_mtime(tmp_path: Path):
    pool = tmp_path / "pool"
    ws = pool / "-Volumes-T7-Shield-Project-09-Mini-Harness"
    jsonl = ws / "old.jsonl"
    lines = [
        _make_entry(
            "assistant",
            ts=_ts(-7200),
            content=[{"type": "tool_use"}],
        ),
    ]
    _write_jsonl(jsonl, lines, mtime=_NOW - timedelta(seconds=7200))  # 2h old

    config = ScanConfig(pool_root=pool, threshold_seconds=180, recent_k_minutes=60)
    verdicts = scan_pool(
        config,
        _NOW,
        {"-Volumes-T7-Shield-Project-09-Mini-Harness": "your-harness"},
    )
    assert verdicts == []


def test_no_significant_entry(tmp_path: Path):
    pool = tmp_path / "pool"
    ws = pool / "-Volumes-T7-Shield-Project-05-Write-Score"
    jsonl = ws / "noisy.jsonl"
    lines = [
        _make_entry("system", ts=_ts(-50)),
        _make_entry("queue-operation", ts=_ts(-30)),
        _make_entry("attachment", ts=_ts(-10)),
    ]
    _write_jsonl(jsonl, lines, mtime=_NOW - timedelta(seconds=10))

    config = ScanConfig(pool_root=pool, threshold_seconds=180)
    verdicts = scan_pool(
        config, _NOW, {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"}
    )
    assert len(verdicts) == 1
    assert verdicts[0].is_stall is False
    assert verdicts[0].skip_reason == "no_significant_entry"


def test_empty_jsonl_emits_skip(tmp_path: Path):
    pool = tmp_path / "pool"
    ws = pool / "-Volumes-T7-Shield-Project-05-Write-Score"
    jsonl = ws / "empty.jsonl"
    ws.mkdir(parents=True, exist_ok=True)
    jsonl.write_text("", encoding="utf-8")
    os.utime(jsonl, (_NOW.timestamp() - 10, _NOW.timestamp() - 10))

    config = ScanConfig(pool_root=pool, threshold_seconds=180)
    verdicts = scan_pool(
        config, _NOW, {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"}
    )
    assert len(verdicts) == 1
    assert verdicts[0].skip_reason == "no_entries"


def test_missing_pool_root_empty(tmp_path: Path):
    config = ScanConfig(pool_root=tmp_path / "does-not-exist", threshold_seconds=180)
    verdicts = scan_pool(config, _NOW, {})
    assert verdicts == []


def test_two_families_two_workspaces(tmp_path: Path):
    """Pool with two mapped workspaces — verdicts emitted per workspace."""
    pool = tmp_path / "pool"

    ws1 = pool / "-Volumes-T7-Shield-Project-05-Write-Score"
    _write_jsonl(
        ws1 / "a.jsonl",
        [
            _make_entry(
                "assistant",
                ts=_ts(-400),
                content=[{"type": "tool_use"}],
            ),
        ],
        mtime=_NOW - timedelta(seconds=30),
    )

    ws2 = pool / "-Volumes-T7-Shield-Project-09-Mini-Harness"
    _write_jsonl(
        ws2 / "b.jsonl",
        [
            _make_entry(
                "user",
                ts=_ts(-500),
                content=[{"type": "tool_result"}],
            ),
        ],
        mtime=_NOW - timedelta(seconds=30),
    )

    config = ScanConfig(pool_root=pool, threshold_seconds=180)
    mapping = {
        "-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>",
        "-Volumes-T7-Shield-Project-09-Mini-Harness": "your-harness",
    }
    verdicts = scan_pool(config, _NOW, mapping)
    families = sorted({v.family_slug for v in verdicts if v.is_stall})
    assert families == ["<example-family>", "your-harness"]


def test_partial_write_does_not_break_scan(tmp_path: Path):
    pool = tmp_path / "pool"
    ws = pool / "-Volumes-T7-Shield-Project-05-Write-Score"
    ws.mkdir(parents=True)
    jsonl = ws / "p.jsonl"
    good = _make_entry(
        "assistant", ts=_ts(-300), content=[{"type": "tool_use"}]
    )
    jsonl.write_text(good + "\n{partial\n", encoding="utf-8")
    os.utime(jsonl, (_NOW.timestamp() - 30, _NOW.timestamp() - 30))

    config = ScanConfig(pool_root=pool, threshold_seconds=180)
    verdicts = scan_pool(
        config, _NOW, {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"}
    )
    assert len(verdicts) == 1
    assert verdicts[0].is_stall is True


def test_now_naive_datetime_treated_as_utc(tmp_path: Path):
    pool = tmp_path / "pool"
    ws = pool / "-Volumes-T7-Shield-Project-05-Write-Score"
    jsonl = ws / "naive.jsonl"
    lines = [
        _make_entry(
            "assistant",
            ts=_ts(-400),
            content=[{"type": "tool_use"}],
        ),
    ]
    _write_jsonl(jsonl, lines, mtime=_NOW - timedelta(seconds=30))

    naive_now = _NOW.replace(tzinfo=None)
    config = ScanConfig(pool_root=pool, threshold_seconds=180)
    verdicts = scan_pool(
        config,
        naive_now,
        {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"},
    )
    stalls = [v for v in verdicts if v.is_stall]
    assert len(stalls) == 1


def test_session_uuid_from_filename(tmp_path: Path):
    pool = tmp_path / "pool"
    ws = pool / "-Volumes-T7-Shield-Project-05-Write-Score"
    jsonl = ws / "16f9c712-d4c4-4e94-8fdc-e91565f2b950.jsonl"
    lines = [
        _make_entry(
            "assistant",
            ts=_ts(-400),
            content=[{"type": "tool_use"}],
        ),
    ]
    _write_jsonl(jsonl, lines, mtime=_NOW - timedelta(seconds=30))

    config = ScanConfig(pool_root=pool, threshold_seconds=180)
    verdicts = scan_pool(
        config, _NOW, {"-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>"}
    )
    assert verdicts[0].session_uuid == "16f9c712-d4c4-4e94-8fdc-e91565f2b950"
