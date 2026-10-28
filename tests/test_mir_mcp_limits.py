"""Security limits exercised in isolated processes on both interpreter versions."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from mir_mcp_interpreters import INTERPRETERS

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "plugins/mir-mcp/mir_mcp.py"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX SIGALRM interruption")
@pytest.mark.parametrize("interpreter", INTERPRETERS)
def test_global_deadline_interrupts_tool_without_guard_reentry(interpreter, tmp_path):
    from test_mir_mcp_protocol import _request, _success, _tool_result

    wrapper = tmp_path / "blocking_tool.py"
    wrapper.write_text("""import importlib.util, signal, sys
spec = importlib.util.spec_from_file_location("blocking_mir_mcp", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
def block(*args):
    print("tool blocked without Guard reentry", file=sys.stderr, flush=True)
    while True:
        signal.pause()
m.tool_data = block
m.main()
""")
    frames = [
        _request("tools/call", {
            "name": "ontology_validate",
            "arguments": {"target_root": str(tmp_path), "scope": "contract"},
        }),
        _request("tools/list", identity=2),
    ]
    try:
        completed = subprocess.run(
            [interpreter, "-I", "-B", "-u", str(wrapper), str(SERVER)],
            input="".join(json.dumps(frame) + "\n" for frame in frames),
            text=True, capture_output=True, timeout=15, env={},
        )
    except subprocess.TimeoutExpired:
        pytest.fail("global call deadline did not interrupt blocked tool within 15s")
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == "tool blocked without Guard reentry\n"
    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(replies) == 2
    assert _tool_result(replies[0])["error"] == {"code": "E_TIMEOUT"}
    assert replies[1]["id"] == 2
    assert _success(replies[1])["tools"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX dir_fd replacement race")
@pytest.mark.parametrize("interpreter", INTERPRETERS)
def test_read_limits_and_replacement_in_both_interpreters(interpreter, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    for index in range(258):
        (target / f"file{index}").write_text("x")
    for index in range(5):
        (target / f"large{index}").write_bytes(b"x" * 1048576)
    wrapper = tmp_path / "limits.py"
    wrapper.write_text("""import json, os, runpy, sys
m = runpy.run_path(sys.argv[1])
root = sys.argv[2]
codes = []
for scenario in ("count", "bytes", "time", "race"):
    guard = m["Guard"](root)
    original = os.open
    try:
        if scenario == "count":
            for n in range(258):
                guard.read("file" + str(n))
        if scenario == "bytes":
            for n in range(5):
                guard.read("large" + str(n))
        if scenario == "time":
            guard.deadline = 0
            guard.read("file0")
        if scenario == "race":
            def race(path, flags, *args, **kwargs):
                if path == "file0":
                    os.unlink(root + "/file0")
                    os.symlink("/etc/passwd", root + "/file0")
                return original(path, flags, *args, **kwargs)
            os.open = race
            guard.read("file0")
    except m["Refusal"] as exc:
        codes.append(exc.code)
    finally:
        os.open = original
        guard.close()
print(json.dumps(codes))
""")
    result = subprocess.run(
        [interpreter, "-I", "-B", "-u", str(wrapper), str(SERVER), str(target)],
        capture_output=True,
        text=True,
        timeout=15,
        env={},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["E_LIMIT", "E_LIMIT", "E_TIMEOUT", "E_PATH"]
    assert result.stderr == ""


@pytest.mark.parametrize("interpreter", INTERPRETERS)
def test_output_cap_and_stateless_cursor_bindings(interpreter, tmp_path):
    target = tmp_path / "target"
    (target / ".mir").mkdir(parents=True)
    (target / "source.py").write_text("def sample(): pass\n")
    mapping = target / ".mir/ontology-map.json"
    data = {
        "contract": {"id": "mir.common-semantics", "version": "1.1.0"},
        "domain": {
            "concepts": [
                {
                    "name": "sample",
                    "ref": "source.py",
                    "evidence": ["source.py#" + "x" * 200 + str(index) for index in range(100)],
                },
            ]
        },
    }
    mapping.write_text(json.dumps(data))
    meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
    }

    def call(**extra):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "_meta": meta,
                "name": "ontology_lookup",
                "arguments": {
                    "target_root": str(target),
                    "query": "sample",
                    "page_size": 1,
                    **extra,
                },
            },
        }
        result = subprocess.run(
            [interpreter, "-I", "-B", "-u", str(SERVER)],
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            timeout=15,
            env={},
        )
        assert result.returncode == 0 and result.stderr == ""
        assert len(result.stdout.encode()) <= 16384
        return json.loads(result.stdout)["result"]["structuredContent"]

    assert call()["error"] == {"code": "E_LIMIT"}
    data["domain"]["concepts"] = [{"name": "sample", "ref": "source.py"}] * 3
    mapping.write_text(json.dumps(data))
    first = call()
    second = call(cursor=first["next_cursor"])
    assert first["ok"] and second["ok"]
    assert second["data"]["matches"][0]["pointer"] != first["data"]["matches"][0]["pointer"]
    assert call(cursor=first["next_cursor"], page_size=2)["error"] == {"code": "E_CURSOR"}
    assert call(cursor="DO_NOT_DISCLOSE_SENTINEL")["error"] == {"code": "E_CURSOR"}


# Each interpreter as found, plus one with tomllib blocked so the unavailable branch
# stays covered on hosts whose system Python is 3.11 or newer.
@pytest.mark.parametrize(
    "interpreter,block_tomllib",
    [(interpreter, False) for interpreter in INTERPRETERS] + [(INTERPRETERS[-1], True)],
)
def test_protected_root_and_malformed_profile(interpreter, block_tomllib, tmp_path):
    wrapper = tmp_path / "profile.py"
    blocker = "sys.modules['tomllib'] = None\n" if block_tomllib else ""
    wrapper.write_text("""import json, runpy, sys
""" + blocker + """m = runpy.run_path(sys.argv[1])
print(json.dumps(m["execute"]("ontology_validate", {
    "target_root": sys.argv[2], "scope": "contract"})))
""")
    root = tmp_path / "secrets"
    root.mkdir()

    def run(path):
        completed = subprocess.run(
            [interpreter, "-I", "-B", "-u", str(wrapper), str(SERVER), str(path)],
            capture_output=True,
            text=True,
            timeout=15,
            env={},
        )
        assert completed.returncode == 0 and completed.stderr == ""
        return json.loads(completed.stdout)

    assert run(root)["error"] == {"code": "E_PROTECTED"}
    target = tmp_path / "target"
    (target / ".mir").mkdir(parents=True)
    (target / ".mir/repo-profile.toml").write_text('[paths]\nprotected_paths="SENTINEL"\n')
    result = run(target)
    probe = subprocess.run([interpreter, "-I", "-c", "import tomllib"], capture_output=True)
    if block_tomllib or probe.returncode != 0:
        assert result["ok"] and result["profile_protections"] == "unavailable"
    else:
        assert result["error"] == {"code": "E_FORMAT"}


@pytest.mark.parametrize("interpreter", INTERPRETERS)
@pytest.mark.parametrize("modern", [False, True])
def test_windows_backstop_flushes_timeout_and_exits(interpreter, tmp_path, modern):
    import time

    from test_mir_mcp_protocol import _request

    wrapper = tmp_path / "windows_block.py"
    wrapper.write_text("""import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("windows_block_mcp", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
def block(*args):
    time.sleep(60)
m.execute = block
sys.exit(m.main(windows=True))
""")
    frames = []
    if not modern:
        frames = [_request("initialize", {"protocolVersion": "2025-11-25",
                  "clientInfo": {"name": "test", "version": "1"}, "capabilities": {}},
                  modern=False),
                  {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    frames.append(_request("tools/call", {"name": "ontology_validate", "arguments": {}},
                           modern=modern, identity="blocked"))
    start = time.monotonic()
    child = subprocess.run([interpreter, "-I", "-B", "-u", str(wrapper), str(SERVER)],
                           input=b"".join(json.dumps(f).encode() + b"\n" for f in frames),
                           capture_output=True, timeout=12, env={})
    assert time.monotonic() - start < 10.5
    assert child.returncode == 0 and child.stderr == b""
    assert child.stdout.endswith(b"\n") and b"\r\n" not in child.stdout
    response = json.loads(child.stdout.splitlines()[-1])
    expected = {"content": [{"type": "text", "text": '{"code":"E_TIMEOUT"}'}],
                "structuredContent": {"ok": False, "data": None,
                    "error": {"code": "E_TIMEOUT"}, "next_cursor": None,
                    "profile_protections": "available"}, "isError": True}
    if modern:
        expected["resultType"] = "complete"
    assert response == {"jsonrpc": "2.0", "id": "blocked", "result": expected}


def test_windows_normal_call_joins_worker(monkeypatch):
    import importlib.util
    import threading

    from test_mir_mcp_protocol import _request

    spec = importlib.util.spec_from_file_location("windows_normal_mcp", SERVER)
    module = importlib.util.module_from_spec(spec)
    exec(compile(SERVER.read_bytes(), str(SERVER), "exec"), module.__dict__)
    before = set(threading.enumerate())
    workers = []
    def execute(*args):
        workers.append(threading.current_thread())
        return {"ok": True, "data": {}, "error": None, "next_cursor": None,
                "profile_protections": "available"}
    monkeypatch.setattr(module, "execute", execute)
    reply = module.Protocol(windows=True).request(_request(
        "tools/call", {"name": "ontology_validate", "arguments": {}}))
    assert reply["result"]["structuredContent"]["ok"]
    assert len(workers) == 1 and workers[0] is not threading.current_thread()
    assert not workers[0].is_alive() and set(threading.enumerate()) == before
