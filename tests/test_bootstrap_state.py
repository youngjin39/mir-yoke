"""Fresh unmodified-shell verification of the supplementary state records."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter

import pytest
from w1_golden import ROOT, assert_replay

FIXTURE = ROOT / "native/handoff-packet/tests/fixtures/bootstrap-state.json"
RECORDS = json.loads(FIXTURE.read_text())


def test_bootstrap_state_inventory():
    source = RECORDS["source"]
    assert hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest() == source["sha256"]
    assert Counter(r["state"] for r in RECORDS["reused"]) == {
        "missing": 3, "pending": 2, "restart_required": 2,
        "ready": 10, "invalid": 25, "template_maintainer": 1,
    }
    assert len(RECORDS["legacy_native"]) == 42
    assert len({r["id"] for r in RECORDS["new"]}) == len(RECORDS["new"])
    assert all(r["expected"]["delta"] == {} and r["expected"]["deleted"] == []
               for r in RECORDS["new"])


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell oracle")
@pytest.mark.parametrize("record", RECORDS["new"], ids=lambda r: r["id"])
def test_supplementary_shell_state_records(record, tmp_path):
    assert_replay(record, tmp_path / "replay")
