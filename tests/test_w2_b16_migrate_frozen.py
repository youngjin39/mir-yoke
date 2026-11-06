"""B16: capture only the unmodified Python CLI; never regenerate from a port.

Assumptions: extension availability is controlled, not the SQLite connection;
read-only means mode 0444. Logical inspection must not create or checkpoint files.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from mir.cli import migrate
from mir.core.engine.memory import store

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b16-migrate.json"
VERSIONS = ("001", "002", "003", "004", "014", "015", "016", "017", "018")


def _files(db):
    return {suffix: {"exists": (p := Path(str(db) + suffix)).exists(),
                     "nonempty": p.exists() and p.stat().st_size > 0}
            for suffix in ("", "-wal", "-shm", "-journal")}


def _fingerprints(db):
    return {suffix: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
            for suffix in ("", "-wal", "-shm", "-journal")
            for p in [Path(str(db) + suffix)]}


def _state(db, held=None):
    result = {"files": _files(db)}
    if not db.exists():
        return result
    conn = held or sqlite3.connect(f"{db.as_uri()}?immutable=1&mode=ro", uri=True)
    try:
        objects = [list(row) for row in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")]
        result["schema_sha256"] = hashlib.sha256(
            json.dumps(objects, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
        result["pragmas"] = {name: conn.execute(f"PRAGMA {name}").fetchone()[0]
                             for name in ("journal_mode", "user_version", "application_id")}
        result["migrations"] = ([list(row) for row in conn.execute(
            "SELECT * FROM schema_migrations ORDER BY version")]
            if any(row[1] == "schema_migrations" for row in objects) else None)
    except sqlite3.Error as exc:
        result["error"] = [type(exc).__name__, str(exc)]
    finally:
        if held is None:
            conn.close()
    return result


def _call(argv, db, tmp, held=None, vec=False):
    before = _state(db, held)
    fingerprints = _fingerprints(db)
    stdout, stderr = io.StringIO(), io.StringIO()
    connections = []
    original = store.connect

    def connect(*args, **kwargs):
        wrapped = original(*args, **kwargs)
        connections.append({name: wrapped.conn.execute(f"PRAGMA {name}").fetchone()[0]
                            for name in ("journal_mode", "synchronous", "foreign_keys",
                                         "query_only", "busy_timeout")})
        return wrapped

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
            mock.patch.object(store, "connect", side_effect=connect), \
            mock.patch.object(store, "_load_sqlite_vec", return_value=(vec, "fixture")), \
            mock.patch.object(store.log, "handlers", [logging.StreamHandler(stderr)]), \
            mock.patch.object(store.log, "propagate", False), \
            mock.patch.object(store.log, "level", logging.WARNING):
        try:
            exit_code = migrate.main(argv)
            error = None
        except SystemExit as exc:
            exit_code, error = exc.code, None
        except Exception as exc:  # noqa: BLE001 - freeze CLI exceptions as well as output
            exit_code = None
            error = [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]
    changed = {suffix: value != fingerprints[suffix]
               for suffix, value in _fingerprints(db).items()}
    return {"exit": exit_code, "error": error, "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue().replace(str(tmp), "<tmp>"),
            "connections": connections, "before": before, "after": _state(db, held),
            "files_changed": changed}


def _case(action, mode, version=None, vec=False):
    def run(tmp):
        db = tmp / "nested/db"
        held = None
        db.parent.mkdir()
        with mock.patch.object(store, "_now_iso", return_value="<time>"):
            try:
                if mode == "empty":
                    db.touch()
                elif mode == "invalid":
                    db.write_text("not sqlite", encoding="ascii")
                elif mode != "missing":
                    held = sqlite3.connect(db)
                    if mode != "fresh":
                        entries = list(store._iter_migrations())
                        if mode == "wal":
                            entries = entries[:2]
                        if mode == "earlier":
                            entries = [m for m in entries if m.version <= version]
                        with mock.patch.object(store, "_iter_migrations", return_value=entries):
                            store.apply_migrations(held)
                    if mode == "future":
                        held.execute(
                            "INSERT INTO schema_migrations VALUES ('999', 'future', '<time>')")
                        held.commit()
                    if mode == "versionless":
                        held.execute("DELETE FROM schema_migrations")
                        held.commit()
                    if mode == "wal":
                        held.execute("PRAGMA journal_mode=WAL")
                        held.execute("PRAGMA wal_autocheckpoint=0")
                        held.execute("CREATE TABLE wal_marker(value)")
                        held.execute("INSERT INTO wal_marker VALUES (7)")
                        held.commit()
                        assert Path(str(db) + "-wal").stat().st_size > 0
                    else:
                        held.close()
                        held = None
                    if mode == "readonly":
                        db.chmod(0o444)
                result = _call([action, "--db", str(db)], db, tmp, held, vec)
                if mode == "wal":
                    result["wal_rows"] = [list(row) for row in held.execute(
                        "SELECT * FROM wal_marker")]
                return result
            finally:
                if held is not None:
                    held.close()
                if db.exists():
                    db.chmod(0o644)
    return run


def _args(argv):
    return lambda tmp: _call(argv, tmp / "db", tmp)


CASES = {f"{action}.{mode}": _case(action, mode)
         for action in ("up", "status")
         for mode in ("missing", "empty", "fresh", "latest", "future", "invalid",
                      "readonly", "wal", "versionless")}
CASES.update({f"{action}.earlier_{version}": _case(action, "earlier", version)
              for action in ("up", "status") for version in VERSIONS[:-1]})
CASES.update({"up.vec_available": _case("up", "missing", vec=True),
              "args.help": _args(["--help"]), "args.missing": _args([]),
              "args.unknown": _args(["rollback"]), "args.option": _args(["up", "--bad"]),
              "args.db_value": _args(["status", "--db"]),
              "args.up_help": _args(["up", "--help"]),
              "args.status_help": _args(["status", "--help"])})


def observe(case, tmp: Path) -> dict:
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze exception class and message
        return {"error": [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]}


RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
