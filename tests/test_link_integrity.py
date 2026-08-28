"""Test that all markdown internal links resolve to existing files."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_links_resolve():
    tracked_and_candidate = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    md_files = [ROOT / relative for relative in tracked_and_candidate if relative.endswith(".md")]

    pattern = re.compile(r'\[.*?\]\(([^)]+)\)')
    broken = []
    for md in md_files:
        content = md.read_text(encoding="utf-8")
        for match in pattern.finditer(content):
            link = match.group(1).split("#")[0].strip()
            if not link:
                continue
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            target = (md.parent / link).resolve()
            if not target.exists():
                broken.append((str(md.relative_to(ROOT)), link))
    assert not broken, f"Broken links: {broken[:10]}"


if __name__ == "__main__":
    test_all_links_resolve()
    print("test_link_integrity: PASS")
