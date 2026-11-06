"""W2-B05-F01: unmodified Python query records, never recaptured from a port.

The task brief owns scope. Missing semantic support and terminal-subject results
are reference observations, not corrections. All databases are synthetic.
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest

from mir.cli import memory
from mir.core.engine.memory import store

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b05-memory-query.json"


def _seed(db):
    conn = sqlite3.connect(db)
    store.apply_migrations(conn)
    conn.executemany("INSERT INTO entities(id, slug) VALUES (?, ?)",
                     [(1, "alpha"), (2, "beta"), (3, "retired")])
    rows = [(1, "topic", "needle", "active"),
            (2, "topic", "needle", "active"),
            (1, "detail", "needle long extra padding words", "active"),
            (1, "topic", "needle expired", "expired"),
            (2, "detail", "needle superseded", "superseded"),
            (3, "status", "historical-snapshot", "active"),
            (3, "topic", "needle terminal", "active"),
            (2, "special", 'quote "alpha beta" star* adr-99 key:value NEAR (group)', "active"),
            (1, "unicode", "\uba54\ubaa8 caf\u00e9", "active")]
    conn.executemany(
        "INSERT INTO facts(subject_entity_id, predicate, object_literal, status, polarity) "
        "VALUES (?, ?, ?, ?, 'asserted')", rows)
    conn.commit()
    return conn


def _invoke(tmp, db, args):
    out, err = io.StringIO(), io.StringIO()
    handler = logging.StreamHandler(err)
    # Force a real optional-import failure independent of host installation.
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch.dict(sys.modules, {"sqlite_vec": None}), \
            mock.patch.object(store.log, "handlers", [handler]), \
            mock.patch.object(store.log, "propagate", False), \
            mock.patch.object(store.log, "level", logging.WARNING):
        result = {"exit": None}
        try:
            result["exit"] = memory.main(["query", *args, "--db", str(db)])
        except SystemExit as exc:
            result["exit"] = exc.code
        except Exception as exc:  # noqa: BLE001 - preserve CLI exception and streams
            result["error"] = [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]
    return {**result, "stdout": out.getvalue().replace(str(tmp), "<tmp>"),
            "stderr": err.getvalue().replace(str(tmp), "<tmp>")}


def _query(*args, mode="normal"):
    def run(tmp):
        db = tmp / "db"
        if mode == "missing":
            return _invoke(tmp, db, args)
        if mode == "invalid":
            db.write_text("not sqlite", encoding="ascii")
            return _invoke(tmp, db, args)
        conn = _seed(db)
        try:
            if mode in ("unknown", "future"):
                conn.execute("DELETE FROM schema_migrations")
                conn.execute("INSERT INTO schema_migrations VALUES (?, ?, 'fixed')",
                             ("unknown" if mode == "unknown" else "999", "synthetic.sql"))
                conn.commit()
            if mode.startswith("wal"):
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA wal_autocheckpoint=0")
                conn.execute("INSERT INTO facts(predicate, object_literal, status) "
                             "VALUES ('wal', 'needle committed', 'active')")
                conn.commit()
                if mode == "wal_uncommitted":
                    conn.execute("INSERT INTO facts(predicate, object_literal, status) "
                                 "VALUES ('wal', 'needle uncommitted', 'active')")
                assert Path(f"{db}-wal").stat().st_size > 0
            if mode == "unreadable":
                db.chmod(0)
            result = _invoke(tmp, db, args)
            if mode == "state":
                result["state"] = {
                    "pragmas": {key: conn.execute(f"PRAGMA {key}").fetchone()[0]
                                for key in ("journal_mode", "user_version")},
                    "versions": [list(row) for row in conn.execute(
                        "SELECT version, name FROM schema_migrations ORDER BY version")],
                    "objects": [list(row) for row in conn.execute(
                        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")]}
            return result
        finally:
            db.chmod(0o600)
            conn.rollback()
            conn.close()
    return run


CASES = {
    "query.default": _query("needle", mode="state"),
    "query.limit_zero": _query("needle", "--limit", "0"),
    "query.limit_one": _query("needle", "--limit", "1"),
    "query.limit_negative": _query("needle", "--limit", "-1"),
    "query.history": _query("needle", "--history"),
    "query.no_match": _query("absenttoken"),
    "query.semantic_unavailable": _query("needle", "--semantic"),
    **{f"query.keyword_{name}": _query(keyword) for name, keyword in (
        ("quotes", '"alpha beta"'), ("unmatched_quote", '"alpha'),
        ("star", "star*"), ("hyphen", "adr-99"), ("colon", "key:value"),
        ("near", "NEAR"), ("parentheses", "(group)"), ("empty", ""),
        ("unicode", "\uba54\ubaa8"))},
    **{f"query.{mode}": _query("needle", mode=mode) for mode in (
        "missing", "invalid", "unreadable", "unknown", "future",
        "wal_committed", "wal_uncommitted")},
    # argparse surface: abbreviations, = values, help, missing and extra positionals.
    **{f"query.args_{name}": _query(*args) for name, args in (
        ("abbrev_history", ("needle", "--hist")), ("abbrev_limit", ("needle", "--lim", "1")),
        ("equals_limit", ("needle", "--limit=1")), ("help", ("-h",)),
        ("no_keyword", ()), ("extra_positional", ("needle", "other")),
        ("option_first", ("--limit", "1", "needle")), ("double_dash", ("--", "--needle")),
        ("limit_missing_value", ("needle", "--limit")))},
}


def observe(case, tmp: Path) -> dict:
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - frozen exception class and message
        return {"error": [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]}


RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
