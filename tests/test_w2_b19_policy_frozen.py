"""W2-B19-F01: policy adapter records from the unmodified Python reference.

These records are the Rust port oracle and must never be regenerated from a port.
Only the native query boundary is replaced; no native binary is executed.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from unittest import mock

import pytest

from mir.cli import policy

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b19-policy.json"


def _main(argv, result=None):
    def run(tmp: Path):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(policy, "_native_query", return_value=result) as query, \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = policy.main(list(argv))
        return {"exit": code, "stdout": stdout.getvalue(), "stderr": stderr.getvalue(),
                "native_argv": [call.args[0] for call in query.call_args_list]}
    return run


CASES = {
    "main.help_long": _main(["--help"]),
    "main.help_short": _main(["-h"]),
    "main.empty": _main([]),
    "main.unknown": _main(["unknown"]),
    "main.help_extra": _main(["--help", "extra"]),
    "main.short_help_extra": _main(["-h", "extra"]),
    "main.resolve_not_first": _main(["--help", "resolve"]),
    "main.resolve_zero": _main(["resolve", "--category", "unit"], 0),
    "main.resolve_seven": _main(
        ["resolve", "--category", "unit", "--repo-root", "relative-repo",
         "--format", "json"], 7),
    "main.resolve_bare": _main(["resolve"], 0),
    "main.resolve_help_forwarded": _main(["resolve", "--help"], 7),
    "main.resolve_unavailable": _main(["resolve", "--category", "unit"]),
}


def observe(case, tmp: Path) -> dict:
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze the error class and message
        return {"error": [type(exc).__name__, str(exc)]}


RECORDS = json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
