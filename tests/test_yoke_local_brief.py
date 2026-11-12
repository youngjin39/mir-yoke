"""Yoke uses declarative validation; its reference records remain reproducible."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_yoke_owns_only_declarative_brief_validation():
    config = json.loads((ROOT / "config/mir-executor.local.json").read_text())
    assert config.get("native_policy") == {
        "version": 1, "brief_profile": {"name": "base_v1"},
    }
    assert config["python_local_hooks"] is False
    retained = {
        "tools/mir_executor/local.py":
            "c398bd016fac16f00b428a671276c46a614911acb2e4bac2f1f067f4f3cb6a6c",
        "tools/mir_executor/tests/local/test_local.py":
            "8a2b5c0b0d0059b5d6be62bdf1ea0483291545f19c2fce806533bdf8ddf22d97",
    }
    for path, digest in retained.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    # Supported consumers still receive the bridge and Python APIs.
    assert (ROOT / "tools/mir_executor/local_bridge.py").is_file()
    assert (ROOT / "tools/mir_executor/executor.py").is_file()


def test_pinned_yoke_hook_records_are_reproducible(tmp_path):
    if os.name == "nt":
        import pytest
        pytest.skip("Unix permission diagnostic record requires an unprivileged Unix host")
    output = tmp_path / "records.json"
    subprocess.run([
        sys.executable, str(ROOT / "tests/fixtures/generate_yoke_local_brief.py"),
        "--scratch", str(tmp_path / "oracle"), "--output", str(output),
    ], cwd=ROOT, check=True, capture_output=True)
    assert output.read_bytes() == (ROOT / "tests/fixtures/yoke_local_brief.json").read_bytes()


def test_yoke_status_with_retained_hook_stays_native(monkeypatch):
    from tools.mir_executor import entrypoint
    monkeypatch.setattr(entrypoint, "_HOME_ROOT", ROOT)
    monkeypatch.setattr(entrypoint, "_status_codec_decline", lambda: False)
    monkeypatch.setattr(entrypoint, "_native_status", lambda argv: 37)
    monkeypatch.setitem(sys.modules, "tools.mir_executor.cli", None)
    assert entrypoint.main(["status", "--job-id", "synthetic"]) == 37


@pytest.mark.parametrize("text,disabled", [
    ('{"python_local_hooks":false}', True),
    ('{}', False), ('{"python_local_hooks":true}', False),
    ('[]', False), ('{', False),
    ('{"python_local_hooks":false,"ignored":' + '[' * 130 + '0' + ']' * 130 + '}', True),
])
def test_status_opt_out_requires_exact_false(monkeypatch, tmp_path, text, disabled):
    from tools.mir_executor import entrypoint
    (tmp_path / "config").mkdir()
    module = tmp_path / "tools/mir_executor/local.py"
    module.parent.mkdir(parents=True)
    module.write_text("raise AssertionError('inactive')\n")
    (tmp_path / "config/mir-executor.local.json").write_text(text)
    monkeypatch.setattr(entrypoint, "_HOME_ROOT", tmp_path)
    monkeypatch.setattr(entrypoint, "_status_codec_decline", lambda: False)
    monkeypatch.setattr(entrypoint, "_native_status", lambda argv: 37)
    legacy = types.ModuleType("tools.mir_executor.cli")
    legacy.main = lambda argv: 41
    monkeypatch.setitem(sys.modules, "tools.mir_executor.cli", legacy)
    assert entrypoint.main(["status", "--job-id", "missing"]) == (37 if disabled else 41)


@pytest.mark.parametrize("local,value", [
    (local, value) for local in [False, True]
    for value in [None, 0, 1, "false", "unknown", [], {}, False, True]
    if not (local and isinstance(value, bool))
])
def test_status_selector_errors_are_final(monkeypatch, tmp_path, capsys, value, local):
    from tools.mir_executor import entrypoint
    (tmp_path / "config").mkdir()
    (tmp_path / "config/mir-executor.local.json").write_text(
        json.dumps({"python_local_hooks": value}))
    if local:
        module = tmp_path / "tools/mir_executor/local.py"
        module.parent.mkdir(parents=True)
        module.write_text("raise AssertionError('must not import')\n")
    monkeypatch.setattr(entrypoint, "_HOME_ROOT", tmp_path)
    monkeypatch.setitem(sys.modules, "tools.mir_executor.cli", None)
    monkeypatch.setattr(entrypoint, "_native_status", lambda argv: pytest.fail("native called"))
    assert entrypoint.main(["status", "--job-id", "missing"]) == 1
    expected = ("python_local_hooks requires tools/mir_executor/local.py"
                if isinstance(value, bool) else "python_local_hooks must be a boolean")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"[mir_executor] native local policy configuration error: {expected}\n"


@pytest.mark.parametrize("text", [
    '{"ignored":' + '[' * 10001 + '0' + ']' * 10001 + '}',
    '{"ignored":"python_local_hooks",?}',
])
def test_absent_selector_does_not_add_a_status_json_depth_failure(monkeypatch, tmp_path, text):
    from tools.mir_executor import entrypoint
    (tmp_path / "config").mkdir()
    (tmp_path / "config/mir-executor.local.json").write_text(text)
    monkeypatch.setattr(entrypoint, "_HOME_ROOT", tmp_path)
    monkeypatch.setattr(entrypoint, "_native_status", lambda argv: 37)
    assert entrypoint.main(["status", "--job-id", "missing"]) == 37
