"""Validate ADR-78's exhaustive public-template asset classification."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import tempfile
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


def classify_candidate_files(
    root: Path, manifest: dict[str, object]
) -> dict[str, str]:
    files = _candidate_files(root)
    rules = manifest["rules"]
    classified: dict[str, str] = {}
    unclassified: list[str] = []
    duplicate: list[dict[str, object]] = []
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
    if unclassified or duplicate:
        raise AssetManifestError(
            f"unclassified surfaces: {unclassified}; "
            f"surfaces with multiple classifications: {duplicate}"
        )
    return classified


# @spec FR-003
def classify_tracked_files(root: Path, manifest: dict[str, object]) -> dict[str, object]:
    files = _candidate_files(root)
    prohibited_patterns = manifest["prohibited_active_paths"]
    classified = classify_candidate_files(root, manifest)
    prohibited = [path for path in files if _matches(path, prohibited_patterns)]
    if prohibited:
        raise AssetManifestError(f"prohibited active surfaces: {prohibited}")

    counts = Counter(classified.values())
    return {
        "tracked_count": len(files),
        "classified_count": len(classified),
        "by_classification": dict(sorted(counts.items())),
        "unclassified": [],
        "duplicate": [],
        "prohibited": prohibited,
    }


def build_adopter_payload(
    root: Path,
    manifest: dict[str, object],
    boundary: dict[str, object],
    *,
    payload_path: str = "config/adopter-payload.json",
) -> dict[str, object]:
    remove = boundary.get("remove_classifications")
    if not isinstance(remove, list) or not all(isinstance(item, str) for item in remove):
        raise AssetManifestError("adopter boundary requires remove_classifications")
    classified = classify_candidate_files(root, manifest)
    files = []
    for relative, classification in sorted(classified.items()):
        if relative == payload_path:
            continue
        path = root / relative
        files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "classification": classification,
                "disposition": "remove" if classification in remove else "preserve",
            }
        )
    return {
        "$schema": "./adopter-payload.schema.json",
        "schema_version": 1,
        "generated_from": "config/template-assets.json",
        "files": files,
    }


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.close(descriptor)
        temp_path = Path(temp_name)
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temp_path, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.template_assets")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--write-adopter-payload", action="store_true")
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    manifest_path = args.manifest or root / "config/template-assets.json"
    try:
        manifest = load_manifest(manifest_path)
        report = classify_tracked_files(root, manifest)
        if args.write_adopter_payload:
            boundary_path = root / "config" / "adopter-boundary.json"
            boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
            payload_path = root / str(
                boundary.get("payload_manifest", "config/adopter-payload.json")
            )
            _atomic_write_json(
                payload_path,
                build_adopter_payload(
                    root,
                    manifest,
                    boundary,
                    payload_path=payload_path.relative_to(root).as_posix(),
                ),
            )
    except (AssetManifestError, jsonschema.ValidationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(json.dumps(report, indent=2) if args.as_json else "template asset classification: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
