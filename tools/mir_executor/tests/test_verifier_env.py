"""Opt-in verifier isolation preserves only explicit environment inputs."""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

from tools.mir_executor import dispatch
from tools.mir_executor.tests.test_dispatch import _cleanup, _make_repo


def test_should_reject_unknown_verifier_env_before_running(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "config/mir-executor.local.json").write_text(json.dumps({
        "verifiers": {"pass": ["true"]}, "verifier_env": "unknown",
    }))
    outcome = dispatch.run_dispatch(
        repo, "invalid-verifier-env", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )
    try:
        with pytest.raises(ValueError, match="verifier_env"):
            dispatch.evaluate_merge_gate(
                outcome.worktree, allowlist=[], expect_changes=False,
                verification_commands=["pass"],
            )
    finally:
        _cleanup(outcome)


@pytest.mark.parametrize("result", ["success", "failure", "timeout", "exception"])
def test_should_isolate_each_verifier_and_remove_directories(tmp_path, monkeypatch, result):
    repo = _make_repo(tmp_path)
    script = "import sys; sys.exit(0)"
    if result == "failure":
        script = "import sys; sys.exit(7)"
    elif result == "timeout":
        script = "import time; time.sleep(30)"
    argv = [sys.executable, "-c", script]
    (repo / "config/mir-executor.local.json").write_text(json.dumps({
        "verifiers": {"first": argv, "second": argv},
        "verifier_env": "isolated",
        "child_env_extra_keys": ["PROJECT_ALLOWED_TOKEN", "HOME", "UV_CACHE_DIR"],
    }))
    for key, value in {
        "HOME": str(tmp_path / "real-home"),
        "UV_CACHE_DIR": str(tmp_path / "real-cache"),
        "LANG": "C",
        "LC_MESSAGES": "C",
        "PROJECT_ALLOWED_TOKEN": "explicit-opt-in",
        "OPENAI_API_KEY": "must-not-inherit",
        "CODEX_HOME": "must-not-inherit",
        "PYTHONPATH": "must-not-inherit",
        "MIR_SUB_AGENT_POLICY": "must-not-inherit",
    }.items():
        monkeypatch.setenv(key, value)
    outcome = dispatch.run_dispatch(
        repo, "verifier-env", codex_runner=lambda *_: dispatch.CodexAttempt(0)
    )
    original = dispatch.subprocess.run
    environments = []
    directories = []

    def run(command, **kwargs):
        if command == argv:
            env = kwargs["env"]
            environments.append(dict(env))
            home, cache = pathlib.Path(env["HOME"]), pathlib.Path(env["UV_CACHE_DIR"])
            directories.extend([home, cache])
            assert home.is_dir()
            assert cache.is_dir()
            (home / "written-by-verifier").touch()
            (cache / "written-by-verifier").touch()
            if result == "exception":
                raise OSError("verifier process could not start")
        return original(command, **kwargs)

    monkeypatch.setattr(dispatch.subprocess, "run", run)
    try:
        if result == "exception":
            with pytest.raises(OSError, match="verifier process could not start"):
                dispatch.evaluate_merge_gate(
                    outcome.worktree, allowlist=[], expect_changes=False,
                    verification_commands=["first"],
                )
        else:
            gate = dispatch.evaluate_merge_gate(
                outcome.worktree, allowlist=[], expect_changes=False,
                verification_commands=["first", "second"],
                verify_timeout=0.05 if result == "timeout" else None,
            )
            assert gate.approved == (result == "success")
            if result == "failure":
                assert gate.reason == "verification-failed:first"
            elif result == "timeout":
                assert gate.reason == "verification-timeout"
        for env in environments:
            assert set(env) == {
                key for key in os.environ
                if key in {"PATH", "LANG", "TMPDIR", "PROJECT_ALLOWED_TOKEN"}
                or key.startswith("LC_")
            } | {"HOME", "UV_CACHE_DIR"}
            assert env["HOME"] != os.environ["HOME"]
            assert env["UV_CACHE_DIR"] != os.environ["UV_CACHE_DIR"]
            assert env["PROJECT_ALLOWED_TOKEN"] == "explicit-opt-in"
            assert env["LANG"] == env["LC_MESSAGES"] == "C"
        if result == "success":
            assert len(environments) == 2
            assert environments[0]["HOME"] != environments[1]["HOME"]
            assert environments[0]["UV_CACHE_DIR"] != environments[1]["UV_CACHE_DIR"]
        assert directories
        assert all(not path.exists() for path in directories)
    finally:
        _cleanup(outcome)
