"""Test that no Korean Hangul characters appear in user-facing files (public template must be English-only)."""
import re
from pathlib import Path

# Build Hangul regex from Unicode code points -- no literal Hangul bytes in this source file.
# U+AC00-U+D7AF: Hangul syllables
# U+1100-U+11FF: Hangul Jamo
# U+3130-U+318F: Hangul compatibility Jamo
_RANGE = (
    chr(0xAC00) + "-" + chr(0xD7AF)
    + chr(0x1100) + "-" + chr(0x11FF)
    + chr(0x3130) + "-" + chr(0x318F)
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
        matches = HANGUL.findall(content)
        if matches:
            violations.append((str(path), matches[:5]))
    assert not violations, (
        f"Korean Hangul detected in {len(violations)} file(s):\n"
        + "\n".join(f"  {p}: {m}" for p, m in violations[:10])
    )


if __name__ == "__main__":
    test_no_korean_in_template()
    print("test_no_korean_in_user_facing: PASS")
