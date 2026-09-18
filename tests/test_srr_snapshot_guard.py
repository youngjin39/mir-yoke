from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from mir.core.engine.memory import store


def _create_database(path: Path, value: str = "base") -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE sample(value TEXT)")
        connection.execute("INSERT INTO sample VALUES (?)", (value,))
        connection.commit()
    finally:
        connection.close()


def _wal_writer(path: Path, value: str) -> sqlite3.Connection:
    writer = sqlite3.connect(path)
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute("INSERT INTO sample VALUES (?)", (value,))
    writer.commit()
    return writer


def test_connect_read_only_rechecks_after_open_and_closes_stale_connection(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory.db"
    _create_database(db_path)
    original_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []
    writer: sqlite3.Connection | None = None

    def race_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal writer
        if kwargs.get("uri"):
            writer = _wal_writer(db_path, "committed-in-wal")
            assert Path(f"{db_path}-wal").stat().st_size > 0
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    try:
        with patch.object(store.sqlite3, "connect", race_connect):
            with pytest.raises(store.ReadOnlySnapshotUnavailable):
                store.connect_read_only(db_path, load_vec=False)
        assert opened
        with pytest.raises(sqlite3.ProgrammingError):
            opened[-1].execute("SELECT 1")
    finally:
        if writer is not None:
            writer.close()


def test_immutable_snapshot_guard_allows_stable_read_without_sidecars(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    _create_database(db_path)
    sidecars = [Path(f"{db_path}-wal"), Path(f"{db_path}-journal")]

    with store.immutable_snapshot_guard(db_path):
        snapshot = store.connect_read_only(db_path, load_vec=False)
        try:
            assert snapshot.conn.execute("SELECT value FROM sample").fetchall() == [("base",)]
        finally:
            snapshot.conn.close()

    assert not any(path.exists() for path in sidecars)


def test_immutable_snapshot_guard_rejects_wal_commit_during_read(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    _create_database(db_path)
    writer: sqlite3.Connection | None = None

    try:
        with pytest.raises(store.ReadOnlySnapshotUnavailable):
            with store.immutable_snapshot_guard(db_path):
                snapshot = store.connect_read_only(db_path, load_vec=False)
                try:
                    rows = snapshot.conn.execute("SELECT value FROM sample").fetchall()
                    assert rows == [("base",)]
                finally:
                    snapshot.conn.close()
                writer = _wal_writer(db_path, "committed-in-wal")
        assert writer is not None
    finally:
        if writer is not None:
            writer.close()


def test_immutable_snapshot_guard_rejects_rollback_journal_during_read(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory.db"
    _create_database(db_path)
    writer = sqlite3.connect(db_path)
    try:
        with pytest.raises(store.ReadOnlySnapshotUnavailable, match="rollback journal"):
            with store.immutable_snapshot_guard(db_path):
                snapshot = store.connect_read_only(db_path, load_vec=False)
                try:
                    rows = snapshot.conn.execute("SELECT value FROM sample").fetchall()
                    assert rows == [("base",)]
                finally:
                    snapshot.conn.close()
                writer.execute("BEGIN IMMEDIATE")
                writer.execute("INSERT INTO sample VALUES ('uncommitted')")
                assert Path(f"{db_path}-journal").stat().st_size > 0
    finally:
        writer.rollback()
        writer.close()


def test_immutable_snapshot_guard_rejects_empty_wal_deletion_during_read(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory.db"
    _create_database(db_path)
    wal_path = Path(f"{db_path}-wal")
    wal_path.touch()

    with pytest.raises(store.ReadOnlySnapshotUnavailable):
        with store.immutable_snapshot_guard(db_path):
            snapshot = store.connect_read_only(db_path, load_vec=False)
            try:
                assert snapshot.conn.execute("SELECT value FROM sample").fetchall() == [("base",)]
            finally:
                snapshot.conn.close()
            wal_path.unlink()


def test_immutable_snapshot_guard_rejects_checkpoint_truncate_during_read(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory.db"
    _create_database(db_path)
    writer = sqlite3.connect(db_path)
    try:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        with pytest.raises(store.ReadOnlySnapshotUnavailable):
            with store.immutable_snapshot_guard(db_path):
                snapshot = store.connect_read_only(db_path, load_vec=False)
                try:
                    rows = snapshot.conn.execute("SELECT value FROM sample").fetchall()
                    assert rows == [("base",)]
                finally:
                    snapshot.conn.close()
                writer.execute("INSERT INTO sample VALUES ('checkpointed')")
                writer.commit()
                writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        writer.close()


def test_immutable_snapshot_guard_rejects_database_replacement_during_read(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory.db"
    replacement_path = tmp_path / "replacement.db"
    _create_database(db_path)
    _create_database(replacement_path, "replacement")

    with pytest.raises(store.ReadOnlySnapshotUnavailable):
        with store.immutable_snapshot_guard(db_path):
            snapshot = store.connect_read_only(db_path, load_vec=False)
            try:
                assert snapshot.conn.execute("SELECT value FROM sample").fetchall() == [("base",)]
            finally:
                snapshot.conn.close()
            os.replace(replacement_path, db_path)
