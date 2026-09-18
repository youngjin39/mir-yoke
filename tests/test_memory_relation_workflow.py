"""Real memory-gateway to read-only SRR lifecycle contracts."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from mir.cli.memory import main as memory_main
from mir.cli.relations import main as relations_main
from mir.core.engine.memory import store


def _fixture(root: Path) -> tuple[Path, Path]:
    (root / ".mir").mkdir()
    db = root / ".mir/memory.db"
    connection = store.connect(db)
    store.apply_migrations(connection.conn)
    connection.conn.close()
    (root / "src").mkdir()
    (root / "src/checkout.py").write_text("VALUE = 1\n")
    (root / "tests").mkdir()
    (root / "tests/test_checkout.py").write_text("def test_checkout(): pass\n")
    (root / "docs/decisions").mkdir(parents=True)
    source = root / "docs/decisions/adr-checkout.md"
    _declare(source, "MOD-PAYMENT")
    return db, source


def _declare(source: Path, dependency: str | None) -> None:
    edges = [
        "[REQ-CHECKOUT, realized_by, MOD-CHECKOUT]",
        "[MOD-CHECKOUT, implemented_in, src/checkout.py]",
        "[REQ-CHECKOUT, verified_by, tests/test_checkout.py]",
    ]
    if dependency:
        edges.append(f"[MOD-CHECKOUT, depends_on, {dependency}]")
    source.write_text(
        "---\ntitle: Checkout structure\nstatus: accepted\nmemory_relations:\n"
        + "".join(f"  - {edge}\n" for edge in edges)
        + "---\nMaintained declaration.\n"
    )


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _dependencies(root: Path, capsys) -> set[str]:
    assert (
        relations_main(
            [
                "query",
                "MOD-CHECKOUT",
                "--purpose",
                "dependencies",
                "--memory",
                "--root",
                str(root),
                "--depth",
                "1",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    return {edge["target"] for edge in payload["edges"]}


def test_should_read_ingested_relation_bundle_without_mutating_files(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db, source = _fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert memory_main(["ingest-md", str(source), "--db", str(db)]) == 0
    capsys.readouterr()
    before = _snapshot(tmp_path)
    assert (
        relations_main(
            [
                "bundle",
                "REQ-CHECKOUT",
                "--memory",
                "--root",
                str(tmp_path),
                "--purpose",
                "implementation",
                "--purpose",
                "verification",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert {edge["target"] for edge in payload["edges"]} >= {
        "MOD-CHECKOUT",
        "src/checkout.py",
        "tests/test_checkout.py",
    }
    assert _snapshot(tmp_path) == before
    with sqlite3.connect(db) as connection:
        count = connection.execute(
            "SELECT count(*) FROM facts f JOIN provenance p ON p.fact_id=f.id "
            "WHERE f.object_entity_id IS NOT NULL AND p.strength='stated'"
        ).fetchone()[0]
        assert count == 4


def test_should_replace_and_restore_declared_dependencies_through_memory_gateway(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db, source = _fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    for dependency in ("MOD-PAYMENT", "MOD-TOKEN", "MOD-PAYMENT"):
        _declare(source, dependency)
        assert memory_main(["ingest-md", str(source), "--db", str(db)]) == 0
        capsys.readouterr()
        assert _dependencies(tmp_path, capsys) == {dependency}
        assert (
            relations_main(
                [
                    "bundle",
                    "REQ-CHECKOUT",
                    "--memory",
                    "--root",
                    str(tmp_path),
                    "--purpose",
                    "implementation",
                    "--purpose",
                    "verification",
                    "--json",
                ]
            )
            == 0
        )
        stable = json.loads(capsys.readouterr().out)
        assert {edge["target"] for edge in stable["edges"]} >= {
            "MOD-CHECKOUT",
            "src/checkout.py",
            "tests/test_checkout.py",
        }
    _declare(source, None)
    assert memory_main(["ingest-md", str(source), "--db", str(db)]) == 0
    capsys.readouterr()
    assert _dependencies(tmp_path, capsys) == set()
    with sqlite3.connect(db) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM facts WHERE predicate='depends_on' AND status='superseded'"
            ).fetchone()[0]
            >= 3
        )


def test_should_reject_bad_declaration_without_partial_ingest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db, source = _fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert memory_main(["ingest-md", str(source), "--db", str(db)]) == 0
    capsys.readouterr()
    with sqlite3.connect(db) as connection:
        before = tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("facts", "provenance", "content_items")
        )
    source.write_text("---\ntitle: Invalid\nmemory_relations:\n  - [A, guesses, B]\n---\n")
    assert memory_main(["ingest-md", str(source), "--db", str(db)]) == 2
    capsys.readouterr()
    with sqlite3.connect(db) as connection:
        after = tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("facts", "provenance", "content_items")
        )
    assert after == before


def test_should_reingest_unchanged_relations_after_copying_repository_root(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    first = tmp_path / "original"
    first.mkdir()
    db, source = _fixture(first)
    monkeypatch.chdir(first)
    assert memory_main(["ingest-md", str(source), "--db", str(db)]) == 0
    capsys.readouterr()
    second = tmp_path / "copied"
    shutil.copytree(first, second)
    monkeypatch.chdir(second)
    assert (
        memory_main(
            [
                "ingest-md",
                str(second / "docs/decisions/adr-checkout.md"),
                "--db",
                str(second / ".mir/memory.db"),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert _dependencies(second, capsys) == {"MOD-PAYMENT"}


def test_should_reject_oversized_relation_source_without_mutation(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db, source = _fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    with sqlite3.connect(db) as connection:
        before = connection.execute("SELECT count(*) FROM content_items").fetchone()[0]
    source.write_text(source.read_text().replace("Checkout structure", "x" * (1024 * 1024)))
    assert memory_main(["ingest-md", str(source), "--db", str(db)]) == 2
    capsys.readouterr()
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT count(*) FROM content_items").fetchone()[0] == before


@pytest.mark.parametrize("operation", ["revision", "deletion"])
def test_should_rollback_relation_changes_when_audit_cannot_be_recorded(
    tmp_path: Path,
    monkeypatch,
    capsys,
    operation: str,
) -> None:
    db, source = _fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert memory_main(["ingest-md", str(source), "--db", str(db)]) == 0
    capsys.readouterr()
    with sqlite3.connect(db) as connection:
        before_facts = connection.execute("SELECT * FROM facts ORDER BY id").fetchall()
        before_content = connection.execute("SELECT count(*) FROM content_items").fetchone()[0]
        before_provenance = connection.execute("SELECT count(*) FROM provenance").fetchone()[0]
        connection.executescript(
            "CREATE TRIGGER reject_relation_audit BEFORE INSERT ON audit_log "
            "BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END;"
        )
    if operation == "revision":
        _declare(source, "MOD-TOKEN")
        command = ["ingest-md", str(source), "--db", str(db)]
    else:
        source.unlink()
        command = ["reconcile-missing", "--project-root", str(tmp_path), "--db", str(db)]
    with pytest.raises(sqlite3.DatabaseError, match="audit unavailable"):
        memory_main(command)
    capsys.readouterr()
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT * FROM facts ORDER BY id").fetchall() == before_facts
        assert (
            connection.execute("SELECT count(*) FROM content_items").fetchone()[0] == before_content
        )
        assert (
            connection.execute("SELECT count(*) FROM provenance").fetchone()[0] == before_provenance
        )
