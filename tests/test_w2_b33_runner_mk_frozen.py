"""Frozen unmodified runner/MK observations; never recapture from a port.

Assumptions: synthetic homes only, no real child, and logical JSON observations.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins/mir-core/skills/ontology/scripts"
FIXTURE = ROOT / "native/handoff-packet/tests/fixtures/w2/b33-runner-mk.json"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner, mk = load("mir_ontology_runner"), load("mk_query")


def write(path, body=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="ascii")
    return path


def attempt(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - frozen error contract
        return {"error": [type(exc).__name__, str(exc)]}


def run(tmp, kind, mode):
    out, err, calls = io.StringIO(), io.StringIO(), []
    with contextlib.ExitStack() as stack:
        for patch in (mock.patch.dict(os.environ, {"HOME": str(tmp), "PATH": "bin",
                      "PRIVATE_TOKEN": "synthetic"}, clear=True),
                      mock.patch.object(Path, "home", return_value=tmp),
                      mock.patch.object(runner, "pwd", None), mock.patch.object(mk, "pwd", None),
                      mock.patch.object(runner, "REPO_ROOT", tmp / "repo"),
                      mock.patch.object(runner.sys, "executable", "python"),
                      contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)):
            stack.enter_context(patch)
        def fake_run(argv, **kw):
            calls.append({"argv": argv, "kwargs": kw})
            return SimpleNamespace(returncode=7)
        stack.enter_context(mock.patch.object(runner.subprocess, "run", side_effect=fake_run))
        stack.enter_context(mock.patch.object(mk.subprocess, "Popen",
                                             side_effect=AssertionError("unexpected child")))
        def checker(runtime, version):
            return write(runner.cache_root(tmp, runtime) / version / runner.CHECKER)
        def action():
            if kind == "version":
                return [runner.valid_version(mode), attempt(lambda: runner.version_key(mode))]
            if kind == "cache":
                for version in ("1.0.0", "2.0.0-rc.1", "2.0.0", "bad"):
                    checker(".codex", version)
                write(runner.cache_root(tmp, ".codex") / "9.0.0")
                return [runner.cache_root(tmp, ".codex"),
                        sorted(p.name for p in runner.cached_versions(tmp, ".codex"))]
            if kind == "claude":
                if mode != "missing":
                    path = checker(".claude", "1.0.0")
                    body = {"plugins": {runner.PLUGIN: [{"version": "1.0.0",
                            "installPath": str(path.parents[3])}]}}
                    write(tmp / ".claude/plugins/installed_plugins.json",
                          "{" if mode == "invalid" else json.dumps(body))
                return runner.claude_active(tmp)
            if kind == "codex":
                checker(".codex", "1.0.0")
                if mode == "ambiguous":
                    checker(".codex", "2.0.0")
                config = tmp / ".codex/config.toml"
                write(config, '[other]\nversion="ignored"\n[plugins."mir-core@mir-yoke"]\n'
                      + mode.replace(";", "\n") if mode not in ("single", "ambiguous")
                      else '[plugins."mir-core@mir-yoke"]\nenabled=true\n')
                return [runner.codex_fields(config), runner.codex_active(tmp)]
            if kind in ("select", "runner"):
                if mode != "missing":
                    path = checker(".codex", "1.0.0")
                    checker(".codex", "2.0.0")
                    write(path.with_name("mk_query.py"))
                if mode == "override":
                    os.environ["MIR_ONTOLOGY_CHECKER"] = str(path)
                if mode == "invalid_override":
                    os.environ["MIR_ONTOLOGY_CHECKER"] = str(tmp / "absent")
                if kind == "select":
                    return [runner.select_distribution(), runner.find_checker()]
                os.environ["MIR_ONTOLOGY_CHECKER"] = str(path)
                if mode == "bogus":
                    stack.enter_context(mock.patch.object(sys, "argv",
                                                          ["mir_ontology_runner.py"]))
                    try:
                        return runner.main(mode.split())
                    except SystemExit as exc:  # argparse rejects the command
                        return {"exit": exc.code}
                return runner.main(mode.split())
            if kind == "active":
                path = checker(".codex", "1.0.0")
                return runner.select_active_distribution(
                    [("1.0.0", path, "first"), ("2.0.0" if mode == "disagree" else
                     "1.0.0", tmp / "missing" if mode == "missing" else path, "second")])
            if kind == "config":
                config = tmp / (".mir/knowledge-supply.json" if mode == "default"
                                else ".env-config" if mode == "secret" else "config.json")
                if mode != "default":
                    os.environ["MIR_KNOWLEDGE_SUPPLY_CONFIG"] = str(config)
                body = {"memory_keeper": {"command": ["fake", "serve"], "cwd": str(tmp),
                                          "timeout_sec": 1}}
                if mode == "invalid":
                    body["memory_keeper"]["timeout_sec"] = True
                # Zero timeout, an unknown binding key and a blank argument are all rejected.
                if mode == "zero":
                    body["memory_keeper"]["timeout_sec"] = 0
                if mode == "extra":
                    body["memory_keeper"]["extra"] = "x"
                if mode == "blank":
                    body["memory_keeper"]["command"] = ["fake", " "]
                if mode != "missing":
                    write(config, "{" if mode == "malformed" else json.dumps(body))
                return [mk.config_path(), mk.load_config(tmp if mode == "inside" else tmp / "repo")]
            if kind in ("exchange", "call"):
                init = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}}
                reply = {"jsonrpc": "2.0", "id": 2, "result": {"structuredContent": {"ok": True}}}
                if mode == "error":
                    reply["error"] = {"message": "synthetic"}
                if mode == "text":
                    reply["result"] = {"content": [{"type": "text", "text": '{"ok":true}'}]}
                if mode == "tool_error":
                    reply["result"] = {"isError": True}
                lines = b"" if mode == "eof" else (json.dumps(init) + "\n" +
                        ("{" if mode == "malformed" else json.dumps(reply)) + "\n").encode()
                if mode == "oversized":
                    lines = b"x" * (mk.MAX_MESSAGE + 1)
                child = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(lines), pid=123,
                                        wait=lambda **kw: 0)
                if kind == "exchange":
                    value = attempt(lambda: mk.exchange(child, "lookup", {"q": "x"}, "client"))
                    return [value, child.stdin.getvalue().decode()]
                def popen(argv, **kw):
                    calls.append({"argv": argv, "cwd": kw["cwd"], "env": sorted(kw["env"])})
                    return child
                stack.enter_context(mock.patch.object(mk.subprocess, "Popen", side_effect=popen))
                stack.enter_context(mock.patch.object(mk.os, "killpg"))
                stack.enter_context(mock.patch.object(child.stdin, "close"))
                stack.enter_context(mock.patch.object(child.stdout, "close"))
                if mode == "timeout":
                    stack.enter_context(mock.patch.object(mk.queue.Queue, "get",
                                                         side_effect=mk.queue.Empty))
                value = attempt(lambda: mk.call(["fake"], str(tmp), 1, "lookup", {}, "client"))
                return [value, child.stdin.getvalue().decode()]
            if kind == "fence":
                pack = {"nodes": [{"namespace": "ns:core"}, {"namespace": "private"}, 1],
                        "citations": [{"namespace": "ns:skills"}]}
                return [mk.fence_namespaces(pack, None if mode == "default" else ["private"]), pack]
            if kind in ("main", "mainargs"):
                stack.enter_context(mock.patch.object(mk, "load_config",
                    side_effect=mk.Unavailable("missing") if mode.startswith("missing") else None,
                    return_value=(["fake"], str(tmp), 1)))
                def call(*args):
                    calls.append(list(args))
                    return {"nodes": [{"namespace": "private"}]} if "filtered" in mode else {}
                stack.enter_context(mock.patch.object(mk, "call", side_effect=call))
                if kind == "mainargs":
                    # argparse names the program from argv[0]; pin the script's own name.
                    stack.enter_context(mock.patch.object(sys, "argv", ["mk_query.py"]))
                    try:
                        return mk.main(["--repo", str(tmp / "repo"), *MAIN_ARGS[mode]])
                    except SystemExit as exc:  # argparse rejects before any call
                        return {"exit": exc.code}
                return mk.main(["--repo", str(tmp / "repo"),
                                *(["--soft"] if "--soft" in mode else []), "query", "x"])
        value = attempt(action)
    return json.loads(json.dumps([value, out.getvalue(), err.getvalue(), calls],
                                 default=str).replace(str(tmp), "<tmp>"))

# Query length, blank-after-strip, --k range and int() grammar boundaries.
MAIN_ARGS = {"ctrl": ["query", "\x1c"], "long": ["query", "x" * 8193],
             "max": ["query", "x" * 8192, "--k=1_0"], "k0": ["query", "x", "--k", "0"],
             "k100": ["query", "x", "--k", "100"], "k101": ["query", "x", "--k", "101"],
             "kquote": ["query", "x", "--k", "a'b"], "badcmd": ["bogus"],
             "badverdict": ["feedback", "r", "bogus"]}
CASES = {}
for kind, modes in {
    "version": ["0.0.0", "1.2.3-alpha.2", "1.2.3-alpha.10", "1.2.3+build",
                "01.2.3", "1.2.3-01", "bad"],
    "cache": [""], "claude": ["missing", "valid", "invalid"],
    "codex": ["single", "ambiguous", "enabled=false", "enabled=maybe",
              'enabled=true;version="1.0.0"', "enabled=true;enabled=true",
              "enabled=true;version=bad"],
    "select": ["missing", "cache", "override", "invalid_override"],
    "active": ["same", "disagree", "missing"],
    "runner": ["--which", "mapping --handoff input", "mk query x --soft",
               "mk feedback r used --soft", "bogus"],
    "config": ["default", "explicit", "missing", "inside", "secret", "malformed", "invalid",
               "zero", "extra", "blank"],
    "exchange": ["ok", "text", "error", "tool_error", "malformed", "eof", "oversized"],
    "call": ["ok", "timeout", "error"], "fence": ["default", "explicit"],
    "main": ["", "--soft", "missing", "missing --soft", "filtered", "filtered --soft"],
    "mainargs": list(MAIN_ARGS),
}.items():
    for mode in modes:
        CASES[f"{kind}.{mode or 'default'}"] = lambda tmp, k=kind, m=mode: run(tmp, k, m)


def observe(case, tmp):
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - frozen error contract
        return {"error": [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]}

RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
