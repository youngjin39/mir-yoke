"""ADR-06 Phase 6C-3: Discord webhook push with retry + tolerant fallback.

The webhook URL is supplied per call (no global state); callers resolve it from
``MIR_STALL_WATCHDOG_WEBHOOK_<FAMILY_SLUG_UPPER>`` or
``MIR_STALL_WATCHDOG_WEBHOOK_DEFAULT`` and fall back to dry-run when neither is
set. ``push_to_discord`` never raises; all transport errors result in a False
return + warn log. URLs are never logged in plaintext.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

_LOG = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10
_RETRY_BACKOFF_SECONDS = 2


@dataclass(frozen=True)
class StallAlarm:
    family: str
    family_display: str
    workspace_encoded: str
    session_uuid: str
    idle_seconds: int
    last_entry_top_type: str
    last_entry_nested_type: str
    last_entry_ts: datetime | None
    jsonl_path: Path
    incident_code: str = "MIR-STALL-001"


@dataclass(frozen=True)
class VerdictAlarm:
    family: str
    family_display: str
    source: str
    kind: str
    recommendation: str
    detail: str
    observed_at: datetime
    reference: str
    incident_code: str = "MIR-AGENT-HEALTH-001"


def format_alarm_message(alarm: StallAlarm | VerdictAlarm) -> str:
    """ADR-06 §2.2.6.2 message format."""
    if isinstance(alarm, VerdictAlarm):
        return (
            f"[{alarm.incident_code}] {alarm.family_display} "
            f"({alarm.family}) agent health verdict\n"
            f"- source: {alarm.source}\n"
            f"- kind: {alarm.kind}\n"
            f"- recommendation: {alarm.recommendation}\n"
            f"- observed_at: {alarm.observed_at.isoformat()}\n"
            f"- reference: {alarm.reference}\n"
            f"- detail: {alarm.detail}"
        )
    ts = alarm.last_entry_ts.isoformat() if alarm.last_entry_ts else "unknown"
    nested = alarm.last_entry_nested_type or "_"
    return (
        f"[{alarm.incident_code}] {alarm.family_display} "
        f"({alarm.family}) session stall detected\n"
        f"- session_uuid: {alarm.session_uuid}\n"
        f"- workspace: {alarm.workspace_encoded}\n"
        f"- idle: {alarm.idle_seconds}s\n"
        f"- last_entry: {alarm.last_entry_top_type}/{nested} @ {ts}\n"
        f"- jsonl: {alarm.jsonl_path}"
    )


class _HttpClient(Protocol):
    def Request(self, url, data, headers, method): ...  # noqa: N802
    def urlopen(self, req, timeout): ...


def _redact_url(url: str) -> str:
    """Return a safe form of a Discord webhook URL for logging."""
    if "/webhooks/" not in url:
        return "<webhook>"
    head, _, _ = url.partition("/webhooks/")
    return head + "/webhooks/<redacted>"


def push_to_discord(
    webhook_url: str,
    alarm: StallAlarm | VerdictAlarm,
    *,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    retries: int = 1,
    backoff_seconds: int = _RETRY_BACKOFF_SECONDS,
    http: object | None = None,
    sleep=time.sleep,
) -> bool:
    """POST ``{"content": format_alarm_message(alarm)}`` to ``webhook_url``.

    Returns True on a 2xx response. Returns False (no raise) on any transport
    error after exhausting retries. ``http`` defaults to ``urllib.request`` and
    can be replaced with a stub in tests.
    """
    if not webhook_url:
        _LOG.info("push_to_discord: empty webhook URL — dry-run skip")
        return False

    transport = http or urllib.request
    payload = json.dumps(
        {"content": format_alarm_message(alarm)}, ensure_ascii=False
    ).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    redacted = _redact_url(webhook_url)

    attempt = 0
    last_exc: Exception | None = None
    while attempt <= retries:
        try:
            req = transport.Request(
                webhook_url, data=payload, headers=headers, method="POST"
            )
            with transport.urlopen(req, timeout=timeout_seconds) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                if 200 <= status < 300:
                    return True
                _LOG.warning(
                    "push_to_discord: non-2xx status=%s url=%s (attempt %d/%d)",
                    status,
                    redacted,
                    attempt + 1,
                    retries + 1,
                )
        except urllib.error.HTTPError as exc:
            _LOG.warning(
                "push_to_discord: HTTPError code=%s url=%s (attempt %d/%d)",
                exc.code,
                redacted,
                attempt + 1,
                retries + 1,
            )
            last_exc = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            _LOG.warning(
                "push_to_discord: transport error url=%s err=%s (attempt %d/%d)",
                redacted,
                exc,
                attempt + 1,
                retries + 1,
            )
            last_exc = exc
        attempt += 1
        if attempt <= retries:
            sleep(backoff_seconds)
    _LOG.warning(
        "push_to_discord: giving up after %d attempts (last_exc=%s, url=%s)",
        retries + 1,
        last_exc,
        redacted,
    )
    return False
