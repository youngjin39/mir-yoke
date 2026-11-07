"""B30 bootstrap oracle captured from unmodified Python, never from a port."""
import contextlib
import hashlib
import io
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from mir.cli import bootstrap as M

FIXTURE = (Path(__file__).parents[1] /
           'native/handoff-packet/tests/fixtures/w2/b30-bootstrap-surfaces.json')
CASES = {}
def observe(case, tmp):
    try:
        calls = []
        def run(argv, **kw):
            calls.append([argv, str(kw.get('cwd', '')), kw.get('input')])
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
    path.write_text(body, encoding='utf-8')
    return path
def architecture(tmp, mode):
    coverage = {k: dict(total=n, filled=n, derived=0, na=0, tbd=0)
                for k, n in [('l1', 1), ('l2', 1), ('l3', 9), ('l4', 10)]}
    coverage['ai_ready'] = dict(ready=1, incomplete=0, blocked=0)
    evidence = dict(schema_version=2, sequence=list(M._ARCHITECTURE_SEQUENCE),
                    capability_commit='abc', outputs=list(M._ARCHITECTURE_OUTPUTS),
                    coverage=coverage, open_gaps=0, full_review=dict.fromkeys(
                        'project_structure memory discoverability requirements organization'
                        .split(), 'pass'))
    docs = dict(zip(M._ARCHITECTURE_OUTPUTS, ['Complete', 'requirements: [{status: ready}]',
                    'nodes: [a]\nedges: []', 'gaps: []'], strict=True))
    if mode.startswith('field:'):
        evidence[mode[6:]] = None
    if mode == 'review_partial':
        evidence['full_review']['memory'] = 'fail'
    if mode.startswith('count:'):
        coverage['l3'][mode[6:]] = -1 if mode.endswith('derived') else 1
    coverage.update({'l2': dict(total=0, filled=0, derived=0, na=0, tbd=0)}
                    if mode == 'zero' else {'l4': None} if mode == 'layer' else {})
    coverage['ai_ready'].update({'blocked': 1} if mode == 'ai_blocked' else {})
    if mode == 'ai_invalid':
        coverage['ai_ready'] = {}
    if mode.startswith('doc:'):
        _, name, body = mode.split(':', 2)
        docs['spec/' + name] = body
    for name, body in docs.items():
        put(tmp, name, body)
    path = put(tmp, 'spec/bootstrap-evidence.json', json.dumps(evidence))
    lock = put(tmp, '.mir/capability-lock.json', json.dumps({'source': {'commit': 'abc'}}))
    if mode in ('missing', 'linked'):
        path.unlink()
        if mode == 'linked':
            path.symlink_to(lock)
    if mode == 'list':
        path.write_text('[]')
    if mode in ('lock_missing', 'lock_bad', 'lock_list', 'lock_source'):
        lock.unlink()
        if mode != 'lock_missing':
            lock.write_text({'lock_bad': '{', 'lock_list': '[]', 'lock_source': '{}'}[mode])
    if mode in ('output_missing', 'output_linked'):
        out = tmp / 'spec/STATE.md'
        out.unlink()
        if mode == 'output_linked':
            out.symlink_to(lock)
    return M._validate_architecture_evidence(tmp)
SURFACES = ['CLAUDE.md', 'AGENTS.md', '.claude/settings.json', '.codex/config.toml',
            '.codex/hooks.json', '.ai-harness/deny-list.yaml',
            '.claude/agents/main-orchestrator.md', '.codex/agents/main-orchestrator.toml',
            'config/sub-agent-policy.json', 'config/capability-sources.json',
            'config/adopter-boundary.json', 'config/adopter-payload.json', '.claude/hooks/a.sh']
def surfaces(tmp, mode):
    for name in SURFACES:
        put(tmp, name, '{"hooks":{"Stop":[]}}' if name.endswith('.json') else '')
    if mode.startswith('missing:'):
        (tmp / mode[8:]).unlink()
    if mode.startswith('json:'):
        (tmp / mode[5:]).write_text('{')
    if mode in ('hooks', 'settings_list'):
        (tmp / '.claude/settings.json').write_text('{}' if mode == 'hooks' else '[]')
    if mode in ('toml', 'mixed'):
        (tmp / '.codex/config.toml').write_text('[' if mode == 'toml' else
                                              'sandbox_mode="x"\ndefault_permissions="x"')
    with mock.patch.object(M.shutil, 'which', side_effect=lambda name:
                           None if mode == 'runtime' else '/tools/' + name):
        return M._validate_surfaces(tmp)
def atomic(tmp, kind, fail):
    path = put(tmp, 'nested/value', 'old')
    with (mock.patch.object(M.os, 'replace', side_effect=OSError('replace denied'))
          if fail else contextlib.nullcontext()):
        result = observe(lambda _: M._atomic_write_json(path, {'z': '\u00e9', 'a': 1})
                         if kind == 'json' else M._atomic_write_text(path, 'line\n\u00e9'), tmp)
    return [result, path.read_bytes().hex(), sorted(p.name for p in path.parent.iterdir())]
def state(path):
    with sqlite3.connect(path) as db:
        return [[db.execute('PRAGMA ' + k).fetchall() for k in
                 ('journal_mode', 'user_version', 'schema_version')],
                (db.execute('SELECT * FROM schema_migrations ORDER BY version').fetchall()
                 if db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'")
                 .fetchone() else []),
                db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master '
                           'ORDER BY type,name,tbl_name,sql').fetchall()]
def stage(tmp, mode):
    path = tmp / 'db/source.db'
    path.parent.mkdir()
    source = sqlite3.connect(path) if mode != 'missing' else None
    try:
        if source:
            source.execute('PRAGMA journal_mode=' + ('WAL' if mode == 'wal' else 'DELETE'))
            source.executescript('PRAGMA user_version=7; CREATE TABLE schema_migrations'
                                 '(version INTEGER, name TEXT);'
                                 "INSERT INTO schema_migrations VALUES(1,'seed');")
        staged = M._stage_memory_db(path)
        if source:
            before = [state(path), state(staged)]
            with sqlite3.connect(staged) as db:
                db.execute("INSERT INTO schema_migrations VALUES(2,'isolated')")
            return [before, state(path), state(staged)]
        return [staged.parent == path.parent, staged != path, staged.is_file(), state(staged)]
    finally:
        if source:
            source.close()
def memory(tmp, mode):
    path = tmp / 'synthetic.db'
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE external_archives(id, slug);'
                         'CREATE TABLE external_documents(id, archive_id, relative_path);'
                         'CREATE TABLE external_chunks(id, document_id);'
                         'CREATE VIRTUAL TABLE external_chunks_fts USING fts5(body);'
                         "INSERT INTO external_archives VALUES(1,'demo-content');"
                         "INSERT INTO external_documents VALUES(1,1,'a.md');"
                         'INSERT INTO external_chunks VALUES(1,1);'
                         "INSERT INTO external_chunks_fts(rowid,body) VALUES(1,'alpha');")
        if mode in ('archive', 'path', 'no_hit'):
            db.execute({'archive': "UPDATE external_archives SET slug='other'",
                        'path': "UPDATE external_documents SET relative_path='b.md'",
                        'no_hit': 'DELETE FROM external_chunks_fts'}[mode])
    archive = dict(classification='notes', path='notes', acceptance=dict(
        query='"' if mode == 'fts_error' else 'alpha', expected_path='a.md'))
    if mode in ('invalid', 'absent'):
        archive['acceptance'] = {} if mode == 'invalid' else None
    with mock.patch.object(M.store, '_load_sqlite_vec', return_value=(False, 'disabled')):
        return M._validate_content_memory_acceptance(tmp, path, 'demo', {'archives':
            [] if mode == 'empty' else [None] if mode == 'entry' else [archive]})
def projection(tmp, mode):
    path = tmp / 'synthetic.db'
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE entities(id,slug); CREATE TABLE content_items(id,source,'
                         'metadata_json); CREATE TABLE facts(id,subject_entity_id,predicate,'
                         'object_literal,status,created_from);')
    if mode != 'missing':
        for name in ('docs/memory-map.md', 'tasks/lessons.md'):
            put(tmp, name, 'prefix\n' + ('<!-- mir:generated:start -->old<!-- mir:generated:end -->'
                                       '\nsuffix' if mode == 'markers' else 'kept\n'))
    with mock.patch.object(M.store, '_load_sqlite_vec', return_value=(False, 'disabled')):
        updates = M._build_projection_updates(tmp, path)
        return {str(k.relative_to(tmp)): v for k, v in updates.items()}
def emit(tmp, status, as_json):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        M._emit(SimpleNamespace(json=as_json), dict(status=status, errors=['blocked'], z='\u00e9'))
    return out.getvalue()
for mode in ['ok', 'missing', 'linked', 'list', 'lock_missing', 'lock_bad',
             'lock_list', 'lock_source', 'layer', 'zero', 'ai_invalid', 'ai_blocked',
             'output_missing', 'output_linked'] + ['field:' + k for k in
             ['schema_version', 'sequence', 'capability_commit', 'outputs', 'coverage',
              'full_review', 'open_gaps']] + ['count:' + k for k in ['total', 'filled', 'derived',
              'tbd']] + ['doc:' + n + ':' + b for n, b in [('STATE.md', ''), ('STATE.md', 'TBD'),
              ('gaps.yaml', '['), ('gaps.yaml', '{}'), ('gaps.yaml', 'gaps: [1]'),
              ('index.yaml', '['), ('index.yaml', '[]'), ('index.yaml', '{}'),
              ('index.yaml', 'requirements: []'), ('graph.yaml', '['), ('graph.yaml', '[]'),
              ('graph.yaml', '{}')]]:
    CASES['architecture.' + mode] = lambda tmp, m=mode: architecture(tmp, m)
for mode in ['review_partial'] + ['doc:STATE.md:' + b for b in [
        'de\u017fcribe', 'descr\u0130be', 'descr\u0131be', '\u0301tbd', 'tbd1', '\u00b2tbd',
        '\x0b\x0c']]:
    CASES['architecture.' + mode] = lambda tmp, m=mode: architecture(tmp, m)
for mode in ['ok', 'hooks', 'settings_list', 'toml', 'mixed', 'runtime'] + [
        'missing:' + p for p in SURFACES] + ['json:' + p for p in SURFACES if p.endswith('.json')]:
    CASES['surfaces.' + mode] = lambda tmp, m=mode: surfaces(tmp, m)
def stage_pages(tmp):
    path = tmp / 'db/source.db'
    path.parent.mkdir()
    source = sqlite3.connect(path)
    source.executescript('CREATE TABLE t(x INTEGER, v TEXT); WITH RECURSIVE c(x) AS '
                         '(SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 400) '
                         "INSERT INTO t SELECT x, printf('%0300d', x) FROM c; "
                         'DELETE FROM t WHERE x % 3 > 0 OR x < 200;')
    source.close()
    staged = M._stage_memory_db(path)
    with contextlib.closing(sqlite3.connect(staged)) as db:
        return [db.execute('PRAGMA ' + k).fetchall() for k in ('page_count', 'freelist_count')] + [
            db.execute('SELECT count(*), min(rowid), max(rowid), sum(rowid) FROM t').fetchall()]
CASES['stage.pages'] = stage_pages
for body in [None, '{', '{"a":1}']:
    CASES['json.' + str(body)] = lambda tmp, b=body: M._validate_json_file(
        tmp / 'value' if b is None else put(tmp, 'value', b))
for kind in ('json', 'text'):
    for fail in (False, True):
        CASES[f'atomic.{kind}.{fail}'] = lambda tmp, k=kind, f=fail: atomic(tmp, k, f)
for group, call, modes in [('stage', stage, ['missing', 'delete', 'wal']),
        ('acceptance', memory, ['ok', 'empty', 'entry', 'absent', 'invalid', 'archive', 'path',
                                'no_hit', 'fts_error']),
        ('projection', projection, ['missing', 'append', 'markers'])]:
    for mode in modes:
        CASES[group + '.' + mode] = lambda tmp, m=mode, f=call: f(tmp, m)
for status in ('ready', 'restart_required', 'blocked'):
    for as_json in (False, True):
        CASES[f'emit.{status}.{as_json}'] = lambda tmp, s=status, j=as_json: emit(tmp, s, j)
RECORDS = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}
def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)
@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
