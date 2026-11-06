"""W2-B03-F01: records captured only from the unmodified Python reference.

These records are the Rust port oracle; never regenerate them from a port.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from mir.core.engine.memory import store

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b03-store.json"


def _state(conn):
    return {
        "objects": [list(row) for row in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")],
        "versions": [list(row) for row in conn.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version")],
        "version": store.schema_version(conn),
        "transaction": conn.in_transaction,
    }


def _connect(timeout=None):
    def run(tmp):
        wrapped = store.connect(tmp / "nested/db", load_vec=False, timeout=timeout)
        conn = wrapped.conn
        try:
            return {"pragmas": {name: conn.execute(f"PRAGMA {name}").fetchone()[0]
                                for name in ("journal_mode", "synchronous", "foreign_keys",
                                             "busy_timeout")},
                    "row_factory": conn.row_factory,
                    "row_type": type(conn.execute("SELECT 1").fetchone()).__name__,
                    "objects": [list(row) for row in conn.execute(
                        "SELECT type, name FROM sqlite_master ORDER BY type, name")],
                    "vec": [wrapped.vec_available, wrapped.vec_reason]}
        finally:
            conn.close()
    return run


def _resources(tmp):
    return [[entry.version, entry.name,
             hashlib.sha256(store.files("mir.core.engine.memory.migrations")
                            .joinpath(entry.name).read_bytes()).hexdigest()]
            for entry in store._iter_migrations()]


def _migration(mode):
    def run(tmp):
        with sqlite3.connect(tmp / "db") as conn:
            before = None
            if mode == "earlier":
                entries = list(store._iter_migrations())[:2]
                with mock.patch.object(store, "_iter_migrations", return_value=entries):
                    first = store.apply_migrations(conn)
                before = {"applied": first, "state": _state(conn)}
            applied = store.apply_migrations(conn)
            result = {"before": before, "applied": applied, "state": _state(conn)}
            if mode == "rerun":
                result["rerun"] = store.apply_migrations(conn)
                result["after_rerun"] = _state(conn)
            return result
    return run


def _synthetic(tmp):
    root = tmp / "migrations"
    root.mkdir()
    bodies = {"020_fail.sql": "CREATE TABLE lost(x);\nINSERT INTO absent VALUES (1);\n",
              "003_keep.sql": "CREATE TABLE kept(x);\nINSERT INTO kept VALUES (7);\n",
              "README.md": "ignored", "1_bad.sql": "ignored", "004_UPPER.sql": "ignored"}
    for name, body in bodies.items():
        (root / name).write_text(body, encoding="ascii")
    with mock.patch.object(store, "files", return_value=root):
        entries = [[m.version, m.name] for m in store._iter_migrations()]
        with sqlite3.connect(tmp / "db") as conn:
            failure = observe(lambda _: store.apply_migrations(conn), tmp)
            return {"entries": entries, "failure": failure, "state": _state(conn),
                    "kept": [list(row) for row in conn.execute("SELECT * FROM kept")]}


def _split(body):
    return lambda tmp: list(store._iter_complete_statements(body))


def _version(mode):
    def run(tmp):
        with sqlite3.connect(tmp / "db") as conn:
            if mode != "missing":
                conn.execute(store._SCHEMA_MIGRATIONS_DDL)
            return store.schema_version(conn)
    return run


def _missing(name):
    return lambda tmp: getattr(store, name)


CASES = {
    "connect.default": _connect(),
    "connect.zero_timeout": _connect(0),
    "connect.custom_timeout": _connect(0.125),
    "migrations.resources": _resources,
    "migrations.empty": _migration("empty"),
    "migrations.rerun": _migration("rerun"),
    "migrations.earlier": _migration("earlier"),
    "migrations.rollback": _synthetic,
    "split.multi": _split("CREATE TABLE a(x);\nINSERT INTO a VALUES (1);\n"),
    "split.same_line": _split("SELECT 1; SELECT 2;\n"),
    "split.trigger": _split("CREATE TRIGGER t AFTER INSERT ON a BEGIN\n"
                            "INSERT INTO b VALUES ('a;b');\nUPDATE b SET x=2;\nEND;\n"),
    "split.comments_tail": _split("-- head;\nSELECT ';';\n/* block; */\nSELECT 2"),
    "split.empty": _split(""),
    "split.comment_only": _split("-- comment only"),
    "schema.missing_table": _version("missing"),
    "schema.empty_table": _version("empty"),
    "schema.guard_absent": _missing("_assert_schema_version"),
    "checkpoint.absent": _missing("checkpoint_passive"),
    "filter.ids_absent": _missing("filter_current_fact_ids"),
    "filter.default": lambda tmp: store.current_fact_filter_sql(),
    "filter.custom": lambda tmp: store.current_fact_filter_sql("fact_2"),
    "filter.invalid": lambda tmp: store.current_fact_filter_sql("f;DROP"),
    "schema.latest": lambda tmp: store.latest_schema_version(),
}


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
