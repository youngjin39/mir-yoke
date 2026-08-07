"""Mir orchestrator run_state driver — phase-4 13-state SM."""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import jsonschema

from tools.run_orchestrator.state_machine import (
    RUN_TRANSITIONS,
    InvalidRunTransitionError,
    RunState,
    is_valid_run_transition,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_STATE_PATH = Path(
    os.environ.get("MIR_RUN_STATE_PATH", str(PROJECT_ROOT / "tasks" / "run_state.json"))
)
DEFAULT_RUN_STATE_SCHEMA_PATH = (
    PROJECT_ROOT / "docs" / "templates" / "_schema" / "run_state.schema.json"
)

# Crockford base32 alphabet (no I, L, O, U)
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class RunOrchestratorError(Exception):
    """Base exception for run orchestrator errors."""


class SchemaValidationError(RunOrchestratorError):
    """Raised when run_state.json fails schema validation."""


# ----- ULID generation -----


def _generate_ulid() -> str:
    """Generate a 26-char Crockford base32 ULID.

    48-bit millisecond timestamp (10 chars) + 80-bit random (16 chars).
    """
    ts_ms = time.time_ns() // 1_000_000  # milliseconds
    rand_bytes = secrets.token_bytes(10)
    rand_int = int.from_bytes(rand_bytes, "big")

    # Encode timestamp: 10 chars, 5 bits each = 50 bits (top 2 bits unused, ts fits in 48)
    ts_chars: list[str] = []
    ts = ts_ms
    for _ in range(10):
        ts_chars.append(_CROCKFORD[ts & 0x1F])
        ts >>= 5
    ts_str = "".join(reversed(ts_chars))

    # Encode random: 16 chars, 5 bits each = 80 bits
    rand_chars: list[str] = []
    r = rand_int
    for _ in range(16):
        rand_chars.append(_CROCKFORD[r & 0x1F])
        r >>= 5
    rand_str = "".join(reversed(rand_chars))

    return ts_str + rand_str


# ----- ULID validation -----

_ULID_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _validate_ulid(value: str, field_name: str) -> None:
    """Raise ValueError if value is not a valid Crockford base32 ULID (26 chars)."""
    if not _ULID_PATTERN.match(value):
        raise ValueError(
            f"Invalid ULID for '{field_name}': {value!r}. "
            "Must be 26 uppercase Crockford base32 characters [0-9A-HJKMNP-TV-Z]."
        )


# ----- schema cache -----

_schema_cache: dict | None = None


def _load_schema(schema_path: Path = DEFAULT_RUN_STATE_SCHEMA_PATH) -> dict:
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = json.loads(schema_path.read_text(encoding="utf-8"))
    return _schema_cache


def _validate(run_state: dict, schema_path: Path = DEFAULT_RUN_STATE_SCHEMA_PATH) -> None:
    schema = _load_schema(schema_path)
    try:
        jsonschema.validate(run_state, schema)
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError(str(exc)) from exc


# ----- atomic write -----


def _atomic_write(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ----- public API -----


def load_run_state(path: Path = DEFAULT_RUN_STATE_PATH) -> dict:
    """Load + jsonschema validate run_state.json. Raise on schema fail."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    _validate(raw)
    return raw


def init_run(
    task_id: str,
    run_id: str | None = None,
    session_id: str | None = None,
    path: Path = DEFAULT_RUN_STATE_PATH,
) -> dict:
    """Create new run_state with status=IDLE.
    Optional session_id binds run to a Session per 5-tier spec.
    """
    now = datetime.now(UTC).isoformat()
    run_state = {
        "run_id": run_id or _generate_ulid(),
        "task_id": task_id,
        "status": RunState.IDLE.value,
        "started_at": now,
        "last_transition": now,
    }
    if session_id is not None:
        _validate_ulid(session_id, "session_id")
        run_state["session_id"] = session_id
    _validate(run_state)
    _atomic_write(run_state, path)
    return run_state


def transition(
    to_state: RunState | str,
    path: Path = DEFAULT_RUN_STATE_PATH,
    **kwargs: object,
) -> dict:
    """Transition current run to to_state.

    Validate against RUN_TRANSITIONS. Update last_transition timestamp.
    Atomic tempfile write. Raise InvalidRunTransitionError if not allowed.
    Optional kwargs land in run_state fields:
      current_lane, blocked_reason, rollback_target, approval_id, retry_count.
    """
    run_state = load_run_state(path)
    current = RunState(run_state["status"])
    target = RunState(to_state) if isinstance(to_state, str) else to_state

    if not is_valid_run_transition(current, target):
        allowed = sorted(s.value for s in RUN_TRANSITIONS.get(current, set()))
        raise InvalidRunTransitionError(
            f"Invalid transition {current.value} -> {target.value}. Allowed: {allowed}"
        )

    now = datetime.now(UTC).isoformat()
    run_state["status"] = target.value
    run_state["last_transition"] = now

    # Permitted optional fields from kwargs
    _ALLOWED_KWARGS = {
        "current_lane",
        "blocked_reason",
        "rollback_target",
        "approval_id",
        "retry_count",
        "current_step_id",
        "session_id",
    }
    for key, value in kwargs.items():
        if key in _ALLOWED_KWARGS:
            run_state[key] = value

    _validate(run_state)
    _atomic_write(run_state, path)
    return run_state


def get_current_state(path: Path = DEFAULT_RUN_STATE_PATH) -> RunState:
    """Return the current RunState enum value of the active run."""
    run_state = load_run_state(path)
    return RunState(run_state["status"])


def record_tool_event(
    event_id: str,
    tool: str,
    idempotency_key: str,
    result: dict,
    path: Path = DEFAULT_RUN_STATE_PATH,
) -> None:
    """Append a tool_event ULID to current run_state.tool_events array.

    Caller writes the tool_event.json separately; this just updates the ref.
    The event_id must be a valid ULID matching the schema pattern.
    """
    run_state = load_run_state(path)
    events: list[str] = run_state.setdefault("tool_events", [])
    if event_id not in events:
        events.append(event_id)
    run_state["tool_events"] = events
    _validate(run_state)
    _atomic_write(run_state, path)
