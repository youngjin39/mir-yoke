"""ADR-06 Phase 6C-3 unit tests — tools/stall_watchdog/discord_push.py."""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

from tools.stall_watchdog.discord_push import (
    StallAlarm,
    _redact_url,
    format_alarm_message,
    push_to_discord,
)


def _alarm(**overrides):
    base = dict(
        family="<example-family>",
        family_display=overrides.pop("display", "WriteScore"),
        workspace_encoded="-Volumes-T7-Shield-Project-05-Write-Score",
        session_uuid="abc-123",
        idle_seconds=240,
        last_entry_top_type="user",
        last_entry_nested_type="tool_result",
        last_entry_ts=datetime(2026, 5, 11, 3, 28, 40, tzinfo=UTC),
        jsonl_path=Path("/users/ai/.claude/projects/x/abc.jsonl"),
    )
    base.update(overrides)
    return StallAlarm(**base)


def test_format_alarm_message_contains_required_fields():
    msg = format_alarm_message(_alarm())
    assert "MIR-STALL-001" in msg
    assert "WriteScore" in msg
    assert "<example-family>" in msg
    assert "-Volumes-T7-Shield-Project-05-Write-Score" in msg
    assert "240s" in msg
    assert "user/tool_result" in msg
    assert "abc-123" in msg


def test_format_alarm_message_handles_unknown_ts():
    a = _alarm()
    a = StallAlarm(
        family=a.family,
        family_display=a.family_display,
        workspace_encoded=a.workspace_encoded,
        session_uuid=a.session_uuid,
        idle_seconds=a.idle_seconds,
        last_entry_top_type=a.last_entry_top_type,
        last_entry_nested_type=a.last_entry_nested_type,
        last_entry_ts=None,
        jsonl_path=a.jsonl_path,
    )
    msg = format_alarm_message(a)
    assert "unknown" in msg


def test_redact_url_hides_webhook_secret():
    redacted = _redact_url(
        "https://discord.com/api/webhooks/12345/somesecret-token"
    )
    assert "somesecret" not in redacted
    assert "<redacted>" in redacted


def test_redact_url_handles_non_webhook():
    assert _redact_url("https://example.com/") == "<webhook>"


class _StubResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def getcode(self):
        return self.status


class _StubHttp:
    def __init__(self, responses):
        # responses: list of (status_or_exception)
        self._responses = list(responses)
        self.calls = []

    def Request(self, url, data, headers, method):  # noqa: N802
        return ("REQ", url, data, headers, method)

    def urlopen(self, req, timeout):
        self.calls.append((req, timeout))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _StubResponse(item)


def test_push_returns_true_on_2xx():
    http = _StubHttp([204])
    result = push_to_discord(
        "https://discord.com/api/webhooks/x/y", _alarm(), http=http
    )
    assert result is True
    assert len(http.calls) == 1


def test_push_retry_on_5xx_then_success():
    http = _StubHttp([500, 204])
    result = push_to_discord(
        "https://discord.com/api/webhooks/x/y",
        _alarm(),
        retries=1,
        http=http,
        sleep=lambda s: None,
    )
    assert result is True
    assert len(http.calls) == 2


def test_push_returns_false_on_timeout_after_retries():
    http = _StubHttp([TimeoutError("slow"), TimeoutError("slow")])
    result = push_to_discord(
        "https://discord.com/api/webhooks/x/y",
        _alarm(),
        retries=1,
        http=http,
        sleep=lambda s: None,
    )
    assert result is False
    assert len(http.calls) == 2


def test_push_returns_false_on_url_error():
    http = _StubHttp([urllib.error.URLError("dns")])
    result = push_to_discord(
        "https://discord.com/api/webhooks/x/y",
        _alarm(),
        retries=0,
        http=http,
        sleep=lambda s: None,
    )
    assert result is False


def test_push_dry_run_when_url_empty():
    http = _StubHttp([])  # would raise if called
    result = push_to_discord("", _alarm(), http=http)
    assert result is False
    assert http.calls == []


def test_push_handles_non_2xx_after_retries():
    http = _StubHttp([500, 500])
    result = push_to_discord(
        "https://discord.com/api/webhooks/x/y",
        _alarm(),
        retries=1,
        http=http,
        sleep=lambda s: None,
    )
    assert result is False


def test_secret_not_logged_in_format_message():
    msg = format_alarm_message(_alarm())
    assert "discord.com" not in msg
    assert "webhook" not in msg.lower()


def test_korean_display_in_payload_utf8():
    a = _alarm(display="<example-family>")
    msg = format_alarm_message(a)
    # Confirm round-trip JSON encode preserves Korean
    payload = json.dumps({"content": msg}, ensure_ascii=False).encode("utf-8")
    decoded = payload.decode("utf-8")
    assert "<example-family>" in decoded


def test_request_body_is_utf8_json():
    captured = []

    class CaptureHttp:
        def Request(self, url, data, headers, method):  # noqa: N802
            captured.append({"url": url, "data": data, "headers": headers, "method": method})
            return "REQ"

        def urlopen(self, req, timeout):
            return _StubResponse(204)

    push_to_discord(
        "https://discord.com/api/webhooks/x/y",
        _alarm(display="<example-family>"),
        http=CaptureHttp(),
        retries=0,
    )
    body = captured[0]["data"].decode("utf-8")
    parsed = json.loads(body)
    assert "MIR-STALL-001" in parsed["content"]
    assert "<example-family>" in parsed["content"]
