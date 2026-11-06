"""B11 ingest oracle from unmodified Python; never recapture from a port.

The task brief owns intent. Ingest has no consent argument: freeze its default.
State includes committed rows after failures; source paths are normalized in-case.
"""
from __future__ import annotations

import contextlib
import io
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from unittest import mock

import pytest

from mir.cli import memory
from mir.core.engine.memory import distill as d
from mir.core.engine.memory import relation_facts as r
from mir.core.engine.memory import store

FIXTURE = Path(__file__).parent / '../native/handoff-packet/tests/fixtures/w2/b11-ingest.json'
CLOCK = '2001-02-03T04:05:06.000000+00:00'


def _rows(conn, query):
    return [list(row) for row in conn.execute(query)]


def _state(conn):
    return {**{table: _rows(conn, f'SELECT * FROM {table} ORDER BY rowid')
               for table in ('content_items', 'entities', 'facts', 'audit_log', 'fact_links',
                             'provenance', 'fact_documents')},
            'transaction': conn.in_transaction}


def _schema(conn):
    return {'pragmas': {p: conn.execute(f'PRAGMA {p}').fetchone()[0]
                        for p in ('journal_mode', 'foreign_keys', 'synchronous')},
            'migrations': _rows(conn, 'SELECT * FROM schema_migrations ORDER BY version'),
            'objects': _rows(conn, 'SELECT type, name, tbl_name, sql FROM sqlite_master '
                                  'ORDER BY type, name')}


def _scenario(kind, mode=''):
    def run(tmp):
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
                result = _schema(conn) if kind == 'schema' else _execute(conn, tmp, kind, mode)
            return json.loads(json.dumps(result, ensure_ascii=True).replace(str(tmp), '<tmp>'))
        finally:
            conn.close()
    return run


def _execute(conn, tmp, kind, mode):
    path = tmp / 'docs/decisions/adr-main.md'
    path.parent.mkdir(parents=True)
    steps = []

    def ingest(body=None, *, globs=d.DEFAULT_WHITELIST, fail='', outer=False):
        if body is not None:
            path.write_text(body, encoding='utf-8')
        if outer:
            conn.execute('BEGIN')
        with contextlib.ExitStack() as stack:
            if fail == 'content':
                stack.enter_context(mock.patch.object(
                    d, 'reconcile_relation_facts', side_effect=RuntimeError('after content')))
            if fail == 'fact':
                original = d.insert_triple

                def broken(*args, **kwargs):
                    original(*args, **kwargs)
                    raise RuntimeError('after fact')

                stack.enter_context(mock.patch.object(d, 'insert_triple', side_effect=broken))
            result = observe(lambda _: asdict(d.ingest_markdown_file(
                path, conn=conn, project_root=tmp, whitelist_globs=globs)), tmp)
        with sqlite3.connect(tmp / 'synthetic.db') as reader:
            steps.append([result, _state(conn), {'committed': _state(reader)}])
        if outer:
            conn.commit()

    def fm(text):
        return f'---\n{text}\n---\nbody\n'

    if kind == 'paths':
        path = tmp / mode
        path.parent.mkdir(parents=True, exist_ok=True)
        ingest(fm('title: first'), globs=('**',) if '_archive' in mode else d.DEFAULT_WHITELIST)
        ingest(fm('title: changed'), globs=('**',) if '_archive' in mode else d.DEFAULT_WHITELIST)
    elif kind == 'frontmatter':
        ingest(mode)
        ingest()
    elif kind == 'sequence':
        ingest(fm('type: decision\nkeywords: [a, b]\nuse: old\nstatus: accepted'))
        ingest()
        ingest(fm('type: changed\nkeywords:\n  - b\n  - c\nuse: new\nstatus: superseded'))
        ingest()
    elif kind == 'winners':
        ingest(fm('use: old'))
        vf, confidence = mode
        conn.execute('UPDATE facts SET valid_from=?, confidence=?', (vf, confidence))
        conn.commit()
        ingest(fm('uses: new'))
        ingest()
    elif kind == 'relations':
        target = tmp / 'tests/check.py'
        target.parent.mkdir()
        target.write_text('# fixture\n', encoding='ascii')
        for status, edge in [('accepted', 'CAP-A'), ('accepted', 'CAP-B'),
                             ('proposed', 'CAP-B'), ('archived', 'CAP-B'),
                             ('accepted', 'CAP-B')]:
            ingest(fm(f'status: {status}\nmemory_relations:\n'
                      f'  - [REQ-1, realized_by, {edge}]\n'
                      '  - [REQ-1, verified_by, tests/check.py]'))
            ingest()
        ingest(fm('title: removed'))
        ingest(fm('memory_relations: [[REQ-1, depends_on, CAP-A]]'))
        ingest('plain body\n')
        ingest()
    elif kind == 'links':
        target = path.with_name('adr-target.md')
        target.write_text(fm('title: target'), encoding='utf-8')
        steps.append(asdict(d.ingest_markdown_file(target, conn=conn, project_root=tmp)))
        ingest(fm('title: source') + 'docs/decisions/adr-target.md docs/decisions/adr-target.md\n'
               'docs/decisions/adr-main.md docs/decisions/adr-missing.md\n')
        ingest()
    elif kind == 'failure':
        ingest(fm('use: old'))
        ingest(fm('use: new'), fail=mode, outer=False)
        ingest(fail=mode, outer=True)
        ingest()
        ingest()
    elif kind == 'cli':
        path = tmp / ('notes.md' if mode == 'override' else 'docs/decisions/adr-main.md')
        path.write_text(fm('title: <private>p</private><secret>s</secret><noindex>n</noindex>')
                        if mode != 'invalid' else fm('memory_relations: broken'), encoding='utf-8')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            for _ in range(2):
                args = ['ingest-md', str(path), '--db', str(tmp / 'synthetic.db')]
                if mode == 'override':
                    args += ['--whitelist', '*.md']
                result = observe(lambda _, args=args: memory.main(args), tmp)
                steps.append([result, _state(conn)])
        steps.append({'stdout': out.getvalue(), 'stderr': err.getvalue()})
    return steps


def _missing_via_link(tmp):
    # Path.resolve(strict=False) still resolves the symlinked parent of a missing file.
    real = tmp / 'real'
    (real / 'docs/decisions').mkdir(parents=True)
    (tmp / 'link').symlink_to(real, target_is_directory=True)
    conn = store.connect(tmp / 'synthetic.db', load_vec=False).conn
    try:
        store.apply_migrations(conn)
        path = tmp / 'link/docs/decisions/adr-gone.md'
        return asdict(d.ingest_markdown_file(path, conn=conn, project_root=real))
    finally:
        conn.close()


def _two_roots(tmp):
    # A declared source dedups per project root; an undeclared one dedups by path only.
    conn = store.connect(tmp / 'synthetic.db', load_vec=False).conn
    out = []
    try:
        store.apply_migrations(conn)
        for root, body in [('a', 'memory_relations: [[REQ-1, depends_on, CAP-A]]')] * 2 + [
                ('b', 'memory_relations: [[REQ-1, depends_on, CAP-A]]'),
                ('c', 'title: same'), ('d', 'title: same')]:
            path = tmp / root / 'docs/decisions/adr-main.md'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'---\n{body}\n---\n', encoding='utf-8')
            result = d.ingest_markdown_file(path, conn=conn, project_root=tmp / root)
            out.append([root, asdict(result)])
        return out
    finally:
        conn.close()


CASES = {
    'schema': _scenario('schema'),
    **{f'paths.{i}': _scenario('paths', p) for i, p in enumerate((
        'notes.md', 'docs/_archive/adr-main.md', 'docs/_archive/nested/adr-main.md'))},
    **{f'frontmatter.{i}': _scenario('frontmatter', body) for i, body in enumerate((
        '', 'no frontmatter', '---\n---\n', '---\nbroken\n',
        '---\n: bad\nignore\nblank:\n---\n',
        '---\nprivate: <PRIVATE>p</PRIVATE><SECRET>s</SECRET><noindex>n</noindex>\n---\n',
        '\ufeff---\ntitle: bom\n---\n',
        '---\nmemory_relations: [[REQ-1, illegal, CAP-A]]\n---\n',
        '---\ntitle: caf\u00e9 \u2603\n---\n'))},
    'sequence': _scenario('sequence'),
    **{f'winners.{name}': _scenario('winners', args) for name, args in {
        'r1_new': ('2000', 1.0), 'r1_old': ('2002', 0.0),
        'r2_new': (CLOCK, 0.2), 'r2_old': (CLOCK, 2.0), 'tie': (CLOCK, 1.0),
    }.items()},
    'relations': _scenario('relations'), 'links': _scenario('links'),
    **{f'failure.{phase}': _scenario('failure', phase) for phase in ('content', 'fact')},
    **{f'cli.{mode}': _scenario('cli', mode) for mode in ('normal', 'override', 'invalid')},
    'paths.missing_via_link': _missing_via_link,
    'roots.dedup': _two_roots,
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
