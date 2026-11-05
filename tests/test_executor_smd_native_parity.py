"""Captured execution hooks compose byte-for-byte through initial and resumed CLI."""

from __future__ import annotations

import argparse
import json
import runpy
import sqlite3
import sys
from pathlib import Path

import pytest

HUB = runpy.run_path(str(Path(__file__).with_name("test_executor_hub_native_parity.py")))
P1, DISPATCH, SUPPORT = HUB["P1"], HUB["DISPATCH"], HUB["SUPPORT"]
binary = HUB["binary"]
GOLDEN = json.loads(
    (
        Path(__file__).parents[1]
        / "native/handoff-packet/tests/fixtures/executor_smd_binding_render.json"
    ).read_text()
)


def expand(value, root):
    # Substitute JSON string content so Windows path separators remain escaped.
    return json.loads(json.dumps(value).replace("<root>", json.dumps(str(root))[1:-1]))


def owner_hooks(monkeypatch):
    monkeypatch.setitem(sys.modules, "mir.core.conductor.dispatch_brief", None)
    namespace = {}
    exec(GOLDEN["oracle_source"], namespace)
    namespace["DispatchBrief"].model_rebuild(_types_namespace=namespace)
    return namespace


def test_oracle_pins_and_runtime():
    assert GOLDEN["sha256"] == {
        "local": "12dc59e6f6b24bff2c2c2a03dc11a40162454fc475bfd0b5ca16e2ddb922a3e4",
        "contracts": "4193e0f14721d85532727ba72797317db99b1e72d3e9a743aa453bcee3be67a1",
        "loader": "703b5be8a0ef9d9a582b29d17e832168d34c6f97b4a09f9f0466733041b832ea",
    }
    assert GOLDEN["runtime"] == {
        "python": "3.12.13", "pydantic": "2.13.4", "unicode": "15.0.0"
    }


def family_policy():
    return {
        "mode": "alias_map",
        "aliases": {},
        "unknown": {
            "kind": "ValueError",
            "message": "Unknown family slug: {family_repr}. {key_error}",
        },
        "unknown_key_error": "unknown family",
        "root_conflict": {
            "kind": "ValueError",
            "message": "--family {family_repr} resolves to {family_root}, not {requested_root}",
        },
    }


def seed(root, bridge, case):
    launcher, environment, args = DISPATCH["seed"](root, "success", SUPPORT)
    for path in (root / "server.py", launcher):
        if path.suffix != ".cmd":
            path.write_text(
                path.read_text().replace(
                    "    elif method == 'turn/start':",
                    "    elif method == 'turn/start':\n"
                    "        (root / 'rendered-prompt').write_text("
                    "request['params']['input'][0]['text'], encoding='utf-8')",
                )
            )
    config_path = root / "config/mir-executor.local.json"
    config = json.loads(config_path.read_text())
    body = case["payload"]
    if bridge:
        (root / "tools/mir_executor/local.py").write_text(GOLDEN["oracle_source"])
    else:
        (root / "tools/mir_executor/local.py").unlink()
        config["native_policy"] = dict(
            version=1,
            brief_profile={"name": "execution_v1"},
            brief_controls={"mode": "execution_subset"},
            verifier_aliases={"configuration_root": "target"},
            target_admission={"family": family_policy()},
        )
    config_path.write_text(json.dumps(config))
    brief = root / body["resume_state_ref"]
    brief.parent.mkdir(parents=True, exist_ok=True)
    raw = case["raw"]
    brief.write_text(raw)
    (root / "brief.json").write_text(raw)
    agent = root / ".claude/agents/offline-agent.md"
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_text(
        "---\nexecution_backend: codex\nmodel: offline-fixture\neffort: medium\n"
        "---\nOffline profile.\n"
    )
    if case["name"] in ("missing_agent", "multiple_binding_errors"):
        agent.unlink()
    supplied = expand(case["args"], root)
    args[args.index("--dispatch-brief") + 1] = supplied["dispatch_brief"]
    for flag, key in (("--allow-path", "allow_paths"), ("--verify-cmd", "verify_cmds")):
        index = args.index(flag)
        del args[index : index + 2]
        for value in supplied.get(key, []):
            args += [flag, value]
    if supplied.get("change_id"):
        args += ["--change-id", supplied["change_id"], "--category", "unit"]
    if supplied.get("codex_args"):
        args += ["--codex-args", supplied["codex_args"]]
    if supplied.get("codex_args_file"):
        (root / "instruction.txt").write_text("  file café 漢字 😀\nstep  ", encoding="utf-8")
        args += ["--codex-args-file", supplied["codex_args_file"]]
    if case["name"] == "missing_file":
        brief.unlink()
    return launcher, environment, args, brief


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["name"])
def test_captured_hooks(tmp_path, monkeypatch, case):
    namespace = owner_hooks(monkeypatch)
    root = tmp_path / "oracle"
    (root / "config").mkdir(parents=True)
    (root / "config/mir-executor.local.json").write_text(
        json.dumps({"verifiers": GOLDEN["verifiers"]})
    )
    supplied = expand(case["args"], root)
    path = Path(supplied["dispatch_brief"]) if supplied["dispatch_brief"] else None
    if path is not None and case["name"] != "missing_file":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(case["raw"])
    agent = root / ".claude/agents/offline-agent.md"
    agent.parent.mkdir(parents=True)
    if case["name"] not in ("missing_agent", "multiple_binding_errors"):
        agent.write_text("Offline profile.\n")
    (root / "instruction.txt").write_text("  file café 漢字 😀\nstep  ", encoding="utf-8")
    supplied["repo_root"] = root
    if supplied.get("codex_args_file"):
        supplied["codex_args_file"] = Path(supplied["codex_args_file"])
    args = argparse.Namespace(**supplied)
    outcome = {}
    try:
        namespace["pre_execute"](args, root)
        if args.dispatch and path is not None:
            brief = namespace["validate_brief"](path, root)
            outcome["rendered"] = namespace["render_brief"](brief, root)
            outcome["rendered_again"] = namespace["render_brief"](brief, root)
    except Exception as error:
        outcome = dict(kind=type(error).__name__, message=str(error))

    def normalized(value):
        return json.loads(
            json.dumps(value, default=str).replace(json.dumps(str(root))[1:-1], "<root>")
        )

    assert normalized(vars(args)) == case["patch"]
    assert normalized(outcome) == {
        key: case[key] for key in ("kind", "message", "rendered", "rendered_again") if key in case
    }


CLI_CASES = [case for case in GOLDEN["cases"] if case["name"] != "plain"]


@pytest.mark.parametrize("case", CLI_CASES, ids=lambda case: case["name"])
def test_cli_matches_owner(binary, tmp_path, case):
    values = []
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        launcher, environment, args, _ = seed(root, bridge, case)
        result = P1["invoke"](binary, root, environment, args)
        value = HUB["snapshot"](root, launcher, result, True)
        prompt = root / "rendered-prompt"
        value["provider_prompt_bytes"] = prompt.read_bytes() if prompt.exists() else None
        value["brief_artifact_bytes"] = [
            path.read_bytes() for path in sorted((root / "artifacts").rglob("brief.md"))
        ]
        values.append(value)
        if case["name"] == "conflicting_instruction":
            # The existing native argv parser declines this combination before hooks.
            assert result.returncode == 64, value
        elif "kind" in case:
            assert result.returncode == 1, value
            assert expand(case["message"], root).encode() in result.stderr
            assert not (root / "provider-methods").exists()
        if prompt.exists() and "rendered" in case:
            assert case["rendered"].encode() in value["brief_artifact_bytes"]
        if case["name"] in ("default", "initial_instruction", "file_instruction"):
            assert result.returncode == 0, value
        if case["name"] == "subset":
            # Binding accepts the normalized prefix; the existing literal merge gate refuses it.
            assert result.returncode == 1, value
            assert prompt.exists()
    assert values[0] == values[1], values


@pytest.mark.parametrize("instruction", ["default", "explicit", "empty"])
def test_resume_instruction_matches_owner(binary, tmp_path, instruction):
    values = []
    case = GOLDEN["cases"][0]
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        launcher, environment, _, brief = seed(root, bridge, case)
        payload = json.loads(brief.read_text())
        payload["tdd_change_refs"] = ["tasks/tdd.json#fixture"]
        brief.write_text(json.dumps(payload))
        (root / "brief.json").write_text(json.dumps(payload))
        args = DISPATCH["resume"](root, "current")
        with sqlite3.connect(root / "tasks/jobs.db") as connection:
            options = json.loads(
                connection.execute("SELECT dispatch_options_json FROM jobs").fetchone()[0]
            )
            options["dispatch_brief"] = str(brief)
            argv = (
                ["exec", "--model", "fixture", "  resumed café 漢字 😀  "]
                if instruction == "explicit"
                else ([] if instruction == "empty" else ["offline fixture"])
            )
            connection.execute(
                "UPDATE jobs SET dispatch_options_json=?, dispatch_brief_path=?, codex_args=?, "
                "change_id='fixture', category='unit'",
                (json.dumps(options), str(brief), json.dumps(argv)),
            )
        result = P1["invoke"](binary, root, environment, args)
        value = HUB["snapshot"](root, launcher, result, True)
        assert result.returncode == 0, value
        value["provider_prompt_bytes"] = (root / "rendered-prompt").read_bytes()
        values.append(value)
    assert values[0] == values[1], values


@pytest.mark.parametrize("hook", ["validate_brief", "pre_execute", "render_brief"])
def test_duplicate_exports_fail_closed(binary, tmp_path, hook):
    root = tmp_path / "native"
    _, environment, args, _ = seed(root, False, GOLDEN["cases"][0])
    (root / "tools/mir_executor/local.py").write_text(
        "from pathlib import Path\n"
        '(Path(__file__).resolve().parents[2] / "unexpected-import").touch()\n'
        f"def {hook}(*args): pass\n"
    )
    result = P1["invoke"](binary, root, environment, args)
    assert result.returncode == 1
    assert hook.encode() in result.stderr
    for path in ("unexpected-import", "provider-methods", "tasks/jobs.db"):
        assert not (root / path).exists()


def test_undeclared_keeps_python(binary, tmp_path):
    root = tmp_path / "python"
    _, environment, args, _ = seed(root, True, GOLDEN["cases"][0])
    with (root / "tools/mir_executor/local.py").open("a") as source:
        source.write('\ndef pre_execute(args, root):\n    raise ValueError("python-owned")\n')
    result = P1["invoke"](binary, root, environment, args)
    assert result.returncode == 1
    assert b"python-owned" in result.stderr


@pytest.mark.parametrize("family", ["sample", "missing"])
def test_family_and_mapping_precede_binding(binary, tmp_path, family):
    values = []
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        case = next(case for case in GOLDEN["cases"] if case["name"] == "wrong_path")
        launcher, environment, args, _ = seed(root, bridge, case)
        resolver = root / "tools/profile_compiler"
        resolver.mkdir()
        (resolver / "__init__.py").write_text("")
        (resolver / "cli.py").write_text(
            "from pathlib import Path\n"
            "def resolve_family_path(family):\n"
            '    if family != "sample": raise KeyError("unknown family")\n'
            "    return Path(__file__).resolve().parents[2]\n"
        )
        config_path = root / "config/mir-executor.local.json"
        config = json.loads(config_path.read_text())
        if not bridge:
            config["native_policy"]["target_admission"] = {
                "family": {
                    "mode": "alias_map",
                    "aliases": {"sample": "."},
                    "unknown": {
                        "kind": "ValueError",
                        "message": "Unknown family slug: {family_repr}. {key_error}",
                    },
                    "unknown_key_error": "unknown family",
                    "root_conflict": {
                        "kind": "ValueError",
                        "message": "--family {family_repr} resolves to {family_root}, "
                        "not {requested_root}",
                    },
                }
            }
        config_path.write_text(json.dumps(config))
        args += ["--family", family]
        result = P1["invoke"](binary, root, environment, args)
        assert result.returncode == 1
        assert (
            b"Unknown family slug:"
            if family == "missing"
            else b"DispatchBrief error: DispatchBrief path must match its resume_state_ref"
        ) in result.stderr
        assert not (root / "tasks/jobs.db").exists()
        values.append(HUB["snapshot"](root, launcher, result, True))
    assert values[0] == values[1], values


def test_missing_resumed_job_instruction_falls_back(tmp_path, monkeypatch):
    namespace = owner_hooks(monkeypatch)
    (tmp_path / "tasks").mkdir()
    args = argparse.Namespace(resume_job_id="missing", jobs_db=tmp_path / "tasks/jobs.db")
    brief = namespace["DispatchBrief"](**GOLDEN["cases"][0]["payload"])
    assert namespace["_active_instruction"](args, brief) == GOLDEN["missing_resume_instruction"]


def test_missing_resumed_job_matches_owner(binary, tmp_path):
    values = []
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        launcher, environment, _, _ = seed(root, bridge, GOLDEN["cases"][0])
        result = P1["invoke"](binary, root, environment, ["resume", "--job-id", "missing"])
        assert result.returncode == 1
        assert not (root / "provider-methods").exists()
        values.append(HUB["snapshot"](root, launcher, result, True))
    assert values[0] == values[1], values
