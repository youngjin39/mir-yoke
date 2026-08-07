from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import jsonschema

from mir.cli import SUBCOMMANDS
from mir.cli import bootstrap_adoption as adoption_cli

SOURCE_COMMIT = "a" * 40
SURFACE_KEYS = (
    "bootstrap_start_gate",
    "project_profile",
    "identity_finalize",
    "managed_python_launcher",
    "content_onboarding",
    "memory_acceptance",
    "phase2_spec",
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _write_profile(
    root: Path,
    *,
    repository_type: str = "code_app",
    overlay_archetype: str = "app_product_flutter",
) -> None:
    _write(
        root / ".mir" / "repo-profile.toml",
        f"""[repo]
slug = "sample-project"
repository_type = "{repository_type}"
overlay_archetype = "{overlay_archetype}"
purpose = "Maintain a mature project with verified repository evidence."
technology_stack = ["python", "sqlite"]

[execution]
non_code_profile = "deliberately-unrelated-value"
""",
    )


def _write_gate_and_launcher(root: Path) -> None:
    _write(
        root / ".claude/hooks/_lib/bootstrap-gate.sh",
        "#!/usr/bin/env bash\n"
        "mir_bootstrap_gate_state() { return 0; }\n"
        "mir_bootstrap_gate_enforce() { return 0; }\n",
    )
    _write(
        root / ".claude/hooks/_lib/run-python.sh",
        "#!/usr/bin/env bash\n"
        'if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then '
        'exec "$PROJECT_DIR/.venv/bin/python" "$@"; fi\n'
        'if [ -x "$PROJECT_DIR/.venv/Scripts/python.exe" ]; then '
        'exec "$PROJECT_DIR/.venv/Scripts/python.exe" "$@"; fi\n'
        'exec uv run --project "$PROJECT_DIR" python "$@"\n',
    )
    _write(
        root / ".claude/hooks/session-start.sh",
        "#!/usr/bin/env bash\n"
        "_MIR_PYTHON_LAUNCHER=.claude/hooks/_lib/run-python.sh\n"
        ". .claude/hooks/_lib/bootstrap-gate.sh\n"
        "mir_bootstrap_gate_state .\n",
    )
    _write(
        root / ".claude/hooks/pre-tool-use.sh",
        "#!/usr/bin/env bash\n"
        "_MIR_PYTHON_LAUNCHER=.claude/hooks/_lib/run-python.sh\n"
        ". .claude/hooks/_lib/bootstrap-gate.sh\n"
        'mir_bootstrap_gate_enforce "$INPUT" .\n',
    )
    hooks = {
        "hooks": {
            "SessionStart": [{"hooks": [{"command": "bash .claude/hooks/session-start.sh"}]}],
            "PreToolUse": [{"hooks": [{"command": "bash .claude/hooks/pre-tool-use.sh"}]}],
        }
    }
    _write(root / ".claude/settings.json", json.dumps(hooks))
    _write(root / ".codex/hooks.json", json.dumps(hooks))


def _write_memory(root: Path) -> None:
    _write(root / "docs/memory.md", "MatureProjectEvidence is searchable here.\n")
    _write(
        root / "harness_a.toml",
        '[memory]\nenabled = true\nrequired = true\nbackend = "sqlite_fts5"\n'
        'db_path = ".mir/memory.db"\n',
    )
    db_path = root / ".mir/memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE external_archives (
          id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, root_path TEXT NOT NULL);
        CREATE TABLE external_documents (
          id INTEGER PRIMARY KEY, archive_id INTEGER NOT NULL, relative_path TEXT NOT NULL);
        CREATE TABLE external_chunks (id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL);
        CREATE VIRTUAL TABLE external_chunks_fts USING fts5(content);
        INSERT INTO external_archives VALUES (1, 'sample-docs', 'docs');
        INSERT INTO external_documents VALUES (1, 1, 'memory.md');
        INSERT INTO external_chunks VALUES (1, 1);
        INSERT INTO external_chunks_fts(rowid, content)
          VALUES (1, 'MatureProjectEvidence is searchable here.');
        """
    )
    connection.commit()
    connection.close()


def _manifest() -> dict[str, object]:
    surfaces: dict[str, dict[str, object]] = {
        key: {"disposition": "repository_owned", "evidence_paths": ["CLAUDE.md"]}
        for key in SURFACE_KEYS
    }
    surfaces["bootstrap_start_gate"] = {
        "disposition": "applied",
        "evidence_paths": [
            ".claude/hooks/_lib/bootstrap-gate.sh",
            ".claude/hooks/session-start.sh",
            ".claude/hooks/pre-tool-use.sh",
            ".claude/settings.json",
            ".codex/hooks.json",
        ],
    }
    surfaces["project_profile"] = {
        "disposition": "repository_owned",
        "evidence_paths": [".mir/repo-profile.toml"],
    }
    surfaces["identity_finalize"] = {
        "disposition": "repository_owned",
        "evidence_paths": [".mir/repo-profile.toml"],
    }
    surfaces["managed_python_launcher"] = {
        "disposition": "applied",
        "evidence_paths": [
            ".claude/hooks/_lib/run-python.sh",
            ".claude/hooks/session-start.sh",
            ".claude/hooks/pre-tool-use.sh",
        ],
    }
    surfaces["content_onboarding"] = {
        "disposition": "not_applicable",
        "evidence_paths": [],
        "reason": "The selected code profile does not own a content archive workspace.",
    }
    surfaces["memory_acceptance"] = {
        "disposition": "repository_owned",
        "evidence_paths": ["harness_a.toml", "docs/memory.md"],
        "queries": [{
            "archive_slug": "sample-docs",
            "query": "MatureProjectEvidence",
            "expected_path": "memory.md",
        }],
    }
    surfaces["phase2_spec"] = {
        "disposition": "repository_owned",
        "evidence_paths": [
            "CLAUDE.md",
            "harness_a.toml",
            "docs/memory.md",
            "spec/meta.yaml",
            "spec/gaps.yaml",
            "spec/bootstrap-adoption-review.yaml",
        ],
        "coverage": {
            "l1": {"total": 2, "filled": 2, "derived": 0, "na": 0, "tbd": 0},
            "l2": {"total": 3, "filled": 2, "derived": 1, "na": 0, "tbd": 0},
            "l3": {"total": 4, "filled": 3, "derived": 1, "na": 0, "tbd": 0},
            "l4": {"total": 5, "filled": 4, "derived": 0, "na": 1, "tbd": 0},
        },
        "ai_ready": {"ready": 1, "incomplete": 0, "blocked": 0},
        "open_gaps": 0,
        "full_review": {
            "project_structure": "pass",
            "memory": "pass",
            "discoverability": "pass",
            "requirements": "pass",
            "organization": "pass",
        },
        "native_evidence": {
            "format": "mir_spec_yaml_v1",
            "meta_path": "spec/meta.yaml",
            "coverage_key": "coverage",
            "gaps_path": "spec/gaps.yaml",
            "review_path": "spec/bootstrap-adoption-review.yaml",
        },
    }
    return {
        "schema_version": 1,
        "project_slug": "sample-project",
        "repository_archetype": "app_product_flutter",
        "profile": "code_app",
        "mir_yoke_source_commit": SOURCE_COMMIT,
        "surfaces": surfaces,
    }


def _ready_project(root: Path) -> dict[str, object]:
    _write(root / "CLAUDE.md", "# Repository contract\n\nPreserve authored behavior.\n")
    _write(
        root / "spec/meta.yaml",
        """coverage:
  l1: {total: 2, filled: 2, derived: 0, na: 0, tbd: 0}
  l2: {total: 3, filled: 2, derived: 1, na: 0, tbd: 0}
  l3: {total: 4, filled: 3, derived: 1, na: 0, tbd: 0}
  l4: {total: 5, filled: 4, derived: 0, na: 1, tbd: 0}
ai_ready: {ready: 1, incomplete: 0, blocked: 0}
""",
    )
    _write(root / "spec/gaps.yaml", "gaps: []\n")
    _write(
        root / "spec/bootstrap-adoption-review.yaml",
        """reviews:
  project_structure:
    status: pass
    evidence_paths: [spec/meta.yaml]
    verification: Parsed four-layer structure matches the adoption manifest.
  memory:
    status: pass
    evidence_paths: [harness_a.toml, docs/memory.md]
    verification: Live project memory query returns the expected archive path.
  discoverability:
    status: pass
    evidence_paths: [CLAUDE.md]
    verification: Repository instructions expose the maintained project contract.
  requirements:
    status: pass
    evidence_paths: [spec/meta.yaml]
    verification: Native coverage has no unresolved requirement slots.
  organization:
    status: pass
    evidence_paths: [spec/gaps.yaml]
    verification: Native gaps evidence contains no open entries.
""",
    )
    _write_profile(root)
    _write_gate_and_launcher(root)
    _write_memory(root)
    manifest = _manifest()
    _write(root / "config/bootstrap-adoption.json", json.dumps(manifest, indent=2))
    return manifest


def _run(root: Path, *args: str) -> int:
    return adoption_cli.main(["--project-root", str(root), "--json", *args])


def test_bootstrap_adoption_read_only_should_not_write_receipt_or_database(tmp_path, capsys):
    _ready_project(tmp_path)
    db_path = tmp_path / ".mir/memory.db"
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    mir_files_before = sorted(path.name for path in (tmp_path / ".mir").iterdir())

    assert _run(tmp_path) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["status"] == "ready"
    assert report["apply"] is False
    assert report["receipt_written"] is False
    assert report["memory_acceptance"]["queries"][0]["status"] == "pass"
    assert not (tmp_path / ".mir/bootstrap-receipt.json").exists()
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before
    assert sorted(path.name for path in (tmp_path / ".mir").iterdir()) == mir_files_before


def test_bootstrap_adoption_profile_should_map_repo_identity_not_execution_field(
    tmp_path, capsys
):
    _ready_project(tmp_path)

    assert _run(tmp_path) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["profile"]["mapped_profile"] == "code_app"
    assert report["profile"]["repository_type"] == "code_app"
    assert report["profile"]["overlay_archetype"] == "app_product_flutter"


def test_bootstrap_adoption_should_support_meta_harness_mapping(tmp_path, capsys):
    manifest = _ready_project(tmp_path)
    _write_profile(
        tmp_path,
        repository_type="meta_harness",
        overlay_archetype="meta_harness",
    )
    manifest["repository_archetype"] = "meta_harness"
    manifest["profile"] = "meta_harness"
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["profile"]["mapped_profile"] == "meta_harness"


def test_content_workspace_should_use_repository_type_over_hybrid_overlay(
    tmp_path, capsys
):
    manifest = _ready_project(tmp_path)
    _write_profile(
        tmp_path,
        repository_type="content_workspace",
        overlay_archetype="hybrid_pipeline",
    )
    _write(tmp_path / "records/history.md", "ArchivedProjectHistory is retained.\n")
    onboarding = {
        "schema_version": 1,
        "profile": "content_workspace",
        "purpose": "Maintain the repository's authored records.",
        "technology_stack": ["markdown"],
        "archives": [
            {
                "classification": "history",
                "path": "records",
                "kind": "directory",
                "formats": ["md"],
                "indexed_formats": ["md"],
                "document_count": 1,
                "indexed_document_count": 1,
            }
        ],
        "scan": {
            "candidates": [{"path": "records"}],
            "unclassified": [],
        },
    }
    _write(tmp_path / "config/content-onboarding.json", json.dumps(onboarding))
    manifest["repository_archetype"] = "hybrid_pipeline"
    manifest["profile"] = "content_workspace"
    manifest["surfaces"]["content_onboarding"] = {
        "disposition": "repository_owned",
        "evidence_paths": ["config/content-onboarding.json", "records/history.md"],
    }
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["profile"]["mapped_profile"] == "content_workspace"
    assert report["content_onboarding"]["status"] == "pass"


def test_bootstrap_adoption_should_reject_profile_mapping_conflict(tmp_path, capsys):
    manifest = _ready_project(tmp_path)
    manifest["profile"] = "hybrid_pipeline"
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path) == 2
    report = json.loads(capsys.readouterr().out)
    assert any("maps to profile 'code_app'" in error for error in report["errors"])
    assert not (tmp_path / ".mir/bootstrap-receipt.json").exists()


def test_bootstrap_adoption_native_phase2_should_not_equate_ai_ready_to_l1(
    tmp_path, capsys
):
    _ready_project(tmp_path)
    assert _run(tmp_path) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["phase2"]["status"] == "pass"
    assert report["phase2"]["coverage"]["l1"]["total"] == 2
    assert report["phase2"]["ai_ready"]["ready"] == 1


def test_bootstrap_adoption_documented_exceptions_should_remain_visible_in_ready_receipt(
    tmp_path, capsys
):
    manifest = _ready_project(tmp_path)
    manifest["surfaces"]["memory_acceptance"] = {
        "disposition": "exception",
        "evidence_paths": ["docs/memory.md"],
        "reason": "The legacy index is being preserved during a bounded migration.",
        "blockers": ["The native archive adapter cannot expose its index through SQLite FTS5."],
    }
    manifest["surfaces"]["phase2_spec"] = {
        "disposition": "exception",
        "evidence_paths": ["spec/native-evidence.md"],
        "reason": "The mature repository retains its accepted native specification system.",
        "blockers": ["Automated four-layer export is not available from the native format."],
    }
    _write(
        tmp_path / "spec/native-evidence.md",
        "# Native specification evidence\n\nThe accepted native format remains in force.\n",
    )
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path, "--apply") == 0
    stdout = json.loads(capsys.readouterr().out)
    receipt = json.loads(
        (tmp_path / ".mir/bootstrap-receipt.json").read_text(encoding="utf-8")
    )
    assert stdout["receipt_written"] is True
    assert receipt["status"] == "ready"
    assert receipt["phase2"]["status"] == "exception"
    assert {row["surface"] for row in receipt["exceptions"]} == {
        "memory_acceptance",
        "phase2_spec",
    }


def test_bootstrap_adoption_should_reject_missing_or_placeholder_phase2_evidence(
    tmp_path, capsys
):
    manifest = _ready_project(tmp_path)
    manifest["surfaces"]["phase2_spec"]["evidence_paths"].append("spec/missing.md")
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path) == 2
    missing = json.loads(capsys.readouterr().out)
    assert any("evidence path is missing" in error for error in missing["errors"])

    _write(tmp_path / "spec/missing.md", "TBD\n")
    assert _run(tmp_path) == 2
    placeholder = json.loads(capsys.readouterr().out)
    assert any("placeholder" in error for error in placeholder["errors"])


def test_bootstrap_adoption_should_accept_resolved_tbd_count_in_phase2_evidence(
    tmp_path, capsys
):
    manifest = _ready_project(tmp_path)
    _write(tmp_path / "spec/evidence.yaml", "tbd: 0\n")
    manifest["surfaces"]["phase2_spec"]["evidence_paths"].append(
        "spec/evidence.yaml"
    )
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"


def test_bootstrap_adoption_should_reject_incomplete_exception_contract(tmp_path, capsys):
    manifest = _ready_project(tmp_path)
    manifest["surfaces"]["memory_acceptance"] = {
        "disposition": "exception",
        "evidence_paths": ["docs/memory.md"],
        "reason": "Preserve the current native index.",
        "blockers": [],
    }
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path) == 2
    report = json.loads(capsys.readouterr().out)
    assert any("requires non-empty blockers" in error for error in report["errors"])


def test_bootstrap_adoption_should_reject_unknown_manifest_fields(tmp_path, capsys):
    manifest = _ready_project(tmp_path)
    manifest["pending"] = True
    manifest["surfaces"]["identity_finalize"]["attestation_only"] = True
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path) == 2
    report = json.loads(capsys.readouterr().out)
    assert any("manifest has unknown fields" in error for error in report["errors"])
    assert any(
        "surface 'identity_finalize' has unknown fields" in error
        for error in report["errors"]
    )


def test_bootstrap_adoption_should_reject_unclassified_live_content(tmp_path, capsys):
    manifest = _ready_project(tmp_path)
    _write_profile(
        tmp_path,
        repository_type="content_workspace",
        overlay_archetype="ontology_content",
    )
    _write(tmp_path / "records/history.md", "ArchivedProjectHistory is retained.\n")
    _write(tmp_path / "uncatalogued/notes.md", "UncataloguedEvidence remains visible.\n")
    onboarding = {
        "schema_version": 1,
        "profile": "content_workspace",
        "archives": [{"classification": "history", "path": "records"}],
        "scan": {"candidates": [{"path": "records"}], "unclassified": []},
    }
    _write(tmp_path / "config/content-onboarding.json", json.dumps(onboarding))
    manifest["repository_archetype"] = "ontology_content"
    manifest["profile"] = "content_workspace"
    manifest["surfaces"]["content_onboarding"] = {
        "disposition": "applied",
        "evidence_paths": ["config/content-onboarding.json", "records/history.md"],
    }
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path) == 2
    report = json.loads(capsys.readouterr().out)
    assert any("unclassified candidates" in error for error in report["errors"])


def test_bootstrap_adoption_should_reject_incomplete_native_coverage(tmp_path, capsys):
    manifest = _ready_project(tmp_path)
    phase2 = manifest["surfaces"]["phase2_spec"]
    phase2["coverage"]["l3"] = {
        "total": 2,
        "filled": 1,
        "derived": 0,
        "na": 0,
        "tbd": 1,
    }
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path) == 2
    report = json.loads(capsys.readouterr().out)
    assert any("unresolved TBD" in error for error in report["errors"])


def test_bootstrap_adoption_should_reject_manifest_counts_that_drift_from_native_spec(
    tmp_path, capsys
):
    manifest = _ready_project(tmp_path)
    manifest["surfaces"]["phase2_spec"]["coverage"]["l3"] = {
        "total": 4,
        "filled": 3,
        "derived": 0,
        "na": 1,
        "tbd": 0,
    }
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path) == 2
    report = json.loads(capsys.readouterr().out)
    assert any("does not match native evidence" in error for error in report["errors"])


def test_bootstrap_adoption_should_reject_unsubstantiated_native_review(
    tmp_path, capsys
):
    _ready_project(tmp_path)
    _write(
        tmp_path / "spec/bootstrap-adoption-review.yaml",
        """reviews:
  project_structure: pass
  memory: pass
  discoverability: pass
  requirements: pass
  organization: pass
""",
    )

    assert _run(tmp_path) == 2
    report = json.loads(capsys.readouterr().out)
    assert any("native review dimension" in error for error in report["errors"])


def test_bootstrap_adoption_should_verify_gate_and_managed_launcher_wiring(tmp_path, capsys):
    _ready_project(tmp_path)
    _write(
        tmp_path / ".claude/hooks/session-start.sh",
        "#!/usr/bin/env bash\npython3 scripts/build_session_upfront_context.py\n",
    )

    assert _run(tmp_path) == 2
    report = json.loads(capsys.readouterr().out)
    assert any("bootstrap gate" in error for error in report["errors"])
    assert any("managed Python launcher" in error for error in report["errors"])


def test_bootstrap_adoption_apply_should_write_hash_bound_atomic_ready_receipt(
    tmp_path, capsys
):
    _ready_project(tmp_path)
    manifest_path = tmp_path / "config/bootstrap-adoption.json"
    expected_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    assert _run(tmp_path, "--apply") == 0
    report = json.loads(capsys.readouterr().out)
    receipt_path = tmp_path / ".mir/bootstrap-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert report["receipt_written"] is True
    assert receipt["schema_version"] == 1
    assert receipt["status"] == "ready"
    assert receipt["mode"] == "existing_repository_adoption"
    assert receipt["manifest"]["sha256"] == expected_hash
    assert receipt["source"]["mir_yoke_commit"] == SOURCE_COMMIT
    assert set(receipt["surfaces"]) == set(SURFACE_KEYS)
    assert receipt["memory_acceptance"]["queries"][0]["expected_path"] == "memory.md"
    assert not list(receipt_path.parent.glob(".bootstrap-receipt.json.*"))


def test_bootstrap_adoption_failure_should_preserve_existing_receipt(tmp_path, capsys):
    manifest = _ready_project(tmp_path)
    receipt_path = tmp_path / ".mir/bootstrap-receipt.json"
    original = b'{"schema_version":1,"status":"ready","marker":"preserve"}\n'
    receipt_path.write_bytes(original)
    del manifest["surfaces"]["phase2_spec"]
    _write(tmp_path / "config/bootstrap-adoption.json", json.dumps(manifest))

    assert _run(tmp_path, "--apply") == 2
    capsys.readouterr()
    assert receipt_path.read_bytes() == original


def test_public_cli_should_register_bootstrap_adoption() -> None:
    assert "bootstrap-adoption" in SUBCOMMANDS


def test_bootstrap_adoption_main_should_read_sys_argv_when_omitted(
    tmp_path, capsys, monkeypatch
) -> None:
    _ready_project(tmp_path)
    monkeypatch.setattr(
        adoption_cli.sys,
        "argv",
        [
            "mir bootstrap-adoption",
            "--project-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert adoption_cli.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"


def test_bootstrap_adoption_schema_should_validate_the_portable_manifest() -> None:
    root = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (root / "docs/templates/_schema/bootstrap-adoption.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_manifest(), schema)
