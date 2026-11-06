"""B14: freeze the unmodified GC/doctor CLI; never recapture from a port.

Doctor has no --db option: freeze that rejection and use a configured synthetic
DB for its operational cases. Missing migration means a missing ledger row.
Read-only means chmod 0444 on the DB file, with a writable parent directory.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

from mir.cli import memory
from mir.core.engine.memory import distill, store

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b14-gc-doctor.json"
NOW = "2030-01-02T00:00:00.123456+00:00"


def _state(db):
    if not db.exists():
        return {"exists": False}
    try:
        conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
        try:
            objects = [list(row) for row in conn.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")]
            tables = {row[1] for row in objects if row[0] == "table"}
            rows = {name: [list(row) for row in conn.execute(f'SELECT * FROM "{name}" ORDER BY 1')]
                    for name in ("schema_migrations", "entities", "facts", "audit_log",
                                 "sqlite_sequence", "external_archives", "external_store_meta",
                                 "external_documents", "external_chunks") if name in tables}
            # The schema is frozen in full by B03; record its digest here.
            return {"objects_sha256": hashlib.sha256(json.dumps(objects).encode()).hexdigest(),
                    "rows": rows,
                    "pragmas": {key: conn.execute(f"PRAGMA {key}").fetchone()[0]
                                for key in ("journal_mode", "user_version", "application_id")}}
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return {"error": [type(exc).__name__, str(exc)]}


def _invoke(argv, tmp):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch.object(store.log, "handlers", [logging.StreamHandler(err)]), \
            mock.patch.object(store.log, "propagate", False):
        try:
            code = memory.main(argv)
        except SystemExit as exc:
            code = exc.code
        except Exception as exc:  # noqa: BLE001 - CLI can raise without returning an exit code
            code = [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]
    return {"exit": code, "stdout": out.getvalue().replace(str(tmp), "<tmp>"),
            "stderr": err.getvalue().replace(str(tmp), "<tmp>")}


def _case(action, mode, as_json=True, apply=False):
    def run(tmp):
        (tmp / ".mir").mkdir()
        db = tmp / ".mir" / "db"
        (tmp / "docs").mkdir()
        (tmp / "harness_a.toml").write_text(
            '[memory]\nenabled=true\nrequired=true\nbackend="sqlite_fts5"\n'
            'db_path=".mir/db"\nvector_mode="' +
            ("optional" if mode == "vector" else "off") +
            '"\n[memory.embedding]\nenabled=false\nrequired=false\n'
            '[[memory.external_archives]]\nslug="docs"\nroot="' +
            ("d\\u00f6cs" if mode == "unicode_root" else "docs") + '"\n', encoding="ascii")
        keeper = None
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(store, "_now_iso", return_value=NOW))
            stack.enter_context(mock.patch.object(distill, "_now_iso", return_value=NOW))
            stack.enter_context(mock.patch.object(store, "datetime", wraps=datetime))
            store.datetime.now.return_value = datetime.fromisoformat(NOW)
            stack.enter_context(mock.patch.object(store, "_load_sqlite_vec",
                                                  return_value=(False, "fixture unavailable")))
            stack.enter_context(mock.patch.object(memory.uuid, "uuid4",
                                                  return_value=mock.Mock(hex="0" * 32)))
            stack.enter_context(mock.patch("sys.argv", ["mir"]))
            if mode.startswith("relative"):
                # Relative --project-root and --db resolve against the working directory.
                stack.enter_context(contextlib.chdir(tmp))
            if mode == "empty":
                db.touch()
            elif mode == "non_sqlite":
                db.write_text("not sqlite\n", encoding="ascii")
            elif mode not in ("missing", "db_option"):
                conn = sqlite3.connect(db)
                store.apply_migrations(conn)
                if action == "gc":
                    conn.executemany("INSERT INTO facts(status, valid_to) VALUES (?, ?)",
                                     [("active", value) for value in (
                                         None, "2030-01-01", "2030-01-01T23:59:59+00:00",
                                         "2030-01-02", "2030-01-02T00:00:00+00:00",
                                         "2030-01-03")] + [("expired", "2030-01-01"),
                                                                 ("superseded", "2030-01-01")])
                if mode == "missing_migration":
                    conn.execute("DELETE FROM schema_migrations WHERE version = "
                                 "(SELECT MIN(version) FROM schema_migrations)")
                elif mode == "future":
                    conn.execute("INSERT INTO schema_migrations VALUES ('999', 'future', ?)",
                                 (NOW,))
                elif mode == "fts_missing":
                    conn.execute("DROP TABLE facts_fts")
                elif mode == "fts_broken":
                    conn.execute("DROP TRIGGER facts_fts_ai")
                elif mode in ("ready", "ready_short", "relative_link", "stale"):
                    # A synced archive seeded directly; ready_short has no 6-character token,
                    # stale drifted and was never scanned, and an unconfigured archive is ignored.
                    text = "a bc def\n" if mode == "ready_short" else "alpha betagamma\n"
                    (tmp / "docs" / "note.md").write_text(text, encoding="ascii")
                    stale = mode == "stale"
                    conn.execute("INSERT INTO external_archives(id, slug, root_path, mode, owner, "
                                 "created_at, last_scanned_at) VALUES (1, 'docs', ?, 'indexed', "
                                 "'family:docs', ?, ?)",
                                 (str(tmp / ("elsewhere" if stale else "docs")), NOW,
                                  None if stale else NOW))
                    conn.execute("INSERT INTO external_archives(id, slug, root_path, mode, owner, "
                                 "created_at) VALUES (2, 'other', ?, 'indexed', 'family:other', ?)",
                                 (str(tmp / "other"), NOW))
                    conn.execute("INSERT INTO external_store_meta VALUES "
                                 "('schema_metadata_version:archive:1', '5')")
                    conn.execute("INSERT INTO external_documents(id, archive_id, relative_path, "
                                 "file_hash) VALUES (1, 1, 'note.md', 'h')")
                    conn.execute("INSERT INTO external_chunks VALUES (1, 1, 0, 0, ?, 'h')",
                                 (len(text),))
                    conn.execute("INSERT INTO external_chunks_fts(rowid, content) VALUES (1, ?)",
                                 (text,))
                conn.commit()
                if mode == "wal":
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA wal_autocheckpoint=0")
                    conn.execute("INSERT INTO facts(status) VALUES ('active')")
                    conn.commit()
                    keeper = conn
                else:
                    conn.close()
                if mode == "readonly":
                    db.chmod(0o444)
            try:
                before = _state(db)
                argv = [action]
                if mode == "relative_db":
                    argv += ["--db", ".mir/db"]
                elif mode == "relative_root":
                    argv += ["--project-root", "nowhere"]
                elif mode == "relative_missing":
                    argv += ["--db", "absent.db"]
                elif mode == "relative_link":
                    (tmp / "alias").symlink_to(tmp, target_is_directory=True)
                    argv += ["--project-root", "alias"]
                elif action == "gc" or mode == "db_option":
                    argv += ["--db", str(db)]
                else:
                    argv += ["--project-root", str(tmp)]
                if as_json:
                    argv += ["--json"]
                if apply:
                    argv += ["--apply"]
                result = {"before": before, "command": _invoke(argv, tmp), "after": _state(db)}
                if keeper is not None:
                    result["nonempty_wal"] = Path(f"{db}-wal").stat().st_size > 0
                # Seeded archive rows hold the scratch path; records never keep host paths.
                return json.loads(json.dumps(result).replace(str(tmp), "<tmp>"))
            finally:
                if db.exists():
                    db.chmod(0o600)
                if keeper is not None:
                    keeper.close()
    return run


CASES = {
    **{f"gc.{apply}.{fmt}": _case("gc", "migrated", fmt, apply)
       for apply in (False, True) for fmt in (False, True)},
    **{f"gc.{mode}": _case("gc", mode) for mode in ("missing", "empty", "non_sqlite")},
    **{f"doctor.{mode}.{fmt}": _case("doctor", mode, fmt)
       for mode in ("db_option", "missing", "empty", "non_sqlite", "migrated",
                    "missing_migration", "future", "fts_missing", "fts_broken",
                    "vector", "wal", "readonly") for fmt in (False, True)},
    "gc.relative_db": _case("gc", "relative_db"),
    "gc.relative_missing": _case("gc", "relative_missing"),
    "doctor.ready.False": _case("doctor", "ready", False),
    **{f"doctor.{mode}.True": _case("doctor", mode)
       for mode in ("unicode_root", "relative_root", "ready", "ready_short", "relative_link",
                    "stale")},
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
