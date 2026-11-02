"""Keep native decline diagnostics outside the CLI byte contract."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def decline_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("MIR_EXECUTOR_DECLINE_TRACE", str(tmp_path / "decline-trace.log"))


def trace_details():
    path = os.environ.get("MIR_EXECUTOR_DECLINE_TRACE")
    if path is None:
        return "native decline trace: disabled"
    trace = Path(path)
    content = trace.read_text(encoding="utf-8") if trace.is_file() else "<no declines>"
    return f"native decline trace ({trace}):\n{content}"
