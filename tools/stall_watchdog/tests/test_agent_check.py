import json
import os
from datetime import UTC, datetime, timedelta

import tools.stall_watchdog.cli as cli_mod
from tools.stall_watchdog.cli import main


def _make_entry(top, *, ts, content=None):
    obj = {"type": top, "timestamp": ts}
    if content is not None:
        obj["message"] = {"content": content}
    return json.dumps(obj)


def _write_session(pool, workspace, name, lines, mtime_offset=-30):
    ws = pool / workspace
    ws.mkdir(parents=True, exist_ok=True)
    jsonl = ws / f"{name}.jsonl"
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    now_ts = datetime.now(tz=UTC).timestamp()
    os.utime(jsonl, (now_ts + mtime_offset, now_ts + mtime_offset))


def test_agent_check_no_issues(tmp_path, capsys, monkeypatch):
    pool = tmp_path / "pool"
    pool.mkdir()
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.setenv("MIR_AGENT_CHECK_EVENTS_PATH", str(tmp_path / "no-events.jsonl"))
    monkeypatch.setenv("MIR_AGENT_CHECK_DB_PATH", str(tmp_path / "no.db"))
    monkeypatch.setenv("MIR_AGENT_CHECK_CHANGE_ID", "")
    rc = main(["agent-check"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== No issues found ===" in out


def test_agent_check_hang_verdict_in_table(tmp_path, capsys, monkeypatch):
    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        json.dumps(
            {
                "ts": "2026-06-22T09:58:00Z",
                "pid": 1,
                "exit_code": 142,
                "signal": None,
                "duration_s": 120.0,
                "error_sig": None,
            }
        )
        + "\n"
    )
    pool = tmp_path / "pool"
    pool.mkdir()
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.setenv("MIR_AGENT_CHECK_EVENTS_PATH", str(events_file))
    monkeypatch.setenv("MIR_AGENT_CHECK_DB_PATH", str(tmp_path / "no.db"))
    monkeypatch.setenv("MIR_AGENT_CHECK_CHANGE_ID", "")
    rc = main(["agent-check"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "HANG" in out
    assert "ESCALATE_HUMAN" in out


def test_agent_check_mcp_success_event_no_issues(tmp_path, capsys, monkeypatch):
    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        json.dumps(
            {
                "ts": "2026-07-02T09:58:00Z",
                "exit_code": 0,
                "duration_s": 9000.0,
                "error_sig": "",
                "transport": "mcp",
                "threadId": "thread-abc",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pool = tmp_path / "pool"
    pool.mkdir()
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.setenv("MIR_AGENT_CHECK_EVENTS_PATH", str(events_file))
    monkeypatch.setenv("MIR_AGENT_CHECK_DB_PATH", str(tmp_path / "no.db"))
    monkeypatch.setenv("MIR_AGENT_CHECK_CHANGE_ID", "")

    rc = main(["agent-check"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "=== No issues found ===" in out
    assert "HANG" not in out
    assert "DURATION_ANOMALY" not in out


def test_agent_check_mcp_failed_event_no_false_hang(tmp_path, capsys, monkeypatch):
    events_file = tmp_path / "events.jsonl"
    events_file.write_text(
        json.dumps(
            {
                "ts": "2026-07-02T09:58:00Z",
                "exit_code": 124,
                "signal": None,
                "duration_s": 120.0,
                "error_sig": "timeout-sig",
                "transport": "mcp",
                "threadId": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pool = tmp_path / "pool"
    pool.mkdir()
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.setenv("MIR_AGENT_CHECK_EVENTS_PATH", str(events_file))
    monkeypatch.setenv("MIR_AGENT_CHECK_DB_PATH", str(tmp_path / "no.db"))
    monkeypatch.setenv("MIR_AGENT_CHECK_CHANGE_ID", "")

    rc = main(["agent-check"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "=== No issues found ===" in out
    assert "HANG" not in out
    assert "DURATION_ANOMALY" not in out


def test_agent_check_stall_in_table(tmp_path, capsys, monkeypatch):
    pool = tmp_path / "pool"
    now = datetime.now(tz=UTC)
    _write_session(
        pool,
        "-Volumes-T7-Shield-Project-05-Write-Score",
        "abc",
        [
            _make_entry(
                "assistant",
                ts=(now - timedelta(seconds=400)).isoformat().replace("+00:00", "Z"),
                content=[{"type": "tool_use"}],
            ),
            _make_entry(
                "queue-operation",
                ts=(now - timedelta(seconds=200)).isoformat().replace("+00:00", "Z"),
            ),
        ],
        mtime_offset=-30,
    )
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.setenv("MIR_STALL_WATCHDOG_THRESHOLD_SECONDS", "180")
    monkeypatch.setenv("MIR_STALL_WATCHDOG_RECENT_K_MINUTES", "60")
    monkeypatch.setenv("MIR_AGENT_CHECK_EVENTS_PATH", str(tmp_path / "no-events.jsonl"))
    monkeypatch.setenv("MIR_AGENT_CHECK_DB_PATH", str(tmp_path / "no.db"))
    monkeypatch.setenv("MIR_AGENT_CHECK_CHANGE_ID", "")
    rc = main(["agent-check"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "STALL" in out
    assert "<example-family>" in out


def test_agent_check_dedup_suppresses_repeat_push(tmp_path, capsys, monkeypatch):
    pool = tmp_path / "pool"
    now = datetime.now(tz=UTC)
    _write_session(
        pool,
        "-Volumes-T7-Shield-Project-05-Write-Score",
        "stall-sess",
        [
            _make_entry(
                "assistant",
                ts=(now - timedelta(seconds=400)).isoformat().replace("+00:00", "Z"),
                content=[{"type": "tool_use"}],
            ),
        ],
        mtime_offset=-30,
    )
    monkeypatch.setenv("MIR_STALL_WATCHDOG_POOL_ROOT", str(pool))
    monkeypatch.setenv("MIR_STALL_WATCHDOG_THRESHOLD_SECONDS", "180")
    monkeypatch.setenv("MIR_STALL_WATCHDOG_RECENT_K_MINUTES", "60")
    monkeypatch.setenv(
        "MIR_STALL_WATCHDOG_WEBHOOK_WRITE_SCORE", "https://discord.example/webhook"
    )
    monkeypatch.setenv("MIR_AGENT_CHECK_EVENTS_PATH", str(tmp_path / "no-events.jsonl"))
    monkeypatch.setenv("MIR_AGENT_CHECK_DB_PATH", str(tmp_path / "no.db"))
    monkeypatch.setenv("MIR_AGENT_CHECK_CHANGE_ID", "")
    calls = []

    def fake_push(url, alarm, **kwargs):
        calls.append((url, alarm.family))
        return True

    monkeypatch.setattr(cli_mod, "push_to_discord", fake_push)
    rc1 = main(["agent-check", "--push"])
    assert rc1 == 0
    first_count = len(calls)
    # second call: monkeypatch DedupLedger.already_alarmed to always return True
    from tools.stall_watchdog import dedup as dedup_mod

    original_already = dedup_mod.DedupLedger.already_alarmed
    dedup_mod.DedupLedger.already_alarmed = lambda self, *a, **kw: True
    try:
        rc2 = main(["agent-check", "--push"])
        assert rc2 == 0
    finally:
        dedup_mod.DedupLedger.already_alarmed = original_already
    assert first_count == 1
    assert len(calls) == 1  # dedup suppressed second push
