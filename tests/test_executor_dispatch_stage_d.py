"""Stage D RED evidence: compare current native dispatch with frozen Python."""

from __future__ import annotations

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
