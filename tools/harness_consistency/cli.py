from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.harness_consistency.generate import build_manifest
from tools.harness_consistency.runner import run


def _default_project_root() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "config" / "harness-consistency.json").exists():
            return candidate
    return cwd


def _format_console(result: dict) -> str:
    summary = result["summary"]
    lines = [
        f"repo: {result['repo'].get('slug', '')}",
        f"overall: {result['overall']}",
        (
            "summary: "
            f"total={summary['total']} "
            f"error={summary['error']} "
            f"warn={summary['warn']} "
            f"info={summary['info']}"
        ),
    ]
    for finding in result["findings"]:
        location = f" ({finding['location']})" if finding["location"] else ""
        lines.append(
            "[{severity}] {rule_id} {rule_name}: {message}{location}".format(
                severity=finding["severity"],
                rule_id=finding["rule_id"],
                rule_name=finding["rule_name"],
                message=finding["message"],
                location=location,
            )
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.harness_consistency")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--project-root", type=Path, default=None)
    run_parser.add_argument("--manifest", type=Path, default=None)
    run_parser.add_argument("--format", choices=("console", "json"), default="console")
    run_parser.add_argument("--report", type=Path, default=None)

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--repo-root", type=Path, required=True)
    generate_parser.add_argument("--profile", type=Path, default=None)
    generate_parser.add_argument("--output", type=Path, default=None)
    generate_parser.add_argument("--green", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        manifest = build_manifest(args.repo_root, args.profile, green=args.green)
        output = json.dumps(manifest, indent=2) + "\n"
        if args.output is not None:
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        return 0

    if args.command != "run":
        parser.error(f"unsupported command: {args.command}")

    project_root = args.project_root.resolve() if args.project_root else _default_project_root()
    result = run(project_root, args.manifest)
    output = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else _format_console(result)
    )

    if args.report is not None:
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(output)
    return 0 if result["overall"] == "pass" else 1
