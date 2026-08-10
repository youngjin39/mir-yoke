"""Create and verify an installed Mir CLI runtime manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mir.core.adoption.runtime import create_runtime_manifest, verify_runtime_manifest


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mir runtime-manifest")
    subcommands = parser.add_subparsers(dest="command", required=True)
    create = subcommands.add_parser("create")
    create.add_argument("--runtime-root", required=True, type=Path)
    create.add_argument("--manifest", required=True, type=Path)
    create.add_argument("--source-url", required=True)
    create.add_argument("--source-commit", required=True)
    create.add_argument("--constraints-sha256", required=True)
    verify = subcommands.add_parser("verify")
    verify.add_argument("--runtime-root", required=True, type=Path)
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--source-url", required=True)
    verify.add_argument("--source-commit", required=True)
    verify.add_argument("--constraints-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    ns = _parse(argv)
    try:
        if ns.command == "create":
            document = create_runtime_manifest(
                ns.runtime_root,
                ns.manifest,
                source_url=ns.source_url,
                source_commit=ns.source_commit,
                constraints_sha256=ns.constraints_sha256,
            )
            print(json.dumps({"status": "created", "entries": len(document["entries"])}))
            return 0
        findings = verify_runtime_manifest(
            ns.runtime_root,
            ns.manifest,
            source_url=ns.source_url,
            source_commit=ns.source_commit,
            constraints_sha256=ns.constraints_sha256,
        )
    except (OSError, ValueError) as exc:
        print(f"runtime manifest error: {exc}", file=sys.stderr)
        return 2
    if findings:
        for finding in findings:
            print(f"runtime manifest error: {finding}", file=sys.stderr)
        return 2
    return 0
