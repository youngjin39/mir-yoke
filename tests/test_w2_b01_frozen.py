"""W2-B01-F01 frozen records: canonical JSON, instance IDs, structured errors, ToolContract.

Expected values were captured by running these cases against the unmodified Python reference;
they are the oracle for the Rust port and are never regenerated from it.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
from pathlib import Path
from unittest import mock

import pytest
from pydantic import BaseModel

from mir.core.crypto import canonical
from mir.core.engine import instance_id, structured_error, tool_contract

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


def _error(data):
    return lambda tmp: structured_error.StructuredError.from_dict(data).to_json()


def _emit(prefix=None):
    def run(tmp: Path) -> str:
        err = structured_error.StructuredError(structured_error.ErrorType.POLICY, False, "blocked")
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            if prefix is None:
                structured_error.emit_error_to_stderr(err)
            else:
                structured_error.emit_error_to_stderr(err, prefix)
        return buffer.getvalue()
    return run


def _contract(data):
    return lambda tmp: tool_contract.ToolContract.from_dict(data).to_json()


BASE = {"idempotency_key": "k", "precondition": "ready", "dry_run": True,
        "side_effect_summary": "none"}

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
    "error.minimal": _error({"type": "policy", "recoverable": False, "summary": "blocked"}),
    "error.full": _error({"type": "tool_failure", "recoverable": True, "summary": "retry",
                          "details_ref": "log:1", "context": {"z": 1, "a": "\u00e9"}}),
    "error.empty_context": _error({"type": "schema", "recoverable": True, "summary": "s",
                                   "context": {}, "details_ref": ""}),
    "error.non_bool_recoverable": _error({"type": "unknown", "recoverable": "yes", "summary": 3}),
    "error.ignored_extra": _error({"type": "interrupt", "recoverable": False, "summary": "s",
                                   "other": 1}),
    "error.missing_all": _error({}),
    "error.missing_recoverable": _error({"type": "policy", "summary": "s"}),
    "error.missing_summary": _error({"type": "policy", "recoverable": False}),
    "error.invalid_type": _error({"type": "bad", "recoverable": False, "summary": "s"}),
    "error.from_json": lambda tmp: structured_error.StructuredError.from_json(
        '{"summary":"s","type":"transition","recoverable":true}').to_json(),
    "error.from_json_invalid": lambda tmp: structured_error.StructuredError.from_json("{"),
    "error.types": lambda tmp: [member.value for member in structured_error.ErrorType],
    "error.emit_default": _emit(),
    "error.emit_prefix": _emit("[hook]"),
    "contract.minimal": _contract(BASE),
    "contract.extra": _contract({**BASE, "dry_run": False, "extra": {"z": 1, "a": [1]}}),
    "contract.empty_extra": _contract({**BASE, "extra": {}}),
    "contract.summary_200": _contract({**BASE, "side_effect_summary": "x" * 200}),
    "contract.summary_201": _contract({**BASE, "side_effect_summary": "x" * 201}),
    "contract.summary_not_str": _contract({**BASE, "side_effect_summary": 5}),
    "contract.missing_all": _contract({}),
    "contract.missing_precondition": _contract({"idempotency_key": "k"}),
    "contract.missing_dry_run": _contract({"idempotency_key": "k", "precondition": "p"}),
    "contract.missing_summary": _contract({"idempotency_key": "k", "precondition": "p",
                                           "dry_run": False}),
    "contract.from_json": lambda tmp: tool_contract.ToolContract.from_json(
        json.dumps(BASE)).to_json(),
    "contract.key_none": lambda tmp: tool_contract.make_idempotency_key(),
    "contract.key_one": lambda tmp: tool_contract.make_idempotency_key("write_file"),
    "contract.key_parts": lambda tmp: tool_contract.make_idempotency_key("a", "b|c", ""),
    "contract.key_unicode": lambda tmp: tool_contract.make_idempotency_key("\uba85", "\u00e9"),
}
if hasattr(structured_error, "to_tool_event_type"):
    CASES["error.tool_event_types"] = lambda tmp: {
        member.value: structured_error.to_tool_event_type(member)
        for member in structured_error.ErrorType}


def observe(case, tmp: Path) -> dict:
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - the error class and text are the frozen behaviour
        return {"error": [type(exc).__name__, str(exc)]}


RECORDS = json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
