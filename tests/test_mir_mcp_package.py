"""ADR-91 exact package shape; this test helper is not admission authority."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "plugins/mir-mcp"
FILES = {
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".mcp.claude.json",
    ".mcp.codex.json",
    "mir_mcp.py",
    "ontology/scripts/ontology_check.py",
    "ontology/references/common-contract.json",
    "shared/relations_query.py",
}


def _closed_json(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, f"duplicate key: {key}"
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=unique)
    assert isinstance(value, dict)
    return value


def _assert_shape(package: Path) -> None:
    """Independent closed-shape oracle, deliberately outside production validators."""
    assert package.is_dir()
    directories = {
        str(parent) for file in FILES for parent in Path(file).parents if str(parent) != "."
    }
    found = set()
    for path in package.rglob("*"):
        relative = path.relative_to(package).as_posix()
        mode = path.lstat().st_mode
        assert not stat.S_ISLNK(mode)
        if stat.S_ISDIR(mode):
            assert relative in directories
        else:
            assert stat.S_ISREG(mode)
            assert not mode & 0o111
            found.add(relative)
    assert found == FILES
    manifests = []
    for runtime, variable in (("claude", "CLAUDE_PLUGIN_ROOT"), ("codex", "PLUGIN_ROOT")):
        manifest = _closed_json(package / f".{runtime}-plugin/plugin.json")
        keys = {"name", "version", "description", "mcpServers"}
        if runtime == "codex":
            keys |= {"author", "interface"}
            assert set(manifest["author"]) == {"name"}
            assert set(manifest["interface"]) == {"displayName", "shortDescription"}
        assert set(manifest) == keys
        assert manifest["name"] == "mir-mcp"
        assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", manifest["version"])
        assert isinstance(manifest["description"], str) and manifest["description"]
        assert manifest["mcpServers"] == f"./.mcp.{runtime}.json"
        declaration = _closed_json(package / f".mcp.{runtime}.json")
        server = {"command": "python3", "args": ["-I", "-B", "-u", f"${{{variable}}}/mir_mcp.py"]}
        server.update({"type": "stdio"} if runtime == "claude" else {"env_vars": []})
        assert declaration == {"mcpServers": {"mir-mcp": server}}
        manifests.append(manifest)
    assert manifests[0]["version"] == manifests[1]["version"]
    assert manifests[0]["description"] == manifests[1]["description"]


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
    with pytest.raises(AssertionError):
        _assert_shape(package)
