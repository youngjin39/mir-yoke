"""Protocol and direct-hook parity for the persistent local extension bridge."""

import json
import pathlib
import subprocess
import sys

import pytest

from tools.mir_executor import local_hooks

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "local_bridge.py"
VERSION = "mir-executor.local@1"


def test_pre_execute_returns_mutated_namespace_without_changing_result(repo):
    client = Client(repo)
    reply = client.call(
        "pre_execute",
        [
            {"$type": "namespace", "value": {"repo_root": {"$type": "path", "value": str(repo)}}},
            {"$type": "path", "value": str(repo)},
        ],
    )
    assert reply["ok"]
    assert reply["handle"]
    assert reply["args"][0] == {
        "$type": "namespace",
        "value": {"repo_root": {"$type": "path", "value": str(repo)}, "changed": True},
    }
    client.close()


@pytest.fixture
def repo(tmp_path_factory):
    # The caller sets pytest basetemp to the authorized scratch directory.
    root = tmp_path_factory.mktemp("bridge-target")
    folder = root / "tools/mir_executor"
    folder.mkdir(parents=True)
    (folder / "local.py").write_text("""
from contextlib import contextmanager
from types import SimpleNamespace
print("loaded")
count = 0

def register_execute_options(parser):
    raise AssertionError("must not run")

def validate_brief(value, root):
    global count
    count += 1
    print("validated")
    return SimpleNamespace(value=value, count=count)

def render_brief(brief, root):
    return [brief.value, brief.count]

def pre_execute(args, root):
    args.changed = True
    return args

def job_identity(*args, **kwargs):
    return [args, kwargs]

def authorize_target(*args):
    raise ValueError("refused")

@contextmanager
def writer_scope(root):
    path = root / "scope.txt"
    path.write_text("entered")
    try:
        yield
    finally:
        path.write_text("exited")

def named(name):
    def hook(*args, **kwargs):
        return [name, args, kwargs]
    return hook

resolve_agent_route = named("resolve_agent_route")
before_run = named("before_run")
after_run = named("after_run")
after_provider_call = named("after_provider_call")
on_job_event = named("on_job_event")
""")
    return root


class Client:
    def __init__(self, repo):
        self.process = subprocess.Popen(
            [sys.executable, "-I", str(SCRIPT), str(repo)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.hello = json.loads(self.process.stdout.readline())

    def call(self, hook, args=(), **extra):
        frame = dict(version=VERSION, id=1, hook=hook, args=list(args), **extra)
        self.process.stdin.write(json.dumps(frame).encode() + b"\n")
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)
        output = self.process.stdout.read()
        errors = self.process.stderr.read()
        assert not output
        assert self.process.returncode == 0
        return errors


def test_should_load_once_and_reuse_opaque_brief(repo):
    client = Client(repo)
    assert client.hello["version"] == VERSION
    assert client.hello["register_execute_options"] is True
    assert "register_execute_options" not in client.hello["hooks"]
    brief = client.call("validate_brief", ["text", {"$type": "path", "value": str(repo)}])
    assert brief["ok"] and brief["handle"]
    assert client.call("render_brief", [None, str(repo)], handles={"0": brief["handle"]})[
        "result"
    ] == ["text", 1]
    assert client.call("validate_brief", ["next", str(repo)])["handle"] != brief["handle"]
    errors = client.close().decode()
    assert errors.count("loaded") == 1
    assert errors.count("validated") == 2


@pytest.mark.parametrize(
    "hook",
    [
        "job_identity",
        "resolve_agent_route",
        "before_run",
        "after_run",
        "after_provider_call",
        "on_job_event",
    ],
)
def test_should_match_direct_hook_mapping(repo, hook):
    client = Client(repo)
    direct = local_hooks.invoke_hook(repo, hook, "event", {"value": 2}, flag=True)
    response = client.call(hook, ["event", {"value": 2}], kwargs={"flag": True})
    assert response["ok"]
    assert response["result"] == json.loads(json.dumps(direct))
    client.close()


def test_should_keep_args_identity_and_cleanup_scope_on_eof(repo):
    client = Client(repo)
    namespace = client.call(
        "bridge.object", [{"$type": "namespace", "value": {"changed": False}}], force_handle=True
    )
    result = client.call("pre_execute", [None, str(repo)], handles={"0": namespace["handle"]})
    assert result["handle"] == namespace["handle"]
    context = client.call("writer_scope", [{"$type": "path", "value": str(repo)}])
    assert client.call("writer_scope.enter", [None], handles={"0": context["handle"]})["ok"]
    assert (repo / "scope.txt").read_text() == "entered"
    client.close()
    assert (repo / "scope.txt").read_text() == "exited"


def test_should_exit_scope_explicitly(repo):
    client = Client(repo)
    context = client.call("writer_scope", [{"$type": "path", "value": str(repo)}])
    assert client.call("writer_scope.enter", [None], handles={"0": context["handle"]})["ok"]
    assert client.call("writer_scope.exit", [None], handles={"0": context["handle"]})["ok"]
    assert (repo / "scope.txt").read_text() == "exited"
    client.close()


def test_should_report_hook_errors_and_reject_parser_hook(repo):
    client = Client(repo)
    error = client.call("authorize_target")["error"]
    assert error == {"type": "ValueError", "message": "refused"}
    assert not client.call("register_execute_options")["ok"]
    assert not client.call("render_brief", [None], handles={"0": "missing"})["ok"]
    client.close()


@pytest.mark.parametrize(
    "raw",
    [b"{\n", b"[]\n", b"\xff\n", b"{}\n", b"x" * (1024 * 1024 + 1) + b"\n"],
    ids=["json", "array", "utf8", "version", "oversize"],
)
def test_should_reject_malformed_frames(repo, raw):
    client = Client(repo)
    client.process.stdin.write(raw)
    client.process.stdin.flush()
    assert json.loads(client.process.stdout.readline())["ok"] is False
    assert client.call("job_identity")["ok"]
    client.close()


def test_should_advertise_empty_hooks_without_local_module(tmp_path):
    client = Client(tmp_path)
    assert client.hello == {"version": VERSION, "hooks": [], "register_execute_options": False}
    assert client.call("validate_brief")["result"] is None
    client.close()


def test_should_keep_json_brief_handle_and_validate_before_side_effects(repo):
    path = repo / "tools/mir_executor/local.py"
    path.write_text(
        path.read_text() + "\ndef validate_brief(value, root):\n    return {'value': value}\n"
    )
    client = Client(repo)
    brief = client.call("validate_brief", ["text", str(repo)])
    assert brief["result"] == {"value": "text"}
    assert brief["handle"]
    response = client.call("bridge.object", [None], handles={"0": brief["handle"]})
    assert response["handle"] == brief["handle"]
    response = client.call(
        "writer_scope", [{"$type": "path", "value": str(repo)}], force_handle="bad"
    )
    assert not response["ok"]
    assert not (repo / "scope.txt").exists()
    client.close()


def test_should_map_base_exception_to_error_frame(repo):
    path = repo / "tools/mir_executor/local.py"
    path.write_text(path.read_text() + "\ndef before_run():\n    raise SystemExit('stopped')\n")
    client = Client(repo)
    assert client.call("before_run")["error"] == {"type": "SystemExit", "message": "stopped"}
    assert client.call("job_identity")["ok"]
    client.close()


PARITY_HOOKS = [
    "authorize_target",
    "pre_execute",
    "validate_brief",
    "render_brief",
    "job_identity",
    "resolve_agent_route",
    "before_run",
    "after_run",
    "after_provider_call",
    "on_job_event",
    "writer_scope",
]


@pytest.mark.parametrize("hook", PARITY_HOOKS)
def test_should_match_every_direct_hook_value_and_side_effect_order(repo, hook):
    source = """
from pathlib import Path
from contextlib import contextmanager
LOG = Path(__file__).parents[2] / "trace.txt"
def record(value):
    with LOG.open("a") as stream:
        stream.write(value + "\\n")
def make_hook(name):
    def call(*args, **kwargs):
        record(name)
        return [name, args, kwargs]
    return call
@contextmanager
def writer_scope(*args, **kwargs):
    record("writer_scope.enter")
    try:
        yield
    finally:
        record("writer_scope.exit")
"""
    source += "\n".join(
        f"{name} = make_hook({name!r})" for name in PARITY_HOOKS if name != "writer_scope"
    )
    (repo / "tools/mir_executor/local.py").write_text(source)
    trace = repo / "trace.txt"
    if hook == "writer_scope":
        with local_hooks.invoke_hook(repo, hook, "input"):
            pass
        expected = None
    else:
        expected = local_hooks.invoke_hook(repo, hook, "input", flag=True)
    direct_trace = trace.read_text()
    trace.unlink()
    client = Client(repo)
    actual = client.call(
        hook, ["input"], **({"kwargs": {"flag": True}} if hook != "writer_scope" else {})
    )
    if hook == "writer_scope":
        handle = actual["handle"]
        assert client.call("writer_scope.enter", [None], handles={"0": handle})["ok"]
        assert client.call("writer_scope.exit", [None], handles={"0": handle})["ok"]
    else:
        assert actual["result"] == json.loads(json.dumps(expected))
    assert trace.read_text() == direct_trace
    client.close()


@pytest.mark.parametrize("hook", PARITY_HOOKS)
def test_should_match_every_direct_hook_exception(repo, hook):
    source = f"def {hook}(*args, **kwargs):\n    raise LookupError('hook refused: {hook}')\n"
    (repo / "tools/mir_executor/local.py").write_text(source)
    with pytest.raises(LookupError) as caught:
        local_hooks.invoke_hook(repo, hook)
    client = Client(repo)
    assert client.call(hook)["error"] == {
        "type": type(caught.value).__name__,
        "message": str(caught.value),
    }
    client.close()


def test_should_freeze_loaded_module_until_process_exit(repo):
    client = Client(repo)
    path = repo / "tools/mir_executor/local.py"
    path.write_text("def job_identity():\n    return 'changed'\n")
    assert client.call("job_identity")["result"] == [[], {}]
    client.close()


@pytest.mark.parametrize("stage", ["enter", "exit"])
def test_should_match_writer_scope_entry_and_exit_errors(repo, stage):
    source = f"""
from contextlib import contextmanager
@contextmanager
def writer_scope():
    if {stage!r} == "enter":
        raise OSError("scope enter")
    yield
    raise OSError("scope exit")
"""
    (repo / "tools/mir_executor/local.py").write_text(source)
    with pytest.raises(OSError) as caught:
        with local_hooks.invoke_hook(repo, "writer_scope"):
            pass
    client = Client(repo)
    handle = client.call("writer_scope")["handle"]
    entered = client.call("writer_scope.enter", [None], handles={"0": handle})
    actual = (
        entered
        if stage == "enter"
        else client.call("writer_scope.exit", [None], handles={"0": handle})
    )
    assert actual["error"] == {"type": "OSError", "message": str(caught.value)}
    client.close()


def test_should_recover_from_deep_json_and_reject_numeric_overflow_id(repo):
    client = Client(repo)
    client.process.stdin.write(b"[" * 20000 + b"0" + b"]" * 20000 + b"\n")
    client.process.stdin.flush()
    assert json.loads(client.process.stdout.readline())["error"]["type"] == "RecursionError"
    frame = b'{"version":"mir-executor.local@1","id":1e999,"hook":"job_identity"}\n'
    client.process.stdin.write(frame)
    client.process.stdin.flush()
    assert not json.loads(client.process.stdout.readline())["ok"]
    assert client.call("job_identity")["ok"]
    client.close()


def test_should_run_installed_package_module_under_isolation(repo, tmp_path):
    import shutil
    import venv

    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False).create(environment)
    interpreter = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    site_packages = subprocess.check_output(
        [str(interpreter), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        text=True,
    )
    package_root = pathlib.Path(site_packages.strip()) / "tools/mir_executor"
    package_root.mkdir(parents=True)
    for name in ("__init__.py", "local_bridge.py", "local_hooks.py"):
        shutil.copyfile(SCRIPT.parent / name, package_root / name)
    result = subprocess.run(
        [str(interpreter), "-I", "-m", "tools.mir_executor.local_bridge", str(repo)],
        input=b"",
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["version"] == VERSION


def test_should_bound_response_and_keep_request_identity(repo):
    path = repo / "tools/mir_executor/local.py"
    path.write_text("def job_identity():\n    return 'x' * (1024 * 1024)\n")
    client = Client(repo)
    response = client.call("job_identity")
    assert response["id"] == 1
    assert response["error"] == {"type": "ValueError", "message": "Response exceeds frame limit"}
    client.close()


def test_should_reject_unterminated_frame_on_eof(repo):
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(repo)],
        input=b'{"version":"mir-executor.local@1","id":1,"hook":"job_identity"}',
        capture_output=True,
        timeout=5,
    )
    hello, response = [json.loads(line) for line in result.stdout.splitlines()]
    assert hello["version"] == VERSION
    assert response["error"]["message"] == "Request must end with a newline"
    assert result.returncode == 0


def test_should_preserve_provider_result_dataclass_through_replacement(repo):
    (repo / "tools/mir_executor/local.py").write_text("""
from dataclasses import replace

def after_provider_call(result, metadata):
    assert result.command == ['fake', 'app-server']
    assert metadata == {'attempt': 1}
    return replace(result, exit_code=7, stdout='replaced', duration_seconds=0.0)
""")
    client = Client(repo)
    value = {
        "command": ["fake", "app-server"], "exit_code": 0,
        "stdout": "original", "stderr": "", "duration_seconds": 1.0,
    }
    reply = client.call("after_provider_call", [
        {"$type": "subprocess_result", "value": value}, {"attempt": 1},
    ])
    assert reply["ok"], reply
    assert reply["result"] == {"$type": "subprocess_result", "value": {
        **value, "exit_code": 7, "stdout": "replaced", "duration_seconds": 0.0,
    }}
    client.close()


def test_dispatch_dataclasses_survive_hook_replacement(repo):
    """Dispatch hooks receive real immutable records, including path and tuple fields."""
    (repo / "tools/mir_executor/local.py").write_text('''
from dataclasses import replace
from pathlib import Path
from tools.mir_executor.dispatch import CodexAttempt
from tools.mir_executor.worktree import DispatchWorktree

def after_provider_call(result, metadata):
    assert isinstance(result, CodexAttempt)
    assert result.tokens_used == (("input_tokens", 7),)
    return replace(result, exit_code=1, retryable=False, blocked_reason="budget")

def before_run(worktree, attempt):
    assert isinstance(worktree, DispatchWorktree)
    assert isinstance(worktree.path, Path)
    assert attempt == 1
''', encoding="utf-8")
    client = Client(repo)
    try:
        paths = {key: {"$type": "path", "value": str(repo / key)} for key in (
            "main_repo_root", "path", "brief_path", "status_path", "result_path",
        )}
        worktree = {"$type": "dispatch_worktree", "value": dict(
            paths, dispatch_id="fixture", branch="fixture", base_commit="fixture",
        )}
        assert client.call("before_run", [worktree, 1])["ok"]
        reply = client.call("after_provider_call", [
            {"$type": "codex_attempt", "value": {
                "exit_code": 0, "tokens_used": [["input_tokens", 7]],
            }}, {},
        ])
        assert reply["ok"], reply
        assert reply["result"]["$type"] == "codex_attempt"
        assert reply["result"]["value"]["blocked_reason"] == "budget"
        assert reply["result"]["value"]["tokens_used"] == [["input_tokens", 7]]
    finally:
        client.close()
