"""Single-source credential detection and redaction for untrusted text."""

from __future__ import annotations

import re

_PEM_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
    r"[\s\S]*?"
    r"(?:-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|\Z)",
    re.IGNORECASE,
)
_SECRET_NAME = (
    r"(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?key|authorization|bearer|password|secret|token)"
    r"(?:[_-]?key)?"
)
# A quoted key keeps its quotes and a quoted value is replaced whole, so JSON-like text
# such as `"api_key": "value"` or a value containing spaces is not left partly visible.
_ASSIGNMENT_SECRET = re.compile(
    rf"(?i)\b(?P<key>{_SECRET_NAME})(?P<key_quote>[\"']?)(?P<sep>\s*(?:=|:)\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|(?:(?:bearer|basic)\s+)?[^\s,;]+)"
)
_SECRET_KEY_NAME = re.compile(rf"(?i){_SECRET_NAME}")
_BEARER_SECRET = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_PROVIDER_TOKEN_SECRET = re.compile(
    r"(?i)\b(?:"
    r"sk[-_](?:proj[-_]|svcacct[-_]|ant[-_])?[a-z0-9_-]{12,}"
    r"|(?:gh[pousr]|github_pat)_[a-z0-9_]{20,}"
    r"|xox[baprs]-[a-z0-9-]{12,}"
    r"|AKIA[A-Z0-9]{16}"
    r"|AIza[0-9A-Za-z_-]{20,}"
    r")"
)


def contains_secret_like_content(value: str) -> bool:
    """Return whether text contains a credential or PEM private-key shape."""
    return any(
        pattern.search(value) is not None
        for pattern in (
            _PEM_PRIVATE_KEY_BLOCK,
            _ASSIGNMENT_SECRET,
            _BEARER_SECRET,
            _PROVIDER_TOKEN_SECRET,
        )
    )


def _redact_assignment(match: re.Match[str]) -> str:
    if not match["key_quote"]:
        return f"{match['key']}=[REDACTED]"
    value_quote = match["value"][0] if match["value"][0] in "\"'" else ""
    return f"{match['key']}{match['key_quote']}{match['sep']}{value_quote}[REDACTED]{value_quote}"


def redact_secret_like_content(value: str) -> str:
    """Redact every supported credential shape without retaining its value."""
    redacted = _PEM_PRIVATE_KEY_BLOCK.sub("[REDACTED_PRIVATE_KEY]", value)
    redacted = _ASSIGNMENT_SECRET.sub(_redact_assignment, redacted)
    redacted = _BEARER_SECRET.sub("Bearer [REDACTED]", redacted)
    return _PROVIDER_TOKEN_SECRET.sub("[REDACTED_TOKEN]", redacted)


def redact_structured_value(value: object) -> object:
    """Redact JSON string values before serialization, preserving structure."""
    if isinstance(value, str):
        return redact_secret_like_content(value)
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if isinstance(key, str) and isinstance(item, str) and item
            and _SECRET_KEY_NAME.fullmatch(key)
            else redact_structured_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_structured_value(item) for item in value]
    return value


__all__ = ("contains_secret_like_content", "redact_secret_like_content", "redact_structured_value")
