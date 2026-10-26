"""Independent regressions for indirect reads required by ADR-91 section 4.4."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "plugins/mir-mcp/mir_mcp.py"


@pytest.fixture
def server():
    spec = importlib.util.spec_from_file_location("indirect_mir_mcp", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value", [None, [], "invalid", {"id": 3}, {"version": [1]}])
@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("ontology_validate", {}),
        ("ontology_lookup", {"query": "sample"}),
        ("handoff_pins", {"paths": ["source.py"]}),
    ],
)
def test_malformed_contract_has_short_error(server, tmp_path, value, tool, arguments):
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/ontology-map.json").write_text(json.dumps({"contract": value}))
    (tmp_path / "source.py").write_text("pass\n")
    result = server.execute(tool, {"target_root": str(tmp_path), **arguments})
    assert result["error"] == {"code": "E_FORMAT"}


def test_bundled_replacement_refuses_external_file(server, tmp_path, monkeypatch):
    package = tmp_path / "package"
    shutil.copytree(ROOT / "plugins/mir-mcp", package)
    monkeypatch.setattr(server, "PACKAGE", package)
    original = server.os.open
    contract = package / "ontology/references/common-contract.json"
    external = tmp_path / "external"
    external.write_text("DO_NOT_DISCLOSE_SENTINEL")

    def replace(path, flags, *args, **kwargs):
        if path == "common-contract.json":
            contract.unlink()
            contract.symlink_to(external)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(server.os, "open", replace)
    with pytest.raises(server.Refusal):
        server.bundled("ontology/references/common-contract.json")


def test_git_root_replacement_before_preflight_refuses_without_child(server, tmp_path, monkeypatch):
    def init(path, commit):
        metadata = path / ".git"
        (metadata / "refs/heads").mkdir(parents=True)
        (metadata / "objects/info").mkdir(parents=True)
        (metadata / "HEAD").write_text("ref: refs/heads/main\n")
        (metadata / "refs/heads/main").write_text(commit * 40 + "\n")
        (metadata / "config").write_text("[core]\nrepositoryformatversion=0\nbare=false\n")

    root = tmp_path / "target"
    external = tmp_path / "external"
    init(root, "a")
    init(external, "b")
    guard = server.Guard(str(root))
    saved = tmp_path / "saved"
    root.rename(saved)
    root.symlink_to(external, target_is_directory=True)

    def forbidden_child(*args, **kwargs):
        raise AssertionError("preflight must reject a replaced root before spawning")

    monkeypatch.setattr(subprocess, "Popen", forbidden_child)
    try:
        with pytest.raises(server.Refusal) as error:
            server.run_git(guard, "head", "rev-parse", "--verify", "HEAD")
        assert error.value.code in {"E_PATH", "E_GIT"}
    finally:
        root.unlink()
        saved.rename(root)
        guard.close()
