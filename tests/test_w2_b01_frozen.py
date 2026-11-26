"""W2-B01-F01 Python reference checks for canonical JSON and instance IDs.

Expected values were captured by running these cases against the unmodified Python reference;
they are the oracle for the Rust port and are never regenerated from it.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from unittest import mock

import pytest
from pydantic import BaseModel
from w5_reference import load_reference

canonical = load_reference("mir.core.crypto.canonical", "src/mir/core/crypto/canonical.py")
instance_id = load_reference("mir.core.engine.instance_id", "src/mir/core/engine/instance_id.py")

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b01.json"


class _Model(BaseModel):
    b: int = 2
    a: str = "x"
    signature: str = "sig"


def _canon(payload, **kwargs):
    return lambda tmp: canonical.canonical_json(payload, **kwargs)


def _instance(files, node="host-a", initial=True):
    def run(tmp: Path) -> str:
        paths = []
        for index, body in enumerate(files):
            path = tmp / f"id-{index}"
            if body is not None:
                path.write_text(body, encoding="utf-8")
            paths.append(path)
        module_file = instance_id.__file__
        if not initial:
            module_file = str(tmp / "engine/instance_id.py")
        instance_id.current_instance_id.cache_clear()
        try:
            with mock.patch.object(instance_id, "_MACHINE_ID_FILES", tuple(paths)), \
                    mock.patch.object(instance_id.platform, "node", return_value=node), \
                    mock.patch.object(instance_id, "__file__", module_file):
                return instance_id.current_instance_id()
        finally:
            instance_id.current_instance_id.cache_clear()
    return run


CASES = {
    "canonical.sorted_nested": _canon({"z": 1, "a": {"y": [3, {"b": 1, "a": 2}], "x": None}}),
    "canonical.unicode_escapes": _canon({"s": "\uba85\u0301\n\t\"\\\x00\x7f\u2028\U0001f680"}),
    "canonical.numbers": _canon({"i": 1, "f": 1.0, "nz": -0.0, "big": 1e16, "small": 1.5e-7,
                                 "huge": 2 ** 64, "neg": -3, "third": 1 / 3}),
    "canonical.non_finite": _canon({"nan": math.nan, "inf": math.inf, "ninf": -math.inf}),
    "canonical.bool_null": _canon({"t": True, "f": False, "n": None}),
    "canonical.int_keys": _canon({2: "b", 1: "a", 10: "c"}),
    "canonical.mixed_keys": _canon({1: "a", "b": 2}),
    "canonical.tuple_value": _canon({"t": (1, "a")}),
    "canonical.set_value": _canon({"s": {1}}),
    "canonical.omit_default": _canon({"b": 2, "signature": "x", "nested": {"signature": "kept"}}),
    "canonical.omit_custom": _canon({"b": 2, "signature": "x", "drop": 1}, omit=("drop",)),
    "canonical.omit_none": _canon({"signature": "x"}, omit=()),
    "canonical.model": _canon(_Model()),
    "canonical.pairs": _canon([("b", 1), ("a", 2)]),
    "canonical.empty": _canon({}),
    "instance.first_file": _instance(["machine-1\n", "machine-2"]),
    "instance.blank_then_second": _instance([" \n", "machine-2\n", "machine-3"]),
    "instance.missing_then_third": _instance([None, None, "uuid-3"]),
    "instance.fallback": _instance([None, None, None]),
    "instance.fallback_other_host": _instance([None, None, None], node="host-b"),
    "instance.fallback_empty_node": _instance([None, None, None], node=""),
    "instance.fallback_no_migration": _instance([None, None, None], initial=False),
}


def observe(case, tmp: Path) -> dict:
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - the error class and text are the frozen behaviour
        return {"error": [type(exc).__name__, str(exc)]}


RECORDS = {
    name: record
    for name, record in json.loads(FIXTURE.read_text(encoding="utf-8")).items()
    if name.startswith(("canonical.", "instance."))
}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
