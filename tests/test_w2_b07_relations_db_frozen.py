"""B07-F02 oracle captured from unmodified Python; never recapture from a port.

Scope stops before memory row validation/traversal (F03). Reconcile replay is
intentionally NOT a no-op. All databases are synthetic and caller-owned.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from mir.core import memory_relations as m
from mir.core.engine.memory import relation_facts as f
from mir.core.engine.memory import store

FIXTURE = (Path(__file__).parent
           / '../native/handoff-packet/tests/fixtures/w2/b07-relations-db.json')
CLOCK = '2001-02-03T04:05:06.000000+00:00'
DECLS = tuple(f.RelationDeclaration(*row, quote='proof') for row in [
    ('A', 'depends_on', 'B'), ('A', 'depends_on', 'C'),
    ('B', 'implemented_in', 'src/a.py::z'), ('C', 'implemented_in', 'src/a.py::a')])


def observe(case, tmp):
    try:
        return {'value': case(tmp)}
    except Exception as exc:  # noqa: BLE001 - preserve reference errors
        return {'error': [type(exc).__name__, str(exc)]}


def rows(conn, sql):
    return [list(row) for row in conn.execute(sql)]


def state(conn):
    return {table: rows(conn, f'SELECT * FROM {table} ORDER BY rowid')
            for table in ['facts', 'entities', 'provenance', 'audit_log']}


def reconcile(conn, tmp, source='a.md', cid=1, status='active', declarations=DECLS):
    return list(f.reconcile_relation_facts(
        conn, declarations=declarations, content_item_id=cid, project_root=tmp,
        source_path=source, document_status=status))


def _compact(value):
    """Record strings over 256 characters as their length and SHA-256 to keep records small."""
    if isinstance(value, str) and len(value) > 256:
        return {'len': len(value), 'sha256': hashlib.sha256(value.encode()).hexdigest()}
    if isinstance(value, list):
        return [_compact(item) for item in value]
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()}
    return value


def scenario(kind, mode=None):
    def run(tmp):
        conn = sqlite3.connect(tmp / 'synthetic.db')
        try:
            store.apply_migrations(conn)
            for cid, source in [(1, 'a.md'), (2, 'b.md')]:
                metadata = f.relation_metadata(path=source, project_root=tmp,
                                               document_status='active')
                conn.execute('INSERT INTO content_items(id, source, text_hash, metadata_json) '
                             'VALUES (?, ?, ?, ?)',
                             (cid, 'self_ingest_md', 'hash', json.dumps(metadata)))
            conn.commit()
            with mock.patch.object(f, '_now_iso', return_value=CLOCK), \
                    mock.patch.object(store, '_now_iso', return_value=CLOCK):
                result = execute(conn, tmp, kind, mode)
            # Normalize only the synthetic root, including metadata embedded in SQL rows.
            return _compact(json.loads(json.dumps(result).replace(str(tmp), '<tmp>')))
        finally:
            conn.close()
    return run


def execute(conn, tmp, kind, mode):
    if kind == 'schema':
        return {'pragmas': {p: conn.execute(f'PRAGMA {p}').fetchone()[0]
                            for p in ['journal_mode', 'foreign_keys', 'synchronous']},
                'migrations': rows(conn, 'SELECT version, name FROM schema_migrations '
                                        'ORDER BY version'),
                'schema': rows(conn, 'SELECT type, name, tbl_name, sql FROM sqlite_master '
                                    'ORDER BY type, name')}
    if kind == 'upsert':
        ids = [f._upsert_entity(conn, slug) for slug in ['A', 'A', '', 'a', 'ns:A']]
        return [ids, state(conn)]
    if kind == 'empty':
        return [reconcile(conn, tmp, cid=None),
                f.has_owned_active_relation_facts(conn, project_root=tmp, source_path='a.md'),
                m._relation_rows(conn, tmp, set(), 'dependencies', limit=1), state(conn)]
    first = reconcile(conn, tmp)
    other = reconcile(conn, tmp, source='b.md', cid=2, declarations=DECLS[:1])
    conn.commit()
    if kind == 'lifecycle':
        before = state(conn)
        if mode == 'replay':
            changed = reconcile(conn, tmp)
        elif mode == 'change':
            changed = reconcile(conn, tmp, declarations=(
                f.RelationDeclaration('A', 'depends_on', 'D', quote='changed'),))
        elif mode == 'remove':
            changed = reconcile(conn, tmp, cid=None)
        else:
            changed = reconcile(conn, tmp, status=mode)
        owned = [list(r) for r in f._owned_active_rows(
            conn, project_path=str(tmp), source_path='a.md')]
        return [first, other, before, changed, owned, state(conn)]
    if kind == 'rollback':
        before = state(conn)
        original = f.audit_append
        calls = []

        def fail(*args, **kwargs):
            calls.append(kwargs['event'])
            if len(calls) == mode:
                raise RuntimeError('injected audit failure')
            return original(*args, **kwargs)

        with mock.patch.object(f, 'audit_append', side_effect=fail):
            with conn:
                failure = observe(lambda _: reconcile(conn, tmp, declarations=(
                    f.RelationDeclaration('D', 'depends_on', 'E', quote='new'), *DECLS)), tmp)
                partial = state(conn)
                conn.rollback()
        return [before, failure, calls, partial, state(conn), conn.in_transaction]
    if kind == 'owned':
        if mode:
            conn.execute(mode)
        return [[list(r) for r in f._owned_active_rows(
            conn, project_path=str(tmp), source_path='a.md')],
            [f.has_owned_active_relation_facts(conn, project_root=root, source_path=source)
             for root, source in [(tmp, 'a.md'), (tmp, 'b.md'), (tmp, 'missing'),
                                  (tmp / 'other', 'a.md')]]]
    if kind == 'provenance':
        conn.execute("INSERT INTO provenance VALUES (1, 1, 'other', NULL, 'inferred')")
        return [m._provenance_is_current(conn, *args) for args in [
            (1, 1, 'proof'), (1, 2, 'proof'), (99, 1, 'proof'),
            (1, 1, 'other'), (1, 1, ''), (1, 1, 'Proof')]]
    if kind == 'query':
        if mode:
            conn.execute(mode)
        return {'queries': [[purpose, limit, sorted(ids) if ids is not None else None,
                             sorted(excluded) if excluded is not None else None, m._relation_rows(
            conn, tmp, frontier, purpose, limit=limit, fact_ids=ids,
            excluded_fact_ids=excluded)]
            for purpose in sorted(m._PURPOSES) for limit in [-1, 0, 1, 2, 5, 6]
            for frontier, ids, excluded in [({'A', 'B'}, None, None),
                ({'A'}, {1, 5}, {1}), ({'A'}, set(), {1}), (set(), None, None)]],
                'eligible': [m._eligible_nodes(conn, tmp, a) for a in ['A', 'B', 'missing']],
                'probe': [m._has_relation_row(conn, tmp, {a}, 'dependencies')
                          for a in ['A', 'B', 'missing']]}
    if kind == 'locator':
        with mock.patch.object(m, 'MAX_EDGES', mode):
            result = [m._locator_nodes(conn, tmp, a) for a in [
                'src/a.py', './src//a.py', 'src/a.py::a', 'src/a.py::z',
                'src/A.py', 'missing', 'A']]
        return [result, rows(conn, "SELECT mir_locator_path('src//a.py::a'), "
                                  "mir_normalized_locator('./src/a.py::z')")]
    raise AssertionError(kind)


CASES = {name: scenario(name) for name in ['schema', 'upsert', 'empty', 'provenance']}
CASES.update({f'lifecycle.{mode}': scenario('lifecycle', mode) for mode in [
    'replay', 'change', 'remove', 'retracted', 'historical', 'draft', 'active']})
CASES.update({f'rollback.{n}': scenario('rollback', n) for n in [1, 5, 6]})
CASES.update({f'locator.{n}': scenario('locator', n) for n in [0, 1, 2, 3]})
OWNED = [None, "UPDATE facts SET status='superseded' WHERE created_from=1",
         "UPDATE facts SET object_literal='literal' WHERE created_from=1",
         "UPDATE facts SET object_entity_id=NULL WHERE created_from=1",
         "UPDATE facts SET scope='global' WHERE created_from=1",
         "UPDATE facts SET project_path='other' WHERE created_from=1",
         "UPDATE content_items SET source='other' WHERE id=1",
         "UPDATE content_items SET metadata_json='{}' WHERE id=1",
         "UPDATE content_items SET metadata_json=json_set(metadata_json, "
         "'$.relation_schema', 'other') WHERE id=1",
         "UPDATE content_items SET metadata_json=json_set(metadata_json, "
         "'$.relation_project_path', 'other') WHERE id=1",
         "UPDATE content_items SET metadata_json=json_set(metadata_json, "
         "'$.path', 'other') WHERE id=1"]
CASES.update({f'owned.{n}': scenario('owned', sql) for n, sql in enumerate(OWNED)})
QUERY = [*OWNED,
         "UPDATE content_items SET text_hash=printf('%0128d', 1) WHERE id=1",
         "UPDATE content_items SET metadata_json=printf('%065536d', 1) WHERE id=1",
         "UPDATE entities SET slug=printf('%04096d', 1) WHERE slug='B'",
         "UPDATE facts SET polarity='negated' WHERE created_from=1",
         "UPDATE facts SET valid_to='ended' WHERE created_from=1",
         "UPDATE content_items SET text_hash=printf('%0129d', 1) WHERE id=1",
         "UPDATE content_items SET metadata_json=printf('%065537d', 1) WHERE id=1",
         "UPDATE entities SET slug=printf('%04097d', 1) WHERE slug='A'",
         *["INSERT INTO facts(subject_entity_id,predicate,object_literal,status,polarity) "
           f"VALUES ({endpoint},'status','{status}','active','asserted')"
           for endpoint in [1, 2] for status in ['historical-new', 'draft', 'active']]]
CASES.update({f'query.{n}': scenario('query', sql) for n, sql in enumerate(QUERY)})

RECORDS = json.loads(FIXTURE.read_text(encoding='ascii')) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
