"""W2-B03-F02: snapshot records captured from the unmodified Python reference.

The Rust port oracle includes absent APIs; never regenerate it from a port.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from mir.core.engine.memory import store

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b03-snapshot.json"


def observe(case, tmp: Path) -> dict:
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze class and normalized message
        return {"error": [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]}


def _database(tmp, schema=True):
    path = tmp / "db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE items(value TEXT)")
    conn.execute("INSERT INTO items VALUES ('base')")
    if schema:
        conn.execute("CREATE TABLE schema_migrations(version TEXT, name TEXT)")
        conn.execute("INSERT INTO schema_migrations VALUES ('999', 'future.sql')")
    conn.commit()
    return path, conn


def _logical(conn):
    objects = [list(row) for row in conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")]
    return {"objects": objects,
            "versions": [list(row) for row in conn.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version")]
            if any(row[1] == "schema_migrations" for row in objects) else None,
            "rows": [list(row) for row in conn.execute("SELECT * FROM items ORDER BY value")],
            "pragmas": {key: conn.execute(f"PRAGMA {key}").fetchone()[0]
                        for key in ("journal_mode", "query_only", "user_version")}}


def _reader(mode):
    def run(tmp):
        path, source = _database(tmp, schema=mode != "no_schema")
        try:
            if mode == "wal":
                source.execute("PRAGMA journal_mode=WAL")
                source.execute("INSERT INTO items VALUES ('wal-row')")
                source.commit()
            if mode in {"empty_wal", "shm"}:
                Path(f"{path}-{'wal' if mode == 'empty_wal' else 'shm'}").touch()
            target = path
            if mode == "symlink":
                target = tmp / "link"
                target.symlink_to(path)
            before, files = _logical(source), sorted(p.name for p in tmp.iterdir())
            wal_before = store._snapshot_file_state(Path(f"{path}-wal"))

            def read(_):
                wrapped = store.connect_read_only(target)
                conn = wrapped.conn
                try:
                    result = {"logical": _logical(conn), "type": type(conn).__name__,
                            "vec": [wrapped.vec_available, wrapped.vec_reason],
                            "write": observe(lambda _: conn.execute(
                                "INSERT INTO items VALUES ('snapshot-write')"), tmp)}
                finally:
                    conn.close()
                    conn.close()
                result["closed_query"] = observe(lambda _: conn.execute("SELECT 1"), tmp)
                return result

            result = observe(read, tmp)
            after = _logical(source)
            return {"read": result, "source_before": before, "source_after": after,
                    "wal_unchanged": wal_before == store._snapshot_file_state(Path(f"{path}-wal")),
                    "copy_exists_after_close": any(p.name not in files for p in tmp.iterdir()),
                    "files_before": files, "source_unchanged": before == after}
        finally:
            source.close()
    return run


def _state(mode):
    def run(tmp):
        path = tmp / "db"
        if mode != "missing":
            path.write_bytes(b"abc")
        before = store._snapshot_file_state(path)
        if mode == "symlink":
            link = tmp / "link"
            link.symlink_to(path)
            return store._snapshot_file_state(link) == before
        if before is None:
            return None
        result = {"fields": [field.name for field in fields(before)], "size": before.size,
                  "equal": before == store._snapshot_file_state(path)}
        try:
            before.size = 0
        except FrozenInstanceError as exc:
            result["frozen"] = type(exc).__name__
        return result
    return run


def _guard(mode, direct=False):
    def run(tmp):
        path, conn = _database(tmp)
        conn.close()
        if mode in {"wal", "journal", "empty_wal", "shm"}:
            suffix = "wal" if mode == "empty_wal" else mode
            Path(f"{path}-{suffix}").write_bytes(b"" if mode == "empty_wal" else b"x")
        before = store._immutable_snapshot_state(path)

        def change():
            if mode == "changed":
                with path.open("ab") as output:
                    output.write(b"x")
            if mode == "deleted":
                path.unlink()
            if mode == "wal_removed":
                Path(f"{path}-wal").unlink()

        if mode == "wal_removed":
            Path(f"{path}-wal").touch()
            before = store._immutable_snapshot_state(path)
        if direct:
            change()
            result = observe(lambda _: store._assert_immutable_snapshot_state(path, before), tmp)
        else:
            def guarded(_):
                with store.immutable_snapshot_guard(path):
                    change()
            result = observe(guarded, tmp)
        after = store._immutable_snapshot_state(path)
        return {"result": result, "keys": sorted(before),
                "present": {key: value is not None for key, value in before.items()},
                "unchanged": {key: before[key] == after[key] for key in before}}
    return run


CASES = {f"connect.{mode}": _reader(mode) for mode in
         ("clean", "wal", "empty_wal", "shm", "symlink", "no_schema")}
CASES.update({f"file_state.{mode}": _state(mode) for mode in ("missing", "file", "symlink")})
CASES.update({f"assert.{mode}": _guard(mode, direct=True) for mode in
              ("stable", "wal", "journal", "changed", "deleted")})
CASES.update({f"guard.{mode}": _guard(mode) for mode in
              ("stable", "wal", "journal", "empty_wal", "shm", "changed",
               "deleted", "wal_removed")})
CASES.update({
    "connect.missing": lambda tmp: store.connect_read_only(tmp / "missing"),
    "api.available_absent": lambda tmp: store.assert_immutable_snapshot_available,
    "api.connection_absent": lambda tmp: store._SnapshotConnection,
    "api.schema_guard_absent": lambda tmp: store._assert_schema_version,
    "error.hierarchy": lambda tmp: [cls.__name__ for cls in
                                     store.ReadOnlySnapshotUnavailable.__mro__],
})

RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
