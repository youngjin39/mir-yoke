"""B17-F02: unmodified Python backfill oracle; never recapture from a port.

No backfill dry-run/batch-size API exists; calls below record per-document batches.
Synthetic archives use public register/scan; SQL only creates coverage/metadata holes.
"""
from __future__ import annotations

import contextlib
import io
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import pytest

from mir.cli import context
from mir.core.engine.memory import external_store as es
from mir.core.engine.memory import store

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b17-backfill.json"


def observe(case, tmp):
    try:
        return {"value": json.loads(json.dumps(case(tmp)), parse_constant=str)}
    except Exception as exc:  # noqa: BLE001 - freeze exception class and message
        return {"error": [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]}


def _state(db, archive):
    conn = db._conn.conn
    return {"coverage": db.vector_coverage(archive), "documents": conn.execute(
        "SELECT relative_path,vec_indexed_at IS NOT NULL FROM external_documents "
        "WHERE archive_id=? ORDER BY relative_path", (archive,)).fetchall(),
        "chunks": conn.execute("SELECT c.id,d.relative_path,c.chunk_index "
                               "FROM external_chunks c JOIN external_documents d "
                               "ON d.id=c.document_id ORDER BY c.id").fetchall(),
        "vectors": conn.execute("SELECT rowid,length(embedding),substr(hex(embedding),1,16) "
                                "FROM external_chunks_vec ORDER BY rowid").fetchall()
        if db._conn.vec_available else [],
        "fingerprint": conn.execute("SELECT value FROM external_store_meta "
                                    "WHERE key='external_embedding_fingerprint'").fetchall()}


def _run(mode):
    def run(tmp):
        calls = []
        fault = True
        def encode(texts):
            calls.append(texts)
            if fault and mode == "failure" and len(calls) == 2:
                raise RuntimeError("synthetic backend failure")
            vectors = [[1.] + [0.] * (es.DEFAULT_EMBED_DIM - 1) for _ in texts]
            if fault and mode == "dimension" and len(calls) == 2:
                vectors[1] = [1.]
            if fault and mode == "count" and len(calls) == 2:
                vectors.pop()
            return vectors
        loader = store._load_sqlite_vec
        def load(raw):
            return ((False, "synthetic unavailable")
                    if mode in ("missing", "cli_missing") else loader(raw))
        with mock.patch.object(store, "_load_sqlite_vec", side_effect=load):
            connection = store.connect(tmp / "synthetic.db")
        conn = connection.conn
        store.apply_migrations(conn)
        try:
            if mode not in ("missing", "cli_missing") and not connection.vec_available:
                raise RuntimeError(connection.vec_reason)
            db = es.ExternalStore(connection)
            root = tmp / "archive"
            root.mkdir()
            archive = db.register(slug="sample", root_path=str(root), mode="indexed",
                                  owner="synthetic", chunk_size=8, chunk_overlap=0)
            if mode == "adopt":
                db.reindex_missing_vectors(archive, embed_fn=encode, encoder_fingerprint="old")
            if mode != "empty":
                (root / "a.md").write_text("alpha001alpha002alpha003", encoding="ascii")
                db.scan(archive, embed_fn=encode if mode in ("seed", "partial", "mismatch",
                        "legacy", "unstamped") else None, encoder_fingerprint="model-a")
                for name in ("b", "c"):
                    (root / f"{name}.md").write_text(name * 24, encoding="ascii")
                (root / "empty.md").write_text("", encoding="ascii")
                db.scan(archive)
            if mode == "partial":
                conn.execute("DELETE FROM external_chunks_vec WHERE rowid=2")
                conn.commit()
            if mode == "unstamped":
                conn.execute("UPDATE external_documents SET vec_indexed_at=NULL "
                             "WHERE relative_path='a.md'")
                conn.commit()
            if mode == "legacy":
                conn.execute("DELETE FROM external_store_meta "
                             "WHERE key='external_embedding_fingerprint'")
                conn.commit()
            if mode in ("changed", "cli_changed"):
                (root / "b.md").write_text("changed since sync", encoding="ascii")
            calls.clear()
            result = {"before": _state(db, archive)}
            fingerprint = "model-b" if mode == "mismatch" else "" if mode == "blank" else "model-a"
            def backfill():
                return asdict(db.reindex_missing_vectors(
                    archive, embed_fn=None if mode == "no_backend" else encode,
                    encoder_fingerprint=fingerprint))
            if mode.startswith("cli"):
                cfg = NS(memory=NS(embedding=NS(enabled=mode != "cli_disabled",
                                                fingerprint=fingerprint)))
                output = io.StringIO()
                def backend(_):
                    if mode == "cli_backend_failure":
                        raise RuntimeError("synthetic backend unavailable")
                    return None if mode == "cli_no_backend" else encode
                with mock.patch.object(context, "_build_embed_fn", side_effect=backend), \
                        contextlib.redirect_stdout(output):
                    result["exit"] = context._do_sync(context._parse(
                        ["sync", "--reindex-missing-vectors"]), connection, cfg, tmp)
                result["stdout"] = output.getvalue()
            else:
                result["first"] = observe(lambda _: backfill(), tmp)
            result["after"] = _state(db, archive)
            result["batches"] = list(calls)
            if mode in ("normal", "seed", "partial", "adopt", "empty", "unstamped"):
                calls.clear()
                result["replay"] = backfill()
                result["replay_batches"] = list(calls)
                result["replay_state"] = _state(db, archive)
            if mode in ("failure", "dimension", "count"):
                # A fresh backend resumes failed documents; successful documents stay untouched.
                calls.clear()
                fault = False
                result["resume"] = backfill()
                result["resume_batches"] = list(calls)
            if mode not in ("missing", "cli_missing"):
                conn.close()
                connection = store.connect(tmp / "synthetic.db")
                result["persisted"] = _state(es.ExternalStore(connection), archive)
            return result
        finally:
            connection.conn.close()
    return run


def _schema(mode):
    def run(tmp):
        with mock.patch.object(store, "_load_sqlite_vec", return_value=(False, "unavailable")) \
                if mode == "missing" else contextlib.nullcontext():
            connection = store.connect(tmp / "synthetic.db")
        conn = connection.conn
        store.apply_migrations(conn)
        try:
            result = {"available": connection.vec_available}
            for dim in (2, 2, 3):
                result.setdefault("create", []).append(observe(
                    lambda _, d=dim: es.ensure_external_vec_table(conn, dim=d), tmp))
            result["schema"] = conn.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            result["migrations"] = conn.execute(
                "SELECT version,name FROM schema_migrations ORDER BY version").fetchall()
            result["pragmas"] = {key: conn.execute(f"PRAGMA {key}").fetchone()[0]
                                 for key in ("journal_mode", "synchronous", "foreign_keys")}
            return result
        finally:
            conn.close()
    return run


CASES = {f"backfill.{mode}": _run(mode) for mode in (
    "normal", "empty", "seed", "partial", "unstamped", "failure", "dimension", "count", "changed",
    "adopt", "mismatch", "legacy", "blank", "no_backend", "missing", "cli",
    "cli_disabled", "cli_missing", "cli_no_backend", "cli_backend_failure", "cli_changed")}
CASES.update({f"table.{mode}": _schema(mode) for mode in ("available", "missing")})
RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
