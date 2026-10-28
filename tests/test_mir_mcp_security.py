"""Hermetic ADR-91 read boundaries, including both supported Python interpreters."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest
from mir_mcp_interpreters import INTERPRETERS

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "plugins/mir-mcp/mir_mcp.py"
# Each interpreter as found, plus one with tomllib blocked so the unavailable branch
# stays covered on hosts whose system Python is 3.11 or newer.
PROFILE_RUNTIMES = [(interpreter, False) for interpreter in INTERPRETERS] + [
    (INTERPRETERS[-1], True)
]
NO_TOMLLIB = (
    "import runpy, sys; sys.modules['tomllib'] = None; "
    "runpy.run_path(sys.argv[1], run_name='__main__')"
)
META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


def load_server():
    spec = importlib.util.spec_from_file_location("mir_mcp_security", SERVER)
    module = importlib.util.module_from_spec(spec)
    # Compile from source so a test never writes __pycache__ into a plugin tree.
    exec(compile(SERVER.read_bytes(), str(SERVER), "exec"), module.__dict__)
    return module


@pytest.fixture(params=INTERPRETERS)
def interpreter(request):
    return request.param


def profile_available(interpreter, block_tomllib):
    probe = subprocess.run([interpreter, "-I", "-c", "import tomllib"], capture_output=True)
    return not block_tomllib and probe.returncode == 0


def call(interpreter, root, tool="handoff_pins", block_tomllib=False, **arguments):
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "_meta": META,
            "name": tool,
            "arguments": {"target_root": str(root), **arguments},
        },
    }
    blocker = ["-c", NO_TOMLLIB] if block_tomllib else []
    result = subprocess.run(
        [interpreter, "-I", "-B", "-u", *blocker, str(SERVER)],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert len(result.stdout.encode()) <= 16384
    assert "DO_NOT_DISCLOSE_SENTINEL" not in result.stdout + result.stderr
    return json.loads(result.stdout)["result"]["structuredContent"]


@pytest.fixture
def target(tmp_path):
    root = tmp_path / "target"
    (root / ".mir").mkdir(parents=True)
    (root / ".mir/repo-profile.toml").write_text('[project]\nslug = "test"\n')
    (root / ".mir/ontology-map.json").write_text(
        json.dumps(
            {
                "schema": "mir-semantic-mapping/v1",
                "namespace": "test",
                "contract": {
                    "id": "mir.common-semantics",
                    "version": "1.1.0",
                    "version_range": ">=1.0.0 <2.0.0",
                },
                "domain": {"concepts": [{"name": "sample", "ref": "source.py"}]},
            }
        )
    )
    (root / "source.py").write_text("def sample(): pass\n")
    return root


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/etc/passwd",
        "sub/../../source.py",
        "-option",
        "a\\b",
    ],
)
def test_input_paths_refuse_escape(interpreter, target, path):
    result = call(interpreter, target, paths=[path])
    assert result["error"] == {"code": "E_PATH"}


def test_explicit_root_alias_is_normalized_and_served(interpreter, target, tmp_path):
    alias = tmp_path / "root-alias"
    alias.symlink_to(target, target_is_directory=True)
    result = call(interpreter, alias, "ontology_lookup", query="sample")
    assert result["ok"], result
    assert result["data"]["matches"][0]["refs"] == ["source.py"]


@pytest.mark.parametrize(
    "path,reason",
    [
        ("/" + "Users/alice/Library/CloudStorage/OneDrive/repo", "macOS CloudStorage"),
        ("/users/ALICE/library/cloudstorage/Dropbox/repo", "macOS CloudStorage"),
        ("/" + "Users/alice/Library/Mobile Documents/com~apple~CloudDocs/repo", "iCloud Drive"),
        ("/" + "Users/alice/Library/CloudStorage", "macOS CloudStorage"),
        ("/" + "Users/alice/projects/repo", None),
        ("/" + "home/alice/CloudStorage/repo", None),
        ("/" + "Users/alice/Library/CloudStorage-backup/repo", None),
    ],
)
def test_cloud_sync_reason_path_shape(monkeypatch, path, reason):
    module = load_server()
    check = module.cloud_sync_reason
    with monkeypatch.context() as patch:
        patch.setattr(module.os, "stat", lambda *args, **kwargs: SimpleNamespace())
        assert check(PurePosixPath(path)) == reason


@pytest.mark.parametrize("attribute", [0x80000, 0x100000, 0x40000, 0x400000, 0x1000])
@pytest.mark.parametrize("marked", [Path("/local/repo"), Path("/local"), Path("/")])
def test_cloud_sync_reason_windows_attributes(monkeypatch, attribute, marked):
    module = load_server()
    check = module.cloud_sync_reason
    seen = []

    def fake_stat(path, *, follow_symlinks):
        assert follow_symlinks is False
        seen.append(path)
        return SimpleNamespace(st_file_attributes=attribute if path == marked else 0)

    with monkeypatch.context() as patch:
        patch.setattr(module.os, "stat", fake_stat)
        assert check(Path("/local/repo")) == "Windows cloud files"
    assert marked in seen


def test_cloud_sync_local_root_is_accepted(target):
    module = load_server()
    guard = module.Guard(str(target))
    try:
        assert guard.root == target.resolve(strict=True)
    finally:
        guard.close()


def test_cloud_sync_refusal_checks_resolved_root_before_open(monkeypatch, target, tmp_path):
    module = load_server()
    alias = tmp_path / "root-alias"
    alias.symlink_to(target, target_is_directory=True)
    seen = []

    def reason(path):
        seen.append(path)
        return "macOS CloudStorage"

    def unexpected_open(*args, **kwargs):
        pytest.fail("Cloud-synced root must be refused before opening")

    with monkeypatch.context() as patch:
        patch.setattr(module, "cloud_sync_reason", reason)
        patch.setattr(module.os, "open", unexpected_open)
        with pytest.raises(module.Refusal, match="E_CLOUD_SYNC"):
            module.Guard(str(alias))
    assert seen == [target.resolve(strict=True)]


def test_resolved_escape_is_refused_before_component_open(interpreter, target, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.txt").write_text("DO_NOT_DISCLOSE_SENTINEL")
    (target / "escape").symlink_to(outside, target_is_directory=True)
    wrapper = tmp_path / "containment.py"
    wrapper.write_text("""import json, runpy, sys
m = runpy.run_path(sys.argv[1])
guard = m["Guard"](sys.argv[2])
opened = []
def audit(event, args):
    if event == "open" and args[0] in ("escape", "payload.txt"):
        opened.append(args[0])
sys.addaudithook(audit)
try:
    guard.read("escape/payload.txt")
except m["Refusal"] as exc:
    code = exc.code
else:
    code = None
finally:
    guard.close()
print(json.dumps({"code": code, "opened": opened}))
""")
    completed = subprocess.run(
        [interpreter, "-I", "-B", "-u", str(wrapper), str(SERVER), str(target)],
        text=True, capture_output=True, timeout=15, env={},
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {"code": "E_PATH", "opened": []}


@pytest.mark.parametrize(
    "path",
    [
        ".ENV.local",
        "nested/secrets/value",
        "data.DB-wal",
        "a.sqlite3",
        ".ssh/config",
        ".aws/config",
        ".gnupg/key",
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".git-credentials",
        "Credentials.ini",
        "token.json",
        "tokens.json",
        "id_rsa.pub",
        "id_ed25519.pub",
        "cert.pem",
        "cert.key",
        "cert.p12",
        "cert.pfx",
        "cert.keystore",
    ],
)
def test_protected_direct_and_indirect(interpreter, target, path):
    candidate = target / path
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("DO_NOT_DISCLOSE_SENTINEL")
    assert call(interpreter, target, paths=[path])["error"] == {"code": "E_PROTECTED"}
    mapping = target / ".mir/ontology-map.json"
    data = json.loads(mapping.read_text())
    data["domain"]["concepts"][0]["ref"] = path
    mapping.write_text(json.dumps(data))
    for tool, kwargs in [
        ("ontology_lookup", {"query": "sample"}),
        ("ontology_impact", {"paths": ["source.py"]}),
        ("ontology_validate", {}),
    ]:
        assert call(interpreter, target, tool, **kwargs)["error"] == {"code": "E_PROTECTED"}


@pytest.mark.parametrize("interpreter,block_tomllib", PROFILE_RUNTIMES)
def test_symlink_special_and_profile(interpreter, block_tomllib, target, tmp_path):
    outside = tmp_path / "outside"
    outside.write_text("DO_NOT_DISCLOSE_SENTINEL")
    (target / "link").symlink_to(outside)
    assert call(interpreter, target, paths=["link"])["error"] == {"code": "E_PATH"}
    (target / "internal-link").symlink_to(target / "source.py")
    assert call(interpreter, target, paths=["internal-link"])["error"] == {"code": "E_PATH"}
    if sys.platform != "win32":
        os.mkfifo(target / "fifo")
        assert call(interpreter, target, paths=["fifo"])["error"] == {"code": "E_PATH"}
    (target / ".mir/repo-profile.toml").write_text(
        '[project]\nslug="test"\n[safety]\nprotected_paths=["source.py"]\n'
    )
    result = call(
        interpreter, target, "ontology_lookup", query="sample", block_tomllib=block_tomllib
    )
    if profile_available(interpreter, block_tomllib):
        assert result["error"] == {"code": "E_PROTECTED"}
    else:
        assert result["ok"] and result["profile_protections"] == "unavailable"


def test_size_depth_and_stale_cursor(interpreter, target):
    mapping = target / ".mir/ontology-map.json"
    data = json.loads(mapping.read_text())
    data["domain"]["concepts"] *= 4
    mapping.write_text(json.dumps(data))
    result = call(interpreter, target, "ontology_lookup", query="sample", page_size=1)
    assert result["next_cursor"]
    cursor = result["next_cursor"]
    data["domain"]["concepts"].append({"name": "sample new", "ref": "source.py"})
    mapping.write_text(json.dumps(data))
    assert call(interpreter, target, "ontology_lookup", query="sample", page_size=1, cursor=cursor)[
        "error"
    ] == {"code": "E_CURSOR"}
    mapping.write_text("[" * 33 + "0" + "]" * 33)
    assert call(interpreter, target, "ontology_lookup", query="sample")["error"] == {
        "code": "E_LIMIT"
    }
    mapping.write_bytes(b" " * (1024 * 1024 + 1))
    assert call(interpreter, target, "ontology_lookup", query="sample")["error"] == {
        "code": "E_LIMIT"
    }


def test_guard_aggregate_count_deadline_and_race(target, monkeypatch):
    module = load_server()
    guard = module.Guard(str(target))
    for index in range(257):
        (target / f"item{index}").write_text("x")
    with pytest.raises(module.Refusal, match="E_LIMIT"):
        for index in range(257):
            guard.read(f"item{index}")
    guard.close()

    guard = module.Guard(str(target))
    guard.deadline = 0
    with pytest.raises(module.Refusal, match="E_TIMEOUT"):
        guard.read("source.py")
    guard.close()
    guard = module.Guard(str(target))
    for index in range(5):
        (target / f"large{index}").write_bytes(b"x" * (1024 * 1024))
    with pytest.raises(module.Refusal, match="E_LIMIT"):
        for index in range(5):
            guard.read(f"large{index}")
    guard.close()
    guard = module.Guard(str(target))
    original = module.windows_open if sys.platform == "win32" else module.os.open
    outside = target.parent / "outside"
    outside.write_text("DO_NOT_DISCLOSE_SENTINEL")

    def replace(path, *args, **kwargs):
        if path == (target / "source.py" if sys.platform == "win32" else "source.py"):
            (target / "source.py").unlink()
            (target / "source.py").symlink_to(outside)
        return original(path, *args, **kwargs)

    if sys.platform == "win32":
        monkeypatch.setattr(module, "windows_open", replace)
    else:
        monkeypatch.setattr(module.os, "open", replace)
    with pytest.raises(module.Refusal):
        guard.read("source.py")
    guard.close()


def test_profile_change_is_refused_before_read(target):
    module = load_server()
    guard = module.Guard(str(target))
    (target / ".mir/repo-profile.toml").write_text(
        '[repo]\nslug="test"\n[paths]\nprotected_paths=["source.py"]\n'
    )
    with pytest.raises(module.Refusal, match="E_PATH"):
        guard.read("source.py")
    guard.close()


@pytest.mark.parametrize(
    "section,key",
    [
        ("paths", "protected_paths"),
        ("paths", "secret_paths"),
        ("boundaries", "secrets"),
    ],
)
@pytest.mark.parametrize("interpreter,block_tomllib", PROFILE_RUNTIMES)
def test_profile_repository_schema_protections(
    interpreter, block_tomllib, target, section, key
):
    (target / ".mir/repo-profile.toml").write_text(
        f'[repo]\nslug="test"\n[{section}]\n{key}=["source.py"]\n'
    )
    result = call(
        interpreter, target, "ontology_lookup", query="sample", block_tomllib=block_tomllib
    )
    if profile_available(interpreter, block_tomllib):
        assert result["error"] == {"code": "E_PROTECTED"}
    else:
        assert result["ok"] and result["profile_protections"] == "unavailable"


def test_indivisible_output_and_graph_endpoint(interpreter, target):
    graph = target / "spec/graph.yaml"
    graph.parent.mkdir()
    (target / ".env").write_text("DO_NOT_DISCLOSE_SENTINEL")
    graph.write_text("edges:\n  - [REQ-1, implemented_in, .env]\n")
    assert call(interpreter, target, "relations_query", anchor="REQ-1", purpose="implementation")[
        "error"
    ] == {"code": "E_PROTECTED"}
    mapping = target / ".mir/ontology-map.json"
    data = json.loads(mapping.read_text())
    data["domain"]["concepts"][0]["name"] = "sample" + "x" * 4096
    mapping.write_text(json.dumps(data))
    assert call(interpreter, target, "ontology_lookup", query="sample")["error"] == {
        "code": "E_LIMIT"
    }


def test_static_closed_imports_and_no_environment():
    files = [
        SERVER,
        ROOT / "plugins/mir-mcp/ontology/scripts/ontology_check.py",
        ROOT / "plugins/mir-mcp/shared/relations_query.py",
    ]
    reviewed = {
        "__future__", "argparse", "base64", "datetime", "fnmatch", "hashlib",
        "importlib", "json", "os", "pathlib", "re", "selectors", "signal", "stat",
        "subprocess", "sys", "time", "tomllib",
    }
    for path in files:
        tree = ast.parse(path.read_text(), feature_version=(3, 9))
        allowed = reviewed | ({"ctypes", "msvcrt", "threading"} if path == SERVER else set())
        loaders = []
        kernel_attributes = set()
        windows_imports = {
            child.lineno for branch in ast.walk(tree)
            if isinstance(branch, ast.If) and ast.dump(branch.test) == ast.dump(ast.parse(
                'sys.platform == "win32"', mode="eval"
            ).body)
            for child in branch.body if isinstance(child, ast.Import)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] in allowed for alias in node.names)
                for alias in node.names:
                    if alias.name in {"ctypes", "msvcrt"}:
                        assert alias.asname is None and node.lineno in windows_imports
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] in allowed
                assert (node.module or "").split(".")[0] not in {"ctypes", "msvcrt"}
            if isinstance(node, ast.Attribute):
                assert node.attr not in {
                    "environ", "getenv", "putenv", "expanduser", "system", "popen",
                    "posix_spawn", "spawnv", "spawnve", "path_hooks", "meta_path",
                }
                if isinstance(node.value, ast.Name) and node.value.id == "kernel32":
                    assert node.attr in {"CreateFileW", "GetFinalPathNameByHandleW", "CloseHandle"}
                    kernel_attributes.add(node.attr)
                if isinstance(node.value, ast.Name) and node.value.id == "msvcrt":
                    assert node.attr == "open_osfhandle"
                assert node.attr not in {"windll", "CDLL", "oledll", "LoadLibrary"}
                if node.attr == "WinDLL":
                    loaders.append(node)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "__import__"}
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "WinDLL":
                    assert path == SERVER
                    assert ast.dump(node) == ast.dump(ast.parse(
                        'ctypes.WinDLL("kernel32", use_last_error=True)', mode="eval"
                    ).body)
        assert len(loaders) == (1 if path == SERVER else 0)
        assert kernel_attributes == (
            {"CreateFileW", "GetFinalPathNameByHandleW", "CloseHandle"} if path == SERVER else set()
        )


def audit_run(interpreter, tmp_path, requests):
    wrapper = tmp_path / "audit.py"
    wrapper.write_text("""import os, runpy, subprocess, sys
def audit(event, args):
    if event == "open":
        mode, flags = args[1], args[2]
        writes = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags & writes:
            raise AssertionError("write denied")
    if event.startswith("socket.") or event == "os.putenv":
        raise AssertionError("forbidden event")
    if event in ("os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.chmod",
                 "os.chown", "os.utime", "os.symlink", "os.link", "os.truncate"):
        raise AssertionError("filesystem mutation denied")
    if event == "subprocess.Popen":
        raise AssertionError("child denied")
def trace(frame, event, arg):
    # Popen opens /dev/null before emitting its audit event. Observe entry too.
    if event == "call" and frame.f_code is subprocess.Popen.__init__.__code__:
        raise AssertionError("child denied")
sys.addaudithook(audit)
sys.setprofile(trace)
runpy.run_path(sys.argv[1], run_name="__main__")
""")
    return subprocess.run(
        [interpreter, "-I", "-B", "-u", str(wrapper), str(SERVER)],
        input=b"".join(requests),
        capture_output=True,
        timeout=15,
        env={},
    )


def test_runtime_audit_no_write_no_network(interpreter, target, tmp_path):
    (target / "spec").mkdir()
    (target / "spec/graph.yaml").write_text("edges:\n  - [REQ-1, implemented_in, source.py]\n")
    (target / ".env").write_text("DO_NOT_DISCLOSE_SENTINEL")
    requests = [b"{bad}\n"]
    cases = [
        ("ontology_validate", {"scope": "contract"}),
        ("ontology_validate", {"scope": "mapping"}),
        ("ontology_lookup", {"query": "sample"}),
        ("ontology_impact", {"paths": ["source.py"]}),
        ("handoff_pins", {"paths": ["source.py"]}),
        ("relations_query", {"anchor": "REQ-1", "purpose": "implementation"}),
        ("handoff_pins", {"paths": [".env"]}),
    ]
    for tool, arguments in cases:
        requests.append(
            (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "_meta": META,
                            "name": tool,
                            "arguments": {"target_root": str(target), **arguments},
                        },
                    }
                )
                + "\n"
            ).encode()
        )
    completed = audit_run(interpreter, tmp_path, requests)
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(responses) == 8
    assert responses[1]["result"]["structuredContent"]["ok"]
    assert completed.stderr == b""
    assert b"DO_NOT_DISCLOSE_SENTINEL" not in completed.stdout
    for index in (2, 3, 4, 6):
        assert responses[index]["result"]["structuredContent"]["ok"]
    assert responses[5]["result"]["structuredContent"]["error"] == {"code": "E_GIT"}
    assert responses[7]["result"]["structuredContent"]["error"] == {"code": "E_PROTECTED"}
    assert not list(target.rglob("*.pyc"))


@pytest.mark.parametrize("config", [
    '[extensions]\npartialClone = origin\n',
    '[remote "origin"]\npromisor = true\n',
], ids=["partial-clone", "promisor"])
def test_runtime_audit_refuses_network_git_before_spawn(interpreter, target, tmp_path, config):
    from test_mir_mcp_git import git_directory

    metadata = git_directory(target)
    with (metadata / "config").open("a") as stream:
        stream.write(config + '[remote "origin"]\nurl = https://127.0.0.1:9/never-contact\n')
    request = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {
            "_meta": META, "name": "handoff_pins",
            "arguments": {"target_root": str(target), "paths": ["source.py"]},
        },
    }
    # The shared audit harness denies every spawn (including helpers) and socket attempt.
    completed = audit_run(interpreter, tmp_path, [(json.dumps(request) + "\n").encode()])
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stderr == b""
    result = json.loads(completed.stdout)["result"]["structuredContent"]
    assert result["ok"] is False
    assert result["error"] == {"code": "E_GIT"}
    assert result["data"]["head"] is result["data"]["dirty"] is None
    assert result["data"]["sources"][0]["sha256"]
