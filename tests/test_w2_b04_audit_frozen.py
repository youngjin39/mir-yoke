"""B04: unmodified Python audit/GC oracle; never recapture from a port.

Task brief owns scope; use migrated synthetic databases and fixed UTC clocks.
SQL traces freeze lock ownership; GC compares stored text to the UTC date.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest

from mir.core.engine.audit_log import AuditLog
from mir.core.engine.memory import store

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b04-audit.json"
NOW = "2030-01-02T00:00:00.123456+00:00"


def _db(tmp):
    conn = sqlite3.connect(tmp / "db", timeout=0.001)
    with mock.patch.object(store, "_now_iso", return_value=NOW):
        store.apply_migrations(conn)
    return conn


def _rows(conn, table):
    return [list(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]


def _state(conn):
    return {"audit": _rows(conn, "audit_log"), "facts": _rows(conn, "facts"),
            "transaction": conn.in_transaction,
            "verify": asdict(store.audit_verify(conn))}


def _audit(mode):
    def run(tmp):
        conn = _db(tmp)
        trace = []
        conn.set_trace_callback(trace.append)
        try:
            if mode.startswith("caller"):
                conn.execute("BEGIN")
            with mock.patch.object(store, "_now_iso", return_value=NOW):
                hashes = [store.audit_append(conn, "a|b", {"z": 1, "a": "\u00e9"},
                                            commit=mode not in ("deferred", "caller_false"))]
                hashes.append(store.audit_append(conn, "", {}))
            statements = list(trace)
            result = {"hashes": hashes, "state": _state(conn), "trace": statements}
            if mode in ("caller", "caller_false", "deferred"):
                conn.rollback()
                result["rollback"] = _state(conn)
            elif mode == "caller_commit":
                conn.commit()
                result["commit"] = _state(conn)
            else:
                result["pragmas"] = {key: conn.execute(f"PRAGMA {key}").fetchone()[0]
                                     for key in ("journal_mode", "foreign_keys", "busy_timeout")}
                result["migrations"] = _rows(conn, "schema_migrations")
                result["objects"] = [list(row) for row in conn.execute(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")]
            return result
        finally:
            conn.close()
    return run


def _busy(tmp):
    conn = _db(tmp)
    other = sqlite3.connect(tmp / "db", timeout=0.001)
    trace = []
    try:
        other.execute("BEGIN IMMEDIATE")
        conn.set_trace_callback(trace.append)
        with mock.patch.object(store, "_now_iso", return_value=NOW):
            error = observe(lambda _: store.audit_append(conn, "busy", {}), tmp)
        statements = list(trace)
        return {"result": error, "trace": statements, "state": _state(conn)}
    finally:
        other.close()
        conn.close()


def _verify(mode, row_id=1):
    def run(tmp):
        conn = _db(tmp)
        try:
            with mock.patch.object(store, "_now_iso", return_value=NOW):
                for index in range(0 if mode == "empty" else 3):
                    store.audit_append(conn, f"event-{index}", {"index": index})
            if mode in ("payload", "hash", "prev_hash", "ts", "event"):
                column = "payload" if mode == "payload" else mode
                conn.execute(f"UPDATE audit_log SET {column} = ? WHERE id = ?", ("x", row_id))
            if mode == "reordered":
                conn.execute("UPDATE audit_log SET id = 0 WHERE id = 2")
            if mode == "gap":
                conn.execute("UPDATE audit_log SET id = 9 WHERE id = 3")
            if mode == "deleted":
                conn.execute("DELETE FROM audit_log WHERE id = 2")
            return _state(conn)
        finally:
            conn.close()
    return run


def _gc(dry_run=True, empty=False, caller=False):
    def run(tmp):
        conn = _db(tmp)
        try:
            rows = [] if empty else [("active", value) for value in (
                None, "2030-01-01", "2030-01-01T23:59:59+00:00", "2030-01-02",
                "2030-01-02T00:00:00+00:00", "2030-01-02T00:00:01+00:00", "2030-01-03")]
            rows += [] if empty else [("expired", "2030-01-01"), ("superseded", "2030-01-01")]
            conn.executemany("INSERT INTO facts(status, valid_to) VALUES (?, ?)", rows)
            conn.commit()
            if caller:
                conn.execute("INSERT INTO facts(status) VALUES ('active')")
            before = _state(conn)
            with mock.patch.object(store, "datetime", wraps=datetime) as clock:
                clock.now.return_value = datetime.fromisoformat(NOW)
                counts = store.gc_scan(conn, dry_run=dry_run)
                after = _state(conn)
                again = store.gc_scan(conn, dry_run=dry_run)
            conn.rollback()
            return {"before": before, "counts": counts, "after": after,
                    "again": again, "rollback": _state(conn)}
        finally:
            conn.close()
    return run


def _facade(mode):
    def run(tmp):
        conn = _db(tmp)
        try:
            facade = AuditLog(conn)
            with mock.patch.object(store, "_now_iso", return_value=NOW):
                if mode == "event":
                    value = facade.event("custom", {"nested": {"b": 2, "a": 1}})
                elif mode == "numbers":
                    # Python float text (1e+16, -0.0) enters the chained hash.
                    value = facade.event("custom", {"f": 1e16, "g": 0.1, "h": -0.0, "s": 1.5e-7})
                elif mode == "extra":
                    value = facade.record("p", "t", "denied", "why", detail="\u00e9", n=0)
                else:
                    value = facade.record("", "", "")
            return {"value": value, "state": _state(conn)}
        finally:
            conn.close()
    return run


def _now(microseconds):
    def run(tmp):
        with mock.patch.object(store, "datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2030, 1, 2, microsecond=microseconds, tzinfo=UTC)
            return {"value": store._now_iso(), "calls": str(clock.now.call_args)}
    return run


def _result(tmp):
    value = store.AuditVerifyResult(True, 0, None, None)
    return {"fields": asdict(value), "repr": repr(value),
            "equal": value == store.AuditVerifyResult(True, 0, None, None),
            "different": value == store.AuditVerifyResult(False, 1, 1, "bad"),
            "frozen": observe(lambda _: setattr(value, "checked", 1), tmp)}


CASES = {
    **{f"now.{n}": _now(n) for n in (0, 1, 999999)},
    **{f"canonical.{name}": (lambda tmp, obj=obj: store._canonical_json(obj))
       for name, obj in (("empty", {}), ("nested", {"z": [None, True, False, -0.0],
                         "a": {"\u00e9": "\n\t\"\\\u0000"}}),
                        ("mixed_keys", {1: "a", "b": 2}), ("set", {"a": {1}}),
                        ("nonfinite", {"n": float("nan"), "i": float("inf")}))},
    **{f"append.{mode}": _audit(mode) for mode in (
        "default", "deferred", "caller", "caller_false", "caller_commit")},
    "append.busy": _busy,
    "result.fields_frozen": _result,
    **{f"verify.{mode}": _verify(mode)
       for mode in ("empty", "valid", "reordered", "gap", "deleted")},
    **{f"verify.{mode}_{row}": _verify(mode, row) for mode in (
        "payload", "hash", "prev_hash", "ts", "event") for row in (1, 2, 3)},
    **{f"gc.{dry}_{empty}_{caller}": _gc(dry, empty, caller)
       for dry in (True, False) for empty in (True, False) for caller in (True, False)},
    **{f"facade.{mode}": _facade(mode) for mode in ("default", "extra", "event", "numbers")},
}


def observe(case, tmp: Path) -> dict:
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze reference exception class and text
        return {"error": [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]}


RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
