"""Validate tool_event JSON against ToolContract requirements.

Invoked by .claude/hooks/pre-tool-use.sh as:
    python3 tools/hooks/validate_tool_contract.py < tool_event.json

Exit codes:
    0 -- valid contract, allow
    2 -- contract missing/invalid, BLOCK (per the hook convention)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow import even when tools/ not in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.mir.core.engine.structured_error import (  # noqa: E402
    ErrorType,
    StructuredError,
    emit_error_to_stderr,
)
from src.mir.core.engine.tool_contract import ContractViolation, ToolContract  # noqa: E402

CONTRACT_REQUIRED_TOOLS = {"Edit", "Write", "Bash"}


def validate_payload(payload: dict) -> int:
    tool_name = payload.get("tool_name", "")
    if tool_name not in CONTRACT_REQUIRED_TOOLS:
        return 0  # not required

    tool_input = payload.get("tool_input", {})
    contract_dict = tool_input.get("_mir_contract")
    if contract_dict is None:
        err = StructuredError(
            type=ErrorType.PRECONDITION,
            recoverable=False,
            summary=f"tool {tool_name} requires _mir_contract field in tool_input",
            details_ref="docs/decisions/adr-44-13-state-sm-migration-2026-05-24.md",
        )
        emit_error_to_stderr(err, prefix="[mir CONTRACT]")
        return 2

    try:
        ToolContract.from_dict(contract_dict)
    except (ValueError, ContractViolation) as e:
        err = StructuredError(
            type=ErrorType.SCHEMA,
            recoverable=False,
            summary=f"invalid ToolContract for {tool_name}: {e}",
            details_ref="src/mir/core/engine/tool_contract.py",
        )
        emit_error_to_stderr(err, prefix="[mir CONTRACT]")
        return 2

    return 0


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0  # empty stdin, allow (defensive)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        err = StructuredError(
            type=ErrorType.SCHEMA,
            recoverable=False,
            summary=f"tool_event JSON parse failed: {e}",
        )
        emit_error_to_stderr(err, prefix="[mir CONTRACT]")
        return 2
    return validate_payload(payload)


if __name__ == "__main__":
    sys.exit(main())
