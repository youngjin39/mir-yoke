"""Capture read-only execution binding and rendering hooks from an explicit owner."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import runpy
import sys
import unicodedata

import pydantic

BASE = runpy.run_path(str(pathlib.Path(__file__).with_name("generate_executor_hub_profile.py")))


def payload():
    value = BASE["brief_payload"]("  exact café 漢字 😀\ncontract goal  ")
    value.update(tdd_change_refs=["tasks/tdd.json#change"], owned_scope=["code.txt", "src/**"])
    return value


def capture(owner, scratch):
    paths = dict(
        local=owner / "tools/mir_executor/local.py",
        contracts=owner / "src/mir/core/contracts/dispatch_brief.py",
        loader=owner / "src/mir/core/conductor/dispatch_brief.py",
    )
    sources = {key: path.read_text(encoding="utf-8") for key, path in paths.items()}
    hooks = {
        "validate_brief",
        "pre_execute",
        "render_brief",
        "_resolve_family",
        "_map_verify_commands",
        "_argv",
        "_scope_covers",
        "_validate_dispatch_brief_execution",
        "_active_instruction",
    }
    oracle = (
        "from __future__ import annotations\nimport argparse, json, pathlib, shlex\n"
        "from collections.abc import Mapping\n"
        "from tools.mir_executor.local_hooks import local_config\n"
        "_INSTRUCTIONS = {}\n"
        + sources["contracts"].replace("from __future__ import annotations", "")
        + "\n"
        + BASE["functions"](sources["loader"], {"load_dispatch_brief"}).replace(
            "path: Path", "path: pathlib.Path"
        )
        + "\n"
        + BASE["functions"](sources["local"], hooks)
        + "\n"
        "import sys, types\n"
        '_loader = types.ModuleType("mir.core.conductor.dispatch_brief")\n'
        "_loader.load_dispatch_brief = load_dispatch_brief\n"
        "sys.modules[_loader.__name__] = _loader\n"
    )
    namespace = {}
    exec(oracle, namespace)
    namespace["DispatchBrief"].model_rebuild(_types_namespace=namespace)
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "config").mkdir(exist_ok=True)
    verifiers = {"offline": ["check"], "last": ["check"], "other": ["other"]}
    (scratch / "config/mir-executor.local.json").write_text(json.dumps({"verifiers": verifiers}))
    agent = scratch / ".claude/agents/offline-agent.md"
    agent.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    variants = [
        ("default", {}, {}),
        ("subset", {}, {"allow_paths": ["src/a", "./code.txt/"]}),
        ("outside", {}, {"allow_paths": ["other.txt"]}),
        ("scope_prefix", {}, {"allow_paths": ["src-other/a"]}),
        ("tdd_mismatch", {}, {"change_id": "other"}),
        ("tdd_exact", {}, {"change_id": "change"}),
        ("mapped_argv", {"verification_commands": ["check"]}, {"verify_cmds": ["check"]}),
        ("quoted_argv", {"verification_commands": ["'check'"]}, {"verify_cmds": ["check"]}),
        ("malformed_declared", {"verification_commands": ["'check"]}, {"verify_cmds": ["'check"]}),
        ("malformed_requested", {}, {"verify_cmds": ["'check"]}),
        ("undeclared_verifier", {}, {"verify_cmds": ["other", "unknown"]}),
        ("missing_agent", {}, {}),
        ("wrong_path", {}, {}),
        ("mapped_path_error", {}, {"verify_cmds": ["check"]}),
        ("multiple_binding_errors", {}, {"change_id": "other", "allow_paths": ["other"]}),
        ("malformed_json", {}, {}),
        ("missing_file", {}, {}),
        (
            "initial_instruction",
            {},
            {"codex_args": "exec --model fixture '  active café 漢字 😀  '"},
        ),
        ("file_instruction", {}, {"codex_args_file": "<root>/instruction.txt"}),
        ("malformed_instruction", {}, {"codex_args": "'unterminated"}),
        (
            "conflicting_instruction",
            {},
            {"codex_args": "exec instruction", "codex_args_file": "<root>/instruction.txt"},
        ),
        ("missing_instruction", {}, {"codex_args_file": "<root>/missing.txt"}),
        ("plain", {}, {"dispatch": False, "dispatch_brief": None}),
    ]
    for name, changes, supplied in variants:
        body = payload()
        body.update(changes)
        brief_path = scratch / body["resume_state_ref"]
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        raw = "{" if name == "malformed_json" else json.dumps(body)
        brief_path.write_text(raw)
        if name == "missing_file":
            brief_path.unlink()
        if name in ("wrong_path", "mapped_path_error"):
            brief_path = scratch / "brief.json"
            brief_path.write_text(raw)
        agent.write_text("Offline profile.\n")
        if name in ("missing_agent", "multiple_binding_errors"):
            agent.unlink()
        (scratch / "instruction.txt").write_text("  file café 漢字 😀\nstep  ")
        args = dict(
            repo_root=str(scratch),
            dispatch=True,
            dispatch_brief=str(brief_path),
            change_id=None,
            allow_paths=["code.txt"],
            verify_cmds=["offline"],
        )
        args.update(supplied)
        if args.get("codex_args_file"):
            args["codex_args_file"] = pathlib.Path(
                str(args["codex_args_file"]).replace("<root>", str(scratch))
            )
        argument = argparse.Namespace(**args)
        # Real CLI receives pathlib-valued repo roots and input files.
        argument.repo_root = scratch
        namespace["_INSTRUCTIONS"].clear()
        outcome = {}
        try:
            namespace["pre_execute"](argument, scratch)
            if argument.dispatch and argument.dispatch_brief:
                validated = namespace["validate_brief"](
                    pathlib.Path(argument.dispatch_brief), scratch
                )
                outcome["rendered"] = namespace["render_brief"](validated, scratch)
                outcome["rendered_again"] = namespace["render_brief"](validated, scratch)
        except Exception as error:
            outcome = dict(kind=type(error).__name__, message=str(error))

        def normalized(value):
            return json.loads(
                json.dumps(value, default=str).replace(json.dumps(str(scratch))[1:-1], "<root>")
            )

        cases.append(
            dict(
                name=name,
                payload=body,
                raw=raw,
                args=normalized(args),
                patch=normalized(vars(argument)),
                **normalized(outcome),
            )
        )
    missing_instruction = namespace["_active_instruction"](
        argparse.Namespace(resume_job_id="missing", jobs_db=scratch / "tasks/jobs.db"),
        namespace["DispatchBrief"](**payload()),
    )
    return dict(
        oracle_source=oracle,
        cases=cases,
        verifiers=verifiers,
        missing_resume_instruction=missing_instruction,
        config_raw=json.dumps({"verifiers": verifiers}),
        sha256={key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()},
        runtime=dict(
            python=sys.version.split()[0],
            pydantic=pydantic.__version__,
            unicode=unicodedata.unidata_version,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for field in ("owner", "scratch", "output"):
        parser.add_argument("--" + field, type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(capture(args.owner, args.scratch), indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
