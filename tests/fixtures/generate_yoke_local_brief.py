"""Freeze Yoke's file-only hook from an immutable Git revision.

Only three pinned source files execute; TaskSpec is an annotation-only stub.
All filesystem operations are confined to the caller's synthetic scratch root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

REFERENCE = "84b7b8a33cff26cd782170befa8621a1c65d9744"
SOURCES = {
    "mir.core.contracts.dispatch_brief": "src/mir/core/contracts/dispatch_brief.py",
    "mir.core.conductor.dispatch_brief": "src/mir/core/conductor/dispatch_brief.py",
    "yoke_local_reference": "tools/mir_executor/local.py",
}


def capture(repo: Path, scratch: Path) -> dict:
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(scratch)
    for name in ("mir", "mir.core", "mir.core.contracts", "mir.core.conductor"):
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
    stub = types.ModuleType("mir.core.contracts.task_spec")
    stub.TaskSpec = type("TaskSpec", (), {})
    sys.modules[stub.__name__] = stub
    sources = []
    for name, path in SOURCES.items():
        raw = subprocess.check_output(["git", "show", f"{REFERENCE}:{path}"], cwd=repo)
        sources.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest()})
        module = types.ModuleType(name)
        sys.modules[name] = module
        exec(compile(raw, path, "exec"), module.__dict__)
    validate = sys.modules["yoke_local_reference"].validate_brief
    good = dict(task_id="task", slice_id="slice", target_agent="executor-agent",
                user_intent="Implement the change.", expanded_goal="Update the owned module.",
                owned_scope=["src/module.rs"], verification_commands=["cargo test"],
                stop_conditions=["Stop outside scope."],
                resume_state_ref="tasks/dispatch/task/slice.json",
                source_refs={"task_spec": "runtime://task", "phase": "tasks/phase.json"})
    inputs = [("valid", good), ("missing_all", {}), ("root_null", None),
              ("root_array", []), ("root_string", "text"), ("root_number", 1),
              ("root_bool", True)]
    fields = {
        "version": [2, None, "bad", 1.5, "1", True, 1.0, "1.0", float("inf"),
                    2 ** 65, "9" * 300],
        "task_id": ["", 1, None, "task\u001c"],
        "phase_id": [1, None, "", "\ud800"],
        "slice_id": ["", None], "target_agent": ["", None],
        "user_intent": ["", 1], "expanded_goal": ["", None, "\ud55c\uae00"],
        "owned_scope": [[], None, "src", [1], ["x", 1]],
        "verification_commands": [[], None, "test", [1]],
        "stop_conditions": [[], [1]], "out_of_scope": [None, [1]],
        "handoff_refs": [None, [1]], "tdd_change_refs": [None, [1]],
        "resume_state_ref": ["wrong", "", None],
        "source_refs": [None, [], {}, {"task_spec": 1, "phase": ""},
                        {"task_spec": "x", "phase": "p", "plan": "other"},
                        {"task_spec": "x", "phase": "p", "extra": 1}],
    }
    for field, values in fields.items():
        for index, value in enumerate(values):
            inputs.append((f"{field}_{index}", dict(good, **{field: value})))
    inputs += [("extra", dict(good, z_extra=1, a_extra="value")),
               ("multiple", dict(good, task_id=1, owned_scope=[], source_refs={})),
               ("unicode", dict(good, user_intent="\ud55c\uae00 \u00e9 \U0001f600"))]
    cases = [{"name": name, "input_kind": "file",
              "bytes_hex": json.dumps(payload, ensure_ascii=True).encode().hex()}
             for name, payload in inputs]
    for name, raw in [("json_empty", b""), ("json_object", b"{"),
                      ("json_trailing", b"{}x"), ("json_nan", b"NaN"),
                      ("json_infinity", b"1e400"), ("utf8", b"\xff"),
                      ("bom", b"\xef\xbb\xbf{}"), ("crlf", b"{\r\n\"task_id\":1\r\n}"),
                      ("json_crlf_error", b"{\r\n?}"), ("json_cr_error", b"{\r?}")]:
        cases.append({"name": name, "input_kind": "file", "bytes_hex": raw.hex()})
    cases.extend({"name": name, "input_kind": "file", "path_kind": kind}
                 for name, kind in [("missing_file", "missing"),
                                    ("directory", "directory"), ("unreadable", "unreadable")])
    for name, raw in [
        ("json_deep_extra", '{"extra":' + '[' * 65 + '0' + ']' * 65 + '}'),
        ("json_surrogate", json.dumps(dict(good, user_intent="\ud800"))),
        ("json_surrogate_tuple", json.dumps(dict(good, owned_scope=["\ud800"]))),
        ("json_surrogate_refs", json.dumps(dict(
            good, source_refs={"task_spec": "\ud800", "phase": "tasks/phase.json"}))),
        ("json_surrogate_plan", json.dumps(dict(
            good, source_refs={"task_spec": "task", "phase": "phase", "plan": "\ud800"}))),
        ("json_surrogate_version", json.dumps(dict(good, version="\ud800"))),
        ("json_surrogate_key", json.dumps(dict(good, **{"\ud800": 1}))),
        ("json_surrogate_key_collision", json.dumps(dict(
            good, **{"\ud800": 1, "\\ud800": 2}))),
        ("json_surrogate_nested_key", json.dumps(dict(
            good, source_refs={"task_spec": "task", "phase": "phase", "\ud800": 1}))),
        ("json_integer_digit_limit", "9" * 4301),
        ("json_recursion_9996", "[" * 9996 + "0" + "]" * 9996),
        ("json_recursion_9997", "[" * 9997 + "0" + "]" * 9997),
        ("json_recursion_9998", "[" * 9998 + "0" + "]" * 9998),
        ("json_recursion_limit", "[" * 10001 + "0" + "]" * 10001),
    ]:
        cases.append({"name": name, "input_kind": "file", "bytes_hex": raw.encode().hex()})
    cases += [{"name": "text", "input_kind": "text", "text": "ordinary prompt"},
              {"name": "empty_text", "input_kind": "text", "text": ""}]
    for case in cases:
        path = scratch / "brief.json"
        if path.exists():
            if path.is_dir():
                path.rmdir()
            else:
                path.chmod(0o600)
                path.unlink()
        kind = case.get("path_kind")
        if case["input_kind"] == "file" and kind != "missing":
            if kind == "directory":
                path.mkdir()
            else:
                path.write_bytes(bytes.fromhex(case.get("bytes_hex", "7b7d")))
                if kind == "unreadable":
                    path.chmod(0)
        try:
            result = validate(path if case["input_kind"] == "file" else case["text"], scratch)
            value = result.model_dump(mode="json") if result is not None else None
            # The reference bridge retains BaseModel results as opaque handles.
            # A successful UTF-16-only value cannot inhabit serde_json::Value;
            # retain its exact oracle JSON, and compare the hook's decision.
            try:
                json.dumps(value, ensure_ascii=False).encode("utf-8")
            except UnicodeEncodeError:
                case.update(decision_only=True, value_json=json.dumps(value, ensure_ascii=True))
            else:
                case["value"] = value
        except Exception as error:
            case.update(kind=type(error).__name__,
                        message=str(error).replace(str(scratch), "<ROOT>"))
        if kind == "unreadable" and case.get("kind") != "PermissionError":
            raise RuntimeError("unreadable fixture requires an unprivileged Unix process")
    return {"reference_commit": REFERENCE, "sources": sources, "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    args.output.write_text(
        json.dumps(capture(repo, args.scratch), indent=2, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()
