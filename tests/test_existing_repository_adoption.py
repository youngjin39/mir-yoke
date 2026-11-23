from __future__ import annotations

import pytest
from installed_mir import installed_mir as installed_mir
from test_bootstrap_adoption_cli import _ready_project, _run_native_adoption


@pytest.fixture(autouse=True)
def _no_published_evaluator(monkeypatch):
    # The repository lock pins published evaluator artifacts; adoption tests stay
    # hermetic and exercise delivery in test_bootstrap_native_delivery.py.
    monkeypatch.setenv("MIR_CAPABILITY_NATIVE_ARTIFACTS", "0")


# @spec CR-005 FR-002 FR-006 IR-002 QR-002
def test_should_report_no_changed_paths_when_existing_repository_is_assessed(
    tmp_path, installed_mir
) -> None:
    _ready_project(tmp_path)

    report = _run_native_adoption(installed_mir, tmp_path, 0)

    assert report["apply"] is False
    assert report["receipt_written"] is False
    assert report["changed_paths"] == []


# @spec FR-006 IR-002 QR-002
def test_should_report_only_local_receipt_when_existing_repository_apply_succeeds(
    tmp_path, installed_mir
) -> None:
    _ready_project(tmp_path)

    report = _run_native_adoption(installed_mir, tmp_path, 0, "--apply")

    assert report["changed_paths"] == [".mir/bootstrap-receipt.json"]
    assert report["receipt_written"] is True
