"""ADR-06 Phase 6C-2 unit tests — tools/stall_watchdog/dedup.py."""

from __future__ import annotations

from datetime import datetime, timedelta

from tools.stall_watchdog.dedup import DedupLedger


def _now(seconds: int = 0) -> datetime:
    base = datetime(2026, 5, 11, 12, 0, 0)
    return base + timedelta(seconds=seconds)


def test_first_alarm_not_seen():
    led = DedupLedger(window_seconds=600)
    workspace = "-Volumes-T7-Shield-Project-05-Write-Score"
    assert led.already_alarmed("<example-family>", workspace, "uuid-1", _now()) is False


def test_mark_then_already_alarmed_within_window():
    led = DedupLedger(window_seconds=600)
    led.mark_alarmed("<example-family>", "ws-1", "uuid-1", _now(0))
    assert led.already_alarmed("<example-family>", "ws-1", "uuid-1", _now(300)) is True


def test_window_expires():
    led = DedupLedger(window_seconds=600)
    led.mark_alarmed("<example-family>", "ws-1", "uuid-1", _now(0))
    assert led.already_alarmed("<example-family>", "ws-1", "uuid-1", _now(601)) is False


def test_different_session_uuid_independent():
    led = DedupLedger()
    led.mark_alarmed("<example-family>", "ws-1", "uuid-1", _now(0))
    assert led.already_alarmed("<example-family>", "ws-1", "uuid-2", _now(60)) is False


def test_different_workspace_independent():
    """Multiple workspace dirs per family must produce independent alarms."""
    led = DedupLedger()
    legacy = "-Users-ai-agent-Flutter-Project-MineSweeper"
    current = "-Volumes-T7-Shield-Project-01-Flutter-03-MineSweeper"
    led.mark_alarmed("minesweeper", legacy, "uuid-1", _now(0))
    assert (
        led.already_alarmed("minesweeper", current, "uuid-1", _now(60)) is False
    )


def test_different_family_independent():
    led = DedupLedger()
    led.mark_alarmed("<example-family>", "ws-1", "uuid-1", _now(0))
    assert led.already_alarmed("your-harness", "ws-1", "uuid-1", _now(60)) is False


def test_gc_drops_old_entries():
    led = DedupLedger(window_seconds=600)
    led.mark_alarmed("<example-family>", "ws-1", "uuid-1", _now(0))
    led.mark_alarmed("<example-family>", "ws-1", "uuid-2", _now(2000))
    dropped = led.gc(_now(2000))
    assert dropped == 1
    assert led.size() == 1


def test_gc_keeps_recent_entries():
    led = DedupLedger(window_seconds=600)
    led.mark_alarmed("<example-family>", "ws-1", "uuid-1", _now(0))
    dropped = led.gc(_now(60))
    assert dropped == 0


def test_size_reflects_marks():
    led = DedupLedger()
    assert led.size() == 0
    led.mark_alarmed("a", "ws", "u1", _now(0))
    led.mark_alarmed("b", "ws", "u2", _now(0))
    assert led.size() == 2


def test_mark_overwrites_timestamp():
    led = DedupLedger(window_seconds=600)
    led.mark_alarmed("<example-family>", "ws-1", "uuid-1", _now(0))
    led.mark_alarmed("<example-family>", "ws-1", "uuid-1", _now(700))
    assert led.already_alarmed("<example-family>", "ws-1", "uuid-1", _now(1000)) is True
