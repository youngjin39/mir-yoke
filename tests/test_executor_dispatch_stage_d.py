"""Stage D RED evidence: compare current native dispatch with frozen Python."""

from __future__ import annotations

import copy
import json
import os
import runpy
import sqlite3
from pathlib import Path

import pytest
from test_executor_status_native_parity import binary  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = runpy.run_path(str(ROOT / "tests/fixtures/generate_executor_dispatch_stage_d.py"))
GOLDEN = json.loads(SUPPORT["OUTPUT"].read_text(encoding="ascii"))
pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX synthetic provider fixtures")


@pytest.fixture(scope="module")
def oracle(tmp_path_factory):
    scratch = tmp_path_factory.mktemp("dispatch-oracle")
    reference = scratch / "reference"
    digest = SUPPORT["DIRECT"]["STATUS"].archive_reference(reference)
    assert digest == GOLDEN["archive_sha256"]
    database = scratch / "template.db"
    SUPPORT["DIRECT"]["STATUS"].template(reference, database)
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM jobs")
    return reference, database


def test_dispatch_frozen_provenance():
    assert GOLDEN["reference"] == SUPPORT["PIN"]
    assert [case["name"] for case in GOLDEN["cases"]] == [case["name"] for case in SUPPORT["CASES"]]
    assert (
        GOLDEN["exception_protocol"] == "exit 1; preserve raw stdout; traceback final stderr line"
    )


@pytest.mark.parametrize("payload", [b"0123456789abcdef", b"0123456789abcdefghij"])
def test_file_hex_is_not_a_generated_identity(oracle, tmp_path, payload):
    reference, database = oracle
    home = tmp_path / "home"
    SUPPORT["seed"](home, {"name": "success"}, reference, database)
    (home / "payload.dat").write_bytes(payload)
    assert SUPPORT["snapshot"](home)["files"]["payload.dat"]["hex"] == payload.hex()


def test_first_difference_reports_decoded_byte_offset():
    difference = SUPPORT["first_difference"]({"stdout_hex": "6162"}, {"stdout_hex": "6163"})
    assert difference == {
        "field": "/stdout_hex",
        "byte": 1,
        "expected_size": 2,
        "actual_size": 2,
        "expected_byte": "62",
        "actual_byte": "63",
    }


def contained_parent_swap_expected(case):
    """Owner exception: refuse at the same write boundary as artifacts-file.

    Derive every byte from frozen Python failure/state records, never native output.
    Only the error and the parent-swap input layout differ from artifacts-file.
    """
    failure = next(item for item in GOLDEN["cases"] if item["name"] == "artifacts-file")
    expected = copy.deepcopy(failure["expected"])
    message = "symlink/reparse point rejected: <root>/artifact-container"
    files = expected["effects"]["files"]
    del files["artifacts"]
    for name, value in case["expected"]["effects"]["files"].items():
        if name == "artifact-container" or name.startswith("fault-"):
            if not name.startswith("fault-outside/artifacts"):
                files[name] = copy.deepcopy(value)
    old = "[Errno 20] Not a directory: '<root>/artifacts/<id>'"
    hooks = bytes.fromhex(files["hook-events"]["hex"]).decode()
    files["hook-events"]["hex"] = hooks.replace(old, message).replace(
        "NotADirectoryError", "ValueError"
    ).encode().hex()
    row = files["tasks/jobs.db"]["tables"]["jobs"][0]
    row["stderr"] = message
    row["dispatch_options_json"] = row["dispatch_options_json"].replace(
        "<root>/artifacts", "<root>/artifact-container/artifacts"
    )
    expected["stderr_hex"] = f"[mir_executor] dispatch failed: {message}\n".encode().hex()
    return expected


@pytest.mark.parametrize("route", ["reference", "binary", "module"])
@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["name"])
def test_dispatch_frozen_parity(binary, oracle, tmp_path, case, route):  # noqa: F811
    reference, database = oracle
    home = (tmp_path / "home").resolve()
    setup = SUPPORT["seed"](
        home, case, reference, database, None if route == "reference" else binary
    )
    actual, routing = SUPPORT["capture"](home, case, setup, route, binary)
    expected = case.get("expected_by_route", {}).get(route, case["expected"])
    if route != "reference" and case["name"] == "fault-artifacts-parent-swap-to-outside":
        expected = contained_parent_swap_expected(case)
    difference = SUPPORT["first_difference"](expected, actual)
    if route != "reference" and case["name"] == "fault-artifacts-parent-swap-to-outside":
        assert (home / "fault-parent-swapped").exists(), "directory swap was not reached"
        outside = home / "fault-outside"
        assert sorted(path.name for path in outside.iterdir()) == ["canary"], (
            "artifact write escaped the validated parent",
            difference,
        )
        assert (outside / "canary").read_bytes() == b"outside must remain unchanged\n"
    assert difference is None, {
        "name": case["name"],
        "route": route,
        "first_difference": difference,
        **routing,
    }


def alias_observation(value, physical, key=""):
    """Keep alias <root> and reference-selected <physical> spellings distinct."""
    if isinstance(value, dict):
        return {key: alias_observation(item, physical, key) for key, item in value.items()}
    if isinstance(value, list):
        return [alias_observation(item, physical) for item in value]
    if isinstance(value, str):
        if key == "hex" or key.endswith("_hex"):
            return bytes.fromhex(value).replace(str(physical).encode(), b"<physical>").hex()
        return value.replace(str(physical), "<physical>")
    return value


@pytest.mark.parametrize("route", ["binary", "module"])
@pytest.mark.parametrize("name", [
    "success", "fault-review-malformed", "reviewer-write", "artifacts-file",
    "fault-cleanup-remove", "fault-cleanup-branch",
])
def test_dispatch_caller_alias_spelling(binary, oracle, tmp_path, name, route):  # noqa: F811
    """Pass a real alias in argv/HOME; compare pinned observations at each surface."""
    reference, database = oracle
    scenario = "fault-review-pass" if name == "reviewer-write" else name
    case = next(case for case in GOLDEN["cases"] if case["name"] == scenario)
    captures = []
    for implementation in ("reference", route):
        parent = tmp_path / implementation
        parent.mkdir()
        physical = parent / "physical"
        physical.mkdir()
        alias = parent / "alias"
        alias.symlink_to(physical, target_is_directory=True)
        home = alias / "home"
        assert str(home) != str(home.resolve())
        setup = SUPPORT["seed"](
            home, case, reference, database,
            None if implementation == "reference" else binary,
        )
        if name == "reviewer-write":
            for script in (home / "server.py", home / "fake-codex"):
                text = script.read_text().replace(
                    "        if review:\n",
                    "        if review:\n"
                    "            (cwd / '.mir-dispatch/reviewer.json').mkdir()\n",
                )
                script.write_text(text)
        actual, _ = SUPPORT["capture"](home, case, setup, implementation, binary)
        captures.append(alias_observation(actual, (physical / "home").resolve()))
    difference = SUPPORT["first_difference"](*captures)
    assert difference is None, difference
