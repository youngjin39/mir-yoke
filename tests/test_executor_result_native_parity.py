"""Pinned result bytes and registry effects through binary and public facade."""
import json
import os
import runpy
import sys
from pathlib import Path

import pytest
from test_executor_status_native_parity import (  # noqa: F401
    binary,
    database,
    install_package,
    readable,
)

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = runpy.run_path(str(ROOT / "tests/fixtures/generate_executor_result.py"))
GOLDEN = json.loads((ROOT / "tests/fixtures/executor_result.json").read_text(encoding="ascii"))


def test_result_reference_provenance():
    assert GOLDEN["reference"] == SUPPORT["PIN"]
    assert [case["name"] for case in GOLDEN["cases"]] == [
        case["name"] for case in SUPPORT["CASES"]]


@pytest.mark.parametrize("route", ["binary", "module"])
@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["name"])
def test_result_frozen_parity(binary, database, tmp_path, route, case):  # noqa: F811
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
    assert actual == expected, {"actual": readable(actual), "expected": readable(expected)}
