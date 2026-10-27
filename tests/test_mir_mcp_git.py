"""Fixed Git queries, preflight refusals, bounded capture and pin projection."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "plugins/mir-mcp/mir_mcp.py"
INTERPRETERS = ["/usr/bin/python3", str(ROOT / ".venv/bin/python")]
SUFFIXES = [
    ("rev-parse", "--verify", "HEAD"),
    ("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=all"),
    ("log", "-1", "--format=%H", "--", "source.txt"),
    ("diff", "--quiet", "--no-ext-diff", "--no-textconv", "--ignore-submodules=all",
     "HEAD", "--", "source.txt"),
]
ENV = {
    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_ATTR_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}
PREFIX = [
    "/usr/bin/git", "--no-optional-locks", "--literal-pathspecs",
    "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
    "-c", "core.hooksPath=/dev/null", "-c", "core.attributesFile=/dev/null",
    "-c", "submodule.recurse=false",
]


@pytest.fixture
def server():
    spec = importlib.util.spec_from_file_location("git_review_mir_mcp", SERVER)
    module = importlib.util.module_from_spec(spec)
    # Compile from source so a test never writes __pycache__ into a plugin tree.
    exec(compile(SERVER.read_bytes(), str(SERVER), "exec"), module.__dict__)
    return module


def setup_git(root, *args):
    return subprocess.run(
        ["/usr/bin/git", "-c", "init.templateDir=", "-c", "user.name=Test",
         "-c", "user.email=test@example.invalid", "-C", str(root), *args],
        capture_output=True, check=True, env=ENV,
    ).stdout.decode().strip()


@pytest.fixture
def repo(tmp_path):
    setup_git(tmp_path, "init", "-q")
    (tmp_path / "source.txt").write_text("source\n")
    setup_git(tmp_path, "add", "--", "source.txt")
    setup_git(tmp_path, "commit", "-qm", "initial")
    return tmp_path


def git_directory(root):
    metadata = root / ".git"
    (metadata / "refs/heads").mkdir(parents=True)
    (metadata / "objects").mkdir()
    (metadata / "HEAD").write_text("ref: refs/heads/main\n")
    (metadata / "refs/heads/main").write_text("a" * 40 + "\n")
    (metadata / "config").write_text("[core]\nrepositoryformatversion = 0\nbare = false\n")
    return metadata


def forbid_child(*args, **kwargs):
    raise AssertionError("Git preflight must refuse before spawning")


def query(server, root, suffix):
    io = server.Guard(str(root))
    try:
        return server.run_git(io, "test", *suffix)
    finally:
        io.close()


def assert_refused(server, root, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", forbid_child)
    io = server.Guard(str(root))
    try:
        assert server.git_preflight(io) is False
        with pytest.raises(server.Refusal, match="^E_GIT$"):
            server.run_git(io, "head", *SUFFIXES[0])
    finally:
        io.close()


def test_should_admit_ordinary_git_metadata(server, tmp_path):
    git_directory(tmp_path)
    io = server.Guard(str(tmp_path))
    try:
        assert server.git_preflight(io) is True
    finally:
        io.close()


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_should_run_only_exact_argv_and_environment(server, repo, monkeypatch, suffix):
    original = subprocess.Popen
    calls = []

    def capture(argv, **kwargs):
        calls.append((argv, kwargs))
        return original(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", capture)
    value = query(server, repo, suffix)
    expected = setup_git(repo, "rev-parse", "HEAD") if suffix[0] in ("log", "rev-parse") else False
    assert value == expected
    argv, kwargs = calls[0]
    assert argv == [*PREFIX, "-C", str(repo), *suffix]
    assert kwargs == {
        "stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
        "shell": False, "env": ENV,
    }


@pytest.mark.parametrize("interpreter", INTERPRETERS, ids=["system-python", "venv-python"])
def test_gitlink_only_nested_filter_never_runs_over_stdio(interpreter, repo):
    from test_mir_mcp_protocol import _request, _run, _tool_result

    nested = repo / "nested"
    nested.mkdir()
    setup_git(nested, "init", "-q")
    (nested / "filtered.txt").write_text("tracked\n")
    (nested / ".gitattributes").write_text("filtered.txt filter=sentinel\n")
    setup_git(nested, "add", "--", ".gitattributes", "filtered.txt")
    setup_git(nested, "commit", "-qm", "nested fixture")
    head = setup_git(nested, "rev-parse", "HEAD")
    setup_git(repo, "update-index", "--add", "--cacheinfo", "160000," + head + ",nested")
    setup_git(repo, "commit", "-qm", "gitlink without gitmodules")
    sentinel = nested / "FILTER_SENTINEL"
    setup_git(nested, "config", "filter.sentinel.clean", "touch FILTER_SENTINEL; cat")
    setup_git(nested, "config", "filter.sentinel.required", "true")
    filtered = nested / "filtered.txt"
    filtered.write_text("changed\n")  # Same size: Git must compare content, invoking the filter.
    modified = filtered.stat()
    os.utime(filtered, ns=(modified.st_atime_ns, modified.st_mtime_ns - 2000000000))
    assert not (repo / ".gitmodules").exists()
    assert not sentinel.exists()

    # Prove this index-only fixture executes the helper without submodule ignoring.
    setup_git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    assert sentinel.exists()
    sentinel.unlink()

    reply = _run(interpreter, [_request("tools/call", {
        "name": "handoff_pins",
        "arguments": {"target_root": str(repo), "paths": ["source.txt"]},
    })], cwd=repo)[0]
    assert not sentinel.exists(), "Git descended through the index and ran a nested filter"
    pins = _tool_result(reply)
    assert pins["data"]["sources"][0]["sha256"] == hashlib.sha256(b"source\n").hexdigest()
    head_pin = next(item for item in pins["data"]["pin_inventory"] if item["pin"] == "head")
    assert head_pin["availability"] == ("available" if pins["data"]["head"] else "unknown")


@pytest.mark.parametrize("kind", ["missing", "gitfile", "symlink", "special"])
def test_should_refuse_nonlocal_git_directory(server, tmp_path, monkeypatch, kind):
    root = tmp_path / "target"
    root.mkdir()
    if kind == "gitfile":
        (root / ".git").write_text("gitdir: /outside/repository\n")
    elif kind == "symlink":
        metadata = git_directory(tmp_path / "outside")
        (root / ".git").symlink_to(metadata, target_is_directory=True)
    elif kind == "special":
        import os
        os.mkfifo(root / ".git")
    assert_refused(server, root, monkeypatch)


@pytest.mark.parametrize("relative", [
    ".git/commondir", ".git/objects/info/alternates", ".git/objects/info/http-alternates",
    ".git/config.worktree", ".git/modules", ".gitmodules",
])
def test_should_refuse_metadata_redirections(server, tmp_path, monkeypatch, relative):
    git_directory(tmp_path)
    pointer = tmp_path / relative
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text("/outside/SENTINEL\n")
    assert_refused(server, tmp_path, monkeypatch)


@pytest.mark.parametrize("config", [
    '[include]\npath = /outside/SENTINEL\n',
    '[includeIf "gitdir:*"]\npath = /outside/SENTINEL\n',
    '[InClUdE.path]\nvalue = /outside/SENTINEL\n',
    '[core]\nworktree = /outside/SENTINEL\n',
    '[core]\ngitDir = /outside/SENTINEL\n',
    '[extensions]\nworktreeConfig = true\n',
    '[extensions]\npartialClone = origin\n',
    '[remote "origin"]\npromisor = true\n',
    '[submodule "child"]\nactive = true\n',
    '[filter "probe"]\nclean = /outside/SENTINEL\n',
    '[core]\nbare = false\\\ncontinued\n',
    '[bad section\n',
    'unscoped = true\n',
    '[core]\n1invalid = true\n',
])
def test_should_refuse_unsafe_or_unparsed_config(server, tmp_path, monkeypatch, config):
    metadata = git_directory(tmp_path)
    (metadata / "config").write_text(config)
    assert_refused(server, tmp_path, monkeypatch)


@pytest.mark.parametrize("section,key", [("core", "excludesFile"), ("diff", "orderFile")])
@pytest.mark.parametrize("value", ["/outside/GIT_REDIRECT_SENTINEL", ".git/info/exclude"])
def test_should_refuse_git_config_read_redirections(
    server, tmp_path, monkeypatch, section, key, value
):
    metadata = git_directory(tmp_path)
    (metadata / "config").write_text(f"[{section}]\n{key} = {value}\n")
    assert_refused(server, tmp_path, monkeypatch)


@pytest.mark.parametrize("relative", [
    ".git/config", ".git/HEAD", ".git/index", ".git/objects", ".git/refs",
    ".git/refs/heads/main", ".git/packed-refs", ".git/shallow",
])
def test_should_refuse_fixed_metadata_symlinks(server, tmp_path, monkeypatch, relative):
    root = tmp_path / "target"
    metadata = git_directory(root)
    path = root / relative
    if path.is_dir():
        path.rename(metadata / (path.name + "-original"))
    elif path.exists():
        path.unlink()
    outside = tmp_path / "outside"
    outside.write_text("SENTINEL")
    path.symlink_to(outside)
    assert_refused(server, root, monkeypatch)


def test_should_refuse_refs_symlink_with_detached_head(server, tmp_path, monkeypatch):
    metadata = git_directory(tmp_path)
    (metadata / "HEAD").write_text("a" * 40 + "\n")
    refs = metadata / "refs"
    original = metadata / "refs-original"
    refs.rename(original)
    refs.symlink_to(original, target_is_directory=True)
    assert_refused(server, tmp_path, monkeypatch)


@pytest.mark.parametrize("head", [
    "ref: objects/unsafe\n", "invalid-detached-head\n", "a" * 39 + "\n",
], ids=["outside-refs", "malformed-detached", "short-detached"])
def test_should_refuse_invalid_head_before_spawn(server, tmp_path, monkeypatch, head):
    metadata = git_directory(tmp_path)
    (metadata / "HEAD").write_text(head)
    assert_refused(server, tmp_path, monkeypatch)


@pytest.mark.parametrize("suffix", [
    ("config", "--global", "--list"), ("show", "HEAD:source.txt"),
    ("log", "-1", "--format=%H", "--", "../outside"),
    ("log", "-1", "--format=%H", "--", "./source.txt"),
    ("log", "-1", "--format=%H", "--", "-option"),
    ("log", "-1", "--format=%H", "--", ".env"),
    ("diff", "--quiet", "--no-ext-diff", "--no-textconv", "HEAD", "--", ".env"),
    ("status", ";", "touch", "marker"),
])
def test_should_refuse_invalid_or_protected_slots(server, repo, monkeypatch, suffix):
    monkeypatch.setattr(subprocess, "Popen", forbid_child)
    with pytest.raises(server.Refusal, match="^E_GIT$"):
        query(server, repo, suffix)


def test_should_expose_only_booleans_for_protected_worktree_changes(server, repo):
    protected = repo / ".env"
    protected.write_text("PROTECTED_SENTINEL_INITIAL\n")
    setup_git(repo, "add", "--", ".env")
    setup_git(repo, "commit", "-qm", "protected fixture")
    protected.write_text("PROTECTED_SENTINEL_CHANGED\n")
    assert query(server, repo, SUFFIXES[1]) is True
    assert query(server, repo, SUFFIXES[3]) is False
    (repo / "source.txt").write_text("changed\n")
    assert query(server, repo, SUFFIXES[3]) is True


def test_should_not_run_hooks_textconv_external_diff_or_fsmonitor(server, repo):
    marker = repo / "HELPER_EXECUTED"
    helper = repo / "probe.sh"
    helper.write_text('#!/bin/sh\nprintf invoked > "' + str(marker) + '"\n')
    helper.chmod(0o755)
    (repo / ".gitattributes").write_text("source.txt diff=probe\n")
    for key, value in (
        ("core.hooksPath", str(repo)), ("core.fsmonitor", str(helper)),
        ("diff.external", str(helper)), ("diff.probe.textconv", str(helper)),
    ):
        setup_git(repo, "config", key, value)
    (repo / "post-index-change").write_bytes(helper.read_bytes())
    (repo / "post-index-change").chmod(0o755)
    (repo / "source.txt").write_text("changed\n")
    before = {
        p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*") if p.is_file()
    }
    for suffix in SUFFIXES:
        query(server, repo, suffix)
    assert not marker.exists()
    after = {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    assert after == before


def test_should_refuse_configured_clean_filter_without_running_it(server, repo, monkeypatch):
    marker = repo / "FILTER_EXECUTED"
    setup_git(repo, "config", "filter.probe.clean", "touch '" + str(marker) + "'")
    (repo / ".gitattributes").write_text("source.txt filter=probe\n")
    assert_refused(server, repo, monkeypatch)
    assert not marker.exists()


def test_should_return_none_for_ordinary_git_failure(server, tmp_path):
    setup_git(tmp_path, "init", "-q")
    assert query(server, tmp_path, SUFFIXES[0]) is None
    assert query(server, tmp_path, SUFFIXES[2]) is None


@pytest.mark.parametrize("failure", ["preflight", "spawn", "child"])
def test_should_keep_partial_pins_and_never_disclose_git_errors(
    server, repo, monkeypatch, failure
):
    mapping = repo / ".mir/ontology-map.json"
    mapping.parent.mkdir()
    payload = b'{"contract":{"id":"mir.common-semantics","version":"1.1.0"}}'
    mapping.write_bytes(payload)
    original = subprocess.Popen
    if failure == "preflight":
        (repo / ".git/commondir").write_text("/outside/GIT_ERROR_SENTINEL\n")
        monkeypatch.setattr(subprocess, "Popen", forbid_child)
    else:
        def child(argv, **kwargs):
            if failure == "spawn":
                raise OSError("GIT_ERROR_SENTINEL")
            return original(
                [sys.executable, "-I", "-B", "-u", "-c",
                 "import sys; print('GIT_ERROR_SENTINEL',file=sys.stderr); sys.exit(2)"],
                **kwargs,
            )
        monkeypatch.setattr(subprocess, "Popen", child)
    result = server.execute("handoff_pins", {"target_root": str(repo), "paths": ["source.txt"]})
    assert result["ok"] is False
    assert result["error"] == {"code": "E_GIT"}
    pins = result["data"]
    assert pins["head"] is pins["dirty"] is None
    assert pins["sources"][0]["revision"] is None
    assert pins["sources"][0]["sha256"] == hashlib.sha256(b"source\n").hexdigest()
    assert pins["mapping_sha256"] == hashlib.sha256(payload).hexdigest()
    assert pins["contract_sha256"]
    assert "GIT_ERROR_SENTINEL" not in json.dumps(result)


@pytest.mark.parametrize("section,key", [("core", "excludesFile"), ("diff", "orderFile")])
def test_should_keep_partial_pins_after_config_read_redirection_refusal(
    server, repo, monkeypatch, section, key
):
    config = repo / ".git/config"
    with config.open("a") as stream:
        stream.write(f"\n[{section}]\n{key} = /outside/GIT_REDIRECT_SENTINEL\n")
    monkeypatch.setattr(subprocess, "Popen", forbid_child)
    result = server.execute("handoff_pins", {"target_root": str(repo), "paths": ["source.txt"]})
    assert result["ok"] is False
    assert result["error"] == {"code": "E_GIT"}
    pins = result["data"]
    assert pins["head"] is pins["dirty"] is None
    assert pins["sources"][0]["revision"] is None
    assert pins["sources"][0]["sha256"] == hashlib.sha256(b"source\n").hexdigest()
    assert pins["contract_sha256"]
    assert "GIT_REDIRECT_SENTINEL" not in json.dumps(result)


@pytest.mark.parametrize("mode,code", [
    ("stdout", "E_LIMIT"), ("stderr", "E_LIMIT"), ("combined", "E_LIMIT"),
    ("timeout", "E_TIMEOUT"), ("invalid", "E_GIT"), ("error", "E_GIT"),
])
def test_should_bound_capture_reap_and_hide_child_errors(server, repo, monkeypatch, mode, code):
    original = subprocess.Popen
    children = []
    scripts = {
        "stdout": "import os; os.write(1,b'SENTINEL'*10000)",
        "stderr": "import os; os.write(2,b'SENTINEL'*10000)",
        "combined": "import os; os.write(1,b'x'*40000); os.write(2,b'SENTINEL'*5000)",
        "timeout": "import time; time.sleep(30)",
        "invalid": "print('CHILD_OUTPUT_SENTINEL')",
    }

    def child(argv, **kwargs):
        if mode == "error":
            raise OSError("SUBPROCESS_ERROR_SENTINEL")
        process = original([sys.executable, "-I", "-B", "-u", "-c", scripts[mode]], **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", child)
    if mode == "timeout":
        monkeypatch.setattr(server, "GIT_RESERVE", 9.95)
    start = time.monotonic()
    with pytest.raises(server.Refusal) as failure:
        query(server, repo, SUFFIXES[0])
    assert str(failure.value) == code
    assert time.monotonic() - start < 5
    assert all(process.poll() is not None for process in children)


def test_should_honor_call_deadline_before_spawn(server, repo, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", forbid_child)
    io = server.Guard(str(repo))
    io.deadline = time.monotonic() - 1
    try:
        with pytest.raises(server.Refusal, match="^E_TIMEOUT$"):
            server.run_git(io, "head", *SUFFIXES[0])
    finally:
        io.close()


def slow_clock(server, monkeypatch, steps):
    """Advance the server clock when a matching Git query spawns, without sleeping."""
    original = subprocess.Popen
    offset = [0.0]
    monkeypatch.setattr(server, "time", types.SimpleNamespace(
        monotonic=lambda: time.monotonic() + offset[0]))

    def child(argv, **kwargs):
        for word, (jump, script) in steps.items():
            if word in argv:
                offset[0] += jump
                if script is not None:
                    argv = [sys.executable, "-I", "-B", "-u", "-c", script]
        return original(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", child)


def pins_call(server, repo):
    return server.execute("handoff_pins", {"target_root": str(repo), "paths": ["source.txt"]})


def unknown_seconds(pins, label, code):
    [item] = [item for item in pins["unknowns"] if item.startswith(label + ": ")]
    match = re.fullmatch(re.escape(label) + ": " + code + r" after (\d+\.\d\d) s", item)
    assert match, item
    return float(match[1])


def test_should_let_slow_status_use_the_call_budget(server, repo, monkeypatch):
    slow_clock(server, monkeypatch, {"status": (6.0, None)})
    result = pins_call(server, repo)
    assert result["ok"] is True and result["error"] is None
    assert result["data"]["dirty"] is False
    assert not [item for item in result["data"]["unknowns"] if item.startswith("dirty")]


@pytest.mark.parametrize("mode", ["error", "timeout"])
def test_should_cost_a_failed_query_only_its_own_pin(server, repo, monkeypatch, mode):
    head = setup_git(repo, "rev-parse", "HEAD")
    if mode == "error":
        slow_clock(server, monkeypatch, {"status": (0.0, "import sys; sys.exit(2)")})
    else:
        slow_clock(server, monkeypatch, {"status": (9.5, None)})
    result = pins_call(server, repo)
    assert result["ok"] is True and result["error"] is None
    pins = result["data"]
    assert pins["head"] == head
    assert pins["dirty"] is None
    source = pins["sources"][0]
    if mode == "error":
        assert unknown_seconds(pins, "dirty", "E_GIT") < 5
        assert source["revision"] == head
        assert source["modified_vs_head"] is False
        assert [item for item in pins["unknowns"] if "E_" in item] == [
            next(item for item in pins["unknowns"] if item.startswith("dirty: "))]
    else:
        assert 9.5 <= unknown_seconds(pins, "dirty", "E_TIMEOUT") < 10
        # The budget is spent, so each later query is named on its own label.
        assert unknown_seconds(pins, "source.txt.revision", "E_TIMEOUT") < 0.5
        assert source["revision"] is None
        assert source["sha256"] == hashlib.sha256(b"source\n").hexdigest()


def test_should_answer_before_the_call_alarm_when_git_hangs(server, repo, monkeypatch):
    head = setup_git(repo, "rev-parse", "HEAD")
    elapsed = 8.5
    # The alarm keeps its 10 s schedule on the server clock, 8.5 s of which pass at once.
    real = server.signal.setitimer
    monkeypatch.setattr(server, "signal", types.SimpleNamespace(
        ITIMER_REAL=server.signal.ITIMER_REAL,
        setitimer=lambda which, value: real(which, value and value - elapsed)))
    slow_clock(server, monkeypatch, {
        "rev-parse": (elapsed, None), "status": (0.0, "import time; time.sleep(30)")})
    fired = []

    def alarm(signum, frame):
        fired.append(signum)
        raise server.Refusal("E_TIMEOUT")

    previous = signal.signal(signal.SIGALRM, alarm)
    try:
        start = time.monotonic()
        reply = server.Protocol().request({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                          "io.modelcontextprotocol/clientCapabilities": {}},
                "name": "handoff_pins",
                "arguments": {"target_root": str(repo), "paths": ["source.txt"]},
            },
        })
        wall = time.monotonic() - start
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    assert not fired
    assert wall < 10 - elapsed
    result = reply["result"]["structuredContent"]
    assert result["ok"] is True and result["error"] is None
    assert result["data"]["head"] == head
    assert unknown_seconds(result["data"], "dirty", "E_TIMEOUT") < 10 - elapsed


def test_should_accept_exact_combined_output_limit_without_disclosure(server, repo, monkeypatch):
    original = subprocess.Popen
    commit = "a" * 40

    def child(argv, **kwargs):
        return original(
            [sys.executable, "-I", "-B", "-u", "-c",
             "import os; os.write(1,b'a'*40+b'\\n'); os.write(2,b'S'*65495)"],
            **kwargs,
        )

    monkeypatch.setattr(subprocess, "Popen", child)
    assert query(server, repo, SUFFIXES[0]) == commit


@pytest.mark.parametrize("interpreter", INTERPRETERS, ids=["system-python", "venv-python"])
def test_protocol_should_report_commit_pins_and_only_dirty_for_protected_change(interpreter, repo):
    (repo / ".env").write_text("PROTECTED_SENTINEL_INITIAL\n")
    setup_git(repo, "add", "--", ".env")
    setup_git(repo, "commit", "-qm", "protected fixture")
    head = setup_git(repo, "rev-parse", "HEAD")
    revision = setup_git(repo, "log", "-1", "--format=%H", "--", "source.txt")
    (repo / ".env").write_text("PROTECTED_SENTINEL_CHANGED\n")
    request = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {
            "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                      "io.modelcontextprotocol/clientCapabilities": {}},
            "name": "handoff_pins",
            "arguments": {"target_root": str(repo), "paths": ["source.txt"]},
        },
    }
    result = subprocess.run(
        [interpreter, "-I", "-B", "-u", str(SERVER)], input=json.dumps(request) + "\n",
        text=True, capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "PROTECTED_SENTINEL" not in result.stdout
    assert len(result.stdout.encode()) <= 16384
    response = json.loads(result.stdout)["result"]["structuredContent"]
    assert response["ok"], response
    pins = response["data"]
    assert pins["head"] == head
    assert pins["dirty"] is True
    assert pins["sources"][0]["revision"] == revision
    assert pins["sources"][0]["modified_vs_head"] is False
    assert pins["sources"][0]["sha256"] == hashlib.sha256(b"source\n").hexdigest()
    assert not list(repo.rglob("*.pyc"))
