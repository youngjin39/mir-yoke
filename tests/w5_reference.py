"""Replay retired Python from pinned data, never from a native implementation."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "tests/fixtures/w5-retired-sources.json").read_text())
PIN = "5b65894635d3c4f2a22d1059db13847377ee6a16"


def reference_bytes(path: str) -> bytes:
    assert DATA["reference_pin"] == PIN
    record = DATA["files"][path]
    data = record["source"].encode()
    assert hashlib.sha256(data).hexdigest() == record["sha256"], path
    return data


def load_reference(name: str, path: str, dependencies=None) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(ROOT / path)
    # Temporary bindings preserve dataclass and Enum identity without restoring a
    # production import route for a retired module.
    with mock.patch.dict(sys.modules, {**(dependencies or {}), name: module}):
        exec(compile(reference_bytes(path), module.__file__, "exec"), module.__dict__)
    return module
