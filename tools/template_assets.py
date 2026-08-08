"""Validate ADR-78's exhaustive public-template asset classification."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from collections import Counter
from pathlib import Path

import jsonschema

CLASSIFICATIONS = frozenset(
    {
        "starter",
        "reference",
        "optional-consumer-tool",
        "template-maintainer-tool",
        "historical",
    }
)


class AssetManifestError(ValueError):
    """The asset manifest is invalid or does not cover the release candidate."""


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def load_manifest(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    schema_path = path.parent / "template-assets.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)
    if set(manifest["classifications"]) != CLASSIFICATIONS:
        raise AssetManifestError("classification enum does not match ADR-78")
    rule_ids = [rule["id"] for rule in manifest["rules"]]
    if len(rule_ids) != len(set(rule_ids)):
        raise AssetManifestError("asset rule ids must be unique")
    return manifest


def _candidate_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(path for path in result.stdout.splitlines() if path and (root / path).is_file())


# @spec FR-003
def classify_tracked_files(root: Path, manifest: dict[str, object]) -> dict[str, object]:
    files = _candidate_files(root)
    rules = manifest["rules"]
    prohibited_patterns = manifest["prohibited_active_paths"]
    classified: dict[str, str] = {}
    unclassified: list[str] = []
    duplicate: list[dict[str, object]] = []
    prohibited = [path for path in files if _matches(path, prohibited_patterns)]

    for path in files:
        matches = [
            rule
            for rule in rules
            if _matches(path, rule["include"]) and not _matches(path, rule["exclude"])
        ]
        if not matches:
            unclassified.append(path)
        elif len(matches) > 1:
            duplicate.append({"path": path, "rules": [rule["id"] for rule in matches]})
        else:
            classified[path] = matches[0]["classification"]

    errors: list[str] = []
    if unclassified:
        errors.append(f"unclassified surfaces: {unclassified}")
    if duplicate:
        errors.append(f"surfaces with multiple classifications: {duplicate}")
    if prohibited:
        errors.append(f"prohibited active surfaces: {prohibited}")
    if errors:
        raise AssetManifestError("; ".join(errors))

    counts = Counter(classified.values())
    return {
        "tracked_count": len(files),
        "classified_count": len(classified),
        "by_classification": dict(sorted(counts.items())),
        "unclassified": unclassified,
        "duplicate": duplicate,
        "prohibited": prohibited,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.template_assets")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    manifest_path = args.manifest or root / "config/template-assets.json"
    try:
        report = classify_tracked_files(root, load_manifest(manifest_path))
    except (AssetManifestError, jsonschema.ValidationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(report, indent=2) if args.as_json else "template asset classification: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
