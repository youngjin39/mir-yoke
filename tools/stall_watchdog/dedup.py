"""ADR-06 Phase 6C-2: in-memory de-duplication ledger.

A stall alarm is uniquely identified by ``(family, workspace_encoded,
session_uuid)``. The ADR-06 §2.2.5 design lists a 4-tuple key
``(family, workspace_encoded, session_uuid, window_bucket)``; this
implementation realises the window dimension via a stored timestamp + elapsed
comparison (``(now - last).total_seconds() < window_seconds``) rather than a
discrete bucket value, which is functionally equivalent without persisting a
synthetic bucket id. The ledger is single-threaded (driven by the watchdog
daemon main loop) so no locking is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class DedupLedger:
    window_seconds: int = 600  # 10 minutes default
    _last_alarmed: dict[tuple[str, str, str], datetime] = field(default_factory=dict)

    def _key(
        self, family: str, workspace_encoded: str, session_uuid: str
    ) -> tuple[str, str, str]:
        return (family, workspace_encoded, session_uuid)

    def already_alarmed(
        self,
        family: str,
        workspace_encoded: str,
        session_uuid: str,
        now: datetime,
    ) -> bool:
        """Return True if an alarm fired within the current window."""
        key = self._key(family, workspace_encoded, session_uuid)
        last = self._last_alarmed.get(key)
        if last is None:
            return False
        return (now - last).total_seconds() < self.window_seconds

    def mark_alarmed(
        self,
        family: str,
        workspace_encoded: str,
        session_uuid: str,
        now: datetime,
    ) -> None:
        """Record that an alarm fired for this key at ``now``."""
        self._last_alarmed[self._key(family, workspace_encoded, session_uuid)] = now

    def gc(self, now: datetime) -> int:
        """Drop entries older than 2 x window_seconds. Return drop count."""
        cutoff = now - timedelta(seconds=2 * self.window_seconds)
        drop_keys = [k for k, ts in self._last_alarmed.items() if ts < cutoff]
        for k in drop_keys:
            del self._last_alarmed[k]
        return len(drop_keys)

    def size(self) -> int:
        return len(self._last_alarmed)
