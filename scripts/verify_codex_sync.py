#!/usr/bin/env python3
"""Verify checked-in Codex derivatives against their Claude sources."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".codex-sync" / "manifest.json"
PATH_SCOPED_INSTRUCTION_ROOTS = ("scripts", "src", "starter", "tests", "tools")
PLUGIN_SKILLS = {
    "mir-core": {
        "automation",
        "commit",
        "design",
        "efficiency",
        "governance",
        "memory-gc",
        "spec-architect",
        "verify",
    },
    "mir-code": {"bluebricks", "code-review", "testing"},
    "mir-content": {"knowledge", "ui-design"},
}


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
        if source_rel.as_posix() == "starter/CLAUDE.md":
            expected_marker = (
                "<!-- Mir Yoke publication derivative. After adoption, this "
                "repository owns this file and HARNESS.md remains canonical. -->"
            )
        else:
            expected_marker = (
                f"<!-- GENERATED FILE: edit {source_rel} and rerun "
                "scripts/generate_codex_derivatives.sh -->"
            )
        if not target_text.startswith(expected_marker):
            failures.append(f"nested AGENTS source marker drifted: {target_rel}")


def _read_json(path: Path, failures: list[str]) -> dict[str, object] | None:
    try:
        label = path.relative_to(ROOT)
    except ValueError:
        label = path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        failures.append(f"invalid JSON: {label}")
        return None
    if not isinstance(value, dict):
        failures.append(f"JSON root is not an object: {label}")
        return None
    return value


def is_product_adopter(root: Path = ROOT) -> bool:
    """Return whether local plugin providers have been externalized by bootstrap."""
    try:
        profile = tomllib.loads(
            (root / ".mir/repo-profile.toml").read_text(encoding="utf-8")
        )
    except (OSError, tomllib.TOMLDecodeError):
        return False
    repo = profile.get("repo")
    return isinstance(repo, dict) and repo.get("overlay_archetype") == "product_adopter"


def validate_plugin_skill_providers(
    failures: list[str], root: Path = ROOT, *, require_local: bool = True
) -> None:
    """Assert every common skill has exactly one dual-runtime plugin provider."""
    for legacy in (
        root / ".claude" / "skills",
        root / ".agents" / "skills",
        root / ".codex-sync" / "staging" / ".agents" / "skills",
    ):
        if legacy.exists() or legacy.is_symlink():
            failures.append(f"legacy raw skill provider remains: {legacy.relative_to(root)}")

    if not require_local:
        for provider in (
            *(root / "plugins" / name for name in PLUGIN_SKILLS),
            root / ".claude-plugin" / "marketplace.json",
            root / ".agents" / "plugins" / "marketplace.json",
        ):
            if provider.exists() or provider.is_symlink():
                failures.append(
                    f"product adopter retains local capability provider: "
                    f"{provider.relative_to(root)}"
                )
        return

    seen: dict[str, str] = {}
    for plugin_name, expected_skills in PLUGIN_SKILLS.items():
        plugin_root = root / "plugins" / plugin_name
        manifests = {}
        for runtime in ("claude", "codex"):
            path = plugin_root / f".{runtime}-plugin" / "plugin.json"
            payload = _read_json(path, failures)
            if payload is None:
                continue
            manifests[runtime] = payload
            if payload.get("name") != plugin_name:
                failures.append(f"{runtime} plugin name mismatch: {plugin_name}")
            if payload.get("version") != "0.8.0":
                failures.append(f"{runtime} plugin version mismatch: {plugin_name}")
        if len(manifests) == 2:
            for field in ("name", "version", "description", "repository", "license"):
                if manifests["claude"].get(field) != manifests["codex"].get(field):
                    failures.append(f"dual-runtime manifest drift: {plugin_name}.{field}")

        skills_root = plugin_root / "skills"
        actual_skills = {
            path.parent.name for path in skills_root.glob("*/SKILL.md") if path.is_file()
        }
        if actual_skills != expected_skills:
            failures.append(f"plugin skill inventory drift: {plugin_name}")
        for skill in actual_skills:
            if skill in seen:
                failures.append(
                    f"duplicate common skill provider: {skill} ({seen[skill]}, {plugin_name})"
                )
            seen[skill] = plugin_name
        if any(path.is_symlink() for path in plugin_root.rglob("*")):
            failures.append(f"plugin contains symlink: {plugin_name}")

    expected_names = set(PLUGIN_SKILLS)
    claude_market = _read_json(root / ".claude-plugin" / "marketplace.json", failures)
    codex_market = _read_json(root / ".agents" / "plugins" / "marketplace.json", failures)
    if claude_market is not None:
        names = {item.get("name") for item in claude_market.get("plugins", [])}
        if names != expected_names:
            failures.append("Claude marketplace plugin inventory drift")
    if codex_market is not None:
        names = {item.get("name") for item in codex_market.get("plugins", [])}
        if names != expected_names:
            failures.append("Codex marketplace plugin inventory drift")


def _directory_digest(root: Path) -> str | None:
    if root.is_symlink() or not root.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            return None
        digest.update(relative)
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_portable_hook_copy(
    failures: list[str], *, source_root: Path = ROOT, output_root: Path = ROOT
) -> None:
    source = source_root / ".claude" / "hooks" / "lib"
    target = output_root / ".codex" / "hooks" / "lib"
    if _directory_digest(source) != _directory_digest(target):
        failures.append("portable Codex hook library drift")


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
    validate_plugin_skill_providers(failures, require_local=not is_product_adopter())
    validate_portable_hook_copy(failures)

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
                and mapping.get("change_scope") != "directory"
                for target in mapping["targets"]
            )
            for relative in sorted(generated_files):
                expected = generated_root / relative
                actual = ROOT / relative
                if not expected.is_file() or not actual.is_file():
                    failures.append(f"missing generated file: {relative}")
                elif expected.read_bytes() != actual.read_bytes():
                    failures.append(f"generated drift: {relative}")
            if (generated_root / ".agents" / "skills").exists():
                failures.append("generator recreated a legacy raw skill provider")
            validate_portable_hook_copy(
                failures,
                source_root=ROOT,
                output_root=generated_root,
            )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("OK: Codex derivatives match Claude sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
