"""Composable Mir Yoke distribution and preservation-first adoption CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from mir.core.distribution.builder import build_distribution
from mir.core.distribution.catalog import DistributionError, install_provider
from mir.core.distribution.composer import (
    CompositionError,
    apply_plan,
    create_plan,
    write_plan,
)


def _provider_home() -> Path:
    configured = os.environ.get("MIR_YOKE_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".mir-yoke"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yoke",
        description="Build and compose the optional Mir Yoke product planes.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="build deterministic core and pack archives")
    build.add_argument("--source-root", type=Path, default=Path.cwd())
    build.add_argument("--output-dir", type=Path, default=Path("dist"))
    build.add_argument("--version")
    build.add_argument("--require-clean", action="store_true")
    build.add_argument("--json", action="store_true", dest="as_json")

    provider = commands.add_parser("provider", help="manage immutable provider installations")
    provider_commands = provider.add_subparsers(dest="provider_command", required=True)
    install = provider_commands.add_parser("install", help="install a content-addressed provider")
    install.add_argument("--source-root", type=Path, default=Path.cwd())
    install.add_argument("--provider-home", type=Path, default=_provider_home())
    install.add_argument("--json", action="store_true", dest="as_json")

    plan = commands.add_parser("plan", help="inspect a target and create a non-mutating plan")
    _add_composition_options(plan)
    plan.add_argument("--output", type=Path)
    plan.add_argument("--json", action="store_true", dest="as_json")

    apply = commands.add_parser("apply", help="transactionally apply an accepted plan")
    apply.add_argument("target_root", type=Path)
    apply.add_argument("--source-root", type=Path, default=Path.cwd())
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _add_composition_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target_root", type=Path)
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--profile", default="minimal")
    parser.add_argument("--pack", action="append", default=[], dest="packs")
    parser.add_argument("--include-recommended", action="store_true")
    parser.add_argument("--without-core", action="store_true")


def _render(payload: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))


def _load_plan(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CompositionError("composition plan must be a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    namespace = _parser().parse_args(argv)
    try:
        if namespace.command == "build":
            result = build_distribution(
                namespace.source_root,
                namespace.output_dir,
                version=namespace.version,
                require_clean=namespace.require_clean,
            )
        elif namespace.command == "provider":
            installed = install_provider(namespace.source_root, namespace.provider_home)
            result = {
                "status": "installed",
                "provider": str(installed),
                "content_digest": installed.name,
            }
        elif namespace.command == "plan":
            result = create_plan(
                namespace.source_root,
                namespace.target_root,
                profile=namespace.profile,
                packs=tuple(namespace.packs),
                include_recommended=namespace.include_recommended,
                include_core=not namespace.without_core,
            )
            if namespace.output:
                write_plan(namespace.output, result)
        elif namespace.command == "apply":
            result = apply_plan(
                namespace.source_root,
                namespace.target_root,
                _load_plan(namespace.plan),
            )
        else:  # pragma: no cover - argparse owns the command choices
            return 2
    except (CompositionError, DistributionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _render(result, namespace.as_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
