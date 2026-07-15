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


def _source_paths(source: str) -> list[Path]:
    return [ROOT / item.strip() for item in source.split("+") if item.strip()]


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
