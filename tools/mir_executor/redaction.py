"""Single-source credential detection and redaction for untrusted text."""

from __future__ import annotations

import re

_PEM_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
    r"[\s\S]*?"
    r"(?:-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|\Z)",
    re.IGNORECASE,
)
_ASSIGNMENT_SECRET = re.compile(
    r"(?ix)\b("
    r"(?:[a-z0-9]+[_-])*(?:api[_-]?key|access[_-]?key|authorization|bearer|password|secret|token)"
    r")\s*(=|:)\s*(?:bearer\s+)?[^\s,;]+"
)
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


def redact_secret_like_content(value: str) -> str:
    """Redact every supported credential shape without retaining its value."""
    redacted = _PEM_PRIVATE_KEY_BLOCK.sub("[REDACTED_PRIVATE_KEY]", value)
    redacted = _ASSIGNMENT_SECRET.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        redacted,
    )
    redacted = _BEARER_SECRET.sub("Bearer [REDACTED]", redacted)
    return _PROVIDER_TOKEN_SECRET.sub("[REDACTED_TOKEN]", redacted)


def redact_structured_value(value: object) -> object:
    """Redact JSON string values before serialization, preserving structure."""
    if isinstance(value, str):
        return redact_secret_like_content(value)
    if isinstance(value, dict):
        return {key: redact_structured_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_structured_value(item) for item in value]
    return value


__all__ = ("contains_secret_like_content", "redact_secret_like_content", "redact_structured_value")
