"""B12 oracle captured from unmodified Python; never recapture from a port.

The task brief owns intent. Git state is real; absent helpers stay absent.
Fixed clocks and normalized paths precede hashing and long-string compaction.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sqlite3
import subprocess
from dataclasses import asdict
from pathlib import Path
from unittest import mock

import pytest

from mir.cli import memory
from mir.core.engine.memory import distill as d
from mir.core.engine.memory import relation_facts as r
from mir.core.engine.memory import store

FIXTURE = (Path(__file__).parent /
           '../native/handoff-packet/tests/fixtures/w2/b12-reconcile-missing.json')
CLOCK = '2001-02-03T04:05:06.000000+00:00'


def _rows(conn, query):
    return [list(row) for row in conn.execute(query)]


def _digest(value):
    body = json.dumps(value, ensure_ascii=True, sort_keys=True).encode('ascii')
    return hashlib.sha256(body).hexdigest()


def _normalize(value, tmp):
    return json.loads(json.dumps(value, ensure_ascii=True).replace(str(tmp), '<tmp>'))


def _compact(value):
    if isinstance(value, str) and len(value) > 256:
        return {'length': len(value), 'sha256': hashlib.sha256(value.encode()).hexdigest()}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items()}
    return value


def _state(conn, tmp):
    schema = {'migrations': _rows(conn, 'SELECT * FROM schema_migrations ORDER BY version'),
              'objects': _rows(conn, 'SELECT type, name, tbl_name, sql FROM sqlite_master '
                                    'ORDER BY type, name')}
    return _compact(_normalize({
        **{table: _rows(conn, f'SELECT * FROM {table} ORDER BY rowid')
           for table in ('content_items', 'entities', 'facts', 'audit_log', 'fact_links',
                         'provenance', 'fact_documents')},
        'schema_sha256': _digest(_normalize(schema, tmp)),
        'pragmas': {p: conn.execute(f'PRAGMA {p}').fetchone()[0]
                    for p in ('journal_mode', 'foreign_keys', 'synchronous')},
        'transaction': conn.in_transaction}, tmp))


def _scenario(kind, cli=False):
    def run(tmp):
        env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
               'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
               'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid',
               'GIT_AUTHOR_DATE': '2001-02-03T04:05:06+00:00',
               'GIT_COMMITTER_DATE': '2001-02-03T04:05:06+00:00'}

        def git(*args):
            return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', *args], cwd=tmp,
                                  env=env, check=True, capture_output=True, text=True).stdout

        git('init', '-b', 'fixture')
        conn = store.connect(tmp / 'synthetic.db', load_vec=False).conn
        try:
            with contextlib.ExitStack() as stack:
                for module in (store, d, r):
                    stack.enter_context(mock.patch.object(module, '_now_iso', return_value=CLOCK))
                stack.enter_context(contextlib.chdir(tmp))
                stack.enter_context(mock.patch.object(store, '_load_sqlite_vec',
                                                      return_value=(False, 'off')))
                stack.enter_context(mock.patch.object(store.log, 'disabled', True))
                store.apply_migrations(conn)
                path = tmp / ('docs/decisions/nested/adr-main.md' if kind == 'nested'
                              else 'docs/decisions/adr-main.md')
                other = tmp / 'docs/decisions/adr-other.md'
                path.parent.mkdir(parents=True)
                other.parent.mkdir(parents=True, exist_ok=True)
                ingested = []
                for source, target in ((path, 'CAP-A'), (other, 'CAP-B')):
                    source.write_text('---\ntitle: source\nstatus: accepted\nmemory_relations:\n'
                                      f'  - [REQ-1, realized_by, {target}]\n---\nbody\n',
                                      encoding='ascii')
                    ingested.append(asdict(d.ingest_markdown_file(
                        source, conn=conn, project_root=tmp, whitelist_globs=('**',))))
                if kind == 'ignored':
                    (tmp / '.gitignore').write_text(path.relative_to(tmp).as_posix() + '\n')
                elif kind not in ('never_present', 'never_missing'):
                    git('add', 'docs')
                    git('commit', '-m', 'fixture sources')
                if kind == 'deleted_untracked':
                    git('rm', str(path.relative_to(tmp)))
                elif kind == 'renamed':
                    git('mv', str(path.relative_to(tmp)), 'docs/decisions/adr-renamed.md')
                elif kind in ('deleted_tracked', 'never_missing', 'nested', 'outer_tx'):
                    path.unlink()
                steps = [{'ingest': ingested, 'state': _state(conn, tmp),
                          'tracked': git('ls-files', '--', str(path.relative_to(tmp))),
                          'exists': path.exists()}]
                for dry in (True, False, False):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        if cli:
                            args = ['reconcile-missing', '--db', str(tmp / 'synthetic.db')]
                            if kind != 'nested':
                                args += ['--project-root', str(tmp)]
                            if dry:
                                args += ['--dry-run']
                            result = memory.main(args)
                        else:
                            if kind == 'outer_tx' and not dry:
                                conn.execute('BEGIN')
                            result = d.reconcile_missing_source(
                                conn, project_root=None if kind == 'nested' else tmp, dry_run=dry)
                            if kind == 'outer_tx' and not dry:
                                result = [result, conn.in_transaction]
                                conn.commit()
                    with sqlite3.connect(tmp / 'synthetic.db') as reader:
                        committed = _state(reader, tmp)
                    steps.append({'dry_run': dry, 'result': result, 'stdout': out.getvalue(),
                                  'stderr': err.getvalue(), 'state': _state(conn, tmp),
                                  'committed': committed})
                return _compact(_normalize(steps, tmp))
        finally:
            conn.close()
    return run


CASES = {f'reconcile.{kind}': _scenario(kind) for kind in (
    'present_tracked', 'deleted_tracked', 'deleted_untracked', 'never_present',
    'never_missing', 'renamed', 'ignored', 'nested', 'outer_tx')}
CASES.update({f'cli.{kind}': _scenario(kind, cli=True)
              for kind in ('deleted_tracked', 'never_present', 'nested')})
CASES['git_tracks.availability'] = lambda tmp: hasattr(d, '_git_tracks')


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
