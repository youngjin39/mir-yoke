"""B15 render oracle captured from unmodified Python; never recapture from a port.

The task brief owns intent. Render has no exclusion flag or multi-file target:
freeze ingest exclusions and sequential applies with a second write failure.
All databases are synthetic; default DB resolution is redirected to the fixture.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from dataclasses import asdict
from pathlib import Path
from unittest import mock

import pytest

from mir.cli import memory
from mir.core.engine.memory import distill as d
from mir.core.engine.memory import store

FIXTURE = (Path(__file__).parent /
           '../native/handoff-packet/tests/fixtures/w2/b15-render.json')
CLOCK = '2001-02-03T04:05:06.000000+00:00'
START, END = '<!-- mir:generated:start -->', '<!-- mir:generated:end -->'
MANUAL = 'Manual prefix\t \n' + START + '\nstale\n' + END + '\nManual suffix  \n'
BODIES = (None, '', 'manual', 'manual\n', 'manual\n\n', MANUAL,
          START + '\norphan\n', 'orphan\n' + END,
          MANUAL + START + '\nsecond\n' + END + '\ntail', END + '\nreverse\n' + START,
          'crlf\r\n' + START + '\r\nold\r\n' + END + '\r\ntail\r')


def _compact(value):
    if isinstance(value, str) and len(value) > 256:
        return {'length': len(value), 'sha256': hashlib.sha256(value.encode()).hexdigest(),
                'first': value[:120], 'last': value[-120:]}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items()}
    return value


def _scenario(kind, mode=None):
    def run(tmp):
        db = tmp / 'synthetic.db'
        conn = store.connect(db, load_vec=False).conn
        try:
            with contextlib.ExitStack() as stack:
                for module in (store, d):
                    stack.enter_context(mock.patch.object(module, '_now_iso', return_value=CLOCK))
                stack.enter_context(contextlib.chdir(tmp))
                stack.enter_context(mock.patch.object(store, '_load_sqlite_vec',
                                                      return_value=(False, 'off')))
                stack.enter_context(mock.patch.object(store.log, 'disabled', True))
                stack.enter_context(mock.patch.object(memory, 'default_db_path', return_value=db))
                store.apply_migrations(conn)
                result = _execute(conn, tmp, kind, mode)
                return _compact(json.loads(json.dumps(result, ensure_ascii=True)
                                           .replace(str(tmp), '<tmp>')))
        finally:
            conn.close()
    return run


def _execute(conn, tmp, kind, mode):
    ingests = []
    if not kind.startswith('empty'):
        for rel, fields in (
            ('docs/decisions/adr-z.md', 'title: Z | title\nkeywords: [z, a, z]\nlesson: last'),
            ('docs/decisions/adr-a.md', 'title: \u00e9\nkeywords: [b, a]\nlesson: first'),
            ('docs/decisions/adr-bare.md', 'use: fallback'),
            ('docs/_archive/adr-hidden.md', 'title: hidden\nlesson: excluded'),
            ('docs/_archive/nested/adr-hidden.md', 'title: nested\nlesson: excluded'),
            ('docs/_archive-neighbor/adr-visible.md', 'title: neighbor'),
        ):
            source = tmp / rel
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(f'---\n{fields}\n---\nbody\n', encoding='utf-8')
            ingests.append(asdict(d.ingest_markdown_file(
                source, conn=conn, project_root=tmp, whitelist_globs=('**',))))
        source = tmp / 'docs/decisions/adr-z.md'
        source.write_text('---\ntitle: updated\nkeywords: [z, c]\nlesson: replaced\n---\nbody2\n')
        ingests.append(asdict(d.ingest_markdown_file(source, conn=conn, project_root=tmp)))
    if kind == 'helpers_direct':
        # Direct inserts bypass ingest dedup: recall dedups keywords and render trims lessons.
        for predicate, value in (('keywords', 'b'), ('lesson', '\t padded \n')):
            d.insert_triple(conn, d.Triple('adr-a', predicate, value))
        return {'index': d.recall_ingested_index(conn), 'lessons': d.recall_lessons(conn),
                'lessons_markdown': memory._render_lessons_section(conn)}
    if kind in ('helpers', 'empty'):
        return {'ingests': ingests, 'index': d.recall_ingested_index(conn),
                'lessons': d.recall_lessons(conn),
                'map_markdown': memory._render_memory_map_section(conn),
                'lessons_markdown': memory._render_lessons_section(conn),
                'pragmas': {p: conn.execute(f'PRAGMA {p}').fetchone()[0]
                            for p in ('journal_mode', 'foreign_keys', 'synchronous')},
                'migrations': [list(r) for r in conn.execute(
                    'SELECT * FROM schema_migrations ORDER BY version')],
                'objects': [list(r) for r in conn.execute(
                    'SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name')]}
    if kind == 'in_place':
        # write_text keeps the existing file: its mode bits and a symlinked path survive.
        real = tmp / 'out/real.md'
        real.parent.mkdir(parents=True)
        real.write_text(MANUAL, encoding='utf-8')
        real.chmod(0o640)
        link = tmp / 'out/link.md'
        link.symlink_to(real.name)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = observe(lambda _: memory.main([
                'render', '--apply', '--target', 'lessons', '--db', str(tmp / 'synthetic.db'),
                '--output-path', str(link)]), tmp)
        return {'result': result, 'stdout': out.getvalue(),
                'mode': oct(real.stat().st_mode & 0o777), 'link_is_symlink': link.is_symlink(),
                'real': real.read_text(encoding='utf-8')}
    output = tmp / 'out/nested/projection.md'
    body = BODIES[mode] if kind == 'markers' else MANUAL
    if body is not None:
        output.parent.mkdir(parents=True)
        output.write_text(body, encoding='utf-8')
    args = ['render']
    if kind in ('cli', 'direct', 'empty_cli'):
        target, apply, explicit = mode
        if target:
            args += ['--target', target]
        if apply:
            args += ['--apply']
        if explicit:
            args += ['--output-path', str(output)]
    elif kind == 'invalid':
        args += mode
    else:
        args += ['--apply', '--output-path', str(output)]
    if kind != 'cli' or mode[0] is not None:
        args += ['--db', str(tmp / 'synthetic.db')]
    out, err = io.StringIO(), io.StringIO()
    results = []
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        def call(argv):
            return memory._do_render(memory._parse(argv), conn) if kind == 'direct' else \
                memory.main(argv)
        results.append(observe(lambda _: call(args), tmp))
        if kind == 'second_failure':
            first = output.read_bytes().decode('utf-8')
            blocked = tmp / 'second.md'
            blocked.mkdir()
            results.append(observe(lambda _: memory.main([
                'render', '--apply', '--target', 'lessons', '--db', str(tmp / 'synthetic.db'),
                '--output-path', str(blocked)]), tmp))
            results.append({'first_after_failure': output.read_bytes().decode('utf-8'),
                            'first_before_failure': first,
                            'second_is_file': blocked.is_file()})
    return {'results': results, 'stdout': out.getvalue(), 'stderr': err.getvalue(),
            'file': output.read_bytes().decode('utf-8') if output.is_file() else None}


CASES = {
    'helpers.populated': _scenario('helpers'), 'helpers.empty': _scenario('empty'),
    **{f'markers.{i}': _scenario('markers', i) for i in range(len(BODIES))},
    **{f'{route}.{target}.{apply}.{explicit}': _scenario(route, (target, apply, explicit))
       for route in ('cli', 'direct') for target in (None, 'memory-map', 'lessons', 'all')
       for apply, explicit in ((False, False), (False, True), (True, True), (True, False))},
    **{f'empty.cli.{apply}': _scenario('empty_cli', ('all', apply, True))
       for apply in (False, True)},
    'cli.second_failure': _scenario('second_failure'),
    'cli.invalid_target': _scenario('invalid', ['--target', 'unknown']),
    'cli.unsupported_exclusion': _scenario('invalid', ['--exclude', 'docs/_archive/']),
    'cli.in_place': _scenario('in_place'),
    'helpers.direct_facts': _scenario('helpers_direct'),
}


def observe(case, tmp):
    try:
        return {'value': case(tmp)}
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - freeze reference errors
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}


RECORDS = json.loads(FIXTURE.read_text(encoding='ascii')) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
