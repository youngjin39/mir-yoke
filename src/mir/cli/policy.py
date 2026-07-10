"""mir policy — sub-agent policy helpers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.mir_executor.policy import load_sub_agent_policy


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mir policy")
    subcommands = p.add_subparsers(dest="command", required=True)

    resolve = subcommands.add_parser("resolve", help="resolve category routing")
    resolve.add_argument("--category", required=True, help="TDD category to resolve")
    resolve.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="repository root (default: cwd)",
    )
    resolve.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="output format (default: json)",
    )
    return p.parse_args(argv)


def _handle_resolve(ns: argparse.Namespace) -> int:
    repo_root = ns.repo_root or Path.cwd()
    policy = load_sub_agent_policy(repo_root)
    result = policy.resolve_category(ns.category)
    if ns.format == "json":
        print(json.dumps(result))
    else:
        print(f"model={result['model'] or ''}")
        print(f"reasoning_effort={result['reasoning_effort'] or ''}")
    return 0


def main(argv: list[str]) -> int:
    ns = _parse(argv)
    if ns.command == "resolve":
        return _handle_resolve(ns)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
