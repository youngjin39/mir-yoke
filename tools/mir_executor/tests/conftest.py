from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mark_codex_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIR_CODEX_MAIN", "1")
