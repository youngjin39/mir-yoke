"""ADR-09 Phase 9A/9B -- agent frontmatter parser + jsonschema validator.

Line-based frontmatter parser (no PyYAML dependency -- matches frontmatter in
scripts/generate_codex_derivatives.py, also exposed through the .sh wrapper).
Handles the simple key: value shape used by .claude/agents/*.md.

Two validation modes:
- 'lenient' (Phase 9A default): execution_backend may be absent. Other required fields
  + enum constraints still enforced.
- 'strict' (Phase 9B onward): execution_backend MUST be present and one of
  {'claude', 'codex'}. Schema's required list (post-Phase 9B) covers this, but strict
  mode also injects execution_backend as a defense-in-depth for any pre-Phase-9B
  schema state.

Schema location resolves dynamically -- NO absolute path hardcoding (avoids the
tools/conductor_bridge/dispatcher.py:30-37 anti-pattern called out in ADR-09 R5).
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import jsonschema

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs" / "templates" / "_schema" / "agent_frontmatter.schema.json"
)
_SCHEMA_CACHE: dict[str, Any] | None = None


class AgentValidationError(ValueError):
    """Raised by load_agent when frontmatter fails validation."""


@dataclass(frozen=True)
class AgentSpec:
    """Parsed and validated agent frontmatter.

    `execution_backend` is Optional in lenient mode (Phase 9A); required in strict mode
    (Phase 9B onward). `context` and `disallowedTools` are always optional.
    """

    name: str
    description: str
    model: str
    execution_backend: str | None = None
    context: str | None = None
    disallowedTools: str | None = None


def _load_schema() -> dict[str, Any]:
    """Read the jsonschema file (cached). Returns a deep copy so callers cannot
    poison the module-level cache by mutating the returned dict (round 2 lens 1 C1).
    Raises FileNotFoundError if missing.
    """
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(_SCHEMA_CACHE)


def _strip_quotes(value: str) -> str:
    """Strip a single set of surrounding double quotes, mirroring the perl pattern."""
    value = value.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Extract the leading --- ... --- frontmatter block as a flat dict.

    The parser:
    - reads until the closing `---` delimiter (trailing newline optional -- round 2
      lens 1 C2: editors that strip the final newline must not produce a misleading
      "delimiter not found" error),
    - matches `key: value` lines (key in [a-zA-Z_][a-zA-Z0-9_]*),
    - strips a single pair of surrounding double quotes from the value,
    - preserves the original casing of keys.

    Multi-line continuation (key on one line, value spanning the next quoted lines)
    is supported for simple double-quoted strings -- the value accumulates until the
    closing quote.

    Raises:
        FileNotFoundError: if path does not exist.
        AgentValidationError: if the opening or closing `---` delimiter is missing.
    """
    text = path.read_text(encoding="utf-8")
    # Trailing newline after closing `---` is optional (round 2 lens 1 C2).
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not match:
        raise AgentValidationError(
            f"frontmatter delimiter (--- ... ---) not found in {path}. "
            "Confirm the file opens with '---\\n' and closes with '\\n---' (trailing "
            "newline optional but the closing '---' must be on its own line)."
        )

    block = match.group(1)
    result: dict[str, str] = {}
    key_pattern = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$")

    current_key: str | None = None
    current_buffer: list[str] = []
    in_quoted_continuation = False

    for line in block.split("\n"):
        if in_quoted_continuation:
            current_buffer.append(line)
            if line.rstrip().endswith('"') and not line.rstrip().endswith('\\"'):
                joined = "\n".join(current_buffer)
                result[current_key] = _strip_quotes(joined)  # type: ignore[index]
                current_key = None
                current_buffer = []
                in_quoted_continuation = False
            continue

        key_match = key_pattern.match(line)
        if key_match:
            key = key_match.group(1)
            value_part = key_match.group(2)
            stripped = value_part.strip()
            if (
                stripped.startswith('"')
                and not (stripped.endswith('"') and len(stripped) > 1)
            ):
                current_key = key
                current_buffer = [value_part]
                in_quoted_continuation = True
            else:
                result[key] = _strip_quotes(value_part)

    return result


def validate_frontmatter(
    data: dict[str, Any],
    mode: Literal["lenient", "strict"] = "lenient",
) -> list[str]:
    """Run jsonschema validation. Returns a list of error messages (empty == valid).

    Mode semantics:
    - 'lenient' (Phase 9A default): drops `execution_backend` from `required` if present.
      Used while .md files have not yet been patched with execution_backend.
    - 'strict' (Phase 9B onward): ensures execution_backend is in required regardless
      of schema state -- defense-in-depth if a future schema edit drops it accidentally.
    """
    schema = _load_schema()
    current_required = schema.get("required", [])
    if mode == "lenient":
        required = [k for k in current_required if k != "execution_backend"]
        schema["required"] = required
    else:
        if "execution_backend" not in current_required:
            schema["required"] = [*current_required, "execution_backend"]

    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    ]


def load_agent(
    path: Path,
    mode: Literal["lenient", "strict"] = "lenient",
) -> AgentSpec:
    """Parse and validate an agent frontmatter file.

    Raises:
        FileNotFoundError: if `path` does not exist (propagated from parse_frontmatter).
        AgentValidationError: on parse or schema failure.
    """
    raw = parse_frontmatter(path)
    errors = validate_frontmatter(raw, mode=mode)
    if errors:
        raise AgentValidationError(
            f"{path}: validation errors (mode={mode}):\n  - "
            + "\n  - ".join(errors)
        )
    return AgentSpec(
        name=raw["name"],
        description=raw["description"],
        model=raw["model"],
        execution_backend=raw.get("execution_backend"),
        context=raw.get("context"),
        disallowedTools=raw.get("disallowedTools"),
    )
