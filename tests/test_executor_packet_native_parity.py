"""Separately captured packet owners share one native validation/rendering profile."""
from __future__ import annotations

import argparse
import ast
import json
import runpy
import shlex
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HUB = runpy.run_path(str(Path(__file__).with_name("test_executor_hub_native_parity.py")))
P1, DISPATCH, SUPPORT = HUB["P1"], HUB["DISPATCH"], HUB["SUPPORT"]
binary = HUB["binary"]
GENERATOR = runpy.run_path(str(ROOT /
    "native/handoff-packet/tests/fixtures/generate_executor_packet_profile.py"))
GOLDEN = json.loads((ROOT /
    "native/handoff-packet/tests/fixtures/executor_development_packet.json").read_text())
SOURCES = GOLDEN["sources"]


def owner_hooks(monkeypatch, source):
    monkeypatch.setitem(sys.modules, "mir.core.conductor.dispatch_brief", None)
    namespace = {"__name__": "packet_oracle"}
    exec(source["oracle_source"], namespace)
    namespace["DispatchBrief"].model_rebuild(_types_namespace=namespace)
    return namespace


def seed(root, bridge, source, text, mode="plain"):
    launcher, environment, args = DISPATCH["seed"](root, "success", SUPPORT)
    # Use tracked source refs while retaining the existing offline dispatch harness.
    GENERATOR["seed_refs"](root)
    config_path = root / "config/mir-executor.local.json"
    config = json.loads(config_path.read_text())
    config["development_packet"] = {"ref_prefixes": ["src/"]}
    oracle = source["oracle_source"]
    if not bridge:
        tree = ast.parse(oracle)
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.FunctionDef) and node.name in
            {"validate_brief", "render_brief"})]
        oracle = ast.unparse(tree)
        config["native_policy"] = {"version": 1,
                                   "brief_profile": {"name": "development_packet_v1"}}
    (root / "tools/mir_executor/local.py").write_text(oracle, encoding="utf-8")
    config_path.write_text(json.dumps(config))
    for path in (root / "server.py", launcher):
        if path.suffix != ".cmd":
            path.write_text(path.read_text().replace(
                "    elif method == 'turn/start':",
                "    elif method == 'turn/start':\n"
                "        (root / 'rendered-prompt').write_text("
                "request['params']['input'][0]['text'], encoding='utf-8')"), encoding="utf-8")
    if mode == "file":
        (root / "brief.json").write_text(json.dumps(GENERATOR["brief_payload"](text)))
    else:
        index = args.index("--dispatch-brief")
        del args[index:index + 2]
        if mode == "raw_file":
            (root / "packet.txt").write_text(text, encoding="utf-8")
            args += ["--codex-args-file", str(root / "packet.txt")]
        else:
            args += ["--codex-args", shlex.join(["exec", text]) if mode == "argv"
                     else shlex.quote(text)]
    return launcher, environment, args


def snapshot(root, launcher, result):
    value = HUB["snapshot"](root, launcher, result, True)
    prompt = root / "rendered-prompt"
    value["provider_prompt_bytes"] = prompt.read_bytes() if prompt.exists() else None
    value["brief_artifact_bytes"] = [path.read_bytes() for path in
        sorted((root / "artifacts").rglob("brief.md"))]
    return value


def test_oracle_pins_and_runtime():
    assert GOLDEN["runtime"] == {
        "python": "3.12.13", "pydantic": "2.13.4", "unicode": "15.0.0"}
    assert [source["sha256"] for source in SOURCES] == [
        {"local": "b3e87c49907a670eaf434832a3f31bb0095793cffff1370f24abba837aeb0c48",
         "contracts": "d42dee5aa53c2386b6ce19c8eb7057a28ee83f650b26539288937b7d35b01b1f",
         "loader": "c207f1df7e028394b551574ae557dd91f98e6861c7d0b3a4ecd2fdad57fc9a3a"},
        {"local": "52add9b9bb6cae89b07ec8e211c0fba0c770fe604573d5e4e5bd3ab2dd8b14d8",
         "contracts": "4261212c8df5177646513775d92c286abb6dd1afb3000a1b1254cd1cac4e22fa",
         "loader": "8171f3ea0f41a84adcde60858d80a1c156a1ecb23ac58602275e0eff7edc80af"}]
    assert SOURCES[0]["cases"] == SOURCES[1]["cases"]
    assert SOURCES[0]["file_cases"] == SOURCES[1]["file_cases"]


@pytest.mark.parametrize("source", SOURCES, ids=["source_a", "source_b"])
def test_captured_packet_oracle(tmp_path, monkeypatch, source):
    root = tmp_path / "oracle"
    symlinks = GENERATOR["seed_refs"](root)
    (root / "config").mkdir()
    (root / "config/mir-executor.local.json").write_text(json.dumps({
        "verifiers": {"offline": ["offline"]},
        "development_packet": {"ref_prefixes": ["src/"]}}))
    namespace = owner_hooks(monkeypatch, source)
    for case in source["cases"]:
        if not symlinks and case["name"] in {"refs_16", "refs_17"}:
            continue
        try:
            value = namespace["validate_brief"](case["text"], root)
            outcome = dict(value=value, rendered=namespace["render_brief"](value, root))
        except Exception as error:
            outcome = dict(kind=type(error).__name__, message=str(error))
        assert outcome == {key: case[key] for key in
            ("value", "rendered", "kind", "message") if key in case}, case["name"]
    for case in source["file_cases"]:
        path = root / "brief.json"
        path.write_text(case["raw"])
        value = namespace["validate_brief"](path, root)
        assert value == case["value"]
        rendered = namespace["render_brief"](value, root)
        assert rendered == case["rendered"]
        assert not rendered.endswith("\n")


@pytest.mark.parametrize("source", SOURCES, ids=["source_a", "source_b"])
@pytest.mark.parametrize("mode", ["plain", "file", "argv", "raw_file"])
def test_cli_input_modes_match_owner(binary, tmp_path, source, mode):
    text = json.dumps(GENERATOR["packet"](), ensure_ascii=True)
    values = []
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        launcher, environment, args = seed(root, bridge, source, text, mode)
        result = P1["invoke"](binary, root, environment, args)
        values.append(snapshot(root, launcher, result))
        assert result.returncode == 0, values[-1]
    assert values[0] == values[1], values


@pytest.mark.parametrize("case", SOURCES[0]["cases"], ids=lambda case: case["name"])
def test_cli_packet_validation_matches_owner(binary, tmp_path, case):
    # Brief-only dispatch reaches native validation, with the Python argv fence retained.
    values = []
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        launcher, environment, args = seed(root, bridge, SOURCES[0], case["text"], "file")
        if case["name"] in {"refs_16", "refs_17"} and not (root / "src/direct.rs").is_symlink():
            pytest.skip("symlinks unavailable")
        result = P1["invoke"](binary, root, environment, args)
        values.append(snapshot(root, launcher, result))
        assert result.returncode == (1 if "kind" in case else 0), values[-1]
        if "kind" in case:
            assert case["message"].encode() in result.stderr
            assert not (root / "provider-methods").exists()
            assert not HUB["jobs"](root)
    assert values[0] == values[1], values


@pytest.mark.parametrize("source", SOURCES, ids=["source_a", "source_b"])
@pytest.mark.parametrize("index", range(5))
def test_cli_file_agent_and_render_matches_owner(binary, tmp_path, source, index):
    case = source["file_cases"][index]
    values = []
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        launcher, environment, args = seed(root, bridge, source, "{}", "file")
        (root / "brief.json").write_text(case["raw"])
        result = P1["invoke"](binary, root, environment, args)
        values.append(snapshot(root, launcher, result))
        expected_failure = case["name"] == "outer_agent_whitespace"
        assert result.returncode == int(expected_failure), values[-1]
    assert values[0] == values[1], values


@pytest.mark.parametrize("variant", ["root_list", "root_null", "version", "missing", "unknown"])
def test_cli_outer_schema_matches_owner(binary, tmp_path, variant):
    payload = GENERATOR["brief_payload"](json.dumps(GENERATOR["packet"]()))
    if variant == "root_list":
        payload = []
    elif variant == "root_null":
        payload = None
    elif variant == "version":
        payload["version"] = 2
    elif variant == "missing":
        payload.pop("user_intent")
    elif variant == "unknown":
        payload["extra"] = True
    values = []
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        launcher, environment, args = seed(root, bridge, SOURCES[0], "{}", "file")
        (root / "brief.json").write_text(json.dumps(payload))
        result = P1["invoke"](binary, root, environment, args)
        values.append(snapshot(root, launcher, result))
        assert result.returncode == 1, values[-1]
        assert not (root / "provider-methods").exists()
    assert values[0] == values[1], values


@pytest.mark.parametrize("source", SOURCES, ids=["source_a", "source_b"])
@pytest.mark.parametrize("text", ["exec 'unterminated", "exec trailing\\", "ordinary prose"])
def test_python_argv_fence_errors_match_owner(binary, tmp_path, source, text):
    values = []
    for bridge in (True, False):
        root = tmp_path / ("bridge" if bridge else "native")
        launcher, environment, args = seed(root, bridge, source, "{}", "argv")
        args[args.index("--codex-args") + 1] = text
        result = P1["invoke"](binary, root, environment, args)
        values.append(snapshot(root, launcher, result))
        assert result.returncode == 1, values[-1]
        assert not (root / "provider-methods").exists()
        assert not HUB["jobs"](root)
    assert values[0] == values[1], values


@pytest.mark.parametrize("source", SOURCES, ids=["source_a", "source_b"])
def test_retained_pre_execute_effect_order(tmp_path, monkeypatch, source):
    namespace = owner_hooks(monkeypatch, source)
    calls = []
    for name in source["pre_execute_order"]:
        namespace[name] = lambda *args, name=name: calls.append(name)
    namespace["pre_execute"](argparse.Namespace(), tmp_path)
    assert calls == source["pre_execute_order"]
    # Failures in the fence prevent backend selection and verifier argument mutation.
    calls.clear()
    def refusal(*args):
        calls.append("_require_packet_argv")
        raise ValueError("fence refused")
    namespace["_require_packet_argv"] = refusal
    with pytest.raises(ValueError, match="fence refused"):
        namespace["pre_execute"](argparse.Namespace(), tmp_path)
    assert calls == source["pre_execute_order"][:2]


@pytest.mark.parametrize("hook", ["validate_brief", "render_brief"])
def test_packet_duplicate_export_fails_before_import(binary, tmp_path, hook):
    root = tmp_path / "native"
    _, environment, args = seed(root, False, SOURCES[0], "{}", "file")
    (root / "tools/mir_executor/local.py").write_text(
        'from pathlib import Path\n'
        '(Path(__file__).resolve().parents[2] / "unexpected-import").touch()\n'
        f'def {hook}(*args): pass\n')
    result = P1["invoke"](binary, root, environment, args)
    assert result.returncode == 1
    assert hook.encode() in result.stderr
    assert b"native local policy configuration error" in result.stderr
    for path in ("unexpected-import", "provider-methods", "tasks/jobs.db"):
        assert not (root / path).exists()


UNREPRESENTABLE = ['{"task":"\\ud800"}', '{"task":NaN}', '{"task":Infinity}',
                   '{"task":-Infinity}', '{"task":1e99999}',
                   '{"task":' + '[' * 129 + '0' + ']' * 129 + '}']


@pytest.mark.parametrize("text", UNREPRESENTABLE)
@pytest.mark.parametrize("mode", ["file", "argv", "raw_file"])
def test_unrepresentable_input_declines_before_effects(binary, tmp_path, text, mode):
    root = tmp_path / "decline"
    _, environment, args = seed(root, False, SOURCES[0], text, mode)
    (root / "tools/mir_executor/local.py").write_text(
        'from pathlib import Path\n'
        '(Path(__file__).resolve().parents[2] / "unexpected-import").touch()\n')
    result = P1["invoke"](binary, root, environment, args)
    assert (result.returncode, result.stdout, result.stderr) == (64, b"", b"")
    for path in ("unexpected-import", "provider-methods", "tasks/jobs.db"):
        assert not (root / path).exists()


@pytest.mark.parametrize("location", ["saved_argv", "saved_brief", "row_brief"])
def test_resume_unrepresentable_packet_declines_without_database_or_hook_effects(
        binary, tmp_path, location):
    root = tmp_path / "decline"
    _, environment, _ = seed(root, False, SOURCES[0],
                             json.dumps(GENERATOR["packet"]()), "file")
    args = DISPATCH["resume"](root, "current")
    unsupported = '{"task":"\\ud800"}'
    db = root / "tasks/jobs.db"
    with sqlite3.connect(db) as connection:
        if location == "saved_argv":
            connection.execute("UPDATE jobs SET codex_args=?",
                               (json.dumps(["exec", unsupported]),))
        else:
            bad = root / "unsupported.json"
            bad.write_text(json.dumps(GENERATOR["brief_payload"](unsupported)))
            if location == "saved_brief":
                saved = json.loads(connection.execute(
                    "SELECT dispatch_options_json FROM jobs").fetchone()[0])
                saved["dispatch_brief"] = str(bad)
                connection.execute("UPDATE jobs SET dispatch_options_json=?",
                                   (json.dumps(saved),))
            else:
                connection.execute("UPDATE jobs SET dispatch_options_json=NULL, "
                                   "dispatch_brief_path=?", (str(bad),))
    (root / "tools/mir_executor/local.py").write_text(
        'from pathlib import Path\n'
        'root = Path(__file__).resolve().parents[2]\n'
        '(root / "unexpected-import").touch()\n'
        'def pre_execute(*args): (root / "unexpected-pre-execute").touch()\n')
    before = db.read_bytes()
    result = P1["invoke"](binary, root, environment, args)
    assert (result.returncode, result.stdout, result.stderr) == (64, b"", b"")
    assert db.read_bytes() == before
    for path in ("unexpected-import", "unexpected-pre-execute", "provider-methods"):
        assert not (root / path).exists()


def test_undeclared_packet_consumer_remains_python(binary, tmp_path):
    root = tmp_path / "python"
    _, environment, args = seed(root, True, SOURCES[0], "ordinary prose", "file")
    result = P1["invoke"](binary, root, environment, args)
    assert result.returncode == 1
    assert b"DispatchBrief error: development dispatch accepts only a typed packet" in result.stderr
    assert not (root / "provider-methods").exists()
