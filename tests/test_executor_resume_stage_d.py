"""Stage D resume RED evidence; expected records come only from pinned Python."""

from __future__ import annotations

import json
import os
import runpy
import sqlite3
from pathlib import Path

import pytest
from test_executor_dispatch_stage_d import contained_parent_swap_expected
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
    if route != "reference" and case["name"] == "dispatch-fault-artifacts-parent-swap-to-outside":
        expected = contained_parent_swap_expected(
            case, cases=GOLDEN["cases"], failure_name="dispatch-artifacts-file"
        )
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


@pytest.mark.parametrize("route", ["binary", "module"])
@pytest.mark.parametrize(
    "scenario",
    ["relative-slash", "absolute-slash", "parent-slash", "uncaught-exit-ok",
     "uncaught-exit-fail", "caught-exit-fail"],
)
def test_resume_read_path_and_writer_teardown(binary, oracle, tmp_path, route, scenario):  # noqa: F811
    reference, database = oracle
    observations = {}
    for implementation in ["reference", route]:
        home = (tmp_path / implementation).resolve()
        case = {"name": "v2"}
        setup = S["seed"](
            home, case, reference, database, None if implementation == "reference" else binary
        )
        if scenario.endswith("slash"):
            spelling = {
                "relative-slash": "./brief.json/",
                "absolute-slash": str(home) + "//./brief.json/",
                "parent-slash": "tools/..//./brief.json/",
            }[scenario]
            with sqlite3.connect(home / "tasks/jobs.db") as db:
                raw = db.execute("SELECT dispatch_options_json FROM jobs").fetchone()[0]
                saved = json.loads(raw)
                saved["dispatch_brief"] = spelling
                db.execute("UPDATE jobs SET dispatch_options_json=?", (json.dumps(saved),))
        else:
            kind = "ValueError" if scenario.startswith("caught") else "RuntimeError"
            exit_body = (
                'raise RuntimeError("exit failed")'
                if scenario.endswith("fail") else "return False"
            )
            with (home / "tools/mir_executor/local.py").open("a") as stream:
                stream.write(
                    '\nimport sys\n'
                    f'def pre_execute(*args):\n    raise {kind}("pre failed")\n'
                    'class ResumeWriter:\n'
                    '    def __enter__(self):\n        return self\n'
                    '    def __exit__(self, *args):\n'
                    '        print("EXIT-MARKER", file=sys.stderr, flush=True)\n'
                    f'        {exit_body}\n'
                    'def writer_scope(*args):\n    return ResumeWriter()\n'
                )
        actual, _ = S["capture"](home, case, setup, implementation, binary)
        # Keep flushed diagnostics/markers as well as the final exception; the
        # frozen capture helper alone retains only the traceback's final line.
        stderr = (home.parent / (home.name + ".stderr")).read_bytes()
        if b"Traceback (most recent call last):" in stderr:
            prefix = stderr.split(b"Traceback (most recent call last):", 1)[0]
            stderr = prefix + stderr.splitlines()[-1] + b"\n"
        observations[implementation] = (actual["exit"], actual["stdout_hex"], stderr)
    expected = observations["reference"]
    if scenario.endswith("slash"):
        assert expected[0] == 0
    else:
        error = (
            b"RuntimeError: exit failed\n"
            if scenario.endswith("fail") else b"RuntimeError: pre failed\n"
        )
        caught = (
            b"[mir_executor] resume root error: pre failed\n"
            if scenario.startswith("caught") else b""
        )
        assert expected[0] == 1
        assert expected[2] == caught + b"EXIT-MARKER\n" + error
    assert observations[route] == expected


def test_snapshot_excludes_only_exact_nested_native_markers(tmp_path):
    D["git"](tmp_path, "init", "-q")
    D["git"](
        tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "--allow-empty", "-qm", "fixture",
    )
    nested = tmp_path / "target"
    nested.mkdir()
    for name in ("native-imported", "native-owned", "native-imported-other", "other"):
        (nested / name).write_text("effect")
    files = D["snapshot"](tmp_path)["files"]
    assert "target/native-imported" not in files
    assert "target/native-owned" not in files
    assert files["target/native-imported-other"]["mode"] == "0o644"
    assert files["target/other"]["mode"] == "0o644"
