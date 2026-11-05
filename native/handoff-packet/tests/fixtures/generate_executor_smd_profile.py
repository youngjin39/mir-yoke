"""Capture execution schema parity from an explicitly supplied read-only owner."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import sys
import types
import unicodedata

import pydantic


def capture(owner: pathlib.Path, scratch: pathlib.Path) -> dict:
    paths = {
        "contracts": owner / "src/mir/core/contracts/dispatch_brief.py",
        "loader": owner / "src/mir/core/conductor/dispatch_brief.py",
        "local": owner / "tools/mir_executor/local.py",
    }
    contract = paths["contracts"].read_text()
    loader = paths["loader"].read_text()
    node = next(
        n
        for n in ast.parse(loader).body
        if isinstance(n, ast.FunctionDef) and n.name == "load_dispatch_brief"
    )
    loader_function = ast.get_source_segment(loader, node)
    module = types.ModuleType("mir.core.contracts.dispatch_brief")
    sys.modules[module.__name__] = module
    exec(contract, module.__dict__)
    exec("import json\nfrom pathlib import Path\n" + loader_function, module.__dict__)
    good = dict(
        task_id="task",
        slice_id="slice",
        target_agent="executor-agent",
        user_intent="Bounded work",
        expanded_goal="Update café 漢字 😀",
        owned_scope=["src/module.rs"],
        verification_commands=["cargo test"],
        stop_conditions=["Stop outside scope"],
        resume_state_ref="tasks/dispatch/task/slice.json",
        source_refs=dict(task_spec="runtime://task", phase="tasks/phase.json"),
    )
    variants = [("valid", good), ("missing_all", {}), ("root_list", []), ("root_null", None)]
    for key in ("task_id", "phase_id", "slice_id", "target_agent"):
        for i, value in enumerate(
            [None, "", "a", "a" * 128, "a" * 129, "-a", "a.b_C-0", "a/b", "a\n", "é", 7]
        ):
            payload = dict(good, **{key: value})
            if key in ("task_id", "slice_id") and isinstance(value, str):
                payload["resume_state_ref"] = (
                    f"tasks/dispatch/{payload['task_id']}/{payload['slice_id']}.json"
                )
            variants.append((f"{key}_{i}", payload))
    tuples = (
        "owned_scope",
        "out_of_scope",
        "verification_commands",
        "stop_conditions",
        "handoff_refs",
        "tdd_change_refs",
    )
    for key in tuples:
        for i, value in enumerate(
            [
                [],
                ["same", "same"],
                [" \t\n"],
                [""],
                [1, None],
                [1],
                None,
                "src",
                ["src/./module.rs"],
                ["src//module.rs"],
                ["../escape"],
                ["/absolute"],
                ["src\\file"],
                ["<unspecified>"],
                ["src/**"],
                ["tasks/tdd.json#id"],
                ["tasks/tdd.json#"],
            ]
        ):
            variants.append((f"{key}_{i}", dict(good, **{key: value})))
    for index, value in enumerate(
        [
            "\u001c\u001f",
            "\u0085\u2007",
            "\u200b",
            "./",
            "a/../b",
            "a/..hidden",
            "C:/file",
            "src/line\nbreak",
            "src/zero\x00byte",
        ]
    ):
        variants.append((f"path_whitespace_{index}", dict(good, owned_scope=[value])))
    variants.extend(
        [
            ("duplicate_before_blank", dict(good, owned_scope=[" ", " "], out_of_scope=["x", "x"])),
            ("version_first", dict(good, version=2, owned_scope=["x", "x"])),
            (
                "multiple_fields",
                dict(
                    good,
                    task_id="/bad",
                    slice_id="-bad",
                    phase_id="",
                    owned_scope=[],
                    verification_commands=[1],
                    stop_conditions=[],
                    extra=1,
                ),
            ),
            (
                "normalized_refs",
                dict(
                    good,
                    owned_scope=["./src//file", "src/./**"],
                    handoff_refs=[".", "./", "a//b", ""],
                ),
            ),
            (
                "normalized_refs_valid",
                dict(
                    good, owned_scope=["./src//file", "src/./**"], handoff_refs=[".", "./", "a//b"]
                ),
            ),
            (
                "source_multiple",
                dict(good, source_refs=dict(task_spec="", phase=2, plan="", extra=1)),
            ),
            (
                "plan_before_tuple",
                dict(
                    good,
                    source_refs=dict(task_spec="x", phase="x", plan="other"),
                    owned_scope=["x", "x"],
                ),
            ),
        ]
    )
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / "brief.json"
    cases = []
    for name, payload in variants:
        text = json.dumps(payload, ensure_ascii=True)
        path.write_text(text, encoding="utf-8")
        try:
            outcome = dict(value=module.load_dispatch_brief(path).model_dump(mode="json"))
        except Exception as error:
            outcome = dict(kind=type(error).__name__, message=str(error))
        cases.append(dict(name=name, text=text, **outcome))
    return dict(
        runtime=dict(
            python=sys.version.split()[0],
            pydantic=pydantic.__version__,
            unicode=unicodedata.unidata_version,
        ),
        sha256={key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()},
        oracle_source=contract + "\n" + loader_function,
        cases=cases,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for key in ("owner", "scratch", "output"):
        parser.add_argument("--" + key, type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(capture(args.owner, args.scratch), indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
