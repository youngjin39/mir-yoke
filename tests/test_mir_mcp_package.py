"""ADR-91 exact package shape; production admission and canonical-source parity."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from mir.core.capabilities.mcp import MCP_FILES, closed_json, validate_mcp_package

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "plugins/mir-mcp"
FILES = set(MCP_FILES)


def _closed_json(path: Path) -> dict:
    return closed_json(path)


def _assert_shape(package: Path) -> None:
    validate_mcp_package(package)


def test_exact_package_and_closed_launch_declarations() -> None:
    _assert_shape(PACKAGE)


@pytest.mark.parametrize(
    "relative,canonical",
    [
        ("ontology/scripts/ontology_check.py", "ontology/scripts/ontology_check.py"),
        ("ontology/references/common-contract.json", "ontology/references/common-contract.json"),
        ("shared/relations_query.py", "selective-relations/scripts/relations_query.py"),
    ],
)
def test_shared_sources_are_byte_identical(relative: str, canonical: str) -> None:
    assert (PACKAGE / relative).read_bytes() == (
        ROOT / "plugins/mir-core/skills" / canonical
    ).read_bytes()


@pytest.mark.parametrize(
    "mutation",
    [
        "extra-file",
        "transient-directory",
        "symlink",
        "executable",
        "special-file",
        "duplicate-key",
        "unknown-manifest-key",
        "inline-server",
        "extra-server",
        "shell",
        "environment",
        "forwarded-environment",
        "cwd",
        "url",
        "args",
        "unsafe-version",
        "codex-metadata",
    ],
)
def test_closed_shape_oracle_rejects_mutations(tmp_path: Path, mutation: str) -> None:
    package = tmp_path / "package"
    shutil.copytree(PACKAGE, package)
    if mutation == "extra-file":
        (package / "README.md").write_text("extra")
    elif mutation == "transient-directory":
        (package / "__pycache__").mkdir()
    elif mutation == "symlink":
        (package / "mir_mcp.py").unlink()
        (package / "mir_mcp.py").symlink_to(PACKAGE / "mir_mcp.py")
    elif mutation == "executable":
        (package / "mir_mcp.py").chmod(0o755)
    elif mutation == "special-file":
        (package / "mir_mcp.py").unlink()
        os.mkfifo(package / "mir_mcp.py")
    elif mutation == "duplicate-key":
        path = package / ".claude-plugin/plugin.json"
        path.write_text(path.read_text().replace('"name":', '"name":"duplicate","name":', 1))
    elif mutation in {"unknown-manifest-key", "inline-server", "unsafe-version", "codex-metadata"}:
        path = package / (
            ".codex-plugin/plugin.json"
            if mutation == "codex-metadata"
            else ".claude-plugin/plugin.json"
        )
        value = _closed_json(path)
        if mutation == "unknown-manifest-key":
            value["skills"] = "./skills/"
        elif mutation == "inline-server":
            value["mcpServers"] = {}
        elif mutation == "unsafe-version":
            value["version"] = "../escape"
        else:
            value["interface"]["defaultPrompt"] = []
        path.write_text(json.dumps(value))
    else:
        path = package / (
            ".mcp.codex.json" if mutation == "forwarded-environment" else ".mcp.claude.json"
        )
        value = _closed_json(path)
        server = value["mcpServers"]["mir-mcp"]
        if mutation == "extra-server":
            value["mcpServers"]["other"] = server.copy()
        elif mutation == "shell":
            server["command"] = "sh"
        elif mutation == "environment":
            server["env"] = {"TOKEN": "sentinel"}
        elif mutation == "forwarded-environment":
            server["env_vars"] = ["TOKEN"]
        elif mutation == "cwd":
            server["cwd"] = "/tmp"
        elif mutation == "url":
            server["url"] = "https://example.invalid"
        else:
            server["args"].insert(0, "-c")
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        _assert_shape(package)
