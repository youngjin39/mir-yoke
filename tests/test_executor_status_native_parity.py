"""Frozen status parity through the fresh binary and the pinned module facade."""
from __future__ import annotations

import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / "native/handoff-packet"
SUPPORT = runpy.run_path(str(ROOT / "tests/fixtures/generate_executor_status.py"))
GOLDEN = json.loads((ROOT / "tests/fixtures/executor_status.json").read_text(encoding="ascii"))


@pytest.fixture(scope="module")
def binary():
    if shutil.which("cargo") is None:
        pytest.skip("cargo unavailable")
    environment = dict(os.environ, CARGO_BUILD_JOBS="4", CARGO_TARGET_DIR=str(CRATE / "target"))
    command = ["cargo", "build", "--release", "--offline", "--locked", "--bin", "executor-query"]
    subprocess.run(command, cwd=CRATE, env=environment, check=True)
    target = Path(environment.get("CARGO_TARGET_DIR", "target"))
    if not target.is_absolute():
        target = CRATE / target
    return target / "release" / ("executor-query.exe" if os.name == "nt" else "executor-query")


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    # Fixture setup uses the frozen schema/rows, never today's Python handler.
    import sqlite3

    root = tmp_path_factory.mktemp("status-template").resolve()
    path = root / "template.db"
    ordinary = next(case for case in GOLDEN["cases"] if case["name"] == "ordinary")
    tables = ordinary["expected"]["storage"]["tasks/jobs.db"]["tables"]
    with sqlite3.connect(path) as connection:
        for name, table in tables.items():
            columns = []
            for _, column, kind, required, default, primary in table["columns"]:
                ddl = f'"{column}" {kind}'
                if primary:
                    ddl += " PRIMARY KEY"
                if required:
                    ddl += " NOT NULL"
                if default is not None:
                    ddl += " DEFAULT " + default
                columns.append(ddl)
            connection.execute(f'CREATE TABLE "{name}" (' + ", ".join(columns) + ")")
            for row in table["rows"]:
                values = [bytes.fromhex(item["bytes"]) if isinstance(item, dict) else item
                          for item in row]
                connection.execute(f'INSERT INTO "{name}" VALUES (' +
                                   ",".join("?" for _ in values) + ")", values)
        connection.execute("CREATE INDEX idx_jobs_status ON jobs(status)")
    return path


def install_package(home, executable, *, compatibility=False):
    package = home / "tools/mir_executor"
    shutil.copytree(ROOT / "tools/mir_executor", package,
                    ignore=shutil.ignore_patterns("__pycache__", "local.py"), dirs_exist_ok=True)
    # A successful former-decline test must never import the retired handler.
    if not compatibility:
        (package / "cli.py").write_text('raise AssertionError("PYTHON_STATUS_FALLBACK")\n',
                                       encoding="ascii")
    destination = home / ".mir/bin" / executable.name
    destination.parent.mkdir(parents=True)
    shutil.copy2(executable, destination)
    destination.chmod(0o755)
    (destination.parent / "executor-query.json").write_text(json.dumps({
        "path": destination.relative_to(home).as_posix(),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }), encoding="ascii")


def readable(result):
    return {key: bytes.fromhex(value).decode("utf-8", "backslashreplace")
            if key.endswith("_hex") else value for key, value in result.items()}


def test_status_reference_provenance():
    assert GOLDEN["reference"] == SUPPORT["PIN"]
    assert GOLDEN["entrypoint"] == "tools.mir_executor.cli.main (direct console call)"
    assert GOLDEN["archive_sha256"] == (
        "21cdfe9b8d08e2671b9b4311713bc834dd837bb06d26768953a7d516d29b68ca")
    assert [case["name"] for case in GOLDEN["cases"]] == [
        case["name"] for case in SUPPORT["CASES"]]


@pytest.mark.parametrize("route", ["binary", "module"])
@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["name"])
def test_status_frozen_parity(binary, database, tmp_path, route, case):
    if case.get("platform", sys.platform) != sys.platform:
        pytest.skip("frozen platform-specific filesystem refusal")
    if os.name == "nt" and "nonutf8" in case["name"]:
        pytest.skip("POSIX surrogateescape argv")
    compatibility = bool(case.get("compatibility") or case.get("legacy_hook"))
    if route == "binary" and compatibility:
        pytest.skip("compatibility decline is implemented by the Python facade")
    home = (tmp_path / "synthetic home").resolve()
    SUPPORT["seed"](home, case, database)
    if route == "module" or case.get("legacy_hook"):
        install_package(home, binary, compatibility=compatibility)
        SUPPORT["install_local_hook"](home, case)
    if route == "module":
        command = [sys.executable, "-m", "tools.mir_executor"]
    else:
        command = [str(binary), "--home-root", str(home)]
    actual = SUPPORT["capture"](home, case, command)
    expected = case.get("expected_by_route", {}).get(route, case["expected"])
    assert actual == expected, {
        "case": case["name"], "route": route,
        "actual": readable(actual), "expected": readable(expected),
    }
