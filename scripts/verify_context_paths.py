#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {".git", ".claude", ".codex", ".agents", ".mir-backup", ".venv", "__pycache__"}
DEFAULT_RELATIVE_TARGETS = (
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "ARCHITECTURE.md",
    ".codex-sync/README.md",
    "docs/memory-map.md",
    "tasks/lessons.md",
    "scripts/CLAUDE.md",
    "tests/CLAUDE.md",
    "src/CLAUDE.md",
)
ROOT_DOC_NAMES = {
    "CLAUDE.md",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "PRD.md",
    "ADR.md",
    "UI_GUIDE.md",
    "README.md",
}
KNOWN_PREFIXES = (
    "./",
    "../",
    ".claude/",
    ".codex/",
    ".agents/",
    "docs/",
    "tasks/",
    "scripts/",
    "tests/",
    "src/",
)
PATH_SUFFIXES = {".md", ".json", ".py", ".sh", ".toml", ".yaml", ".yml", ".txt"}
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
QUOTED_RE = re.compile(r"['\"]([^'\"\n]+)['\"]")


@dataclass(frozen=True)
class TargetSpec:
    path: Path
    line: int | None = None
    explicit: bool = False


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def is_text_surface(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in SKIP_PARTS for part in rel.parts):
        return False
    if path.name == "CLAUDE.md":
        return True
    if rel.as_posix() in DEFAULT_RELATIVE_TARGETS:
        return True
    return path.suffix in PATH_SUFFIXES


def default_targets() -> list[TargetSpec]:
    targets: list[TargetSpec] = []
    for rel in DEFAULT_RELATIVE_TARGETS:
        path = ROOT / rel
        if path.exists():
            targets.append(TargetSpec(path=path))
    for path in sorted(ROOT.rglob("CLAUDE.md")):
        rel = path.relative_to(ROOT)
        if rel.as_posix() == "CLAUDE.md":
            continue
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        targets.append(TargetSpec(path=path))

    seen: set[Path] = set()
    unique: list[TargetSpec] = []
    for spec in targets:
        resolved = spec.path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(spec)
    return unique


def parse_target(raw: str) -> TargetSpec:
    raw = raw.strip()
    line = None
    candidate = raw
    if ":" in raw:
        maybe_path, maybe_line = raw.rsplit(":", 1)
        if maybe_line.isdigit():
            candidate = maybe_path
            line = int(maybe_line)
    path = Path(candidate)
    if not path.is_absolute():
        path = (ROOT / path).resolve(strict=False)
    return TargetSpec(path=path, line=line, explicit=True)


def normalize_token(token: str) -> str | None:
    token = token.strip().strip("`\"'")
    token = token.rstrip(".,:;)")
    if not token:
        return None
    if any(char.isspace() for char in token):
        return None
    if token.startswith(("http://", "https://", "mailto:", "#", "data:", "obsidian://")):
        return None
    if token.startswith("~"):
        return None
    if any(part in token for part in ("*", "{", "}", "$(", " | ", "<", ">")):
        return None
    if token.startswith("/"):
        return None
    if token in ROOT_DOC_NAMES:
        return token
    if token.startswith(KNOWN_PREFIXES):
        return token
    if "/" in token:
        if token.startswith(".") and not token.startswith(
            ("./", "../", ".claude/", ".codex/", ".agents/")
        ):
            return None
        suffix = Path(token.rstrip("/")).suffix
        if token.endswith("/") or suffix in PATH_SUFFIXES:
            return token
        return None
    return None


def resolve_token(source: Path, token: str) -> Path:
    if token.startswith("/"):
        return (ROOT / token.lstrip("/")).resolve(strict=False)
    if token in ROOT_DOC_NAMES:
        return (ROOT / token).resolve(strict=False)
    if token.startswith(("./", "../")):
        return (source.parent / token).resolve(strict=False)
    if "/" in token:
        source_relative = (source.parent / token).resolve(strict=False)
        if source_relative.exists():
            return source_relative
        return (ROOT / token).resolve(strict=False)
    return (ROOT / token).resolve(strict=False)


def extract_tokens(path: Path, line: str) -> list[str]:
    raw_tokens: list[str] = []
    if path.suffix == ".md":
        for match in MARKDOWN_LINK_RE.finditer(line):
            raw_tokens.append(match.group(1))
        for match in BACKTICK_RE.finditer(line):
            raw_tokens.append(match.group(1))
    else:
        for match in QUOTED_RE.finditer(line):
            raw_tokens.append(match.group(1))
        for match in BACKTICK_RE.finditer(line):
            raw_tokens.append(match.group(1))

    tokens: list[str] = []
    seen: set[str] = set()
    for raw in raw_tokens:
        normalized = normalize_token(raw)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
    return tokens


def validate_target(spec: TargetSpec) -> tuple[list[str], int]:
    errors: list[str] = []
    checked = 0
    path = spec.path

    if not path.exists():
        return [f"missing target: {display_path(path)}"], checked

    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return [f"target outside repo: {path}"], checked

    if not is_text_surface(path):
        return [f"target outside validated surface: {rel}"], checked

    lines = read_text(path).splitlines()
    if spec.line is not None and (spec.line < 1 or spec.line > len(lines)):
        return [f"missing target line: {rel}:{spec.line}"], checked

    for lineno, line in enumerate(lines, start=1):
        if spec.line is not None and lineno != spec.line:
            continue
        for token in extract_tokens(path, line):
            checked += 1
            target = resolve_token(path, token)
            try:
                target.relative_to(ROOT)
            except ValueError:
                errors.append(f"{rel}:{lineno}: {token} escapes repository root")
                continue
            if not target.exists():
                errors.append(f"{rel}:{lineno}: missing path reference `{token}`")
    return errors, checked


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str]) -> int:
    targets = [parse_target(arg) for arg in argv] if argv else default_targets()

    failures: list[str] = []
    checked_files = 0
    checked_refs = 0

    for spec in targets:
        errors, count = validate_target(spec)
        checked_refs += count
        if not errors:
            checked_files += 1
        else:
            failures.extend(errors)

    if failures:
        print("FAIL: context path validation")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"PASS: checked {checked_files} files and {checked_refs} path references")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
