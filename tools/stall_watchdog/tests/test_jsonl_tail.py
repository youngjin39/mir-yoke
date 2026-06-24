"""ADR-06 Phase 6C-1 unit tests — tools/stall_watchdog/jsonl_tail.py."""

from __future__ import annotations

import json
from pathlib import Path

from tools.stall_watchdog.jsonl_tail import (
    SIGNIFICANT_TOP_TYPES,
    SKIPABLE_TOP_TYPES,
    JsonlEntry,
    find_last_significant,
    has_following_skipable_only,
    tail_line_jsonl,
)


def _make_entry(top, *, ts="2026-05-11T01:00:00Z", session="s1", content=None):
    obj = {"type": top, "timestamp": ts, "sessionId": session}
    if content is not None:
        obj["message"] = {"content": content}
    return json.dumps(obj)


def test_happy_path_five_entries(tmp_path: Path):
    p = tmp_path / "session.jsonl"
    lines = [
        _make_entry("system"),
        _make_entry("user", content=[{"type": "text"}]),
        _make_entry("assistant", content=[{"type": "text"}]),
        _make_entry("assistant", content=[{"type": "tool_use", "id": "t1"}]),
        _make_entry("user", content=[{"type": "tool_result", "tool_use_id": "t1"}]),
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    entries = tail_line_jsonl(p, n=10)
    assert len(entries) == 5
    assert entries[0].top_type == "system"
    assert entries[-1].top_type == "user"
    assert "tool_result" in entries[-1].nested_content_types


def test_partial_write_last_line_skipped(tmp_path: Path):
    p = tmp_path / "session.jsonl"
    good = _make_entry("assistant", content=[{"type": "tool_use"}])
    partial = good[: len(good) // 2]
    p.write_text(good + "\n" + partial + "\n", encoding="utf-8")
    entries = tail_line_jsonl(p, n=10)
    assert len(entries) == 1
    assert entries[0].top_type == "assistant"


def test_empty_file_returns_empty(tmp_path: Path):
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")
    assert tail_line_jsonl(p, n=5) == []


def test_missing_file_returns_empty(tmp_path: Path):
    p = tmp_path / "does-not-exist.jsonl"
    assert tail_line_jsonl(p, n=5) == []


def test_n_limits_returned_entries(tmp_path: Path):
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join([_make_entry("system")] * 50) + "\n", encoding="utf-8")
    entries = tail_line_jsonl(p, n=5)
    assert len(entries) == 5


def test_find_last_significant_assistant_tool_use(tmp_path: Path):
    p = tmp_path / "session.jsonl"
    lines = [
        _make_entry("system"),
        _make_entry("assistant", content=[{"type": "tool_use"}]),
        _make_entry("queue-operation"),
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    entries = tail_line_jsonl(p, n=10)
    sig = find_last_significant(entries)
    assert sig is not None
    assert sig.top_type == "assistant"


def test_find_last_significant_user_tool_result(tmp_path: Path):
    p = tmp_path / "session.jsonl"
    lines = [
        _make_entry("assistant", content=[{"type": "tool_use"}]),
        _make_entry("user", content=[{"type": "tool_result"}]),
        _make_entry("attachment"),
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    entries = tail_line_jsonl(p, n=10)
    sig = find_last_significant(entries)
    assert sig is not None
    assert sig.top_type == "user"
    assert "tool_result" in sig.nested_content_types


def test_find_last_significant_none_when_only_skipable():
    entries = [
        JsonlEntry(0, None, "system", (), None, ""),
        JsonlEntry(1, None, "queue-operation", (), None, ""),
    ]
    assert find_last_significant(entries) is None


def test_find_last_significant_skips_assistant_text_only():
    entries = [JsonlEntry(0, None, "assistant", ("text",), None, "")]
    assert find_last_significant(entries) is None


def test_has_following_skipable_only_pivot_is_last():
    pivot = JsonlEntry(5, None, "user", ("tool_result",), None, "")
    entries = [JsonlEntry(0, None, "system", (), None, ""), pivot]
    assert has_following_skipable_only(entries, pivot) is True


def test_has_following_skipable_only_with_skipable_tail():
    pivot = JsonlEntry(0, None, "user", ("tool_result",), None, "")
    entries = [
        pivot,
        JsonlEntry(1, None, "queue-operation", (), None, ""),
        JsonlEntry(2, None, "attachment", (), None, ""),
    ]
    assert has_following_skipable_only(entries, pivot) is True


def test_has_following_skipable_only_breaks_on_significant():
    pivot = JsonlEntry(0, None, "assistant", ("tool_use",), None, "")
    entries = [
        pivot,
        JsonlEntry(1, None, "user", ("tool_result",), None, ""),
    ]
    assert has_following_skipable_only(entries, pivot) is False


def test_malformed_line_does_not_escape(tmp_path: Path):
    p = tmp_path / "bad.jsonl"
    good = _make_entry("system")
    p.write_text(good + "\n{not-json}\n" + good + "\n", encoding="utf-8")
    entries = tail_line_jsonl(p, n=10)
    assert len(entries) == 2


def test_top_level_array_skipped(tmp_path: Path):
    p = tmp_path / "array.jsonl"
    p.write_text("[1,2,3]\n" + _make_entry("system") + "\n", encoding="utf-8")
    entries = tail_line_jsonl(p, n=10)
    assert len(entries) == 1
    assert entries[0].top_type == "system"


def test_korean_directory_path(tmp_path: Path):
    # Sub-agent 2 verified Korean Path handling via pathlib. Use unicode escapes
    # so this source file stays byte-stable across heredocs.
    sub = tmp_path / "hangul-directory"
    sub.mkdir()
    p = sub / "session.jsonl"
    p.write_text(
        _make_entry("assistant", content=[{"type": "tool_use"}]) + "\n",
        encoding="utf-8",
    )
    entries = tail_line_jsonl(p, n=5)
    assert len(entries) == 1
    assert entries[0].top_type == "assistant"


def test_significant_types_constants():
    assert "assistant" in SIGNIFICANT_TOP_TYPES
    assert "user" in SIGNIFICANT_TOP_TYPES
    assert "queue-operation" in SKIPABLE_TOP_TYPES
    assert "permission-mode" in SKIPABLE_TOP_TYPES
    assert "file-history-snapshot" in SKIPABLE_TOP_TYPES


def test_assistant_text_only_not_significant(tmp_path: Path):
    p = tmp_path / "session.jsonl"
    p.write_text(
        _make_entry("assistant", content=[{"type": "text"}]) + "\n",
        encoding="utf-8",
    )
    entries = tail_line_jsonl(p, n=10)
    assert find_last_significant(entries) is None


def test_permission_error_returns_empty(tmp_path: Path):
    p = tmp_path / "protected.jsonl"
    p.write_text(_make_entry("system") + "\n", encoding="utf-8")
    p.chmod(0o000)
    try:
        result = tail_line_jsonl(p, n=5)
    finally:
        p.chmod(0o644)
    assert result == []
