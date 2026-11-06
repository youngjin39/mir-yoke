"""B18-F02: unmodified Python register/scan/index/sync oracle; never recapture a port.

Synthetic roots only, fixed clock, offline embeddings. Registration intentionally probes
unvalidated inputs; immutable mode is observed without imposing extra policy.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import pytest

from mir.cli import context
from mir.core.engine.memory import external_store as es
from mir.core.engine.memory import store

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b18-scan.json"
CLOCK = datetime(2026, 1, 2, tzinfo=UTC)


def observe(case, tmp):
    try:
        return {"value": json.loads(json.dumps(case(tmp)), parse_constant=str)}
    except Exception as exc:  # noqa: BLE001 - freeze exception class and message
        return {"error": [type(exc).__name__, str(exc).replace(str(tmp), "<tmp>")]}


def _state(connection, tmp):
    conn = connection.conn
    def clean(value):
        if isinstance(value, str):
            value = value.replace(str(tmp), "<tmp>").replace(CLOCK.isoformat(), "<clock>")
            if len(value) > 100:
                return [len(value), hashlib.sha256(value.encode()).hexdigest()]
        return value
    result = {table: [[clean(v) for v in row] for row in conn.execute(
        f"SELECT * FROM {table} ORDER BY 1").fetchall()] for table in
        ("external_archives", "external_documents", "external_chunks", "external_store_meta")}
    result["fts"] = conn.execute("SELECT count(*) FROM external_chunks_fts").fetchone()[0]
    result["vectors"] = conn.execute(
        "SELECT rowid,length(embedding) FROM external_chunks_vec ORDER BY rowid").fetchall()
    return result


@contextlib.contextmanager
def _db(tmp):
    with mock.patch.object(es, "datetime") as clock:
        clock.now.return_value = CLOCK
        connection = store.connect(tmp / "synthetic.db")
        store.apply_migrations(connection.conn)
        try:
            assert connection.vec_available, connection.vec_reason
            yield connection, es.ExternalStore(connection)
        finally:
            connection.conn.close()


def _write(root, name, text="abcdefghij"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _register(mode):
    def run(tmp):
        with _db(tmp) as (connection, db):
            args = dict(slug="sample", root_path=str(tmp / "archive"), mode="indexed",
                        owner="synthetic", chunk_size=8, chunk_overlap=0)
            changes = {"empty_slug": {"slug": ""}, "odd_slug": {"slug": "../a b"},
                       "mode": {"mode": "invalid"}, "empty_root": {"root_path": ""},
                       "size": {"chunk_size": 0}, "overlap": {"chunk_overlap": 8},
                       "negative": {"chunk_overlap": -1}, "file_root": {}}
            if mode == "file_root":
                _write(tmp, "archive")
            args.update(changes.get(mode, {}))
            first = observe(lambda _: db.register(**args), tmp)
            result = {"first": first, "state": _state(connection, tmp)}
            if mode == "duplicate":
                result["second"] = db.register(**(args | {"owner": "changed"}))
                result["after"] = _state(connection, tmp)
            if mode in ("missing_root", "file_root", "size", "overlap", "negative"):
                if mode in ("size", "overlap", "negative"):
                    _write(tmp / "archive", "a.md")
                result["scan"] = asdict(db.scan(first["value"]))
                result["after"] = _state(connection, tmp)
            return result
    return run


def _scan(mode):
    def run(tmp):
        with _db(tmp) as (connection, db):
            root = tmp / "archive"
            for name in ("a.md", "b.md", "docs/decisions/c.md", "tasks/handoffs/h.md",
                         ".ai-harness/rules/r.md", "docs/old.md", "skip.md", "note.txt"):
                _write(root, name, "# Title\n\nabcdefghij")
            _write(root, "empty.md", "")
            _write(root, "docs/status.md", "---\nstatus: archived\n---\nbody")
            if mode == "frontmatter":
                _write(root, "docs/mirror.md", "---\nsource: Mirrored-Summary\n---\nbody")
                _write(root, "docs/dep.md", "---\nstatus: Deprecated\n---\nbody")
                _write(root, "docs/live.md", "---\nstatus: accepted\nsource: manual\n---\nbody")
            args = dict(slug="sample", root_path=str(root), mode=mode if mode == "immutable"
                        else "indexed", owner="synthetic", chunk_size=8, chunk_overlap=0,
                        glob_include=("**/*.md",), glob_exclude=("skip.md",),
                        historical_glob=("docs/old.md",))
            archive = db.register(**args)
            batches = []
            def encode(texts):
                batches.append(texts)
                if mode == "failure" and len(batches) == 2:
                    raise RuntimeError("synthetic mid-scan failure")
                return [[1.] + [0.] * (es.DEFAULT_EMBED_DIM - 1) for _ in texts]
            def scan():
                return asdict(db.scan(archive, embed_fn=encode, encoder_fingerprint="fake",
                                      embed_batch_size=2))
            result = {"first": scan(), "state": _state(connection, tmp), "calls": list(batches)}
            persisted = store.connect(tmp / "synthetic.db")
            try:
                result["committed"] = _state(persisted, tmp)
            finally:
                persisted.conn.close()
            batches.clear()
            if mode in ("modified", "immutable"):
                _write(root, "a.md", "changed")
            elif mode == "deleted":
                (root / "a.md").unlink()
            elif mode == "renamed":
                (root / "a.md").rename(root / "renamed.md")
            elif mode == "metadata":
                connection.conn.execute("DELETE FROM external_store_meta WHERE key != "
                                        "'external_embedding_fingerprint'")
                connection.conn.execute("UPDATE external_documents SET title='stale'")
                connection.conn.commit()
            elif mode in ("content", "history", "exclude"):
                change = {"content": {"chunk_size": 4}, "history": {"historical_glob": ()},
                          "exclude": {"glob_exclude": ("skip.md", "a.md")}}[mode]
                db.register(**(args | change))
                result["sentinel"] = _state(connection, tmp)
            result.update(replay=scan(), after=_state(connection, tmp), replay_calls=batches)
            return result
    return run


def _index(tmp):
    with _db(tmp) as (connection, db):
        _write(tmp / "archive", "a.md", "\u00e9\u4e2d\n\n# Tail")
        archive = db.register(slug="sample", root_path=str(tmp / "archive"), mode="indexed",
                              owner="synthetic", chunk_size=4, chunk_overlap=1)
        row = db._fetch_archive(archive)
        result = {"id": db._index_file(row, "a.md", embed_fn=None)}
        result["duplicate"] = observe(lambda _: db._index_file(row, "a.md", embed_fn=None), tmp)
        result["missing"] = observe(lambda _: db._index_file(row, "absent.md", embed_fn=None), tmp)
        result["state"] = _state(connection, tmp)
        result["schema"] = connection.conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        result["migrations"] = connection.conn.execute(
            "SELECT version,name FROM schema_migrations ORDER BY version").fetchall()
        result["pragmas"] = {k: connection.conn.execute(f"PRAGMA {k}").fetchone()[0]
                             for k in ("journal_mode", "synchronous", "foreign_keys")}
        return result


def _sync(mode):
    def run(tmp):
        with _db(tmp) as (connection, db):
            archives = [NS(slug=n, root=n, mode="indexed", glob_include=(), glob_exclude=(),
                           historical_glob=(), chunk_size=8, chunk_overlap=0)
                        for n in ("one", "missing", "two")] if mode != "empty" else []
            _write(tmp / "one", "a.md")
            _write(tmp / "two", "b.md")
            if mode == "failure":
                (tmp / "two" / "bad.md").write_bytes(b"\xff")
            cfg = NS(memory=NS(external_archives=archives, embedding=NS(enabled=False)))
            ns = context._parse(["sync", "--db", "synthetic.db", "--project-root", "."])
            output = io.StringIO()
            with mock.patch.object(context, "_build_embed_fn", return_value=None), \
                    contextlib.redirect_stdout(output):
                exits = [context._do_sync(ns, connection, cfg, tmp) for _ in range(2)]
            return {"args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(ns).items()},
                    "exits": exits, "stdout": output.getvalue(), "state": _state(connection, tmp)}
    return run


def _sync_relative(tmp):
    """Configured roots resolve against the project root before registration."""
    with _db(tmp) as (connection, _):
        archives = [NS(slug=n, root=r, mode="indexed", glob_include=(), glob_exclude=(),
                       historical_glob=(), chunk_size=8, chunk_overlap=0)
                    for n, r in (("one", "sub/../one"), ("two", "./two/"))]
        _write(tmp / "one", "a.md")
        _write(tmp / "two", "b.md")
        cfg = NS(memory=NS(external_archives=archives, embedding=NS(enabled=False)))
        ns = context._parse(["sync", "--db", "synthetic.db", "--project-root", "."])
        output = io.StringIO()
        with mock.patch.object(context, "_build_embed_fn", return_value=None), \
                contextlib.redirect_stdout(output):
            exits = [context._do_sync(ns, connection, cfg, tmp) for _ in range(2)]
        return {"exits": exits, "stdout": output.getvalue(), "state": _state(connection, tmp)}


def _guard(mode):
    """Archive lookup and file-read guards; records carry no vector rows."""
    def run(tmp):
        with _db(tmp) as (connection, db):
            root = tmp / "archive"
            _write(root, "a.md")
            _write(tmp, "outside.md")
            (root / "bad.md").write_bytes(b"ab\xffcd")
            if mode == "symlink":
                (root / "inner.md").symlink_to(root / "a.md")
                (root / "outer.md").symlink_to(tmp / "outside.md")
                (root / "dir").symlink_to(tmp, target_is_directory=True)
                names = ("inner.md", "outer.md", "dir/outside.md")
            else:
                names = ("a.md", "../outside.md", "sub/../a.md", "bad.md", "absent.md")
            archive = db.register(slug="sample", root_path=str(root), mode="indexed",
                                  owner="synthetic", chunk_size=8, chunk_overlap=0)
            row = db._fetch_archive(archive)
            return {"fetch": observe(lambda _: db._fetch_archive(999), tmp),
                    "read": [observe(lambda _, n=n: list(db._read_file(row, n)), tmp)
                             for n in names]}
    return run


CASES = {f"register.{m}": _register(m) for m in (
    "empty_slug", "odd_slug", "mode", "empty_root", "missing_root", "file_root", "size",
    "overlap", "negative", "duplicate")}
CASES.update({f"scan.{m}": _scan(m) for m in (
    "unchanged", "modified", "deleted", "renamed", "immutable", "metadata", "content",
    "history", "exclude", "failure", "frontmatter")})
CASES.update({"index.direct": _index, **{f"sync.{m}": _sync(m) for m in
                                      ("empty", "multiple", "failure")}})
CASES.update({f"guard.{m}": _guard(m) for m in ("read", "symlink")})
CASES["sync.relative"] = _sync_relative
RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
