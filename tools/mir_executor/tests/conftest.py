from __future__ import annotations

import pathlib

import pytest


@pytest.fixture(autouse=True)
def _mark_codex_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIR_CODEX_MAIN", "1")


@pytest.fixture(autouse=True)
def _isolate_default_global_policy(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep tests off the host's rendered routing JSON (ADR-88).

    The host's MIR_SUB_AGENT_POLICY names that JSON too, and its `delegation.mode` now
    decides the lane (owner decision 1-A); a test that needs an overlay sets it.
    """
    from tools.mir_executor import policy as policy_module

    monkeypatch.delenv(policy_module.POLICY_ENV_VAR, raising=False)
    absent = tmp_path / "absent-global-policy.json"
    monkeypatch.setattr(policy_module, "default_global_policy_path", lambda: absent, raising=False)
