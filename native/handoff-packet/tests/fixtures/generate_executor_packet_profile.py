"""Capture packet hooks from two explicitly supplied read-only source checkouts."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import subprocess
import sys
import unicodedata

import pydantic

PACKET_FUNCTIONS = {"validate_brief", "render_brief", "_unique_object",
                    "_development_packet", "_check_ref"}
PRE_FUNCTIONS = {"pre_execute", "_require_packet_argv", "_refuse_family",
                 "_map_verify_commands", "_fail", "_check_family", "_repo_policy_slug",
                 "_per_project_backend", "_fill_per_project_backend"}


class StripDocs(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(
                node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body.pop(0)
        return self.generic_visit(node)


def extract(source, names, constants=False):
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if (
        isinstance(node, ast.FunctionDef) and node.name in names
        or constants and isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id.isupper()
                for target in node.targets))]
    return ast.unparse(StripDocs().visit(tree))


def packet(**changes):
    return dict(packet="mir.development-packet/1", task="Bounded update", kind="fix",
                refs=["src/module.rs"], verify=["offline"], **changes)


def brief_payload(text):
    return dict(version=1, task_id="task", slice_id="slice", target_agent="offline-agent",
                user_intent="Update the owned file.", expanded_goal=text,
                owned_scope=["code.txt"], verification_commands=["offline"],
                stop_conditions=["Stop outside scope."],
                resume_state_ref="tasks/dispatch/task/slice.json",
                source_refs=dict(task_spec="runtime://task", phase="tasks/phase.json"))


def variants():
    good = packet()
    cases = [("valid", good), ("root_list", []), ("root_null", None),
             ("root_string", "text"), ("root_number", 1), ("root_bool", True)]
    for key, values in {
        "packet": [None, 1, "mir.development-packet/2", []],
        "task": [None, "", " \t", "a" * 159, "a" * 160, "a" * 161,
                 "café 漢字 😀", "é" * 160, "é" * 161, "a\n", "a\t", "a\x00",
                 "\u0085", "\u00a0", "\u200b", "\u2028", "\ue000", "\U000e0001", 7],
        "kind": [None, "feature", "refactor", "test", "FIX", 1, [], {}],
        "refs": [None, [], ["src/module.rs"] * 20, ["src/module.rs"] * 21,
                 "src/module.rs", [None], [7], ["src/module.rs::Thing::method"],
                 ["src/module.rs::"], ["src/module.rs::bad-name"],
                 ["src/module.rs:::method"], ["src/../code.txt"],
                 ["/src/module.rs"], ["src\\module.rs"], ["src/untracked.rs"],
                 ["src/deleted.rs"], ["src/direct.rs"], ["src/alias/inside.rs"],
                 ["src2/collision.rs"], ["src/./module.rs"], ["src//module.rs"],
                 ["src/café.rs"], ["src/a'quote.rs"], ["src/"], ["SRC/module.rs"]],
        "verify": [None, "offline", [None], [7], ["missing"], [], ["offline", "offline"]],
        "target_agent": [None, "other-agent", "", "Agent", "bad_agent", 7, "a-0", "a\n"],
    }.items():
        cases.append((f"missing_{key}", {k: v for k, v in good.items() if k != key}))
        cases.extend((f"{key}_{i}", dict(good, **{key: value})) for i, value in enumerate(values))
    cases += [("unknown_fields", dict(good, z=1, a=2)),
              ("unicode_unknown", dict(good, **{"é": 1, "漢": 2})),
              ("duplicate_root", '{"packet":1,"packet":2}'),
              ("duplicate_nested", '{"extra":{"x":1,"x":2}}'),
              ("malformed_json", "{not-json"), ("plain_prose", "Update the file.")]
    return [dict(name=name, text=(value if name.startswith("duplicate_") or name in
                {"malformed_json", "plain_prose"} else json.dumps(value, ensure_ascii=True)))
            for name, value in cases]


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def seed_refs(root):
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        git(root, "init", "-q")
    for name in ("src/module.rs", "src/deleted.rs", "src/direct.rs", "src/alias/inside.rs",
                 "src2/collision.rs", "src/café.rs", "src/a'quote.rs"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Fixture body must never be read.\n", encoding="utf-8")
    git(root, "add", "-f", "--", "src", "src2")
    (root / "src/deleted.rs").unlink()
    (root / "src/untracked.rs").write_text("untracked\n")
    probe = root / "symlink-probe"
    try:
        probe.symlink_to("src/module.rs")
    except OSError:
        return False
    probe.unlink()
    (root / "src/direct.rs").unlink()
    (root / "src/direct.rs").symlink_to("module.rs")
    (root / "src/alias/inside.rs").unlink()
    (root / "src/alias").rmdir()
    (root / "actual").mkdir()
    (root / "actual/inside.rs").write_text("ancestor symlink\n")
    (root / "src/alias").symlink_to("../actual", target_is_directory=True)
    return True


def source_hooks(owner):
    paths = {"local": owner / "tools/mir_executor/local.py",
             "contracts": owner / "src/mir/core/contracts/dispatch_brief.py",
             "loader": owner / "src/mir/core/conductor/dispatch_brief.py"}
    sources = {key: path.read_text(encoding="utf-8") for key, path in paths.items()}
    loader = extract(sources["loader"], {"load_dispatch_brief"})
    header = ("from __future__ import annotations\nimport argparse\nimport json\n"
              "import pathlib\nfrom pathlib import Path\nimport re\nimport shlex\n"
              "import subprocess\nimport sys\nimport tomllib\nimport types\n"
              "from tools.mir_executor.local_hooks import local_config\n"
              "from tools.mir_executor import policy\n")
    source = header + sources["contracts"].replace("from __future__ import annotations", "")
    # Retain the real contract's qualified type in Python **mapping diagnostics.
    source += ('\nDispatchBrief.__module__ = "mir.core.contracts.dispatch_brief"\n'
               'DispatchBriefSourceRefs.__module__ = "mir.core.contracts.dispatch_brief"\n')
    source += "\n" + loader + "\n" + extract(
        sources["local"], PACKET_FUNCTIONS | PRE_FUNCTIONS, True)
    source += ('\n_loader = types.ModuleType("mir.core.conductor.dispatch_brief")\n'
               '_loader.load_dispatch_brief = load_dispatch_brief\n'
               'sys.modules[_loader.__name__] = _loader\n')
    return source, {key: hashlib.sha256(path.read_bytes()).hexdigest()
                    for key, path in paths.items()}


def capture(owner, scratch):
    source, pins = source_hooks(owner)
    namespace = {"__name__": "packet_capture"}
    exec(source, namespace)
    namespace["DispatchBrief"].model_rebuild(_types_namespace=namespace)
    seed_refs(scratch)
    (scratch / "config").mkdir(exist_ok=True)
    configuration = {"verifiers": {"offline": ["offline"]},
                     "development_packet": {"ref_prefixes": ["src/"]}}
    (scratch / "config/mir-executor.local.json").write_text(json.dumps(configuration))
    cases = []
    for case in variants():
        outcome = {}
        try:
            value = namespace["validate_brief"](case["text"], scratch)
            outcome = {"value": value, "rendered": namespace["render_brief"](value, scratch)}
        except Exception as error:
            outcome = {"kind": type(error).__name__, "message": str(error)}
        cases.append(dict(case, **outcome))
    file_cases = []
    for name, value in (("agent_absent", packet()),
                        ("agent_null", dict(packet(), target_agent=None)),
                        ("agent_conflict", dict(packet(), target_agent="other-agent")),
                        ("outer_agent_whitespace", packet()),
                        ("unicode_render", dict(packet(), task="café 漢字 😀"))):
        payload = brief_payload(json.dumps(value, ensure_ascii=True))
        if name == "outer_agent_whitespace":
            payload["target_agent"] = " "
        raw = json.dumps(payload, ensure_ascii=True)
        path = scratch / "brief.json"
        path.write_text(raw)
        result = namespace["validate_brief"](path, scratch)
        file_cases.append(dict(name=name, raw=raw, value=result,
                               rendered=namespace["render_brief"](result, scratch)))
    calls = []
    for name in ("_refuse_family", "_check_family", "_require_packet_argv",
                 "_fill_per_project_backend", "_map_verify_commands"):
        namespace[name] = lambda *args, name=name: calls.append(name)
    namespace["pre_execute"](argparse.Namespace(), scratch)
    return dict(sha256=pins, oracle_source=source, cases=cases, file_cases=file_cases,
                pre_execute_order=calls)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-a", type=pathlib.Path, required=True)
    parser.add_argument("--owner-b", type=pathlib.Path, required=True)
    parser.add_argument("--scratch", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    values = [capture(owner, args.scratch / label) for label, owner in
              (("source_a", args.owner_a), ("source_b", args.owner_b))]
    assert values[0]["cases"] == values[1]["cases"]
    assert values[0]["file_cases"] == values[1]["file_cases"]
    args.output.write_text(json.dumps(dict(runtime={"python": sys.version.split()[0],
        "pydantic": pydantic.__version__, "unicode": unicodedata.unidata_version},
        sources=values), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
