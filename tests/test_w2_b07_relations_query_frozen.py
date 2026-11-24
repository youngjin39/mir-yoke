"""F03 oracle from unmodified Python, never recaptured from a port.

Synthetic roots only. Small injected budgets probe both sides of the same limits;
row/proof caps also exercise the shipped defaults. No database bytes are recorded.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from unittest import mock

import pytest
from test_w2_b07_relations_db_frozen import CLOCK, _compact, rows, store

from mir.core import memory_relations as m
from mir.core.engine.memory import relation_facts as f

FIXTURE = (Path(__file__).parent
           / '../native/handoff-packet/tests/fixtures/w2/b07-relations-query.json')
DECLS = [('A', 'depends_on', 'B'), ('B', 'depends_on', 'C'),
         ('A', 'realized_by', 'M'), ('M', 'implemented_in', 'src/a.py::z'),
         ('M', 'implemented_in', 'src/a.py::a'), ('A', 'verified_by', 'tests/a.py')]


def observe(case, tmp):
    try:
        return {'value': _compact(json.loads(json.dumps(case(tmp)).replace(str(tmp), '<tmp>')))}
    except Exception as exc:  # noqa: BLE001 - preserve reference errors
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}


def scenario(kind, arg=None):
    def run(tmp):
        for path in ['src/a.py', 'tests/a.py']:
            (tmp / path).parent.mkdir(exist_ok=True)
            (tmp / path).write_text('pass\n')
        (tmp / '.mir').mkdir()
        db = tmp / '.mir/memory.db'
        if kind == 'path':
            if arg == 'directory':
                db.mkdir()
            elif arg == 'symlink':
                db.symlink_to(tmp / 'src/a.py')
            elif arg == 'regular':
                db.touch()
            elif arg == 'parent':
                (tmp / '.mir').rmdir()
                (tmp / '.mir').symlink_to(tmp / 'src')
                (tmp / 'src/memory.db').touch()
            return str(m._memory_db_path(tmp))
        conn = sqlite3.connect(db)
        try:
            store.apply_migrations(conn)
            for cid in range(1, 10 if kind == 'proofs' else 2):
                path = f'd{cid}.md'
                text = ('---\nstatus: active\nmemory_relations:\n' + ''.join(
                    f'  - [{a}, {p}, {b}]\n' for a, p, b in (
                        DECLS + [('A', 'implemented_in', 'src/a.py::a')]
                        if kind == 'owners' else DECLS)) + '---\n')
                (tmp / path).write_text(text)
                metadata = f.relation_metadata(
                    path=path, project_root=tmp, document_status='active')
                digest = hashlib.sha256(text.encode()).hexdigest()
                conn.execute('INSERT INTO content_items(id,source,text_hash,metadata_json) '
                             'VALUES (?, ?, ?, ?)', (cid, 'self_ingest_md', digest,
                                                     json.dumps(metadata)))
                with mock.patch.object(f, '_now_iso', return_value=CLOCK), \
                        mock.patch.object(store, '_now_iso', return_value=CLOCK):
                    f.reconcile_relation_facts(conn, declarations=f.parse_relation_document(
                        text).declarations, content_item_id=cid, project_root=tmp,
                        source_path=path, document_status='active')
            if kind == 'source':
                raw = {'bom': b'\xef\xbb\xbfx\r\ny\r', 'invalid': b'\xff',
                       'atlimit': b'x' * m._MAX_SOURCE_BYTES,
                       'large': b'x' * (m._MAX_SOURCE_BYTES + 1)}.get(arg, b'x')
                (tmp / 'd1.md').write_bytes(raw)
                if arg == 'missing':
                    (tmp / 'd1.md').unlink()
                if arg == 'unsafe':
                    metadata['path'] = '../outside'
                if arg == 'protected':
                    metadata['path'] = '.env'
                expected = hashlib.sha256(b'x\ny\n' if arg == 'bom' else raw).hexdigest()
                return asdict(m._source_text(tmp, metadata, 'stale' if arg == 'stale' else
                                            expected, (), 0 if arg == 'budget' else len(raw)))
            if kind == 'invalid':
                conn.execute(arg)
            if kind == 'metadata':
                conn.execute('UPDATE content_items SET metadata_json=?',
                             (json.dumps(metadata).ljust(arg),))
            if kind == 'rows':
                conn.executemany('INSERT INTO facts(subject_entity_id,predicate,object_entity_id,'
                                 'polarity,status,scope,project_path,created_from) '
                                 "VALUES (1,'depends_on',2,'asserted','active','project',?,1)",
                                 [(str(tmp),)] * arg)
            if kind == 'owner_rows':  # duplicate the first implemented_in fact
                conn.executemany('INSERT INTO facts(subject_entity_id,predicate,object_entity_id,'
                                 'polarity,status,scope,project_path,created_from) '
                                 'SELECT subject_entity_id,predicate,object_entity_id,polarity,'
                                 'status,scope,project_path,created_from FROM facts '
                                 "WHERE predicate='implemented_in' ORDER BY id LIMIT 1",
                                 [()] * arg)
            conn.commit()
            if kind == 'anchor':
                return m._resolve_query_anchor(conn, tmp, (), arg)
            if kind == 'implemented':
                return [list(r) for r in m._implemented_in_rows(conn, tmp, arg)]
            if kind == 'validate':
                row = list(m._relation_rows(conn, tmp, {'A'}, 'dependencies', limit=1)[0])
                row[arg[0]] = arg[1]
                state = m._SelectionState({}, {}, set())
                edge, reason = m._validate_memory_row(conn, tmp, (), tuple(row), state)
                cached, cached_reason = m._validate_memory_row(conn, tmp, (), tuple(row), state)
                return [edge.as_dict() if edge else None, reason,
                        cached.as_dict() if cached else None, cached_reason, state.source_bytes]
            if kind == 'traverse':
                state = m._SelectionState({}, {}, set())
                edges, notices = m._traverse_memory_rows(conn, tmp, (), [arg[0]], arg[1],
                    depth=arg[2], max_edges=arg[3], state=state)
                return [[e.as_dict() for e in edges], notices, sorted(state.selected_fact_ids),
                        state.source_bytes, state.incomplete, state.proofs_omitted]
            if kind == 'logical':
                return {p: rows(conn, f'PRAGMA {p}') for p in
                        ['journal_mode', 'foreign_keys', 'synchronous']}
        finally:
            conn.close()
        kwargs = {'root': tmp, 'max_bytes': 16000}
        if kind == 'budget':
            with mock.patch.object(m, '_MAX_TOTAL_SOURCE_BYTES', len(text.encode()) + arg):
                return m.query_memory_relations('A', 'implementation', **kwargs)
        if kind == 'owner_rows':
            return m.bundle_memory_relations(['src/a.py'], ['impact', 'dependencies'], **kwargs)
        if kind == 'bundle' or kind == 'owners':
            return m.bundle_memory_relations(*arg[:2], **kwargs, **(arg[2] if len(arg) > 2 else {}))
        if kind == 'query':
            return m.query_memory_relations(arg[0], arg[1], **kwargs, **arg[2])
        return m.query_memory_relations('A', 'dependencies', **kwargs, depth=4)
    return run


CASES = {f'path.{a}': scenario('path', a) for a in
         ['missing', 'directory', 'symlink', 'regular', 'parent']}
CASES.update({f'source.{a}': scenario('source', a) for a in
              ['bom', 'invalid', 'atlimit', 'large', 'missing', 'unsafe',
               'protected', 'stale', 'budget']})
CASES.update({f'anchor.{i}': scenario('anchor', a) for i, a in enumerate(
    ['A', 'missing', 'src/a.py', './src//a.py::z', 'src/A.py', '.env'])})
CASES.update({f'implemented.{i}': scenario('implemented', a) for i, a in enumerate(
    ['src/a.py', 'src/a.py::a', 'missing'])})
CASES.update({f'validate.{i}': scenario('validate', a) for i, a in enumerate(
    [(1, ''), (3, 'missing.py'), (5, 'stale'), (6, '{'), (6, '[]'),
     (2, 'depends_on'), (2, 'realized_by')])})
CASES.update({f'traverse.{p}': scenario('traverse', (a, p, 4, 64)) for p, a in
              [('implementation', 'A'), ('impact', 'src/a.py::z'),
               ('dependencies', 'A'), ('verification', 'A')]})
CASES.update({f'traverse.limit{i}': scenario('traverse', ('A', 'dependencies', d, e))
              for i, (d, e) in enumerate([(0, 64), (1, 64), (2, 64), (4, 1)])})
CASES.update({f'query.{i}': scenario('query', a) for i, a in enumerate([
    ('A', 'implementation', {}), ('A', 'impact', {}), ('A', 'verification', {}),
    ('A', 'dependencies', {}), ('src/a.py', 'impact', {'max_edges': 1}),
    ('missing', 'dependencies', {}), ('A', 'unknown', {}),
    ('A', 'implementation', {'max_bytes': 1024})])})
CASES.update({f'bundle.{i}': scenario('bundle', a) for i, a in enumerate([
    (['A'], ['implementation', 'dependencies', 'verification', 'impact']),
    (['src/a.py'], ['implementation', 'verification']),
    (['missing'], ['impact', 'dependencies']), ([], ['impact', 'dependencies']),
    (['A', 'A'], ['dependencies', 'dependencies']), (['A'], ['unknown', 'impact']),
    (['A'], ['implementation', 'dependencies'], {'max_edges': 1}),
    (['src/a.py'], ['implementation', 'dependencies'], {'max_bytes': 1024})])})
CASES['owners.ambiguous'] = scenario('owners', (['src/a.py'], ['impact', 'dependencies']))
CASES.update({f'rows.{n}': scenario('rows', n) for n in [2046, 2047, 2048]})
# Two implemented_in facts exist already: 2046 more reach the owner row cap, 2047 exceed it.
CASES.update({f'owner_rows.{n}': scenario('owner_rows', n) for n in [2046, 2047]})
CASES.update({f'metadata.{n}': scenario('metadata', n) for n in [65536, 65537]})
CASES.update({f'budget.{n}': scenario('budget', n) for n in [-1, 0, 1]})
CASES.update({f'invalid.{i}': scenario('invalid', sql) for i, sql in enumerate([
    "UPDATE content_items SET text_hash='stale'", "DELETE FROM provenance",
    "UPDATE facts SET predicate='realized_by' WHERE id=1"])})
CASES['proofs'] = scenario('proofs')
CASES['logical'] = scenario('logical')
CASES['limits'] = lambda tmp: [m._MAX_DB_ROWS, m._MAX_METADATA_CHARS,
                               m._MAX_TOTAL_SOURCE_BYTES, m._MAX_PROVENANCE_PER_EDGE]

RECORDS = json.loads(FIXTURE.read_text(encoding='ascii')) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    # Independent lookup on the scenario's filesystem, not the queried endpoint.
    (tmp_path / 'case-probe').write_bytes(b'probe')
    try:
        (tmp_path / 'CASE-PROBE').stat()
        case_sensitive = False
    except FileNotFoundError:
        case_sensitive = True
    expected = RECORDS[name]
    if name == 'anchor.4' and case_sensitive:
        expected = {'error': ['RelationError', 'anchor unavailable endpoint']}
    assert observe(CASES[name], tmp_path) == expected
