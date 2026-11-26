"""Deterministic ToolContract instrumenter (phase-4 §4).

Fills all 4 obligatory ToolContract fields from tool name + args
without LLM assistance. Designed for Option B (manual instrumenter)
per user decision 2026-05-24 Discord 1508028248.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolContract:
    """Tool contract fields emitted by the instrumenter."""

    idempotency_key: str
    precondition: str
    dry_run: bool
    side_effect_summary: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if not result["extra"]:
            result.pop("extra")
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


# Precondition lookup: tool -> declared state requirement
_PRECONDITIONS: dict[str, str] = {
    'Read': 'file_exists',
    'Edit': 'file_exists+writable',
    'Write': 'parent_dir_exists+writable',
    'Bash': 'shell_runnable',
    'mcp__claude_ai_Gmail__search_threads': 'network_reachable',
    'mcp__plugin_discord_discord__reply': 'network_reachable',
    'WebFetch': 'network_reachable',
    'WebSearch': 'network_reachable',
}

_DEFAULT_PRECONDITION = 'tool_runnable'


def _build_side_effect_summary(tool: str, args: dict[str, Any]) -> str:
    """Return a 1-line human summary, truncated to 200 chars."""
    if tool == 'Read':
        path = args.get('file_path', args.get('file', '<unknown>'))
        raw = f'read {path}'
    elif tool == 'Edit':
        path = args.get('file_path', '<unknown>')
        raw = f'edit {path}'
    elif tool == 'Write':
        path = args.get('file_path', '<unknown>')
        raw = f'write {path}'
    elif tool == 'Bash':
        cmd = args.get('command', '<empty>')
        raw = f'run: {cmd[:80]}'
    elif tool.startswith('mcp__'):
        raw = f'mcp call: {tool}'
    else:
        # Generic: tool name + first arg value if available
        first_val = next(iter(args.values()), '') if args else ''
        snippet = str(first_val)[:60] if first_val else ''
        raw = f'{tool}({snippet})' if snippet else f'{tool}()'
    return raw[:200]


def instrument_call(
    tool: str,
    args: dict[str, Any],
    dry_run: bool = False,
) -> ToolContract:
    """Deterministic ToolContract fill from tool + args.

    idempotency_key: sha256(tool|sorted_args)[:32] — stable, 32 hex chars
    precondition: static lookup by tool name, default 'tool_runnable'
    dry_run: passed param (default False)
    side_effect_summary: static template per tool, truncated at 200 chars
    """
    # Build stable key: sha256 of 'tool|[(k,v),...]' sorted by key
    key_src = f'{tool}|{sorted(args.items())}'
    idempotency_key = hashlib.sha256(key_src.encode('utf-8')).hexdigest()[:32]

    precondition = _PRECONDITIONS.get(tool, _DEFAULT_PRECONDITION)
    side_effect_summary = _build_side_effect_summary(tool, args)

    return ToolContract(
        idempotency_key=idempotency_key,
        precondition=precondition,
        dry_run=dry_run,
        side_effect_summary=side_effect_summary,
    )
