"""Capture common parser metadata and admission refusal bytes without launching providers."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pathlib
import sys
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor import cli_parser, local_hooks  # noqa: E402

scratch = pathlib.Path(os.environ["E2B_SCRATCH"])
scratch.mkdir(parents=True, exist_ok=True)
parser = cli_parser._build_parser(scratch, register_local_options=False)
commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
schema = {}
for name, sub in commands.choices.items():
    options = []
    for action in sub._actions:
        default = action.default
        if isinstance(default, pathlib.Path):
            default = {"$type": "path", "value": "$cwd"}
        options.append(
            {
                "flags": action.option_strings,
                "dest": action.dest,
                "default": default,
                "required": action.required,
                "choices": list(action.choices) if action.choices else None,
                "kind": type(action).__name__,
                "type": getattr(action.type, "__name__", None),
            }
        )
    schema[name] = options
pathlib.Path(__file__).with_name("executor_admission_schema.json").write_text(
    json.dumps(schema, ensure_ascii=True, indent=2) + "\n"
)
cases = []
for command in ("execute", "status", "result", "cancel", "sweep"):
    args = [command, "--repo-root", str(scratch / "target")]
    if command in ("status", "result", "cancel"):
        args += ["--job-id", "fixture"]
    parsed = parser.parse_args(args)
    stderr = io.StringIO()
    with (
        patch.object(
            local_hooks, "__file__", str(scratch / "home/tools/mir_executor/local_hooks.py")
        ),
        patch.object(
            local_hooks.subprocess,
            "run",
            return_value=argparse.Namespace(returncode=0, stdout=str(scratch / "home")),
        ),
        patch.object(local_hooks, "invoke_hook", side_effect=RuntimeError("fixture refusal")),
        contextlib.redirect_stderr(stderr),
    ):
        try:
            local_hooks.authorize_target(scratch / "target", parsed)
        except ValueError as exc:
            print(f"[mir_executor] {exc}", file=sys.stderr)
    cases.append(
        {
            "command": command,
            "stderr": stderr.getvalue().replace(str(scratch), "$scratch"),
            "code": 1,
        }
    )
pathlib.Path(__file__).with_name("executor_admission.json").write_text(
    json.dumps(cases, ensure_ascii=True, indent=2) + "\n"
)
print(f"captured {len(cases)} admission cases and {len(schema)} command schemas")

with patch.object(pathlib.Path, "cwd", return_value=scratch / "target"):
    common = cli_parser._build_parser(scratch / "target", register_local_options=False)
parsed_cases = []
for argv in (
    ["execute"],
    ["execute", "--family", "selected", "--dispatch", "--codex-args", "task"],
    ["execute", "--timeout", "42", "--stall-timeout", "1.5", "--no-expect-changes"],
    ["execute", "--allow-path", "src/", "--allow-path", "docs/", "--verify-cmd", "check"],
    ["execute", "--execution-backend", "claude", "--category", "unit", "-a", "-b"],
    ["execute", "--codex-args-file", "prompt.txt", "--dispatch-brief", "brief.json"],
    ["execute", "--max-codex-attempts", "2", "--finalize-lock-timeout", "0"],
    ["status", "--job-id", "fixture"],
    ["result", "--job-id", "fixture"],
    ["cancel", "--job-id", "fixture"],
    ["sweep", "--apply", "--grace-seconds", "0"],
):
    parsed = common.parse_args(argv)
    if parsed.subcommand == "execute":
        parsed.repo_root = parsed.repo_root.resolve()
    expected = {
        key: {"$type": "path", "value": str(value).replace(str(scratch), "$scratch")}
        if isinstance(value, pathlib.Path)
        else value
        for key, value in vars(parsed).items()
    }
    parsed_cases.append({"argv": argv, "expected": expected})
pathlib.Path(__file__).with_name("executor_admission_args.json").write_text(
    json.dumps(parsed_cases, ensure_ascii=True, indent=2) + "\n"
)
print(f"captured {len(parsed_cases)} parsed argument cases")
