"""CLI for pinned global capability providers and project-local agent updates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mir.core.capabilities import CapabilityConfigError, CapabilityError, CapabilityManager

from ._changes import changed_paths, snapshot_project


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mir capability")
    subcommands = parser.add_subparsers(dest="command", required=True)

    for name in ("status", "check", "sync", "update"):
        command = subcommands.add_parser(name)
        _add_common_options(command)
        command.add_argument("--profile")
        if name in {"sync", "update"}:
            command.add_argument(
                "--apply",
                action="store_true",
                help="materialize the pinned provider and update its exact-SHA lock",
            )

    finalize = subcommands.add_parser("finalize")
    _add_common_options(finalize)
    finalize.add_argument("--apply", action="store_true")
    finalize.add_argument(
        "--after-restart",
        action="store_true",
        help="confirm that operator observations came from restarted runtime sessions",
    )
    attest = subcommands.add_parser("attest")
    _add_common_options(attest)
    attest.add_argument("--runtime", choices=("claude-code", "codex-cli-desktop"), required=True)
    attest.add_argument(
        "--observed-skill",
        action="append",
        default=[],
        help="operator-observed namespaced skill from the current runtime catalog",
    )
    attest.add_argument("--apply", action="store_true")
    return parser


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path)
    parser.add_argument("--capability-home", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")


def _render(payload: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    # @spec CR-004 FR-005 QR-003
    namespace = _parser().parse_args(argv)
    project_root = namespace.project_root.expanduser().resolve()
    before = snapshot_project(project_root)
    try:
        manager = CapabilityManager(
            project_root,
            config_path=namespace.config,
            capability_home=namespace.capability_home,
        )
        if namespace.command == "status":
            result = manager.status(namespace.profile)
        elif namespace.command == "check":
            result = manager.check(namespace.profile)
        elif namespace.command == "sync":
            result = manager.sync(namespace.profile, apply=namespace.apply)
        elif namespace.command == "update":
            result = manager.update(namespace.profile, apply=namespace.apply)
        elif namespace.command == "finalize":
            result = manager.finalize(
                apply=namespace.apply,
                after_restart=namespace.after_restart,
            )
        elif namespace.command == "attest":
            result = manager.attest(
                namespace.runtime,
                namespace.observed_skill,
                apply=namespace.apply,
            )
        else:  # pragma: no cover - argparse owns the command choices
            return 2
    except (CapabilityConfigError, CapabilityError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    result["changed_paths"] = changed_paths(before, snapshot_project(project_root))
    _render(result, namespace.as_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
