"""Compare executor query process bytes with the unchanged Python CLI."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import runpy
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tools.mir_executor.jobs import JobRecord, JobRegistry


@contextlib.contextmanager
def _connect(path):
    """Commit like sqlite3's context manager, then close: Windows cannot unlink an open DB."""
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / "native/handoff-packet"
TRACE = runpy.run_path(str(ROOT / "tests/support/executor_decline_trace.py"))
decline_trace = TRACE["decline_trace"]
trace_details = TRACE["trace_details"]
pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo unavailable")


@pytest.fixture(scope="module")
def binary():
    command = ["cargo", "build", "--release", "--locked", "--bin", "executor-query"]
    if os.environ.get("MIR_HANDOFF_CARGO_OFFLINE") == "1":
        command.append("--offline")
    subprocess.run(command, cwd=CRATE, check=True)
    target = Path(os.environ.get("CARGO_TARGET_DIR", "target"))
    if not target.is_absolute():
        target = CRATE / target
    suffix = ".exe" if os.name == "nt" else ""
    return target / "release" / ("executor-query" + suffix)


def seed(root):
    """Use the production schema and data model, without a local extension."""
    package = root / "tools/mir_executor"
    package.mkdir(parents=True)
    for source in (ROOT / "tools/mir_executor").glob("*.py"):
        if source.name != "local.py":
            shutil.copy2(source, package / source.name)
    registry = JobRegistry(root / "tasks/jobs.db")
    records = [
        JobRecord(
            job_id="complete-\ud55c\U0001f600", change_id="change 'quoted' \\ \ud55c",
            category="unit",
            family="family\nline", repo_root=str(root), codex_args=["task"],
            timeout_seconds=600, status="completed", exit_code=0,
            dispatch_brief_path="brief 'quoted' \\ \ud55c.json", resume_count=2,
            last_resumed_at="2026-10-31T12:00:00Z", allow_harness_self_modify=True,
            stdout=("\ud55c\U0001f600'\"\\\n\t\r\x00\u00a0\u2028"
                    + "\u754c\U0001f600" * 300 + "AFTER_LIMIT"),
            stderr="blocked_reason=stderr_reason trailing", duration_seconds=1.25,
            started_at="2026-11-01T00:00:00Z", completed_at="2026-11-01T00:01:00Z",
        ),
        JobRecord(
            job_id="running", change_id="running-change", category="edge", family=None,
            repo_root=str(root), codex_args=[], timeout_seconds=600, status="running",
            started_at="2026-11-01T02:00:00Z", cancel_requested=True,
        ),
        JobRecord(
            job_id="failed", change_id="failed-change", category="unit", family="",
            repo_root=str(root), codex_args=[], timeout_seconds=600, status="failed",
            exit_code=7, stdout="blocked_reason=stdout_reason\u2003details",
            stderr="blocked_reason=ignored", duration_seconds=0.0,
            started_at="2026-11-01T01:00:00Z",
        ),
        JobRecord(
            job_id="cancelled", change_id="", category="", family=None, repo_root=str(root),
            codex_args=[], timeout_seconds=600, status="cancelled", stdout="", stderr="",
            started_at="2026-10-31T23:00:00Z",
        ),
    ]
    for record in records:
        registry.insert(record)
    registry.close()
    return root


@pytest.fixture
def home(tmp_path):
    return seed(tmp_path / "executor home \ud55c with spaces")


def invoke(binary, home, argv, *, python=False, cwd=None):
    command = ([sys.executable, "-m", "tools.mir_executor"] if python else
               [str(binary), "--home-root", str(home)])
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(home),
                       MIR_EXECUTOR_QUERY_IMPL="python", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(command + argv, cwd=cwd or home, env=environment,
                            capture_output=True, timeout=15, check=False)
    return result.stdout, result.stderr, result.returncode


def install_pin(binary, home):
    destination = home / ".mir/bin" / binary.name
    destination.parent.mkdir(parents=True)
    shutil.copy2(binary, destination)
    destination.chmod(0o755)
    (home / ".mir/bin/executor-query.json").write_text(json.dumps({
        "path": destination.relative_to(home).as_posix(),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }))


def pinned_cli(home, route, argv, *, selectors=None):
    prefix = ["-m", "tools.mir_executor"] if route == "module" else ["-m", "mir.cli", "executor"]
    environment = dict(os.environ, PYTHONUTF8="1",
                       PYTHONPATH=os.pathsep.join((str(home), str(ROOT / "src"))),
                       MIR_EXECUTOR_QUERY_IMPL="native", MIR_NATIVE_HOOKS="1",
                       PYTHONDONTWRITEBYTECODE="1")
    environment.update(selectors or {})
    result = subprocess.run([sys.executable, *prefix, *argv], cwd=home, env=environment,
                            capture_output=True, timeout=15, check=False)
    return result.stdout, result.stderr, result.returncode


QUERY_CASES = [
    [command, "--job-id", job_id]
    for command in ("status", "result")
    for job_id in ("complete-\ud55c\U0001f600", "running", "failed", "cancelled",
                   "missing-'\\\ud55c")
] + [["list-jobs"], ["list-jobs", "--status", "running"],
     ["list-jobs", "--status=failed"], ["list-jobs", "--status", "completed"],
     ["list-jobs", "--status", "cancelled"]]


@pytest.mark.parametrize("argv", QUERY_CASES)
def test_executor_query_bytes(binary, home, argv):
    reference = invoke(binary, home, argv, python=True)
    assert reference[2] == (1 if "missing-'\\\ud55c" in argv else 0), (reference, trace_details())
    before = (home / "tasks/jobs.db").read_bytes()
    assert invoke(binary, home, argv) == reference, trace_details()
    assert (home / "tasks/jobs.db").read_bytes() == before, trace_details()
    if argv == ["list-jobs"]:
        assert [line.split(b" status=")[0] for line in reference[0].splitlines()] == [
            b"[JOB] job_id=running", b"[JOB] job_id=failed",
            "[JOB] job_id=complete-\ud55c\U0001f600".encode(), b"[JOB] job_id=cancelled",
        ], trace_details()
    if argv == ["result", "--job-id", "complete-\ud55c\U0001f600"]:
        assert b"AFTER_LIMIT" not in reference[0], trace_details()


@pytest.mark.parametrize("command", ["status", "result", "list-jobs"])
def test_executor_query_explicit_paths(binary, home, command):
    argv = ["--jobs-db=tasks/jobs.db", command, "--repo-root=" + str(home)]
    if command != "list-jobs":
        argv.append("--job-id=complete-\ud55c\U0001f600")
    assert invoke(binary, home, argv) == invoke(binary, home, argv, python=True), trace_details()


def test_executor_query_empty_database(binary, home):
    with _connect(home / "tasks/jobs.db") as connection:
        connection.execute("DELETE FROM jobs")
    for argv in (["list-jobs"], ["list-jobs", "--status", "running"],
                 ["status", "--job-id", "absent"]):
        assert invoke(binary, home, argv) == invoke(binary, home, argv, python=True), (
            trace_details()
        )


@pytest.mark.parametrize("duration", [0.0000001, 0.00001, 1e16, 1e20, 1e100, -1.25])
def test_executor_query_python_float_format(binary, home, duration):
    with _connect(home / "tasks/jobs.db") as connection:
        connection.execute("UPDATE jobs SET duration_seconds=? WHERE job_id='failed'", (duration,))
    argv = ["result", "--job-id", "failed"]
    assert invoke(binary, home, argv) == invoke(binary, home, argv, python=True), trace_details()


@pytest.mark.parametrize("payload", [
    "single ' quote", 'double " quote', "both '\" quotes",
    "\x01\x07\x08\x0b\x0c\x1f\x7f\x85\xad\u200b\u2028\u2029\ufeff",
    "\u0301\u0378\ue000\U0001f600\U000e0001\U000f0000",
])
def test_executor_query_python_repr(binary, home, payload):
    with _connect(home / "tasks/jobs.db") as connection:
        connection.execute("UPDATE jobs SET change_id=?, stdout=?, stderr=? WHERE job_id='failed'",
                           (payload, payload, payload))
    for command in ("status", "result", "list-jobs"):
        argv = [command] if command == "list-jobs" else [command, "--job-id", "failed"]
        assert invoke(binary, home, argv) == invoke(binary, home, argv, python=True), (
            trace_details()
        )


def test_executor_query_equal_timestamp_order(binary, home):
    with _connect(home / "tasks/jobs.db") as connection:
        connection.execute("UPDATE jobs SET started_at='2026-11-01T00:00:00Z'")
    argv = ["list-jobs"]
    assert invoke(binary, home, argv) == invoke(binary, home, argv, python=True), trace_details()


@pytest.fixture
def local_executor_files(home):
    (home / "tools/mir_executor/local.py").write_text(
        "def register_execute_options(parser):\n"
        "    parser.add_argument('--project-review', action='store_true')\n"
        "\n"
        "def validate_brief(brief, repo_root):\n"
        "    raise AssertionError('query called validate_brief')\n"
        "\n"
        "def pre_execute(args, repo_root):\n"
        "    raise AssertionError('query called pre_execute')\n"
        "\n"
        "def authorize_target(home_root, target_root, args):\n"
        "    raise AssertionError('same-home query called authorize_target')\n"
    )
    (home / "config").mkdir()
    (home / "config/mir-executor.local.json").write_text(json.dumps({
        "timeout_seconds_range": [30, 600], "input_limit_bytes": 4096,
        "require_review": True,
    }))


@pytest.mark.parametrize("route", ["module", "mir-cli"])
@pytest.mark.parametrize("argv", [
    ["status", "--job-id", "failed"], ["result", "--job-id", "complete-\ud55c\U0001f600"],
    ["list-jobs"],
])
@pytest.mark.parametrize("files", ["hook", "config", "both"])
def test_executor_query_local_files_match_python(
    binary, home, local_executor_files, route, argv, files,
):
    if files == "hook":
        (home / "config/mir-executor.local.json").unlink()
    elif files == "config":
        (home / "tools/mir_executor/local.py").unlink()
    reference = invoke(binary, home, argv, python=True)
    assert reference[2] == 0, (reference, trace_details())
    before = (home / "tasks/jobs.db").read_bytes()
    assert invoke(binary, home, argv) == reference, trace_details()
    install_pin(binary, home)
    (home / "tools/mir_executor/cli.py").write_text("raise AssertionError('Python CLI imported')\n")
    assert pinned_cli(home, route, argv) == reference, trace_details()
    assert (home / "tasks/jobs.db").read_bytes() == before, trace_details()


@pytest.mark.parametrize("route", ["module", "mir-cli"])
@pytest.mark.parametrize("argv", [
    ["status", "--job-id", "failed"], ["result", "--job-id", "failed"], ["list-jobs"],
])
def test_executor_query_local_import_failure_accepted_divergence(binary, home, route, argv):
    reference = invoke(binary, home, argv, python=True)
    assert reference[2] == 0, (reference, trace_details())
    (home / "tools/mir_executor/local.py").write_text("raise RuntimeError('local import failed')\n")
    python = invoke(binary, home, argv, python=True)
    assert python[2] != 0, trace_details()
    assert b"local import failed" in python[1], trace_details()
    assert invoke(binary, home, argv) == reference, trace_details()
    install_pin(binary, home)
    assert pinned_cli(home, route, argv) == reference, trace_details()


@pytest.mark.parametrize("route", ["module", "mir-cli"])
@pytest.mark.parametrize("argv", [
    ["status", "--job-id", "failed"], ["result", "--job-id", "complete-\ud55c\U0001f600"],
    ["list-jobs"], ["status", "--job-id", "missing"],
])
def test_executor_query_real_pin_avoids_python_executor_import(binary, home, route, argv):
    reference = invoke(binary, home, argv, python=True)
    install_pin(binary, home)
    (home / "tools/mir_executor/cli.py").write_text("raise AssertionError('Python CLI imported')\n")
    before = (home / "tasks/jobs.db").read_bytes()
    assert pinned_cli(home, route, argv) == reference, trace_details()
    assert (home / "tasks/jobs.db").read_bytes() == before, trace_details()


@pytest.mark.parametrize("route", ["module", "mir-cli"])
def test_executor_query_real_pin_unicode_decline_falls_back(binary, home, route):
    with _connect(home / "tasks/jobs.db") as connection:
        connection.execute("UPDATE jobs SET stdout=? WHERE job_id='failed'", ("\U0001fae9",))
    argv = ["result", "--job-id", "failed"]
    reference = invoke(binary, home, argv, python=True)
    install_pin(binary, home)
    assert invoke(binary, home, argv) == (b"", b"", 64), trace_details()
    assert pinned_cli(home, route, argv) == reference, trace_details()


@pytest.mark.parametrize("suffix", ["-journal", "-shm", "-wal"])
def test_executor_query_declines_database_sidecars(binary, home, suffix):
    database = home / "tasks/jobs.db"
    sidecar = Path(str(database) + suffix)
    sidecar.write_bytes(b"active database sidecar")
    before = database.read_bytes()
    assert invoke(binary, home, ["list-jobs"]) == (b"", b"", 64), trace_details()
    assert database.read_bytes() == before, trace_details()
    assert sidecar.read_bytes() == b"active database sidecar", trace_details()


def test_executor_query_declines_non_utf8_streams(binary, home, monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "ascii")
    assert invoke(binary, home, ["list-jobs"]) == (b"", b"", 64), trace_details()


def test_executor_query_declines_parent_database_components(binary, home):
    assert invoke(binary, home, ["--jobs-db", "tasks/../tasks/jobs.db", "list-jobs"]) == (
        b"", b"", 64,
    ), trace_details()


def test_executor_query_declines_absent_database_through_dangling_parent(binary, home):
    database = home / "tasks/jobs.db"
    database.unlink()
    database.parent.rmdir()
    try:
        database.parent.symlink_to(home / "absent", target_is_directory=True)
    except OSError:
        pytest.skip("symlink unavailable")
    assert invoke(binary, home, ["list-jobs"]) == (b"", b"", 64), trace_details()
    assert not (home / "absent").exists(), trace_details()


@pytest.mark.parametrize("case", ["cross-target",
                                      "symlink", "malformed-json", "invalid-type",
                                      "unicode-version"])
def test_executor_query_declines_unsupported_storage(binary, home, tmp_path, case):
    database = home / "tasks/jobs.db"
    argv = ["list-jobs"]
    if case == "legacy":
        with _connect(database) as connection:
            connection.execute("ALTER TABLE jobs DROP COLUMN ai_run_metadata")
    elif case == "cross-target":
        other = tmp_path / "other"
        other.mkdir()
        argv.extend(["--repo-root", str(other)])
    elif case == "symlink":
        saved = database.with_suffix(".saved")
        database.rename(saved)
        try:
            database.symlink_to(saved)
        except OSError:
            pytest.skip("symlink unavailable")
    elif case == "malformed-json":
        with _connect(database) as connection:
            connection.execute("UPDATE jobs SET codex_args = 'not-json' WHERE job_id='running'")
    elif case == "invalid-type":
        with _connect(database) as connection:
            connection.execute("UPDATE jobs SET resume_count='invalid' WHERE job_id='running'")
    elif case == "unicode-version":
        with _connect(database) as connection:
            connection.execute("UPDATE jobs SET stdout=? WHERE job_id='running'", ("\U0001fae9",))
    before = database.read_bytes() if database.exists() else None
    assert invoke(binary, home, argv) == (b"", b"", 64), trace_details()
    assert (database.read_bytes() if database.exists() else None) == before, trace_details()


@pytest.mark.parametrize("argv", [["list-jobs"], ["list-jobs", "--status", "running"],
                                     ["status", "--job-id", "absent"],
                                     ["result", "--job-id", "absent"]])
def test_executor_query_absent_database_matches_with_creation(binary, home, argv):
    database = home / "tasks/jobs.db"
    database.unlink()
    native = invoke(binary, home, argv)
    assert database.exists(), trace_details()
    assert native == invoke(binary, home, argv, python=True), trace_details()


@pytest.mark.parametrize("argv", [
    [], ["--help"], ["status", "--help"], ["result", "--help"], ["list-jobs", "--help"],
    ["unknown"], ["resume"], ["sweep", "--unknown"],
    ["status"], ["result"], ["list-jobs", "--unknown"],
    ["status", "--job-id", "running", "--job-id", "failed"],
    ["list-jobs", "--status", "not-a-status"],
    ["status", "--job", "running"],
    ["list-jobs", "--jobs-db", "tasks/jobs.db"],
])
def test_executor_query_declines_arguments(binary, home, argv):
    before = (home / "tasks/jobs.db").read_bytes()
    assert invoke(binary, home, argv) == (b"", b"", 64), trace_details()
    assert (home / "tasks/jobs.db").read_bytes() == before, trace_details()


@pytest.mark.parametrize("field", ["codex_args", "ai_run_metadata"])
@pytest.mark.parametrize("escape", [
    r"\ud800", r"\udce2", r"\udce2\ud800", r"\ud800\udce2",
    r"\\udce2", r"\\u12",
])
@pytest.mark.parametrize("command", ["status", "result", "list-jobs"])
def test_executor_query_surrogate_escapes(binary, home, field, escape, command):
    payload = ('["' + escape + '"]' if field == "codex_args" else
               '{"' + escape + '": ["' + escape + '"]}')
    json.loads(payload)  # The unchanged Python decoder is the acceptance oracle.
    with _connect(home / "tasks/jobs.db") as connection:
        connection.execute(f"UPDATE jobs SET {field}=? WHERE job_id='failed'", (payload,))
    argv = [command] if command == "list-jobs" else [command, "--job-id", "failed"]
    reference = invoke(binary, home, argv, python=True)
    assert reference[2] == 0, (reference, trace_details())
    before = (home / "tasks/jobs.db").read_bytes()
    assert invoke(binary, home, argv) == reference, trace_details()
    install_pin(binary, home)
    (home / "tools/mir_executor/cli.py").write_text("raise AssertionError('Python fallback')\n")
    for route in ("module", "mir-cli"):
        assert pinned_cli(home, route, argv) == reference, trace_details()
    assert (home / "tasks/jobs.db").read_bytes() == before, trace_details()


@pytest.mark.parametrize("field", ["codex_args", "ai_run_metadata"])
@pytest.mark.parametrize("payload", [r'["\u12"]', r'["\ud800\u12"]', r'["\ud80z"]'])
@pytest.mark.parametrize("command", ["status", "result", "list-jobs"])
def test_executor_query_invalid_unicode_escape_declines(binary, home, field, payload, command):
    with pytest.raises(json.JSONDecodeError):
        json.loads(payload)
    with _connect(home / "tasks/jobs.db") as connection:
        connection.execute(f"UPDATE jobs SET {field}=? WHERE job_id='failed'", (payload,))
    argv = [command] if command == "list-jobs" else [command, "--job-id", "failed"]
    assert invoke(binary, home, argv) == (b"", b"", 64), trace_details()


@pytest.mark.parametrize("payload", [r'"\udce2"', r'["\udce2", 1]', r'{"x":"\udce2"}'])
def test_executor_query_surrogate_args_shape_still_declines(binary, home, payload):
    with _connect(home / "tasks/jobs.db") as connection:
        connection.execute("UPDATE jobs SET codex_args=? WHERE job_id='failed'", (payload,))
    assert invoke(binary, home, ["list-jobs"]) == (b"", b"", 64), trace_details()


@pytest.mark.parametrize("job", ["running", "failed", "cancelled", "complete-\ud55c\U0001f600",
                                  "absent-'\ud55c"])
def test_native_cancel_matches_python(binary, home, job):
    database = home / "tasks/jobs.db"
    saved = database.read_bytes()
    argv = ["cancel", "--job-id", job]
    native = invoke(binary, home, argv)
    with _connect(database) as connection:
        actual = connection.execute("SELECT * FROM jobs ORDER BY job_id").fetchall()
    database.write_bytes(saved)
    reference = invoke(binary, home, argv, python=True)
    with _connect(database) as connection:
        expected = connection.execute("SELECT * FROM jobs ORDER BY job_id").fetchall()
    assert native == reference, trace_details()
    assert actual == expected, trace_details()


@pytest.mark.parametrize("removed", ["ai_run_metadata", "resume_count", "dispatch_brief_path",
                                      "allow_harness_self_modify", "last_resumed_at"])
@pytest.mark.parametrize("command", ["list-jobs", "cancel"])
def test_native_migrates_legacy_registry(binary, home, removed, command):
    database = home / "tasks/jobs.db"
    with _connect(database) as connection:
        connection.execute(f"ALTER TABLE jobs DROP COLUMN {removed}")
    saved = database.read_bytes()
    argv = [command] + (["--job-id", "running"] if command == "cancel" else [])
    native = invoke(binary, home, argv)
    with _connect(database) as connection:
        actual = connection.execute("SELECT * FROM jobs ORDER BY job_id").fetchall()
        columns = connection.execute("PRAGMA table_info(jobs)").fetchall()
    database.write_bytes(saved)
    reference = invoke(binary, home, argv, python=True)
    with _connect(database) as connection:
        assert actual == connection.execute("SELECT * FROM jobs ORDER BY job_id").fetchall(), (
            trace_details()
        )
        assert columns == connection.execute("PRAGMA table_info(jobs)").fetchall(), trace_details()
    assert native == reference, trace_details()


def test_native_cancel_declines_local_hook(binary, home):
    (home / "tools/mir_executor/local.py").write_text("raise RuntimeError('local hook')\n")
    database = home / "tasks/jobs.db"
    saved = database.read_bytes()
    assert invoke(binary, home, ["cancel", "--job-id", "running"]) == (b"", b"", 64), (
        trace_details()
    )
    assert database.read_bytes() == saved, trace_details()


def test_native_cancel_golden_output(binary, home):
    fixture = json.loads((CRATE / "tests/fixtures/executor_registry.json").read_text())
    registry = JobRegistry(home / "tasks/jobs.db")
    registry.insert(JobRecord(job_id="job", change_id="c", category="unit", family=None,
                              repo_root=str(home), codex_args=[], timeout_seconds=60,
                              status="running"))
    registry.close()
    for case in fixture["cancel"]:
        expected = (case["stdout"].replace("\n", os.linesep).encode(),
                    case["stderr"].replace("\n", os.linesep).encode(), case["code"])
        argv = ["cancel", "--job-id", case["job_id"]]
        assert invoke(binary, home, argv) == expected, trace_details()
        assert invoke(binary, home, argv, python=True) == expected, trace_details()


def test_native_cancel_absent_registry(binary, home):
    database = home / "tasks/jobs.db"
    database.unlink()
    argv = ["cancel", "--job-id", "absent"]
    native = invoke(binary, home, argv)
    assert database.exists(), trace_details()
    with _connect(database) as connection:
        columns = connection.execute("PRAGMA table_info(jobs)").fetchall()
    database.unlink()
    assert native == invoke(binary, home, argv, python=True), trace_details()
    with _connect(database) as connection:
        assert columns == connection.execute("PRAGMA table_info(jobs)").fetchall(), trace_details()


def test_registry_fixture_matches_python():
    import runpy

    generator = CRATE / "tests/fixtures/generate_executor_registry.py"
    expected = json.loads(generator.with_name("executor_registry.json").read_text())
    assert runpy.run_path(str(generator))["generate"]() == expected, trace_details()


@pytest.mark.parametrize('job', ['running', 'failed', 'missing'])
def test_pinned_cancel_matches_python(binary, home, job):
    install_pin(binary, home)
    reference = invoke(binary, home, ['cancel', '--job-id', job], python=True)
    with _connect(home / 'tasks/jobs.db') as connection:
        connection.execute('UPDATE jobs SET cancel_requested=0 WHERE job_id=?', (job,))
    assert pinned_cli(home, 'module', ['cancel', '--job-id', job]) == reference, trace_details()
    with _connect(home / 'tasks/jobs.db') as connection:
        row = connection.execute('SELECT cancel_requested FROM jobs WHERE job_id=?',
                                 (job,)).fetchone()
    assert row is None if job == 'missing' else row == (1,), trace_details()


@pytest.mark.parametrize('command,selector', [
    ('cancel', None), ('cancel', 'MIR_EXECUTOR_IMPL'),
    ('cancel', 'MIR_EXECUTOR_CANCEL_IMPL'), ('cancel', 'MIR_NATIVE_HOOKS'),
    ('list-jobs', 'MIR_EXECUTOR_IMPL'),
])
def test_pinned_cancel_and_query_selectors(binary, home, command, selector):
    install_pin(binary, home)
    (home / 'tools/mir_executor/cli.py').write_text(
        "raise RuntimeError('python selected')\n", encoding='utf-8')
    selectors = {selector: '0' if selector == 'MIR_NATIVE_HOOKS' else 'python'} if selector else {}
    arguments = [command] + (['--job-id', 'running'] if command == 'cancel' else [])
    result = pinned_cli(home, 'module', arguments, selectors=selectors)
    assert result[2] == (1 if selector else 0), (result, trace_details())
    assert (b'python selected' in result[1]) == bool(selector), trace_details()


def test_pinned_cancel_declines_hook_to_python(binary, home):
    install_pin(binary, home)
    (home / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        "(Path(__file__).resolve().parents[2] / 'python-import').touch()\n",
        encoding='utf-8')
    result = pinned_cli(home, 'module', ['cancel', '--job-id', 'running'])
    assert result[2] == 0, (result, trace_details())
    assert (home / 'python-import').exists(), trace_details()


@pytest.mark.parametrize('apply', [False, True])
@pytest.mark.parametrize('selector', [None, 'MIR_EXECUTOR_IMPL', 'MIR_EXECUTOR_SWEEP_IMPL'])
def test_pinned_sweep_matches_python_state(binary, tmp_path, apply, selector):
    support = runpy.run_path(str(ROOT / 'tests/fixtures/executor_execute_support.py'))
    dispatch = runpy.run_path(str(ROOT / 'tests/fixtures/executor_dispatch_cli_support.py'))
    snapshots = []
    for implementation in ('python', 'native'):
        root = tmp_path / implementation
        dispatch['seed'](root, 'success', support)
        (root / 'tools/mir_executor/local.py').unlink()
        install_pin(binary, root)
        registry = JobRegistry(root / 'tasks/jobs.db')
        registry.insert(JobRecord(
            job_id='stale', change_id='fixture', category='unit', family=None,
            repo_root=str(root), codex_args=[], timeout_seconds=1, status='running',
            started_at='2000-01-01T00:00:00+00:00',
        ))
        registry.close()
        orphan = root / 'orphan-worktree'
        dispatch['git'](root, 'worktree', 'add', '-b', 'mir-dispatch/orphan',
                        str(orphan), 'HEAD')
        arguments = ['sweep', '--repo-root', str(root)] + (['--apply'] if apply else [])
        database_before = (root / 'tasks/jobs.db').read_bytes()
        selectors = {'MIR_EXECUTOR_IMPL': 'python'} if implementation == 'python' else {}
        if implementation == 'native' and selector:
            selectors[selector] = 'python'
        if implementation == 'native' and selector is None:
            (root / 'tools/mir_executor/cli.py').write_text(
                "raise RuntimeError('unexpected Python sweep fallback')\n", encoding='utf-8')
        result = pinned_cli(root, 'module', arguments, selectors=selectors)
        assert result[2] == 0, (result, trace_details())
        payload = json.loads(result[0])
        assert payload['stale_jobs'] == ['stale'], trace_details()
        assert payload['orphan_worktrees'] == [str(orphan)], trace_details()
        assert orphan.exists() == (not apply), trace_details()
        if not apply:
            assert (root / 'tasks/jobs.db').read_bytes() == database_before, trace_details()
        completed = subprocess.CompletedProcess(arguments, result[2], result[0], result[1])
        snapshots.append(dispatch['snapshot'](root, completed))
    assert snapshots[0] == snapshots[1], trace_details()


def test_executor_decline_trace_is_append_only_and_optional(binary, home, monkeypatch):
    trace = Path(os.environ["MIR_EXECUTOR_DECLINE_TRACE"])
    argv = ["resume", "--unknown"]
    assert not trace.exists(), trace_details()
    for count in (1, 2):
        assert invoke(binary, home, argv) == (b"", b"", 64), trace_details()
        assert trace.is_file(), trace_details()
        lines = trace.read_text(encoding="utf-8").splitlines()
        assert len(lines) == count, trace_details()
        assert all(": " in line and line.endswith(lines[0].split(": ", 1)[1])
                   for line in lines), trace_details()
    before = trace.read_bytes()
    monkeypatch.delenv("MIR_EXECUTOR_DECLINE_TRACE")
    assert invoke(binary, home, argv) == (b"", b"", 64), trace_details()
    assert trace.read_bytes() == before, trace_details()
    for invalid in (home, home / "missing-parent" / "trace.log"):
        monkeypatch.setenv("MIR_EXECUTOR_DECLINE_TRACE", str(invalid))
        assert invoke(binary, home, argv) == (b"", b"", 64), trace_details()
    assert not (home / "missing-parent").exists(), trace_details()
