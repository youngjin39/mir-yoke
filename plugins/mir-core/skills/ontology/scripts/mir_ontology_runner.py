#!/usr/bin/env python3
"""Copy to scripts/mir_ontology.py to run installed ontology tools (Python 3.9+)."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import pwd
except ImportError:
    pwd = None

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "mir-core@mir-yoke"
CHECKER = Path("skills/ontology/scripts/ontology_check.py")
SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)


def version_key(version: str) -> tuple[object, ...]:
    """Order release versions above prereleases without trusting cache mtimes."""
    match = SEMVER.fullmatch(version)
    if match is None:
        raise ValueError(f"invalid distribution version: {version}")
    major, minor, patch, prerelease = match.groups()
    if prerelease and any(
        part.isdigit() and len(part) > 1 and part.startswith("0") for part in prerelease.split(".")
    ):
        raise ValueError(f"invalid distribution version: {version}")
    parts = tuple((0, int(p)) if p.isdigit() else (1, p) for p in (prerelease or "").split("."))
    return (int(major), int(minor), int(patch), prerelease is None, parts)


def valid_version(version: str) -> bool:
    try:
        version_key(version)
    except ValueError:
        return False
    return True


def cache_root(home: Path, runtime: str) -> Path:
    return home / runtime / "plugins/cache/mir-yoke/mir-core"


def cached_versions(home: Path, runtime: str) -> list[Path]:
    root = cache_root(home, runtime)
    return [p for p in root.glob("*") if p.is_dir() and valid_version(p.name)]


def claude_active(home: Path) -> list[tuple[str, Path, str]]:
    metadata = home / ".claude/plugins/installed_plugins.json"
    if not metadata.is_file():
        return []
    try:
        records = (
            json.loads(metadata.read_text(encoding="utf-8")).get("plugins", {}).get(PLUGIN, [])
        )
        if not isinstance(records, list):
            raise ValueError("plugin records must be an array")
        active = []
        for record in records:
            version, install = record["version"], record["installPath"]
            if not isinstance(version, str) or not isinstance(install, str) or not install:
                raise ValueError("version and installPath must be strings")
            version_key(version)
            active.append((version, Path(install).expanduser() / CHECKER, "active Claude record"))
        return active
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise OSError(f"invalid active Claude metadata: {metadata}") from exc


def codex_fields(config: Path) -> dict[str, str]:
    """Read only the plugin table; handle the same small TOML subset on Python 3.9."""
    fields = {}
    selected = False
    table = re.compile(r"""\[\s*plugins\s*\.\s*["']mir-core@mir-yoke["']\s*\]\s*(?:#.*)?$""")
    with config.open(encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if line.startswith("["):
                selected = table.fullmatch(line) is not None
            elif selected:
                assignment = re.fullmatch(r"(enabled|version)\s*=\s*(.*)", line)
                if assignment:
                    key, value = assignment.groups()
                    if key in fields:
                        raise OSError(f"duplicate active Codex field: {key}")
                    # Supported values contain no '#'; other config tables are never parsed.
                    fields[key] = value.split("#", 1)[0].strip()
    return fields


def codex_active(home: Path) -> list[tuple[str, Path, str]]:
    config = home / ".codex/config.toml"
    if not config.is_file():
        return []
    fields = codex_fields(config)
    if not fields or fields.get("enabled") == "false":
        return []
    if fields.get("enabled") != "true":
        raise OSError(f"invalid active Codex enabled field: {config}")
    raw_version = fields.get("version")
    if raw_version is None:
        # Codex currently writes enabled=true without a version. One cached version
        # is unambiguous; multiple cached versions cannot establish the active one.
        versions = cached_versions(home, ".codex")
        if len(versions) != 1:
            raise OSError(
                f"active Codex distribution is {'ambiguous' if versions else 'missing'}: {config}"
            )
        version = versions[0].name
    else:
        match = re.fullmatch(r"""["']([^"']+)["']""", raw_version)
        if match is None or not valid_version(match.group(1)):
            raise OSError(f"invalid active Codex version: {config}")
        version = match.group(1)
    return [(version, cache_root(home, ".codex") / version / CHECKER, "active Codex configuration")]


def select_active_distribution(active: list[tuple[str, Path, str]]) -> tuple[str, Path, str]:
    if len({version for version, _, _ in active}) != 1:
        raise OSError(
            "runtime distributions disagree: " + ", ".join(sorted({v for v, _, _ in active}))
        )
    for _, checker, _ in active:
        if not checker.is_file():
            raise OSError(f"active ontology distribution is missing: {checker}")
    version, checker, reason = active[0]
    return version, checker.resolve(), reason


def select_distribution() -> tuple[str, Path, str]:
    explicit = os.environ.get("MIR_ONTOLOGY_CHECKER")
    if explicit is not None:
        checker = Path(explicit).expanduser()
        if not explicit or not checker.is_file():
            raise OSError(f"MIR_ONTOLOGY_CHECKER is not a file: {checker}")
        version = checker.parents[3].name if len(checker.parents) > 3 else "unknown"
        if not valid_version(version):
            version = "unknown"
        return version, checker.resolve(), "MIR_ONTOLOGY_CHECKER override"

    home_paths = [Path.home()]
    if pwd is not None:
        home_paths.append(Path(pwd.getpwuid(os.getuid()).pw_dir))
    homes = dict.fromkeys(home_paths)
    active = []
    for home in homes:
        active.extend(claude_active(home))
        active.extend(codex_active(home))
    if active:
        return select_active_distribution(active)

    candidates: list[tuple[str, Path, str]] = []
    for home in homes:
        for runtime in (".codex", ".claude"):
            candidates.extend(
                (p.name, p / CHECKER, "newest cached semver fallback")
                for p in cached_versions(home, runtime)
                if (p / CHECKER).is_file()
            )
    if not candidates:
        raise OSError(
            "Yoke ontology distribution is missing; install mir-core or set MIR_ONTOLOGY_CHECKER"
        )
    version, checker, reason = max(candidates, key=lambda item: version_key(item[0]))
    print(
        f"mir_ontology: warning: no active distribution; fallback to cached version {version}",
        file=sys.stderr,
    )
    return version, checker.resolve(), reason


def find_checker() -> Path:
    return select_distribution()[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--which", action="store_true", help="show selected version, path and reason"
    )
    parser.add_argument("command", nargs="?", choices=("mapping", "impact", "lookup", "mk"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if not args.which and args.command is None:
        parser.error("a command or --which is required")
    try:
        version, checker, reason = select_distribution()
        if args.which:
            print(f"version: {version}\npath: {checker}\nreason: {reason}")
            return 0
        forwarded = args.arguments
        if args.command == "mk":
            tool = checker.with_name("mk_query.py")
            soft = []
            if forwarded and forwarded[0] == "query":
                tail = forwarded[2:]
                if "--soft" in tail:
                    soft = ["--soft"]
                    forwarded = forwarded[:2] + [arg for arg in tail if arg != "--soft"]
            elif forwarded and forwarded[-1] == "--soft":
                soft = ["--soft"]
                forwarded = forwarded[:-1]
            command = [sys.executable, str(tool), "--repo", str(REPO_ROOT), *soft, *forwarded]
        else:
            tool = checker
            command = [
                sys.executable,
                str(tool),
                args.command,
                "--repo",
                str(REPO_ROOT),
                *forwarded,
            ]
        if not tool.is_file():
            raise OSError(f"Yoke ontology distribution is missing: {tool}")
        return subprocess.run(command, check=False).returncode
    except OSError as exc:
        print(f"mir_ontology: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
