"""Stage D resume RED evidence; expected records come only from pinned Python."""

from __future__ import annotations

import json
import os
import runpy
import sqlite3
from pathlib import Path

import pytest
from test_executor_status_native_parity import binary  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
S = runpy.run_path(str(ROOT / "tests/fixtures/generate_executor_resume_stage_d.py"))
D = S["D"]
GOLDEN = json.loads(S["OUTPUT"].read_text(encoding="ascii"))
pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX synthetic provider fixtures")


@pytest.fixture(scope="module", autouse=True)
def isolated_git_environment():
    with D["isolated_git_environment"]():
        yield


@pytest.fixture(scope="module")
def oracle(tmp_path_factory):
    scratch = tmp_path_factory.mktemp("resume-oracle")
    reference = scratch / "reference"
    assert D["DIRECT"]["STATUS"].archive_reference(reference) == GOLDEN["archive_sha256"]
    database = scratch / "template.db"
    D["DIRECT"]["STATUS"].template(reference, database)
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM jobs")
    return reference, database


def test_resume_frozen_provenance():
    assert GOLDEN["reference"] == S["PIN"] == "d7ce42656224c719094358f343317907bf6e46a9"
    assert [c["name"] for c in GOLDEN["cases"]] == [c["name"] for c in S["CASES"]]
    assert (
        GOLDEN["exception_protocol"] == "exit 1; preserve raw stdout; traceback final stderr line"
    )


@pytest.mark.parametrize("route", ["reference", "binary", "module"])
@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["name"])
def test_resume_frozen_parity(binary, oracle, tmp_path, route, case):  # noqa: F811
    reference, database = oracle
    home = (tmp_path / "home").resolve()
    setup = S["seed"](home, case, reference, database, None if route == "reference" else binary)
    actual, _ = S["capture"](home, case, setup, route, binary)
    expected = case.get("expected_by_route", {}).get(route, case["expected"])
    difference = D["first_difference"](expected, actual)
    assert difference is None, json.dumps(
        dict(name=case["name"], route=route, **(difference or {}))
    )


@pytest.mark.parametrize("route", ["binary", "module"])
def test_resume_artifact_parent_swap_stays_contained(binary, oracle, tmp_path, route):  # noqa: F811
    reference, database = oracle
    case = next(
        c for c in GOLDEN["cases"] if c["name"] == "dispatch-fault-artifacts-parent-swap-to-outside"
    )
    home = (tmp_path / "home").resolve()
    setup = S["seed"](home, case, reference, database, binary)
    S["capture"](home, case, setup, route, binary)
    assert (home / "fault-parent-swapped").exists(), "fault injection was not reached"
    assert sorted(
        p.relative_to(home / "fault-outside").as_posix()
        for p in (home / "fault-outside").rglob("*")
    ) == ["canary"]
    assert (home / "fault-outside/canary").read_text() == "outside must remain unchanged\n"


@pytest.mark.parametrize("route", ["reference", "binary", "module"])
def test_resume_isolates_inherited_git(binary, oracle, tmp_path, monkeypatch, route):  # noqa: F811
    reference, database = oracle
    hostile = {
        "GIT_DIR": str(tmp_path / "foreign.git"),
        "GIT_WORK_TREE": str(tmp_path / "foreign-tree"),
        "GIT_INDEX_FILE": str(tmp_path / "foreign-index"),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "init.defaultBranch",
        "GIT_CONFIG_VALUE_0": "trunk",
    }
    for key, value in hostile.items():
        monkeypatch.setenv(key, value)
    case = next(c for c in GOLDEN["cases"] if c["name"] == "v2")
    home = (tmp_path / "home").resolve()
    setup = S["seed"](home, case, reference, database, None if route == "reference" else binary)
    actual, _ = S["capture"](home, case, setup, route, binary)
    assert D["first_difference"](case["expected"], actual) is None
    assert {key: os.environ[key] for key in hostile} == hostile
