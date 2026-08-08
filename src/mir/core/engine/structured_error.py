"""Mir structured error format (phase-4 §5).

All hooks and tool calls should emit errors in this format for consistent
parsing by explicitly adopted consumer-local orchestration tools.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class ErrorType(StrEnum):
    """High-level error category for routing/handling."""
    PRECONDITION = "precondition"
    TRANSITION = "transition"
    POLICY = "policy"
    TOOL_FAILURE = "tool_failure"
    SCHEMA = "schema"
    INTERRUPT = "interrupt"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class StructuredError:
    """Standardized error format per phase-4 §5.

    Fields:
        type: ErrorType - for routing
        recoverable: bool - can caller retry?
        summary: str - 1-line human description (no PII)
        details_ref: str | None - pointer to log/file with full details
        context: dict | None - optional structured metadata
    """
    type: ErrorType
    recoverable: bool
    summary: str
    details_ref: str | None = None
    context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (excluding None fields)."""
        d = asdict(self)
        d["type"] = self.type.value
        return {k: v for k, v in d.items() if v is not None}

    def to_json(self) -> str:
        """Serialize to JSON string (sorted keys, no trailing space)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StructuredError:
        """Parse from dict. Raise ValueError on missing required."""
        for required in ("type", "recoverable", "summary"):
            if required not in d:
                raise ValueError(f"missing required field: {required}")
        return cls(
            type=ErrorType(d["type"]),
            recoverable=d["recoverable"],
            summary=d["summary"],
            details_ref=d.get("details_ref"),
            context=d.get("context"),
        )

    @classmethod
    def from_json(cls, s: str) -> StructuredError:
        """Parse from JSON string."""
        return cls.from_dict(json.loads(s))


def emit_error_to_stderr(err: StructuredError, prefix: str = "[mir ERROR]") -> None:
    """Write structured error to stderr as '<prefix> <json>'.
    Hooks should call this before sys.exit(non-zero).
    """
    import sys
    print(f"{prefix} {err.to_json()}", file=sys.stderr)
