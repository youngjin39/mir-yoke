#!/usr/bin/env python3
"""Verify checked-in Codex derivatives against their Claude sources."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".codex-sync" / "manifest.json"
PATH_SCOPED_INSTRUCTION_ROOTS = ("scripts", "src", "tests", "tools")


def _source_paths(source: str) -> list[Path]:
    return [ROOT / item.strip() for item in source.split("+") if item.strip()]


def nested_instruction_pairs(root: Path = ROOT) -> list[tuple[Path, Path]]:
    """Return path-scoped Claude sources and their generated Codex targets."""
    pairs: list[tuple[Path, Path]] = []
    for relative_root in PATH_SCOPED_INSTRUCTION_ROOTS:
        source_root = root / relative_root
        if not source_root.is_dir():
            continue
        for source in source_root.rglob("CLAUDE.md"):
            pairs.append((source, source.with_name("AGENTS.md")))
    return sorted(pairs)


def validate_nested_instruction_derivatives(
    failures: list[str], root: Path = ROOT
) -> None:
    """Pin source direction and Codex-local references for path-scoped rules."""
    for source, target in nested_instruction_pairs(root):
        source_rel = source.relative_to(root)
        target_rel = target.relative_to(root)
        if not target.is_file():
            failures.append(f"missing nested AGENTS derivative: {target_rel}")
            continue
        target_text = target.read_text(encoding="utf-8")
        body = target_text.split("\n", 2)[-1]
        if "CLAUDE.md" in body:
            failures.append(
                f"nested AGENTS derivative retains Claude-only path reference: {target_rel}"
            )
        expected_marker = (
            f"<!-- GENERATED FILE: edit {source_rel} and rerun "
            "scripts/generate_codex_derivatives.sh -->"
        )
        if not target_text.startswith(expected_marker):
            failures.append(f"nested AGENTS source marker drifted: {target_rel}")


def main() -> int:
    failures: list[str] = []
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for mapping in manifest.get("mappings", []):
        source = mapping.get("source", "")
        targets = mapping.get("targets", [])
        if not source or not targets:
            failures.append(f"invalid empty mapping: {mapping!r}")
            continue
        for path in _source_paths(source):
            if not path.exists():
                failures.append(f"missing source: {path.relative_to(ROOT)}")
        for target in targets:
            path = ROOT / target
            if not path.exists() and not path.is_symlink():
                failures.append(f"missing target: {target}")
            if (
                mapping.get("sync_policy") == "symlink"
                and source.startswith(".claude/skills/")
            ):
                if not path.is_symlink():
                    failures.append(f"project skill target is not a directory symlink: {target}")
                elif path.resolve() != (ROOT / source).resolve():
                    failures.append(f"project skill target resolves to the wrong source: {target}")
                staging_path = ROOT / ".codex-sync" / "staging" / target
                if not staging_path.is_symlink():
                    failures.append(
                        f"staged project skill target is not a directory symlink: {target}"
                    )
                elif staging_path.resolve() != (ROOT / source).resolve():
                    failures.append(
                        f"staged project skill target resolves to the wrong source: {target}"
                    )

    agents_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    if "- Skills: `" in agents_text:
        failures.append("AGENTS.md duplicates the auto-discovered skill catalog")
    if "adopt it as your session contract" in agents_text:
        failures.append("AGENTS.md forces a custom-agent body into main startup context")
    if "project_doc_fallback_filenames" in (ROOT / ".codex" / "config.toml").read_text(
        encoding="utf-8"
    ):
        failures.append("Codex config redundantly declares AGENTS.md as its own fallback")
    validate_nested_instruction_derivatives(failures)

    with tempfile.TemporaryDirectory(prefix="mir-yoke-codex-sync-") as temp_dir:
        env = os.environ.copy()
        env["CODEX_DERIVATION_OUTPUT_ROOT"] = temp_dir
        generated = subprocess.run(
            ["bash", str(ROOT / "scripts" / "generate_codex_derivatives.sh")],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if generated.returncode != 0:
            failures.append(generated.stderr.strip() or "generator failed")
        else:
            generated_root = Path(temp_dir)
            generated_manifest = json.loads(
                (generated_root / ".codex-sync" / "manifest.json").read_text(encoding="utf-8")
            )
            generated_files = {"AGENTS.md", ".codex/config.toml", ".codex-sync/manifest.json"}
            generated_files.update(
                target
                for mapping in generated_manifest["mappings"]
                if mapping.get("sync_policy") == "regenerate"
                for target in mapping["targets"]
            )
            for relative in sorted(generated_files):
                expected = generated_root / relative
                actual = ROOT / relative
                if not expected.is_file() or not actual.is_file():
                    failures.append(f"missing generated file: {relative}")
                elif expected.read_bytes() != actual.read_bytes():
                    failures.append(f"generated drift: {relative}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("OK: Codex derivatives match Claude sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
