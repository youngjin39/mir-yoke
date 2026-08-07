from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from mir.cli import SUBCOMMANDS
from mir.cli import bootstrap as bootstrap_cli

_SOURCE_CONFIG = {
    "schema_version": 1,
    "source": {
        "url": "https://github.com/example/mir-yoke.git",
        "ref": "refs/heads/main",
    },
    "plugins": {"mir-core": {"path": "plugins/mir-core"}},
    "profiles": {"packs": {"code_app": ["mir-core"]}},
}


def _write(path: Path, body: str = "placeholder\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _make_harness_surfaces(root: Path) -> None:
    _write(root / "CLAUDE.md")
    _write(root / "AGENTS.md")
    _write(root / ".claude" / "settings.json", '{"hooks":{"SessionStart":[]}}\n')
    _write(
        root / ".codex" / "config.toml",
        'approval_policy = "on-request"\nsandbox_mode = "workspace-write"\n',
    )
    _write(root / ".codex" / "hooks.json", "{}\n")
    _write(root / ".ai-harness" / "deny-list.yaml", "deny: []\n")
    _write(root / ".claude" / "agents" / "main-orchestrator.md")
    _write(root / ".codex" / "agents" / "main-orchestrator.toml")
    _write(root / ".claude" / "hooks" / "session-start.sh", "#!/usr/bin/env bash\n")
    _write(root / "config" / "sub-agent-policy.json", "{}\n")
    _write(
        root / "config" / "capability-sources.json",
        json.dumps(_SOURCE_CONFIG) + "\n",
    )


def _bootstrap(root: Path, *extra: str) -> int:
    return bootstrap_cli.main(
        [
            "--project-root",
            str(root),
            "--slug",
            "sample-project",
            "--skip-capability-activation",
            "--allow-incomplete",
            "--json",
            *extra,
        ]
    )


def _write_architecture_evidence(root: Path, commit: str) -> None:
    _write(root / "spec" / "STATE.md", "# Project specification state\n")
    _write(root / "spec" / "index.yaml", "version: 1\n")
    _write(root / "spec" / "graph.yaml", "nodes: []\n")
    _write(
        root / "spec" / "bootstrap-evidence.json",
        json.dumps(
            {
                "schema_version": 1,
                "sequence": ["mir-core:design", "mir-core:spec-architect"],
                "capability_commit": commit,
                "outputs": ["spec/STATE.md", "spec/index.yaml", "spec/graph.yaml"],
            }
        )
        + "\n",
    )
    _write(
        root / ".mir" / "capability-lock.json",
        json.dumps({"source": {"commit": commit}}) + "\n",
    )


def test_bootstrap_builds_required_memory_and_is_idempotent(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)

    assert _bootstrap(tmp_path) == 0
    first_stdout = json.loads(capsys.readouterr().out)
    receipt_path = tmp_path / ".mir" / "bootstrap-receipt.json"
    first_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    first_projection = (tmp_path / "docs" / "memory-map.md").read_text(encoding="utf-8")

    assert first_stdout["status"] == "incomplete"
    assert first_receipt["capabilities"]["status"] == "skipped"
    assert first_receipt["memory"]["topology"] == "per_repository_sqlite_fts5"
    assert first_receipt["memory"]["archive_fts_probe"] == "ok"
    assert first_receipt["memory"]["archives_registered"] == 3
    assert (tmp_path / "harness_a.toml").is_file()
    assert (tmp_path / ".mir" / "memory.db").is_file()

    assert _bootstrap(tmp_path) == 0
    capsys.readouterr()
    second_projection = (tmp_path / "docs" / "memory-map.md").read_text(encoding="utf-8")
    assert second_projection == first_projection
    with sqlite3.connect(tmp_path / ".mir" / "memory.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM external_archives").fetchone()[0] == 3


def test_external_storage_root_is_verified_and_recorded(tmp_path, capsys):
    project = tmp_path / "project"
    storage = tmp_path / "machine-storage"
    project.mkdir()
    _make_harness_surfaces(project)
    expected = {
        "UV_CACHE_DIR": storage / "uv" / "cache",
        "UV_PYTHON_INSTALL_DIR": storage / "uv" / "python",
        "UV_TOOL_DIR": storage / "uv" / "tools",
        "MIR_CAPABILITY_HOME": storage / "mir" / "capabilities",
    }
    for path in expected.values():
        path.mkdir(parents=True, exist_ok=True)

    storage_env = {name: str(path) for name, path in expected.items()}
    storage_env["UV_PROJECT_ENVIRONMENT"] = str(project / ".venv")
    with patch.dict(os.environ, storage_env):
        assert _bootstrap(project, "--storage-root", str(storage)) == 0

    receipt = json.loads(capsys.readouterr().out)
    assert receipt["storage"]["mode"] == "external-first"
    assert receipt["storage"]["root"] == str(storage.resolve())
    assert receipt["storage"]["same_filesystem_as_project"] is True
    assert receipt["storage"]["large_payloads"] == {
        name: str(path.resolve()) for name, path in expected.items()
    }


def test_external_storage_root_requires_wrapper_environment(tmp_path, capsys):
    project = tmp_path / "project"
    storage = tmp_path / "machine-storage"
    project.mkdir()
    storage.mkdir()
    _make_harness_surfaces(project)

    with patch.dict(
        os.environ,
        {
            "UV_CACHE_DIR": "",
            "UV_PYTHON_INSTALL_DIR": "",
            "UV_TOOL_DIR": "",
            "MIR_CAPABILITY_HOME": "",
            "UV_PROJECT_ENVIRONMENT": "",
        },
    ):
        assert _bootstrap(project, "--storage-root", str(storage)) == 2

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "incomplete"
    assert report["storage"]["mode"] == "external-first"
    assert any("UV_CACHE_DIR" in error for error in report["errors"])
    assert not (project / ".mir" / "memory.db").exists()


def test_preflight_failure_does_not_create_authored_config_or_db(tmp_path, capsys):
    _write(tmp_path / "CLAUDE.md")

    assert _bootstrap(tmp_path) == 2
    report = json.loads(capsys.readouterr().out)

    assert report["status"] == "incomplete"
    assert not (tmp_path / "harness_a.toml").exists()
    assert not (tmp_path / ".mir" / "memory.db").exists()
    assert (tmp_path / ".mir" / "bootstrap-receipt.json").is_file()


def test_invalid_existing_config_is_preserved_and_blocks_bootstrap(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    invalid = "[memory\nenabled = true\n"
    _write(tmp_path / "harness_a.toml", invalid)

    assert _bootstrap(tmp_path) == 2
    capsys.readouterr()

    assert (tmp_path / "harness_a.toml").read_text(encoding="utf-8") == invalid
    assert not (tmp_path / ".mir" / "memory.db").exists()


def test_existing_projection_text_outside_markers_is_preserved(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    _write(tmp_path / "docs" / "memory-map.md", "Authored introduction.\n")

    assert _bootstrap(tmp_path) == 0
    capsys.readouterr()

    rendered = (tmp_path / "docs" / "memory-map.md").read_text(encoding="utf-8")
    assert rendered.startswith("Authored introduction.\n")
    assert "<!-- mir:generated:start -->" in rendered
    assert "<!-- mir:generated:end -->" in rendered


def test_bootstrap_source_has_no_symlink_dependency():
    root = Path(__file__).resolve().parents[1]
    for relative in ("setup.sh", "setup.ps1", "src/mir/cli/bootstrap.py"):
        assert not (root / relative).is_symlink()


def test_public_cli_registers_bootstrap_and_capability() -> None:
    assert {"bootstrap", "capability"} <= set(SUBCOMMANDS)
    for command in ("bootstrap", "capability"):
        completed = subprocess.run(
            [sys.executable, "-m", "mir", command, "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr


def test_capability_install_requires_restart_before_ready(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    evidence = {
        "source_commit": "a" * 40,
        "selected_plugins": ["mir-core"],
        "selected_agents": ["main-orchestrator"],
    }

    with patch.object(bootstrap_cli, "_activate_capabilities", return_value=("ready", evidence)):
        assert bootstrap_cli.main(["--project-root", str(tmp_path), "--json"]) == 0
    install_receipt = json.loads(capsys.readouterr().out)
    assert install_receipt["status"] == "restart_required"
    assert install_receipt["capabilities"]["status"] == "restart_required"
    _write_architecture_evidence(tmp_path, "a" * 40)

    with patch.object(bootstrap_cli, "_finalize_capabilities", return_value=("ready", evidence)):
        assert (
            bootstrap_cli.main(
                [
                    "--project-root",
                    str(tmp_path),
                    "--finalize",
                    "--architecture-initialized",
                    "--json",
                ]
            )
            == 0
        )
    final_receipt = json.loads(capsys.readouterr().out)
    assert final_receipt["status"] == "ready"
    assert final_receipt["capabilities"]["selected_plugins"] == ["mir-core"]
    assert final_receipt["architecture_initialization"]["attested"] is True
    assert set(final_receipt["architecture_initialization"]["evidence"]["output_hashes"]) == {
        "spec/STATE.md",
        "spec/index.yaml",
        "spec/graph.yaml",
    }


def test_finalize_refuses_boolean_attestation_without_architecture_outputs(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    with patch.object(
        bootstrap_cli,
        "_activate_capabilities",
        return_value=("ready", {"source_commit": "a" * 40}),
    ):
        assert bootstrap_cli.main(["--project-root", str(tmp_path), "--json"]) == 0
    capsys.readouterr()

    with patch.object(bootstrap_cli, "_finalize_capabilities") as finalize:
        assert (
            bootstrap_cli.main(
                [
                    "--project-root",
                    str(tmp_path),
                    "--finalize",
                    "--architecture-initialized",
                    "--json",
                ]
            )
            == 1
        )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "incomplete"
    assert report["architecture_initialization"]["attested"] is False
    assert "architecture evidence is missing" in report["capabilities"]["reason"]
    finalize.assert_not_called()


def test_failed_rerun_preserves_existing_db_and_projection(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    assert _bootstrap(tmp_path) == 0
    capsys.readouterr()
    db_path = tmp_path / ".mir" / "memory.db"
    projection_path = tmp_path / "docs" / "memory-map.md"
    db_hash = sha256(db_path.read_bytes()).hexdigest()
    projection = projection_path.read_text(encoding="utf-8")

    (tmp_path / ".claude" / "settings.json").write_text("not json", encoding="utf-8")
    assert _bootstrap(tmp_path) == 1
    capsys.readouterr()

    assert sha256(db_path.read_bytes()).hexdigest() == db_hash
    assert projection_path.read_text(encoding="utf-8") == projection


def test_sync_failure_after_preflight_preserves_live_db(tmp_path, capsys):
    _make_harness_surfaces(tmp_path)
    assert _bootstrap(tmp_path) == 0
    capsys.readouterr()
    db_path = tmp_path / ".mir" / "memory.db"
    projection_path = tmp_path / "docs" / "memory-map.md"
    db_hash = sha256(db_path.read_bytes()).hexdigest()
    projection = projection_path.read_text(encoding="utf-8")

    with patch.object(bootstrap_cli.context_cli, "main", return_value=1):
        assert _bootstrap(tmp_path) == 1
    capsys.readouterr()

    assert sha256(db_path.read_bytes()).hexdigest() == db_hash
    assert projection_path.read_text(encoding="utf-8") == projection
