"""ADR-06 Phase 6C-1: JSONL session ledger tail + significant entry detection.

Read-only tail of Claude Code JSONL session files. Tolerant of partial writes,
malformed lines, and missing fields. See ADR-06 §2.2.2 for the stall signature
model.

Top-level types observed in the 2026-05-11 mini-spike:

    assistant, user, attachment, last-prompt, permission-mode, queue-operation,
    system, ai-title, file-history-snapshot

Tool invocations are nested:
    assistant.message.content[].type == "tool_use"
    user.message.content[].type == "tool_result"

Top-level ``tool_use`` / ``toolUseResult`` types do not exist in this schema.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_LOG = logging.getLogger(__name__)

SIGNIFICANT_TOP_TYPES: frozenset[str] = frozenset({"assistant", "user"})

SKIPABLE_TOP_TYPES: frozenset[str] = frozenset(
    {
        "queue-operation",
        "system",
        "attachment",
        "last-prompt",
        "permission-mode",
        "ai-title",
        "file-history-snapshot",
    }
)


@dataclass(frozen=True)
class JsonlEntry:
    raw_index: int
    ts: datetime | None
    top_type: str
    nested_content_types: tuple[str, ...]
    session_id: str | None
    raw_text: str


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_nested_types(obj: dict) -> tuple[str, ...]:
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return ()
    content = msg.get("content")
    if not isinstance(content, list):
        return ()
    out: list[str] = []
    for c in content:
        if isinstance(c, dict):
            t = c.get("type")
            if isinstance(t, str):
                out.append(t)
    return tuple(out)


def tail_line_jsonl(path: Path, n: int = 20) -> list[JsonlEntry]:
    """Return the last ``n`` parseable JSONL entries from ``path``.

    Order is preserved (oldest in window first). Partial-write or malformed
    lines are skipped with a warn log; ``PermissionError`` / ``FileNotFoundError``
    / ``IsADirectoryError`` / ``UnicodeDecodeError`` yield an empty list. The
    function never raises on bad data.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, IsADirectoryError) as exc:
        _LOG.warning("tail_line_jsonl: cannot read %s: %s", path, exc)
        return []
    except UnicodeDecodeError as exc:
        _LOG.warning("tail_line_jsonl: unicode error %s: %s", path, exc)
        return []

    lines = text.splitlines()
    start = max(0, len(lines) - n)
    entries: list[JsonlEntry] = []
    for idx in range(start, len(lines)):
        line = lines[idx]
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            _LOG.warning(
                "tail_line_jsonl: skip malformed line %d in %s: %s",
                idx,
                path,
                exc.msg,
            )
            continue
        if not isinstance(obj, dict):
            continue
        top_type = obj.get("type")
        if not isinstance(top_type, str):
            top_type = "_unknown"
        session_id_value = obj.get("sessionId")
        entries.append(
            JsonlEntry(
                raw_index=idx,
                ts=_parse_ts(obj.get("timestamp")),
                top_type=top_type,
                nested_content_types=_extract_nested_types(obj),
                session_id=session_id_value
                if isinstance(session_id_value, str)
                else None,
                raw_text=line,
            )
        )
    return entries


def _is_significant(entry: JsonlEntry) -> bool:
    if entry.top_type not in SIGNIFICANT_TOP_TYPES:
        return False
    if entry.top_type == "assistant":
        return "tool_use" in entry.nested_content_types
    if entry.top_type == "user":
        return "tool_result" in entry.nested_content_types
    return False


def find_last_significant(entries: list[JsonlEntry]) -> JsonlEntry | None:
    """Return the most recent significant entry from ``entries``, or ``None``."""
    for entry in reversed(entries):
        if _is_significant(entry):
            return entry
    return None


def has_following_skipable_only(
    entries: list[JsonlEntry], pivot: JsonlEntry
) -> bool:
    """Return ``True`` if every entry after ``pivot`` is in ``SKIPABLE_TOP_TYPES``.

    No following entries at all (pivot is the last line) also returns ``True``.
    Used to distinguish "stalled mid-turn" (skipable-only or empty tail) from
    "session continued normally" (a later significant entry exists).
    """
    pivot_seen = False
    for entry in entries:
        if not pivot_seen:
            if entry.raw_index == pivot.raw_index:
                pivot_seen = True
            continue
        if entry.top_type not in SKIPABLE_TOP_TYPES:
            return False
    return True
