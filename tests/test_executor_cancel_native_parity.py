"""Pinned cancel bytes and registry effects through binary and public facade."""
import json
import os
import runpy
import sys
from pathlib import Path

import pytest
from test_executor_status_native_parity import (  # noqa: F401
    binary,
    database,
    filesystem_reference,
    install_package,
    readable,
)

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = runpy.run_path(str(ROOT / "tests/fixtures/generate_executor_cancel.py"))
GOLDEN = json.loads((ROOT / "tests/fixtures/executor_cancel.json").read_text(encoding="ascii"))


def test_cancel_reference_provenance():
    assert GOLDEN["reference"] == SUPPORT["PIN"]
    assert GOLDEN["archive_sha256"] == (
        "5e00605c90af512ab59ec21df13600f362ff2711d39501d72396647c4aa48570")
    assert [case["name"] for case in GOLDEN["cases"]] == [
        case["name"] for case in SUPPORT["CASES"]]


@pytest.mark.parametrize("route", ["binary", "module"])
@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["name"])
def test_cancel_frozen_parity(binary, database, tmp_path, route, case):  # noqa: F811
    if case.get("platform", sys.platform) != sys.platform:
        pytest.skip("platform-specific record")
    if os.name == "nt" and "nonutf8" in case["name"]:
        pytest.skip("POSIX argv")
    compatibility = bool(case.get("compatibility") or case.get("legacy_hook"))
    if route == "binary" and compatibility:
        pytest.skip("facade compatibility route")
    home = (tmp_path / "synthetic home").resolve()
    SUPPORT["seed"](home, case, database)
    if route == "module" or case.get("legacy_hook"):
        install_package(home, binary, compatibility=compatibility)
        SUPPORT["install_local_hook"](home, case)
    command = ([sys.executable, "-m", "tools.mir_executor"] if route == "module"
               else [str(binary), "--home-root", str(home)])
    actual = SUPPORT["capture"](home, case, command)
    expected = case.get("expected_by_route", {}).get(route, case["expected"])
    if case["name"] == "nonutf8-db-path":
        expected = filesystem_reference(tmp_path, case, database, SUPPORT, GOLDEN)
    assert actual == expected, {"actual": readable(actual), "expected": readable(expected)}


def test_cancel_launcher_owns_native_family_without_selector_fallback():
    import ast

    tree = ast.parse((ROOT / "tools/mir_executor/entrypoint.py").read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    branch = functions["main"].body[1]
    assert isinstance(branch, ast.If)
    assert 'cancel' in ast.unparse(branch.test)
    assert ast.unparse(branch.body[-1]) == "return _native_status(argv)"
    compatibility = next(node for node in branch.body if isinstance(node, ast.If))
    predicate = ast.unparse(compatibility.test)
    assert "_status_codec_decline()" in predicate
    assert "local.py" in predicate and "not disabled" in predicate
    assert "MIR_EXECUTOR_IMPL" not in ast.unparse(branch)
    native = ast.unparse(functions["_native_status"])
    assert "return None" not in native
    assert "Python {command} is retired" in native


@pytest.mark.parametrize("route", ["binary", "module"])
@pytest.mark.parametrize("spelling", ["physical", "linked"])
@pytest.mark.parametrize("name", ["abbreviation", "nested-db", "receipt-absent"])
def test_cancel_tmpdir_spellings(binary, database, tmp_path, route, spelling, name):  # noqa: F811
    physical = tmp_path / "physical"
    physical.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(physical, target_is_directory=True)
    original = next(case for case in GOLDEN["cases"] if case["name"] == name)
    case = {**original, "env": {**original.get("env", {}),
                               "TMPDIR": str(physical if spelling == "physical" else linked)}}
    home = (tmp_path / "synthetic home").resolve()
    SUPPORT["seed"](home, case, database)
    if route == "module":
        install_package(home, binary)
    command = ([sys.executable, "-m", "tools.mir_executor"] if route == "module"
               else [str(binary), "--home-root", str(home)])
    actual = SUPPORT["capture"](home, case, command)
    assert actual == original["expected"], readable(actual)
