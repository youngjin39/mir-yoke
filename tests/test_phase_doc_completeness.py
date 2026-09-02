"""Test that phase-N-*.md documents contain required sections.

Required sections per ci.md §3-5:
  - §0.5 Design Goals (## 0.5 ... or ## Design Goals)
  - Exit Criterion section
  - Adoption/application status section

Note: If no phase-*.md files are found, the test passes (missing baseline
is a separate check; this test only validates found documents).

Historical pointers are skipped. A pointer declares `status: superseded` and its
whole purpose is to be short — it holds a link into the archive, not the sections
this test requires. Reading one as an incomplete phase document would report the
archive move as a defect, and the alternative, padding pointers with the required
headings, would make them lie about having content. The archived body still
carries the sections; the live path deliberately does not.
"""
import re
from pathlib import Path

# Patterns that satisfy each requirement (English-only -- template repo is English-only)
_DESIGN_GOALS_RE = re.compile(
    r"^##\s*(?:0\.5|Design Goals)",
    re.MULTILINE,
)
_EXIT_CRITERION_RE = re.compile(
    r"Exit Criterion",
    re.IGNORECASE,
)
_ADOPTION_STATUS_RE = re.compile(
    r"(?:Mir Adoption Status|applied|land)",
    re.IGNORECASE,
)

# A historical pointer, recognised by its declared status plus the heading form the
# archive convention requires. Both are checked so an ordinary superseded phase
# document that still carries its sections is not skipped by accident.
_POINTER_RE = re.compile(
    r"^status:\s*superseded\b.*^#.*Historical Pointer",
    re.MULTILINE | re.DOTALL,
)


def test_all_phase_docs_have_required_sections():
    harness_dir = Path("docs/harness-engineering")
    if not harness_dir.exists():
        return  # No harness-engineering docs present yet

    phase_docs = list(harness_dir.glob("phase-*.md"))
    if not phase_docs:
        return  # No phase docs present yet — pass (missing is a separate baseline check)

    missing = []
    for doc in phase_docs:
        content = doc.read_text(encoding="utf-8", errors="ignore")
        if _POINTER_RE.search(content):
            continue
        failures = []
        if not _DESIGN_GOALS_RE.search(content):
            failures.append("missing §0.5 Design Goals section")
        if not _EXIT_CRITERION_RE.search(content):
            failures.append("missing Exit Criterion section")
        if not _ADOPTION_STATUS_RE.search(content):
            failures.append("missing adoption/application status section")
        if failures:
            missing.append((str(doc), failures))

    assert not missing, (
        "Phase docs missing required sections:\n"
        + "\n".join(f"  {p}: {'; '.join(f)}" for p, f in missing)
    )


if __name__ == "__main__":
    test_all_phase_docs_have_required_sections()
    print("test_phase_doc_completeness: PASS")
