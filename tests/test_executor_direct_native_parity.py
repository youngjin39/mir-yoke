"""Pinned direct execute bytes and effects through binary and public facade."""

from __future__ import annotations

import ast
import copy
import json
import os
import re
import runpy
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_executor_status_native_parity import (  # noqa: F401
    binary,
    install_package,
    readable,
)

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = runpy.run_path(str(ROOT / "tests/fixtures/generate_executor_direct.py"))
FIXTURE = ROOT / "tests/fixtures/executor_direct.json"
GOLDEN = json.loads(FIXTURE.read_text(encoding="ascii"))


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    path = tmp_path_factory.mktemp("direct-database") / "template.db"
    path.write_bytes(bytes.fromhex(GOLDEN["template_hex"]))
    return path


def test_direct_reference_provenance():
    assert GOLDEN["reference"] == SUPPORT["PIN"]
    assert GOLDEN["archive_sha256"] == (
        "27012f6cebe264d93d2b461c72083b85e6c86341d009a1dca66112bd81e481b2"
    )
    assert [case["name"] for case in GOLDEN["cases"]] == [case["name"] for case in SUPPORT["CASES"]]
    assert GOLDEN["exception_protocol"] == (
        "exit 1; preserve raw stdout; traceback final stderr line"
    )


def expected_for_home(case, home, launcher, route):
    expected = case.get("expected_by_route", {}).get(route, case["expected"])
    if "encoding_error_path" not in case:
        return expected
    expected = copy.deepcopy(expected)
    coordinate = case["encoding_error_path"]
    prefix = str(launcher if coordinate["kind"] == "codex" else home)
    delta = len(json.dumps(prefix, ensure_ascii=False)[1:-1]) - coordinate["width"]
    error = bytes.fromhex(expected["stderr_hex"]).decode("utf-8")
    assert "UnicodeEncodeError:" in error
    error, count = re.subn(
        r"(?<= in position )\d+", lambda match: str(int(match[0]) + delta), error
    )
    assert count == 1
    expected["stderr_hex"] = error.encode("utf-8").hex()
    return expected


@pytest.mark.parametrize("route", ["binary", "module"])
@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["name"])
def test_direct_frozen_parity(binary, database, tmp_path, route, case):  # noqa: F811
    if case.get("platform") == "posix" and os.name != "posix":
        pytest.skip("POSIX process fixture")
    if os.name == "nt" and "nonutf8" in case["name"]:
        pytest.skip("POSIX surrogateescape argv")
    home = (tmp_path / "synthetic home").resolve()
    launcher = SUPPORT["seed"](home, case, database=database)
    if route == "module":
        install_package(home, binary, compatibility=case.get("compatibility", False))
    command = (
        [sys.executable, "-m", "tools.mir_executor"]
        if route == "module"
        else [str(binary), "--home-root", str(home)]
    )
    if route == "binary" and case.get("compatibility") and case["name"].startswith("codec-"):
        before = SUPPORT["snapshot"](home, launcher)
        completed = subprocess.run(
            [*command, *SUPPORT["arguments"](home, case)],
            cwd=home,
            env=SUPPORT["environment"](home, case, launcher),
            capture_output=True,
            timeout=45,
        )
        assert (completed.returncode, completed.stdout, completed.stderr) == (64, b"", b"")
        assert SUPPORT["snapshot"](home, launcher) == before
        return
    actual = SUPPORT["capture"](home, case, launcher, command)
    expected = expected_for_home(case, home, launcher, route)
    assert actual == expected, {
        "case": case["name"],
        "route": route,
        "actual": readable(actual),
        "expected": readable(expected),
    }


@pytest.mark.parametrize("route", ["binary", "module"])
@pytest.mark.parametrize("spelling", ["physical", "linked"])
@pytest.mark.parametrize("name", ["success", "unknown", "ledger-malformed", "db-insert-abort"])
def test_direct_tmpdir_spellings(binary, database, tmp_path, route, spelling, name):  # noqa: F811
    physical = tmp_path / "physical"
    physical.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(physical, target_is_directory=True)
    original = next(case for case in GOLDEN["cases"] if case["name"] == name)
    case = {
        **original,
        "env": {
            **original.get("env", {}),
            "TMPDIR": str(physical if spelling == "physical" else linked),
        },
    }
    home = (tmp_path / "synthetic home").resolve()
    launcher = SUPPORT["seed"](home, case, database=database)
    if route == "module":
        install_package(home, binary)
    command = (
        [sys.executable, "-m", "tools.mir_executor"]
        if route == "module"
        else [str(binary), "--home-root", str(home)]
    )
    actual = SUPPORT["capture"](home, case, launcher, command)
    expected = expected_for_home(original, home, launcher, route)
    assert actual == expected, readable(actual)


@pytest.mark.parametrize(
    "fault", ["missing", "malformed", "shape", "digest", "path", "symlink", "not-executable"]
)
def test_direct_invalid_pin_refuses_before_effects(binary, tmp_path, fault):  # noqa: F811
    home = (tmp_path / "synthetic home").resolve()
    case = {"name": "success"}
    launcher = SUPPORT["seed"](home, case)
    install_package(home, binary)
    pin = home / ".mir/bin/executor-query.json"
    executable = home / ".mir/bin" / binary.name
    if fault == "missing":
        pin.unlink()
    elif fault == "malformed":
        pin.write_bytes(b"{broken")
    elif fault == "shape":
        pin.write_text("[]", encoding="ascii")
    elif fault in {"digest", "path"}:
        value = json.loads(pin.read_text())
        value["sha256" if fault == "digest" else "path"] = (
            "0" * 64 if fault == "digest" else "../executor-query"
        )
        pin.write_text(json.dumps(value), encoding="ascii")
    elif fault == "symlink":
        target = home / "linked-executor"
        executable.rename(target)
        executable.symlink_to(target)
    else:
        if os.name == "nt":
            pytest.skip("POSIX executable permission")
        executable.chmod(0o600)
    before = (home / "tasks/tdd.json").read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "tools.mir_executor", *SUPPORT["BASE"]],
        cwd=home,
        env=SUPPORT["environment"](home, case, launcher),
        capture_output=True,
        timeout=45,
    )
    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        b"",
        b"[mir_executor] pinned native execute unavailable or incompatible; "
        b"Python execute is retired\n",
    )
    assert (home / "tasks/tdd.json").read_bytes() == before
    assert not (home / "tasks/jobs.db").exists()
    assert not (home / "provider-started").exists()


@pytest.mark.parametrize("route", ["reference", "binary", "module"])
@pytest.mark.parametrize("action", ["fail", "abort", "rollback", "ignore"])
def test_direct_late_sql_keeps_raw_background_id_live(
    binary, database, tmp_path, route, action  # noqa: F811
):
    case = next(case for case in GOLDEN["cases"] if case["name"] == "db-update-" + action)
    reference = None
    if route == "reference":
        reference = tmp_path / "reference"
        assert SUPPORT["STATUS"].archive_reference(reference) == GOLDEN["archive_sha256"]
    home = (tmp_path / "home").resolve()
    launcher = SUPPORT["seed"](home, case, reference=reference, database=database)
    if route == "module":
        install_package(home, binary)
    command = {
        "reference": [sys.executable, "-c", "from tools.mir_executor.cli import main; main()"],
        "binary": [str(binary), "--home-root", str(home)],
        "module": [sys.executable, "-m", "tools.mir_executor"],
    }[route]
    environment = SUPPORT["environment"](home, case, launcher)
    environment["EXECUTE_FIXTURE_GATE"] = "1"
    output, errors = home / "raw-output", home / "raw-errors"
    with output.open("wb") as stdout, errors.open("wb") as stderr:
        child = subprocess.Popen(
            [*command, *SUPPORT["arguments"](home, case)], cwd=home, env=environment,
            stdout=stdout, stderr=stderr,
        )
        try:
            deadline = time.monotonic() + 5
            while not (home / "provider-started").exists():
                assert child.poll() is None, errors.read_bytes()
                assert time.monotonic() < deadline, "fake provider did not reach its gate"
                time.sleep(0.01)
            with sqlite3.connect(home / "tasks/jobs.db") as connection:
                job_id, = connection.execute("SELECT job_id FROM jobs").fetchone()
            expected = f"[BACKGROUND] job_id={job_id}\n".encode("ascii")
            assert output.read_bytes() == expected
            assert errors.read_bytes() == b""
            (home / "provider-release").touch()
            assert child.wait(timeout=10) == 1
            assert output.read_bytes() == expected
            error = errors.read_bytes()
            if route == "reference" and error:
                assert error.startswith(b"Traceback (most recent call last):")
                error = error.splitlines()[-1] + b"\n"
            assert error == (
                b"" if action == "ignore" else
                b"sqlite3.IntegrityError: direct late status fault\n"
            )
        finally:
            (home / "provider-release").touch()
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)


def test_direct_facade_has_only_named_compatibility_declines():
    tree = ast.parse((ROOT / "tools/mir_executor/entrypoint.py").read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    branch = next(
        node
        for node in functions["main"].body
        if isinstance(node, ast.If) and "execute" in ast.unparse(node.test)
    )
    text = ast.unparse(branch)
    compatibility = next(
        node
        for node in branch.body
        if isinstance(node, ast.If) and "_status_codec_decline" in ast.unparse(node.test)
    )
    predicate = ast.parse(
        "_status_codec_decline() or "
        "((_HOME_ROOT / 'tools/mir_executor/local.py').exists() and not disabled)",
        mode="eval",
    ).body
    assert ast.dump(compatibility.test) == ast.dump(predicate)
    imports = [
        node
        for node in ast.walk(branch)
        if isinstance(node, ast.ImportFrom) and node.module == "tools.mir_executor.cli"
    ]
    calls = [
        node
        for node in ast.walk(branch)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "python_main"
    ]
    assert len(imports) == len(calls) == 1
    assert compatibility.body == [imports[0], compatibility.body[-1]]
    assert ast.unparse(compatibility.body[-1]) == "return python_main(argv)"
    assert calls[0] is compatibility.body[-1].value
    assert "required=True" in text
    for selector in SUPPORT["SELECTORS"]:
        assert selector not in text
    assert "Python execute is retired" in text
    native = ast.unparse(functions["_native_command"])
    assert "if not required" in native


def test_direct_native_declines_are_named_or_dispatch_guarded():
    source = (ROOT / "native/handoff-packet/src/executor_execute.rs").read_text(encoding="utf-8")
    # Preserve offsets while removing literals and comments for brace matching.
    cleaned = re.sub(
        r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/',
        lambda match: " " * len(match[0]),
        source,
        flags=re.DOTALL,
    )

    def block_end(start):
        depth = 0
        for position in range(start, len(cleaned)):
            depth += (cleaned[position] == "{") - (cleaned[position] == "}")
            if depth == 0:
                return position
        raise AssertionError("unclosed Rust block")

    run_start = source.index("pub fn run(")
    run_open = cleaned.index("{", run_start)
    run_end = block_end(run_open)
    direct_start = cleaned.index("{", cleaned.index("if direct", run_open, run_end))
    direct_end = block_end(direct_start)
    dispatch_start = cleaned.index("{", direct_end + 1, run_end)
    assert cleaned[direct_end + 1 : dispatch_start].strip() == "else"
    dispatch_end = block_end(dispatch_start)
    direct_declines = []
    common_declines = []
    for match in re.finditer(r"executor_protocol::decline\(([^)]+)\)", source):
        if not run_open < match.start() < run_end:
            continue
        argument = match[1].strip().rstrip(",").strip()
        if direct_start < match.start() < direct_end:
            direct_declines.append(argument)
        elif not dispatch_start < match.start() < dispatch_end:
            common_declines.append(argument)
    assert set(direct_declines) == {
        '"execute stream codec or error handler"',
        '"execute invoking-home local parser extension"',
    }
    assert len(direct_declines) == 2
    assert common_declines == ["reason"]
    common = source[dispatch_end:run_end]
    assert re.search(
        r"Admission::Decline\s*\{\s*reason,\s*\.\.\s*\}\)\s+"
        r"if\s+!direct\s*=>\s*(?:\{\s*)?return\s+"
        r"crate::executor_protocol::decline\(reason\)",
        common,
    )
