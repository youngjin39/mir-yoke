"""CLI for bounded, declared relation graph retrieval."""

from __future__ import annotations

import argparse
import sys

from mir.core.relations import (
    DEFAULT_DEPTH,
    DEFAULT_GRAPH,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_EDGES,
    RelationError,
    bundle_relations,
    query_relations,
    render_bundle_human,
    render_human,
    render_json,
)

_PURPOSES = ("implementation", "impact", "verification", "dependencies")


def _common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".")
    parser.add_argument("--graph", default=DEFAULT_GRAPH)
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--max-edges", type=int, default=DEFAULT_MAX_EDGES)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--json", action="store_true")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mir relations")
    commands = parser.add_subparsers(dest="command", required=True)
    query = commands.add_parser("query")
    query.add_argument("anchor")
    query.add_argument("--purpose", required=True, choices=_PURPOSES)
    _common_options(query)
    bundle = commands.add_parser("bundle")
    bundle.add_argument("anchors", nargs="+")
    bundle.add_argument("--purpose", action="append", required=True, choices=_PURPOSES)
    _common_options(bundle)
    args = parser.parse_args(argv)
    try:
        if args.command == "bundle":
            result = bundle_relations(
                args.anchors,
                args.purpose,
                root=args.root,
                graph=args.graph,
                depth=args.depth,
                max_edges=args.max_edges,
                max_bytes=args.max_bytes,
            )
            output = (
                render_json(result, args.max_bytes)
                if args.json
                else render_bundle_human(result, args.max_bytes)
            )
        else:
            result = query_relations(
                args.anchor,
                args.purpose,
                root=args.root,
                graph=args.graph,
                depth=args.depth,
                max_edges=args.max_edges,
                max_bytes=args.max_bytes,
            )
            output = (
                render_json(result, args.max_bytes)
                if args.json
                else render_human(result, args.max_bytes)
            )
    except RelationError as exc:
        print(f"relations: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(output)
    return 0
