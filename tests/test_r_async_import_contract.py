"""R-ASYNC locks reachable import semantics without inventing a worker engine."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from w5_reference import reference_bytes

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/r_async"
spec = importlib.util.spec_from_file_location("r_async_capture", FIXTURES / "capture.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
EXPECTED = json.loads((FIXTURES / "import.json").read_text())


def assert_contract(source, scratch):
    assert capture.observe(source, scratch) == EXPECTED["import"]


def stage_reference(source):
    for relative in capture.FILES:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(reference_bytes("src/" + relative)
                           if relative == capture.FILES[-1]
                           else (ROOT / "src" / relative).read_bytes())


def test_retired_import_matches_pinned_failure(tmp_path):
    assert EXPECTED["reference_pin"] == capture.PIN
    source = tmp_path / "src"
    stage_reference(source)
    assert_contract(source, tmp_path / "probe")


@pytest.mark.parametrize("mutation", ["success", "different-dependency"])
def test_import_contract_rejects_mutants(tmp_path, mutation):
    source = tmp_path / "src"
    stage_reference(source)
    adapter = source / capture.FILES[-1]
    if mutation == "success":
        adapter.write_text("async def run_provider(adapter, compiled):\n    return None\n")
    else:
        original = adapter.read_text()
        assert "mir.core.worker.mir_provider_adapter" in original
        adapter.write_text(original.replace("mir.core.worker.", "mir.core.absent_worker."))
    with pytest.raises(AssertionError):
        assert_contract(source, tmp_path / "probe")
