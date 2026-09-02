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

# File extensions to check
CHECK_EXTENSIONS = {".md", ".py", ".sh", ".yaml", ".yml", ".json", ".toml", ".txt", ".sql"}

# Top-level directories and virtualenv path parts to skip
SKIP_PARTS = {"archive", ".git"}
VIRTUALENV_PARTS = {".venv", "venv", "virtualenv", ".tox", ".nox", "site-packages"}


def test_no_korean_in_template():
    """Template repo is English-only public mirror -- zero Hangul allowed."""
    all_files = list(Path(".").rglob("*"))
    violations = []
    for path in all_files:
        if not path.is_file():
            continue
        # Skip excluded top-level dirs
        if path.parts and path.parts[0] in SKIP_PARTS:
            continue
        if any(part in VIRTUALENV_PARTS for part in path.parts):
            continue
        if path.suffix not in CHECK_EXTENSIONS:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
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


def _checkable_files():
    """Files the sanitization gate reads, using the same scope as the Hangul check."""
    for path in Path(".").rglob("*"):
        if not path.is_file():
            continue
        if path.parts and path.parts[0] in SKIP_PARTS:
            continue
        if any(part in VIRTUALENV_PARTS for part in path.parts):
            continue
        if path.suffix not in CHECK_EXTENSIONS:
            continue
        try:
            yield path, path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue


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


if __name__ == "__main__":
    # The release gate runs this file as a script, so a test that is not called
    # here does not run in the gate no matter what pytest does with it.
    test_no_korean_in_template()
    test_no_platform_channel_ids_in_template()
    print("test_no_korean_in_user_facing: PASS")
