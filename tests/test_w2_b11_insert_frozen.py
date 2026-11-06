"""B11 insert oracle captured from unmodified Python; never recapture from a port.

The task brief owns intent. Foreign DB acceptance is a reference quirk, not policy.
Entity objects are seeded through SQL: Triple has only an object_literal field.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from mir.cli import memory
from mir.core.engine.memory import distill as d
from mir.core.engine.memory import store

FIXTURE = Path(__file__).parent / '../native/handoff-packet/tests/fixtures/w2/b11-insert.json'
CLOCK = '2001-02-03T04:05:06.000000+00:00'


def _compact(value):
    """Record strings over 256 characters as their length and SHA-256 to keep records small."""
    if isinstance(value, str) and len(value) > 256:
        return {'len': len(value), 'sha256': hashlib.sha256(value.encode()).hexdigest()}
    if isinstance(value, list):
        return [_compact(item) for item in value]
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()}
    return value


def _rows(conn, query):
    return [list(row) for row in conn.execute(query)]


def _state(conn):
    return {**{table: _rows(conn, f'SELECT * FROM {table} ORDER BY rowid')
               for table in ('entities', 'facts', 'audit_log', 'fact_links')},
            'transaction': conn.in_transaction}


def _schema(conn):
    return {'pragmas': {p: conn.execute(f'PRAGMA {p}').fetchone()[0]
                        for p in ('journal_mode', 'foreign_keys', 'synchronous')},
            'migrations': _rows(conn, 'SELECT * FROM schema_migrations ORDER BY version'),
            'objects': _rows(conn, 'SELECT type, name, tbl_name, sql FROM sqlite_master '
                                  'ORDER BY type, name')}


def _scenario(kind, mode=None):
    def run(tmp):
        conn = store.connect(tmp / 'synthetic.db', load_vec=False).conn
        try:
            with mock.patch.object(store, '_now_iso', return_value=CLOCK), \
                    mock.patch.object(d, '_now_iso', return_value=CLOCK):
                store.apply_migrations(conn)
                result = _execute(conn, tmp, kind, mode)
            return _compact(result)
        finally:
            conn.close()
    return run


def _execute(conn, tmp, kind, mode):
    if kind == 'schema':
        return _schema(conn)
    steps = []
    if kind == 'upsert':
        for slug, typ in [('A', None), ('A', None), ('A', 'first'),
                          ('A', None), ('A', 'changed'), ('B', 'typed'), ('', None)]:
            steps.append([d._upsert_entity(conn, slug, entity_type=typ), _state(conn)])
    elif kind == 'insert':
        conn.execute("INSERT INTO content_items(id, source, text_hash) VALUES (1, 'test', 'h')")
        d._upsert_entity(conn, 'target', entity_type='node')
        for _ in range(2):
            fid = d.insert_triple(conn, d.Triple(
                'A', ' Uses ', mode, source_content_id=1, scope='project',
                project_path='project', polarity='negated', confidence=0.25),
                consent_scope=kind_scope[mode])
            steps.append([fid, _state(conn)])
    elif kind == 'supersede':
        old_time, new_time, old_conf, new_conf = mode[:4]
        conn.execute("INSERT INTO content_items(id, source, text_hash) VALUES (1, 'test', 'h')")
        old = d.insert_triple(conn, d.Triple('A', 'use', 'old', source_content_id=1))
        conn.execute('UPDATE facts SET valid_from=?, confidence=? WHERE id=?',
                     (old_time, old_conf, old))
        if mode[4] == 'entity':
            conn.execute('UPDATE facts SET object_entity_id=subject_entity_id WHERE id=?', (old,))
        if mode[4] == 'inactive':
            conn.execute("UPDATE facts SET status='rejected' WHERE id=?", (old,))
        new_obj = 'old' if mode[4] == 'equal' else 'new'
        new = d.insert_triple(conn, d.Triple('A', 'use', new_obj, source_content_id=1,
                                            is_list_member=mode[4] == 'list'))
        conn.execute('UPDATE facts SET valid_from=?, confidence=? WHERE id=?',
                     (new_time, new_conf, new))
        steps.append(_state(conn))
        for _ in range(2):
            value = d._supersede_existing(
                conn, subject_id=1, predicate=' Uses ', new_object=new_obj,
                new_confidence=new_conf, new_valid_from=new_time, new_fact_id=new,
                current_content_id=1 if mode[4] == 'batch' else None)
            steps.append([list(value), _state(conn)])
    elif kind == 'audit':
        fid = d.insert_triple(conn, d.Triple('A', 'use', 'old'))
        conn.commit()
        steps.append(_state(conn))
        for attempt in range(2):
            new = d.insert_triple(conn, d.Triple('A', 'use', 'new'))
            conn.execute("UPDATE facts SET status='superseded' WHERE id=?", (fid,))
            with contextlib.ExitStack() as stack:
                if mode == 'failure' and attempt == 0:
                    stack.enter_context(mock.patch.object(
                        store, 'audit_append', side_effect=RuntimeError('injected audit failure')))
                value = d._audit_supersede(conn, fid, 'A', 'use')
            steps.append([new, value, _state(conn)])
            conn.commit()
            with sqlite3.connect(tmp / 'synthetic.db') as reader:
                steps.append({'committed': _state(reader)})
    elif kind == 'links':
        subject = d._upsert_entity(conn, 'adr-self')
        d._upsert_entity(conn, 'adr-empty')
        for slug in ('adr-self', 'adr-target'):
            d.insert_triple(conn, d.Triple(slug, 'use', 'first'))
            d.insert_triple(conn, d.Triple(slug, 'use', 'latest'))
        for raw in ('docs/x/adr-missing.md', 'docs/x/adr-empty.md', 'docs/x/adr-self.md',
                    'docs/x/adr-target.md docs/x/adr-target.md', 'docs/x/adr-target.md'):
            steps.append([d._link_cross_refs(conn, raw, subject), _state(conn)])
    return steps


kind_scope = {
    'plain target': 'ephemeral', 'target': 'persistent',
    '<PRIVATE>a\nb</PRIVATE><secret>s</secret><noindex>n</noindex>': 'ephemeral',
    '<private>a\nb</private><SECRET>s</SECRET><noindex>n</noindex>': 'persistent',
    '<private>x</private>': 'unknown',
}


def _cli(foreign=False):
    def run(tmp):
        cwd, target = tmp / 'cwd', tmp / ('other' if foreign else 'cwd')
        for root in {cwd, target}:
            root.mkdir()
            subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
        db = target / 'synthetic.db'
        conn = store.connect(db, load_vec=False).conn
        out, err, steps = io.StringIO(), io.StringIO(), []
        try:
            with mock.patch.object(store, '_now_iso', return_value=CLOCK), \
                    mock.patch.object(d, '_now_iso', return_value=CLOCK), \
                    mock.patch.object(store, '_load_sqlite_vec', return_value=(False, 'off')), \
                    mock.patch.object(store.log, 'disabled', True), \
                    contextlib.chdir(cwd), contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(err):
                store.apply_migrations(conn)
                for _ in range(2):
                    result = observe(lambda _: memory.main([
                        'insert', '--db', str(db), '--subject', 'A', '--predicate', 'uses',
                        '--object', '<private>x</private><secret>s</secret>',
                        '--consent', 'persistent']), tmp)
                    steps.append([result, _state(conn)])
            return {'steps': steps, 'stdout': out.getvalue().replace(str(tmp), '<tmp>'),
                    'stderr': err.getvalue().replace(str(tmp), '<tmp>'),
                    'schema': _compact(_schema(conn))}
        finally:
            conn.close()
    return run


CASES = {
    'schema': _scenario('schema'), 'upsert.sequence': _scenario('upsert'),
    **{f'insert.{i}': _scenario('insert', body) for i, body in enumerate(kind_scope)},
    **{f'supersede.{name}': _scenario('supersede', args) for name, args in {
        'newer': ('a', 'b', 1.0, 0.0, ''), 'older': ('b', 'a', 0.0, 1.0, ''),
        'higher': ('a', 'a', 0.2, 0.8, ''), 'lower': ('a', 'a', 0.8, 0.2, ''),
        'tie': ('a', 'a', 0.5, 0.5, ''), 'null': (None, '', None, 0.5, ''),
        **{m: ('a', 'b', 0.5, 0.5, m) for m in
           ('equal', 'batch', 'list', 'entity', 'inactive')},
    }.items()},
    'audit.success': _scenario('audit'), 'audit.failure_replay': _scenario('audit', 'failure'),
    'links.sequence': _scenario('links'), 'cli.local': _cli(), 'cli.foreign': _cli(True),
}


def observe(case, tmp):
    try:
        return {'value': case(tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze reference errors
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}


RECORDS = json.loads(FIXTURE.read_text(encoding='ascii')) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
