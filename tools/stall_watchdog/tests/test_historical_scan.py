"""ADR-06 Phase 6F unit tests — tools/stall_watchdog/historical_scan.py."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.stall_watchdog.historical_scan import historical_scan, main


def _make_entry(top, *, ts, content=None):
    obj = {"type": top, "timestamp": ts}
    if content is not None:
        obj["message"] = {"content": content}
    return json.dumps(obj)


def _write_session(pool: Path, workspace: str, name: str, lines, mtime_offset_sec: int = -30):
    ws = pool / workspace
    ws.mkdir(parents=True, exist_ok=True)
    jsonl = ws / f"{name}.jsonl"
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    now_ts = datetime.now(tz=UTC).timestamp()
    os.utime(jsonl, (now_ts + mtime_offset_sec, now_ts + mtime_offset_sec))


_NOW = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)


def _ts(offset: int) -> str:
    return (_NOW + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")


def test_empty_pool_returns_zero_stalls(tmp_path: Path):
    pool = tmp_path / "pool"
    pool.mkdir()
    report = historical_scan(pool, lookback_days=14, now=_NOW)
    assert report["total_stall"] == 0
    assert report["total_sessions_scanned"] == 0


def test_one_stall_per_family(tmp_path: Path, monkeypatch):
    pool = tmp_path / "pool"
    _write_session(
        pool,
        "-Volumes-T7-Shield-Project-05-Write-Score",
        "a",
        [
            _make_entry(
                "assistant",
                ts=_ts(-400),
                content=[{"type": "tool_use"}],
            ),
        ],
    )
    _write_session(
        pool,
        "-Volumes-T7-Shield-Project-09-Mini-Harness",
        "b",
        [
            _make_entry(
                "assistant",
                ts=_ts(-400),
                content=[{"type": "tool_use"}],
            ),
        ],
    )
    mapping = {
        "-Volumes-T7-Shield-Project-05-Write-Score": "<example-family>",
        "-Volumes-T7-Shield-Project-09-Mini-Harness": "your-harness",
    }
    report = historical_scan(
        pool, lookback_days=14, now=_NOW, workspace_to_family=mapping
    )
    assert report["total_stall"] == 2
    assert report["stall_counts"]["<example-family>"] == 1
    assert report["stall_counts"]["your-harness"] == 1


def test_cli_emits_json(tmp_path: Path, capsys, monkeypatch):
    pool = tmp_path / "pool"
    pool.mkdir()
    rc = main(["--pool-root", str(pool), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["incident_code"] == "MIR-STALL-001"
    assert payload["pattern_code"] == "STALL-IDLE-AFTER-TOOLUSE"


def test_cli_default_human_output(tmp_path: Path, capsys, monkeypatch):
    pool = tmp_path / "pool"
    pool.mkdir()
    rc = main(["--pool-root", str(pool)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "total stalls: 0" in out
