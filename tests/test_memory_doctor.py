from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

from mir.cli import context as context_cli
from mir.cli import memory as memory_cli
from mir.core.engine.memory import distill, store


def _write_memory_config(root: Path) -> None:
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "memory.md").write_text(
        "portable memory archive doctorprobecontent\n", encoding="utf-8"
    )
    (root / "harness_a.toml").write_text(
        """[memory]
enabled = true
required = true
backend = "sqlite_fts5"
db_path = ".mir/memory.db"
vector_mode = "off"

[memory.embedding]
enabled = false
required = false

[[memory.external_archives]]
slug = "test-docs"
root = "docs"
mode = "indexed"
glob_include = ["**/*.md"]
""",
        encoding="utf-8",
    )


def _ready_project(root: Path) -> Path:
    _write_memory_config(root)
    db_path = root / ".mir" / "memory.db"
    connection = store.connect(db_path)
    try:
        store.apply_migrations(connection.conn)
    finally:
        connection.conn.close()
    assert context_cli.main(["sync", "--db", str(db_path)]) == 0
    return db_path


def test_doctor_reports_ready_fts_baseline(tmp_path, capsys):
    _ready_project(tmp_path)
    capsys.readouterr()

    assert memory_cli.main(["doctor", "--project-root", str(tmp_path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["status"] == "ready"
    assert report["memory"]["integrity"] == "ok"
    assert report["memory"]["round_trip"] == "ok"
    assert report["memory"]["archive_fts_probe"] == "ok"
    assert report["memory"]["documents_indexed"] >= 1
    assert report["memory"]["chunks_indexed"] >= 1
    assert report["vector"]["mode"] == "off"
    assert not (tmp_path / ".mir" / "bootstrap-receipt.json").exists()


def test_doctor_does_not_create_a_missing_database(tmp_path, capsys):
    _write_memory_config(tmp_path)
    db_path = tmp_path / ".mir" / "memory.db"

    assert memory_cli.main(["doctor", "--project-root", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)

    assert report["status"] == "not_ready"
    assert not db_path.exists()


def test_doctor_returns_two_for_malformed_config(tmp_path, capsys):
    (tmp_path / "harness_a.toml").write_text("[memory\nenabled = true\n", encoding="utf-8")

    assert memory_cli.main(["doctor", "--project-root", str(tmp_path), "--json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert "harness_a.toml" in report["errors"][0]


def test_doctor_rejects_overlapping_archives(tmp_path, capsys):
    (tmp_path / "harness_a.toml").write_text(
        """[memory]
enabled = true
required = true
backend = "sqlite_fts5"
vector_mode = "off"

[[memory.external_archives]]
slug = "all-docs"
root = "docs"

[[memory.external_archives]]
slug = "nested-docs"
root = "docs/decisions"
""",
        encoding="utf-8",
    )

    assert memory_cli.main(["doctor", "--project-root", str(tmp_path), "--json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert "must not overlap" in report["errors"][0]


def test_memory_gc_is_dry_run_unless_apply_is_explicit(tmp_path, capsys):
    db_path = _ready_project(tmp_path)
    capsys.readouterr()
    connection = store.connect(db_path)
    try:
        fact_id = distill.insert_triple(
            connection.conn,
            distill.Triple(
                subject_slug="expired-fact",
                predicate="lesson",
                object_literal="old memory",
            ),
        )
        connection.conn.execute("UPDATE facts SET valid_to = '2000-01-01' WHERE id = ?", (fact_id,))
        connection.conn.commit()
    finally:
        connection.conn.close()

    assert memory_cli.main(["gc", "--db", str(db_path), "--json"]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run == {"applied": False, "expired": 1, "kept_active": 1}

    assert memory_cli.main(["gc", "--apply", "--db", str(db_path), "--json"]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["applied"] is True
    assert applied["expired"] == 1


def test_db_path_must_remain_inside_project_mir_directory(tmp_path, capsys):
    outside = tmp_path.parent / "outside-memory.db"
    (tmp_path / "harness_a.toml").write_text(
        f'''[memory]
enabled = true
required = true
backend = "sqlite_fts5"
db_path = "{outside}"
vector_mode = "off"
''',
        encoding="utf-8",
    )

    assert memory_cli.main(["doctor", "--project-root", str(tmp_path), "--json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert "project-relative" in report["errors"][0]
    assert not outside.exists()


def test_archive_symlink_escape_is_rejected(tmp_path, capsys):
    _write_memory_config(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("secret symlink content", encoding="utf-8")
    os.symlink(outside, tmp_path / "docs" / "escape.md")
    db_path = tmp_path / ".mir" / "memory.db"
    connection = store.connect(db_path)
    try:
        store.apply_migrations(connection.conn)
    finally:
        connection.conn.close()

    assert context_cli.main(["sync", "--db", str(db_path)]) == 1
    sync_output = capsys.readouterr().out
    assert "symbolic links are not indexed" in sync_output


def test_required_vector_mode_blocks_fts_only_index(tmp_path, capsys):
    _ready_project(tmp_path)
    capsys.readouterr()
    config_path = tmp_path / "harness_a.toml"
    config = config_path.read_text(encoding="utf-8")
    config = config.replace('vector_mode = "off"', 'vector_mode = "required"')
    config = config.replace("enabled = false\nrequired = false", "enabled = true\nrequired = true")
    config_path.write_text(config, encoding="utf-8")

    with patch(
        "mir.core.engine.memory.backends.omlx_http.from_config",
        side_effect=RuntimeError("embedding endpoint unavailable"),
    ):
        assert memory_cli.main(["doctor", "--project-root", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["vector"]["documents_missing_vectors"] >= 1
    assert any("no vector index evidence" in error for error in report["errors"])


def test_optional_embedding_failure_retries_fts_only_sync(tmp_path, capsys):
    _write_memory_config(tmp_path)
    config_path = tmp_path / "harness_a.toml"
    config = config_path.read_text(encoding="utf-8")
    config = config.replace('vector_mode = "off"', 'vector_mode = "optional"')
    config = config.replace("enabled = false", "enabled = true", 1)
    config_path.write_text(config, encoding="utf-8")
    db_path = tmp_path / ".mir" / "memory.db"
    connection = store.connect(db_path)
    try:
        store.apply_migrations(connection.conn)
    finally:
        connection.conn.close()

    def unavailable(_texts):
        raise RuntimeError("optional endpoint unavailable")

    with patch.object(context_cli, "_build_embed_fn", return_value=unavailable):
        assert context_cli.main(["sync", "--db", str(db_path)]) == 0
    output = capsys.readouterr().out
    assert "retrying FTS-only" in output
    with sqlite3.connect(db_path) as raw:
        assert raw.execute("SELECT COUNT(*) FROM external_chunks").fetchone()[0] >= 1
