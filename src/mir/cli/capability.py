"""CLI for pinned global capability providers and project-local agent updates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mir.core.capabilities import CapabilityConfigError, CapabilityError, CapabilityManager
from mir.core.capabilities.mcp import closed_json

from ._changes import changed_paths, snapshot_project


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mir capability")
    subcommands = parser.add_subparsers(dest="command", required=True)

    for name in ("status", "check", "sync", "update"):
        command = subcommands.add_parser(name)
        _add_common_options(command)
        command.add_argument("--profile")
        if name != "status":
            command.add_argument(
                "--mcp",
                action=argparse.BooleanOptionalAction,
                default=None,
                help=("explicitly select mir-mcp (or remove it with --no-mcp); "
                      "otherwise retain the lock"),
            )
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
    attest.add_argument(
        "--observed-hook",
        action="append",
        default=[],
        help="operator-observed namespaced hook from the current runtime session",
    )
    attest.add_argument("--apply", action="store_true")
    attest.add_argument(
        "--mcp-evidence",
        type=Path,
        help="JSON object of operator-observed MCP evidence keyed by package name",
    )
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
    try:
        manager = CapabilityManager(
            project_root,
            config_path=namespace.config,
            capability_home=namespace.capability_home,
        )
        before = None if namespace.command == "status" else snapshot_project(project_root)
        if namespace.command == "status":
            result = manager.status(namespace.profile)
        elif namespace.command == "check":
            result = manager.check(
                namespace.profile, **({"mcp": namespace.mcp} if namespace.mcp is not None else {})
            )
        elif namespace.command == "sync":
            result = manager.sync(
                namespace.profile,
                apply=namespace.apply,
                **({"mcp": namespace.mcp} if namespace.mcp is not None else {}),
            )
        elif namespace.command == "update":
            result = manager.update(
                namespace.profile,
                apply=namespace.apply,
                **({"mcp": namespace.mcp} if namespace.mcp is not None else {}),
            )
        elif namespace.command == "finalize":
            result = manager.finalize(
                apply=namespace.apply,
                after_restart=namespace.after_restart,
            )
        elif namespace.command == "attest":
            mcp_evidence = {}
            if namespace.mcp_evidence is not None:
                try:
                    mcp_evidence["observed_mcp"] = closed_json(namespace.mcp_evidence)
                except (ValueError, OSError) as exc:
                    raise CapabilityError("cannot read MCP evidence JSON object") from exc
            result = manager.attest(
                namespace.runtime,
                namespace.observed_skill,
                namespace.observed_hook,
                apply=namespace.apply,
                **mcp_evidence,
            )
        else:  # pragma: no cover - argparse owns the command choices
            return 2
    except (CapabilityConfigError, CapabilityError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if before is not None:
        result["changed_paths"] = changed_paths(before, snapshot_project(project_root))
    else:
        result["change_evidence"] = {
            "status": "not-applicable",
            "reason": "read-only-operation",
        }
    _render(result, namespace.as_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
