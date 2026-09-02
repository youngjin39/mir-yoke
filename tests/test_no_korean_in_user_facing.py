"""The public template's sanitization gate.

`scripts/verify_release_readiness.py` runs this file as the step named
"sanitization", so whatever this file does not check, that gate does not check.
For a long time it checked one thing: Hangul. Identity strings, private
repository slugs and platform identifiers passed it, and a release note once
recorded a sanitize-gate pass that the gate had not earned.

The checks here are pattern-based on purpose. This repository is public, so a
detector that listed the private strings it looks for would be the leak it is
meant to prevent — the same reason the Hangul range below is built from code
points instead of literal characters. Anything that can only be caught by
naming a secret belongs in the source repository's own tooling, not here.

Absolute-path leakage is deliberately NOT checked here.
`tests/test_public_template_surface.py` already owns that contract, over a wider
file scope, with its forbidden tokens assembled from fragments so that the
detector never contains the thing it detects. One authoritative list beats two
that drift apart — an earlier revision of this file added a second one and the
suite caught it immediately, by flagging this very file.

Filename kept despite the widened scope: eight places reference it by path,
including .github/workflows/validate.yml, the release-readiness gate, and a test
that asserts the name.
"""

import re
import subprocess
from pathlib import Path

# Build Hangul regex from Unicode code points -- no literal Hangul bytes in this source file.
# U+AC00-U+D7AF: Hangul syllables
# U+1100-U+11FF: Hangul Jamo
# U+3130-U+318F: Hangul compatibility Jamo
_RANGE = (
    chr(0xAC00)
    + "-"
    + chr(0xD7AF)
    + chr(0x1100)
    + "-"
    + chr(0x11FF)
    + chr(0x3130)
    + "-"
    + chr(0x318F)
)
HANGUL = re.compile("[" + _RANGE + "]")

# Suffixes to skip: binary or machine-generated, where a text scan is meaningless.
# This is a skip list, not an allow list, on purpose. The previous fixed allow list
# ({.md,.py,.sh,.yaml,.yml,.json,.toml,.txt,.sql}) left 19 tracked files outside the
# gate entirely, including scripts/mir.ps1, setup.ps1, a .jsonl log, and — most
# pointedly — .mcp.json.example and harness_a.toml.example, when the identifier this
# gate now catches leaked from an example payload. A new file type is covered by
# default now; only an explicitly listed suffix escapes.
SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".db"}


def _checkable_files():
    """Every tracked or untracked-but-not-ignored text file, with its content.

    Enumeration is `git ls-files`, matching tests/test_public_template_surface.py
    rather than an rglob walk: the two gates now agree on what "the public surface"
    means, and .git, .venv and ignored paths drop out without a hand-maintained
    exclusion list.
    """
    listed = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
    ).splitlines()
    root = Path(__file__).resolve().parents[1]
    for relative in listed:
        path = root / relative
        if not path.is_file() or path.suffix in SKIP_SUFFIXES:
            continue
        try:
            yield Path(relative), path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


def test_no_korean_in_template():
    """Template repo is English-only public mirror -- zero Hangul allowed."""
    violations = []
    for path, content in _checkable_files():
        # Strip fenced code blocks before the Hangul check: code examples may
        # contain an intentional Hangul-range regex literal (the detector pattern
        # itself); only prose Korean is a real leak.
        content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
        matches = HANGUL.findall(content)
        if matches:
            violations.append((str(path), matches[:5]))
    assert not violations, f"Korean Hangul detected in {len(violations)} file(s):\n" + "\n".join(
        f"  {p}: {m}" for p, m in violations[:10]
    )


# A chat or channel id assigned a 17-to-20 digit platform snowflake. Placeholder
# forms (<your-discord-channel-id>, an example name) do not match, so this catches
# a real id left in an example payload without naming any id.
PLATFORM_CHANNEL_ID = re.compile(r"(?:chat|channel)_id\"?\s*[:=]\s*\"?[0-9]{17,20}")


def test_no_platform_channel_ids_in_template():
    """A real Discord/Slack channel id in a public example is topology, not documentation."""
    violations = [
        (str(path), PLATFORM_CHANNEL_ID.findall(content)[:3])
        for path, content in _checkable_files()
        if PLATFORM_CHANNEL_ID.search(content)
    ]
    assert not violations, (
        f"platform channel id detected in {len(violations)} file(s); "
        "replace it with a placeholder such as <your-discord-channel-id>:\n"
        + "\n".join(f"  {p}: {m}" for p, m in violations[:10])
    )


# Credential shapes, which outrank the identifier above in severity. A channel id
# names a room; a webhook URL or a bot token grants access to it. Both are matchable
# from shape alone, so the "do not list the secrets" constraint does not stand in the
# way — nothing below encodes a real value.
CREDENTIAL_SHAPES = (
    ("platform webhook URL", re.compile(r"discord(?:app)?\.com/api/webhooks/[0-9]{15,}/[\w-]{20,}")),
    ("bot token", re.compile(r"\b[MNO][A-Za-z0-9_-]{23}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27}\b")),
)


def _synthetic(kind: str) -> str:
    """Build a fake sample at runtime so this source never contains a matching literal.

    Same reason the Hangul range is assembled from code points: a detector that
    spells out what it detects trips itself, which is exactly how an earlier
    revision of this file failed.
    """
    if kind == "webhook":
        return "https://discord" + ".com/api/webhooks/" + ("1" * 19) + "/" + ("x" * 40)
    if kind == "token":
        return "M" + ("A" * 23) + "." + ("B" * 6) + "." + ("C" * 27)
    if kind == "channel_id":
        return '"chat_id": "' + ("9" * 19) + '"'
    raise AssertionError(kind)


def test_credential_and_identifier_patterns_match_synthetic_samples():
    """A detector nobody has seen fail is an assertion, not a check."""
    shapes = dict(CREDENTIAL_SHAPES)
    assert shapes["platform webhook URL"].search(_synthetic("webhook"))
    assert shapes["bot token"].search(_synthetic("token"))
    assert PLATFORM_CHANNEL_ID.search(_synthetic("channel_id"))


def test_credential_and_identifier_patterns_ignore_placeholders():
    """Over-blocking is its own failure: placeholder forms must stay writable."""
    shapes = dict(CREDENTIAL_SHAPES)
    placeholder_webhook = "https://discord" + ".com/api/webhooks/<id>/<token>"
    placeholder_channel = '"chat_id": "<your-discord-channel-id>"'
    short_numeric = '"retry_after": "1234"'
    assert not shapes["platform webhook URL"].search(placeholder_webhook)
    assert not PLATFORM_CHANNEL_ID.search(placeholder_channel)
    assert not PLATFORM_CHANNEL_ID.search(short_numeric)


def test_no_credential_shapes_in_template():
    """A public template must never carry a usable credential, in any file type."""
    violations = []
    for path, content in _checkable_files():
        for label, pattern in CREDENTIAL_SHAPES:
            if pattern.search(content):
                violations.append((str(path), label))
    assert not violations, (
        f"credential shape detected in {len(violations)} file(s); revoke it, then replace "
        "it with a placeholder:\n" + "\n".join(f"  {p}: {label}" for p, label in violations[:10])
    )


if __name__ == "__main__":
    # The release gate runs this file as a script, so a test that is not called
    # here does not run in the gate no matter what pytest does with it.
    test_no_korean_in_template()
    test_no_platform_channel_ids_in_template()
    test_no_credential_shapes_in_template()
    test_credential_and_identifier_patterns_match_synthetic_samples()
    test_credential_and_identifier_patterns_ignore_placeholders()
    print("test_no_korean_in_user_facing: PASS")
