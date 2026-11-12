"""Pinned cross-root reads and exact transitive Git child traces.

D03 raw list-jobs preserves its unowned-policy decline (64, no child or effects);
the public facade then executes the pinned Python admission behavior exactly once.
"""
import json
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
SUPPORT = runpy.run_path(str(ROOT / "tests/fixtures/generate_executor_crossroot.py"))
GOLDEN = json.loads((ROOT / "tests/fixtures/executor_crossroot.json").read_text(encoding="ascii"))


def test_crossroot_reference_provenance():
    assert GOLDEN["reference"] == SUPPORT["PIN"]
    assert GOLDEN["archive_sha256"] == (
        "cc65107d815338c50856e203d6519eb6c3e7d73620d71549196fddb6062b43f1")
    assert [{key: case[key] for key in ("name", "command", "mode", "argv", "native_home")
             if key in case}
            for case in GOLDEN["cases"]] == SUPPORT["CASES"]
    for case in GOLDEN["cases"]:
        trace = case["expected"]["git_trace"]
        assert len(trace) == (
            0 if case["mode"] in {"empty-path", "nonexecutable-git"} else
            1 if case["mode"] in {"invalid-stdout", "invalid-stderr", "second-call-missing",
                                "parser-help", "parser-explicit-help", "parser-unknown"} else 2)
        for call in trace:
            assert call["argv"] == ["<HOME>/git-path/git", "-C", "<HOME>",
                                     "rev-parse", "--show-toplevel"]
            assert call["cwd"] == "<HOME>"
            assert call["env"]["CROSSROOT_ENV_SENTINEL"] == "unchanged value"


@pytest.mark.parametrize("route", ["binary", "module"])
@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["name"])
def test_crossroot_frozen_parity(binary, database, tmp_path, route, case):  # noqa: F811
    home = (tmp_path / "synthetic home").resolve()
    SUPPORT["seed"](home, case, database)
    if route == "module":
        install_package(home, binary, compatibility=case["command"] == "list-jobs")
    command = ([sys.executable, "-m", "tools.mir_executor"] if route == "module"
               else [str(binary), "--home-root", str(home)])
    actual = SUPPORT["capture"](home, case, command)
    expected = case["expected"]
    if route == "binary" and case["command"] == "list-jobs" and not case.get("native_home"):
        expected = {"exit": 64, "stdout_hex": "", "stderr_hex": "",
                    "storage": case["before_storage"], "git_trace": []}
    assert actual == expected, {"actual": readable(actual), "expected": readable(expected)}


@pytest.mark.parametrize("route", ["binary", "module"])
@pytest.mark.parametrize("command_name", [
    "status", "result", "list-jobs", "cancel", "resume", "sweep",
])
def test_native_crossroot_git_strip_preserves_refusal(
    binary, database, tmp_path, route, command_name,  # noqa: F811
):
    """Python strip characters cannot bypass the existing repository-local gate."""
    import shlex

    home = (tmp_path / "synthetic home").resolve()
    case = {"mode": "path-only-git", "argv": [
        command_name, "--repo-root=<HOME>/target",
        *([] if command_name in {"list-jobs", "sweep"} else ["--job-id=fixture"]),
    ]}
    SUPPORT["seed"](home, case, database)
    (home / "config").mkdir()
    (home / "config/mir-executor.local.json").write_text(json.dumps({
        "native_policy": {"version": 1, "target_admission": {
            "authorize_target": True, "repository_local": {
                "kind": "ValueError", "message": "review repository refusal",
            },
        }},
    }), encoding="ascii")
    if route == "module":
        install_package(home, binary, compatibility=True)
    executable = ([sys.executable, "-m", "tools.mir_executor"] if route == "module"
                  else [str(binary), "--home-root", str(home)])
    git = home / "git-path/git"
    git.write_text("#!/bin/sh\nprintf '%s\\034\\037\\n' "
                   + shlex.quote(str(home)) + "\n", encoding="ascii")
    actual = SUPPORT["capture"](home, case, executable)
    assert actual["exit"] == 1
    assert actual["stdout_hex"] == ""
    assert bytes.fromhex(actual["stderr_hex"]) == (
        b"[mir_executor] authorize_target refused <HOME>/target: "
        b"ValueError: review repository refusal\n")
