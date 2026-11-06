"""B30 phase-2 oracle captured from unmodified Python, never from a port."""
import contextlib
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from mir.cli import bootstrap_adoption as M

FIXTURE = (Path(__file__).parents[1] /
           'native/handoff-packet/tests/fixtures/w2/b30-adoption-phase2.json')
CASES = {}
def observe(case, tmp):
    try:
        calls = []
        def run(argv, **kwargs):
            calls.append([argv, kwargs.get('cwd')])
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        with mock.patch.object(M.subprocess, 'run', side_effect=run):
            value = json.loads(json.dumps(case(tmp)).replace(str(tmp), '<tmp>'))
        assert not calls, calls
        text = json.dumps(value, sort_keys=True)
        return {'value': value if len(text) <= 512 else
                {'len': len(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()}}
    except Exception as exc:  # noqa: BLE001 - freeze reference errors
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}
def put(tmp, name, body):
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body if isinstance(body, bytes) else body.encode())

def content(tmp, mode, change):
    raw = dict(schema_version=1, profile='content_workspace',
               archives=[dict(classification='notes', path='notes')], scan={'unclassified': []})
    raw.update(change)
    (tmp / 'notes').mkdir()
    if mode != 'absent':
        put(tmp, 'notes/a.md', 'searchable')
    if mode == 'uncovered':
        put(tmp, 'other/a.md', 'searchable')
    if mode != 'missing':
        put(tmp, 'config/content-onboarding.json', '{' if mode == 'invalid' else json.dumps(raw))
    with (mock.patch.object(M, '_scan_content_candidates', side_effect=ValueError('scan denied'))
          if mode == 'scan_error' else contextlib.nullcontext()):
        return M._validate_content_onboarding(tmp, 'code_app' if mode == 'profile' else
                                              'content_workspace')

QUERY = dict(archive_slug='notes', query='adr-99', expected_path='a.md')
DDL = ('CREATE TABLE external_archives(id INTEGER PRIMARY KEY, slug, root_path);'
       'CREATE TABLE external_documents(id INTEGER PRIMARY KEY, archive_id, relative_path);'
       'CREATE TABLE external_chunks(id INTEGER PRIMARY KEY, document_id);'
       'CREATE VIRTUAL TABLE external_chunks_fts USING fts5(body);')
def memory(tmp, mode, queries):
    path = tmp / '.mir/memory.db'
    path.parent.mkdir()
    if mode == 'corrupt':
        path.write_bytes(b'not a database')
    elif mode != 'missing':
        with sqlite3.connect(path) as db:
            if mode not in ('schema', 'unreadable'):
                db.executescript(DDL)
                if mode.startswith('drop_'):
                    db.execute('DROP TABLE ' + mode[5:])
                elif mode == 'wrong_columns':
                    db.execute('ALTER TABLE external_documents RENAME COLUMN archive_id TO wrong')
                elif mode != 'empty':
                    db.executescript("INSERT INTO external_archives VALUES(1,'notes','archive');"
                        "INSERT INTO external_documents VALUES(1,1,'a.md');"
                        "INSERT INTO external_chunks VALUES(1,1);"
                        "INSERT INTO external_chunks_fts(rowid,body) "
                        "VALUES(1,'adr 99 alpha beta');")
    with (mock.patch.object(M.sqlite3, 'connect', side_effect=sqlite3.OperationalError('denied'))
          if mode == 'unreadable' else contextlib.nullcontext()):
        result = M._validate_memory(tmp, {'queries': queries})
    if mode in ('missing', 'corrupt', 'unreadable'):
        return result
    with sqlite3.connect(path) as db:
        state = [db.execute('PRAGMA ' + key).fetchall() for key in
                 ('journal_mode', 'user_version', 'schema_version')]
        state.append(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master '
                                'ORDER BY type,name,tbl_name,sql').fetchall())
    return [result, state]

def phase(tmp, target, value):
    coverage = {k: dict(total=1, filled=1, derived=0, na=0, tbd=0) for k in M._LAYER_KEYS}
    ready = dict(ready=1, incomplete=0, blocked=0)
    reviews = {k: dict(status='pass', evidence_paths=['proof'], verification='Checked')
               for k in M._REVIEW_KEYS}
    docs = {'meta': dict(coverage=coverage, ai_ready=ready), 'gaps': {'gaps': []},
            'review': {'reviews': reviews}}
    surface = dict(coverage=json.loads(json.dumps(coverage)), ai_ready=dict(ready), open_gaps=0,
                   full_review=dict.fromkeys(M._REVIEW_KEYS, 'pass'),
                   native_evidence=dict(format='mir_spec_yaml_v1', meta_path='meta',
                       gaps_path='gaps', review_path='review', coverage_key='coverage'),
                   evidence_paths=['meta', 'gaps', 'review', 'proof'])
    objects = {'surface': surface, **docs}
    if target == 'shape':
        if value == 'completeness':
            docs['meta']['completeness'] = docs['meta'].pop('coverage')
            surface['native_evidence']['coverage_key'] = value
        else:
            for rows in [coverage, surface['coverage']]:
                for row in rows.values():
                    row.update(filled=0, derived=1)
    elif target.startswith('file.'):
        pass
    else:
        keys = target.split('.')
        obj = objects
        for key in keys[:-1]:
            obj = obj[key]
        obj[keys[-1]] = value
    for name in docs:
        put(tmp, name, json.dumps(objects[name]))
    put(tmp, 'proof', 'Verified')
    if target.startswith('file.'):
        name = target.split('.')[1]
        if value is None:
            (tmp / name).unlink()
        else:
            put(tmp, name, value)
    return M._validate_phase2(tmp, surface)

for mode, change in [('valid', {}), ('absent', {}), ('uncovered', {}), ('scan_error', {}),
        ('missing', {}), ('invalid', {}), ('profile', {}), ('schema', {'schema_version': 2}),
        ('profile_field', {'profile': 'code_app'}), ('archives_empty', {'archives': []}),
        ('archives_type', {'archives': {}}), ('archive_object', {'archives': [1]}),
        ('classification', {'archives': [{'classification': 'TODO', 'path': 'notes'}]}),
        ('path', {'archives': [{'classification': 'notes', 'path': '../escape'}]}),
        ('archive_missing', {'archives': [{'classification': 'notes', 'path': 'gone'}]}),
        ('duplicate', {'archives': [dict(classification='notes', path='notes')] * 2}),
        ('overlap', {'archives': [dict(classification='notes', path='notes'),
                                dict(classification='child', path='notes/a.md')]}),
        ('overlap_reversed', {'archives': [dict(classification='child', path='notes/a.md'),
                                         dict(classification='notes', path='notes')]}),
        ('scan_type', {'scan': []}), ('unclassified', {'scan': {'unclassified': ['x']}})]:
    CASES[f'content.{mode}'] = lambda tmp, m=mode, c=change: content(tmp, m, c)
for mode in ['valid', 'missing', 'corrupt', 'unreadable', 'schema', 'wrong_columns', 'empty'] + [
        'drop_' + name for name in ['external_archives', 'external_documents',
                                   'external_chunks', 'external_chunks_fts']]:
    CASES[f'memory.{mode}'] = lambda tmp, m=mode: memory(tmp, m, [QUERY])
for name, queries in [('none', None), ('empty', []), ('type', 'query'), ('object', [1]),
        ('fields', [{}]), ('query', [{**QUERY, 'query': 'TODO'}]),
        ('path', [{**QUERY, 'expected_path': ''}]),
        ('wrong_archive', [{**QUERY, 'archive_slug': 'other'}]),
        ('wrong_path', [{**QUERY, 'expected_path': 'other.md'}]), ('mixed', [QUERY, 1])]+[
        ('sanitize_' + str(i), [{**QUERY, 'query': q}]) for i, q in enumerate(
            ['"alpha beta"', 'alpha OR beta', '---', '\u03b1', 'alpha"beta', 'alpha:beta'])]:
    CASES[f'memory.{name}'] = lambda tmp, q=queries: memory(tmp, 'valid', q)
# The 'empty' mode above shares its name with the empty query list; keep both observed.
CASES['memory.mode_empty'] = lambda tmp: memory(tmp, 'empty', [QUERY])
PHASE = [('surface.open_gaps', 0), ('surface.coverage', None), ('surface.coverage', {}),
         ('surface.coverage.l1', []), ('surface.coverage.l1.total', 0),
         ('surface.coverage.l1.total', 2), ('surface.coverage.l1.tbd', 1),
         ('surface.ai_ready', None), ('surface.ai_ready.ready', 0),
         ('surface.ai_ready.blocked', 1), ('surface.open_gaps', 1),
         ('surface.full_review', {}), ('surface.full_review.memory', 'fail'),
         ('surface.native_evidence', None), ('surface.native_evidence.extra', 1),
         ('surface.native_evidence.format', 'other'),
         ('surface.native_evidence.coverage_key', 'bad'),
         ('surface.native_evidence.meta_path', '../escape'), ('surface.evidence_paths', []),
         ('meta.coverage', []), ('meta.coverage.l1', None), ('meta.coverage.l1.filled', 2),
         ('meta.ai_ready.ready', 2), ('gaps.gaps', {}), ('gaps.gaps', [1]),
         ('review.reviews', {}), ('review.reviews.memory', {}),
         ('review.reviews.memory.status', 'fail'), ('review.reviews.memory.evidence_paths', []),
         ('review.reviews.memory.evidence_paths', ['proof', 'proof']),
         ('review.reviews.memory.evidence_paths', ['../escape']),
         ('review.reviews.memory.evidence_paths', ['undeclared']),
         ('review.reviews.memory.verification', 'TODO'), ('file.proof', ''),
         ('file.proof', 'TODO'), ('file.proof', None), ('file.proof', b'\xff'),
         ('file.meta', None), ('file.meta', b'\xff'), ('file.meta', '['), ('file.meta', '[]')]
PHASE += [(f'surface.coverage.l1.{k}', True) for k in M._COUNT_KEYS]
PHASE += [('surface.coverage.l1.total', v) for v in [-1, '1', None]]
PHASE += [('shape', v) for v in ['completeness', 'derived']]
PHASE += [(f'surface.ai_ready.{k}', v) for k in ['ready', 'incomplete', 'blocked']
          for v in [True, -1]]
PHASE += [('review.reviews.memory.evidence_paths', v) for v in [None, 'proof', [1]]]
for i, (target, value) in enumerate(PHASE):
    CASES[f'phase2.{i:02d}.{target}'] = lambda tmp, t=target, v=value: phase(tmp, t, v)
RECORDS = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}
def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)

@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
