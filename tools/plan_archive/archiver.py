from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

_DONE_MONTH_RE = re.compile(r"\((\d{4}-\d{2})-\d{2}, DONE\)")
_TOMBSTONE_RE = re.compile(
    r"^Archived to tasks/archive/plan-archive-\d{4}-\d{2}\.md: ## .+$"
)

_HEADING_DONE_RE = re.compile(r"\(.*\bDONE\b.*\)")
_HEADING_CLOSED_RE = re.compile(r"\(.*\bCLOSED\b.*\)")
_BODY_ELEVATION_CLOSED_RE = re.compile(r"elevation:\s*CLOSED")
STEP_STATUS_VOCAB = ("TODO", "IN_PROGRESS", "DONE", "FAILED", "BLOCKED")
_BODY_STEP_STATUS_RE = re.compile(
    rf"^Step (?P<step_id>\d+): (?P<status>{'|'.join(STEP_STATUS_VOCAB)}|CLOSED)\b"
)


def _is_hard_keep(heading: str, body_lines: list[str]) -> bool:
    if "Pinned Tracker Policies" in heading:
        return True
    for token in ("ACTIVE", "IN_PROGRESS", "PENDING"):
        if token in heading:
            return True
    for line in body_lines[:6]:
        for token in ("ACTIVE", "IN_PROGRESS", "PENDING"):
            if token in line:
                return True
    return False


def _is_archivable(section: Section) -> bool:
    heading = section.heading
    body_lines = section.content.splitlines()
    if _is_hard_keep(heading, body_lines):
        return False
    if _HEADING_DONE_RE.search(heading) or _HEADING_CLOSED_RE.search(heading):
        return True
    for line in body_lines[:6]:
        if _BODY_ELEVATION_CLOSED_RE.search(line):
            return True
    for line in body_lines[:6]:
        match = _BODY_STEP_STATUS_RE.match(line)
        if match and match.group("status") in {"DONE", "CLOSED"}:
            return True
    return False


@dataclass(frozen=True)
class Section:
    heading: str
    content: str
    done_month: str | None


@dataclass(frozen=True)
class ArchiveResult:
    archivable: list[Section] = field(default_factory=list)
    kept_done: list[Section] = field(default_factory=list)
    active_sections: list[Section] = field(default_factory=list)
    plan_path: Path = Path("tasks/plan.md")
    archive_dir: Path = Path("tasks/archive")
    fallback_month: str = ""


def _done_month(heading: str) -> str | None:
    match = _DONE_MONTH_RE.search(heading)
    if not match:
        return None
    return match.group(1)


def _section(heading: str, content_lines: list[str]) -> Section:
    return Section(
        heading=heading,
        content="".join(content_lines),
        done_month=_done_month(heading),
    )


def parse_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    preamble: list[str] = []
    current_heading: str | None = None
    current_content: list[str] = []

    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            if current_heading is None:
                if preamble:
                    sections.append(Section("", "".join(preamble), None))
            else:
                sections.append(_section(current_heading, current_content))
            current_heading = line[3:].rstrip("\r\n")
            current_content = []
            continue

        if current_heading is None:
            preamble.append(line)
        else:
            current_content.append(line)

    if current_heading is None:
        sections.append(Section("", "".join(preamble), None))
    else:
        sections.append(_section(current_heading, current_content))

    return sections


def classify(sections,recency_keep=5):
    a=[s for s in sections if _is_archivable(s)]
    arch=a[:-recency_keep] if recency_keep>0 else a
    kept=a[-recency_keep:] if recency_keep>0 else []
    ids={id(s) for s in a}
    return ArchiveResult(
        archivable=arch,
        kept_done=kept,
        active_sections=[s for s in sections if id(s) not in ids],
    )


def dry_run(result: ArchiveResult, fallback_month: str) -> dict[str, object]:
    by_month: dict[str, int] = {}
    for section in result.archivable:
        month = section.done_month or fallback_month
        by_month[month] = by_month.get(month, 0) + 1

    return {
        "archivable": len(result.archivable),
        "by_month": dict(sorted(by_month.items())),
    }


def _render_section(section: Section) -> str:
    if not section.heading:
        return section.content
    return f"## {section.heading}\n{section.content}"


def _extract_tombstones(content: str) -> tuple[str, list[str]]:
    kept_lines: list[str] = []
    tombstones: list[str] = []
    for line in content.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        if _TOMBSTONE_RE.match(stripped):
            tombstones.append(stripped)
        else:
            kept_lines.append(line)
    return "".join(kept_lines), tombstones


def _clean_sections(sections: list[Section]) -> tuple[list[Section], list[str]]:
    cleaned: list[Section] = []
    tombstones: list[str] = []
    for section in sections:
        content, section_tombstones = _extract_tombstones(section.content)
        cleaned.append(replace(section, content=content))
        tombstones.extend(section_tombstones)
    return cleaned, tombstones


def _month_for(section: Section, fallback_month: str) -> str:
    return section.done_month or fallback_month


def _append_archive(archive_path: Path, month: str, sections: list[Section]) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive_path.exists():
        archive_path.write_text(f"# Plan Archive {month}\n\n", encoding="utf-8")

    existing = archive_path.read_text(encoding="utf-8")
    prefix = "" if existing.endswith("\n") else "\n"
    payload = "".join(_render_section(section).rstrip() + "\n\n" for section in sections)
    with archive_path.open("a", encoding="utf-8") as handle:
        handle.write(prefix + payload)


def _write_plan(
    result: ArchiveResult,
    active_sections: list[Section],
    kept_done: list[Section],
    tombstones: list[str],
) -> None:
    body = "".join(_render_section(section) for section in [*active_sections, *kept_done])
    if tombstones:
        body = body.rstrip() + "\n\n" + "\n".join(tombstones) + "\n"
    result.plan_path.write_text(body, encoding="utf-8")


def apply_archive(
    result: ArchiveResult,
    month_override: str | None = None,
) -> dict[str, int]:
    fallback_month = month_override or result.fallback_month
    archivable, old_tombstones_a = _clean_sections(result.archivable)
    active_sections, old_tombstones_b = _clean_sections(result.active_sections)
    kept_done, old_tombstones_c = _clean_sections(result.kept_done)

    grouped: dict[str, list[Section]] = {}
    for section in archivable:
        month = _month_for(section, fallback_month)
        grouped.setdefault(month, []).append(section)

    for month, sections in sorted(grouped.items()):
        _append_archive(result.archive_dir / f"plan-archive-{month}.md", month, sections)

    new_tombstones = [
        (
            f"Archived to tasks/archive/plan-archive-{_month_for(section, fallback_month)}.md: "
            f"## {section.heading}"
        )
        for section in archivable
    ]
    tombstones = [
        *old_tombstones_a,
        *old_tombstones_b,
        *old_tombstones_c,
        *new_tombstones,
    ][-20:]
    _write_plan(result, active_sections, kept_done, tombstones)
    return {"archived": len(archivable), "tombstones_written": len(tombstones)}
