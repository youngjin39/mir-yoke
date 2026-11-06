"""Frozen unmodified B07 pure parsing/validation records; never recapture from a port."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from mir.core import memory_relations as m
from mir.core.engine.memory import relation_facts as f

FIXTURE = (Path(__file__).parent
           / '../native/handoff-packet/tests/fixtures/w2/b07-relations-pure.json')


def observe(case, tmp):
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze exception class and exact message
        return {"error": [type(exc).__name__, str(exc)]}


def batch(function, inputs):
    return lambda tmp: [observe(lambda unused, value=value: function(value), tmp)
                        for value in inputs]


MULTILINE_EDGES = [
    'memory_relations:\n - subject: A\n   predicate: depends_on\n   object: B\n'
    ' # trailing comment\n\nstatus: active',
    'memory_relations:\n - [A,\n    depends_on,\n    B]  # tail\n - [B, depends_on, C]',
    'memory_relations:\n -\n   - A\n   - depends_on\n   - B\n# c\n',
    'memory_relations:\n - {subject: A,\n    predicate: depends_on, object: B}\n'
    '\n # gap\nstatus: active',
]


def doc(body):
    return '---\n' + body + '\n---\nbody\n'


def parse(raw):
    return asdict(f.parse_relation_document(raw)) | {
        'declarations': [asdict(d) for d in f.parse_relation_document(raw).declarations]}


def node(value, note=False):
    return (f._note_string if note else f._node_string)(yaml.compose(value), label='field')


def root_validation(tmp):
    (tmp / 'src').mkdir()
    (tmp / 'src/unit.py').write_text('pass\n', encoding='ascii')
    (tmp / '.env').write_text('synthetic', encoding='ascii')
    (tmp / 'directory').mkdir()
    cases = [('A', 'depends_on', 'B'), ('A', 'implemented_in', 'src/unit.py::run'),
             ('src/unit.py', 'verified_by', 'src/unit.py'), ('A', 'implemented_in', 'missing'),
             ('A', 'depends_on', '../escape'), ('.env', 'depends_on', 'B'),
             ('A', 'verified_by', '.env'), ('A', 'implemented_in', 'directory')]
    result = [observe(lambda unused, values=values: f.validate_declarations_for_root(
        (f.RelationDeclaration(*values, quote='proof'),), tmp), tmp) for values in cases]
    (tmp / '.mir').mkdir()
    (tmp / '.mir/repo-profile.toml').write_text('invalid = [', encoding='ascii')
    result.append(observe(lambda unused: f.validate_declarations_for_root((), tmp), tmp))
    return result


def sources(tmp):
    (tmp / 'note.md').write_text('synthetic', encoding='ascii')
    (tmp / '.env').write_text('synthetic', encoding='ascii')
    return [observe(lambda unused, path=path: f.safe_source_relative_path(tmp / path, tmp), tmp)
            for path in ['note.md', './note.md', 'missing', '../missing', '.env', '.']]


def metadata(tmp):
    return [{k: v.replace(str(tmp), '<tmp>') for k, v in f.relation_metadata(
        path=path, project_root=tmp / '.', document_status=status).items()}
        for path, status in [('docs/note.md', ' ACTIVE '), ('../raw', 'historical'), ('', '')]]


def coalesce(count, mode):
    emitted, state, added = {}, m._SelectionState({}, {}, set()), []
    for i in range(count):
        proof = None if mode == 'none' else {} if mode == 'empty' else {
            'sources': [None if mode == 'null' else {'fact_id': i, 'source_path': 'docs/a.md'}]}
        edge = m.Edge('A', 'depends_on', 'B' if mode != 'distinct' else str(i),
                      provenance=proof)
        added.append(m._append_edge(emitted, edge, state))
    return {'added': added, 'edges': [edge.to_dict() for edge in emitted.values()],
            'omitted': state.proofs_omitted, 'notices': m._proof_notices(state)}


def gate(value):
    return m._metadata_gate(Path('project'), value)


META = {'relation_schema': f.RELATION_SCHEMA, 'relation_project_path': 'project',
        'relation_document_status': 'active'}
STATUSES = ['', 'active', ' ACTIVE ', 'inactive', 'candidate', 'draft', 'proposed',
            'archived', 'rejected', 'superseded', 'superseded-design', 'historical',
            'historical-snapshot', 'historical-manual-snapshot', 'historical-ledger',
            'applied-ledger-v1', 'done', 'historical-new', 'superseded-new', 'done-new']
RAW = ['', '---', ' ---\n---\n', '---\nx: y', '---\n---\n',
       '---\r\nstatus: Active\r\n---\r\n', doc('status: " Draft "'),
       doc('status: ACTIVE\nstatus: draft'), doc('x: memory_relations'), doc('- memory_relations'),
       doc('memory_relations: []'), doc('memory_relations: null'),
       doc('memory_relations: []\nmemory_relations: []'),
       doc('memory_relations: []\nstatus: A\nstatus: B'),
       doc('memory_relations: []\nstatus: 1'), doc('memory_relations: ['),
       doc('"memory_relations": []\n? [complex, key]\n: ignored'),
       doc('memory_relations: []\nstatus: " ACTIVE "')]
EDGES = ['[A, depends_on, B]', '[A, realized_by, B]', '[A, implemented_in, src/a.py::f]',
         '[A, verified_by, tests/a.py]', '[ns:A, depends_on, ns:B]',
         '[A, alias, B]', '[A, same_as, B]', '[A, inverse_depends_on, B]', '[A, ns:depends_on, B]',
         '[A, DEPENDS_ON, B]', '[A, depends_on, A]',
         '[A, depends_on, ".env"]', '[A, depends_on, "/absolute"]',
         '[A, depends_on, "src/../a.py"]', '[A, depends_on, "a\\tb"]',
         '[A, depends_on]', '[A, depends_on, B, C]', 'scalar', 'null',
         '[1, depends_on, B]', '[A, true, B]', '[A, depends_on, null]',
         '["", depends_on, B]', '[A, depends_on, "../escape"]',
         '["./src/a.py::f", depends_on, "src//a.py::g"]',
         '{subject: A, predicate: depends_on, object: B, summary: why, reason: because}',
         '{subject: A, predicate: depends_on, object: B}',
         '{subject: A}', '{subject: A, subject: B, predicate: depends_on, object: C}',
         '{subject: A, predicate: depends_on, object: B, unknown: x}',
         '{1: A}', '{? [x, y]: z}',
         '{subject: A, predicate: depends_on, object: B, summary: null}',
         '{subject: A, predicate: depends_on, object: B, reason: ""}']

CASES = {
    'frontmatter': batch(f._frontmatter, RAW + ['---\nstatus: A\n --- \n']),
    'key': batch(f.is_relation_declaration_key, ['memory_relations', '"memory_relations"',
        "'memory_relations'", '!!str memory_relations', 'memory_relation', 'MEMORY_RELATIONS',
        '"memory_\\u0072elations"', '[memory_relations]', '*missing',
        'x: y\nmemory_relations', '']),
    'declares': batch(f._frontmatter_declares_relations, ['memory_relations: []',
        '"memory_relations": [', 'x: [', '[memory_relations]', '',
        '  memory_relations: [', '# memory_relations: [', 'x: memory_relations']),
    'declares_cap': batch(lambda n: f._frontmatter_declares_relations('x: y', max_compose_chars=n),
                         [None, 0, 3, 4, 5]),
    'has': batch(f.has_relation_declaration, RAW),
    'has_cap': batch(lambda n: f.has_relation_declaration(doc('x: y'), max_compose_chars=n),
                    [0, 4, 5]),
    'node': batch(node, ['null', '1', '[]', '{}', '""', '" "', 'A', '"\\t"',
                        '"\\u007f"', '"\\u009f"', '"\\u00a0"', '"\\u2028"',
                        '"' + 'a' * 1024 + '"', '"' + 'a' * 1025 + '"']),
    'note': batch(lambda v: node(v, True), ['null', '[]', '""', '" "', 'ok',
        '"a\\nb"', '"a\\rb"', '"\\t"', '"\\u0080"', '"\\u2029"',
        '"' + 'a' * 240 + '"', '"' + 'a' * 241 + '"']),
    'parse_frontmatter': batch(parse, RAW),
    'parse_edges': batch(parse, [doc('memory_relations:\n  - ' + edge) for edge in EDGES]),
    'parse_nested': batch(parse, [doc('memory_relations: &loop [*loop]'),
        doc('memory_relations:\n - [A, depends_on, B]\nstatus: []'),
        doc('memory_relations:\n - [A, depends_on, B]\n - [B, depends_on, C]')]),
    'parse_order_duplicate': batch(parse, [doc('memory_relations:\n' + body) for body in [
        ' - [B, depends_on, A]\n - [A, depends_on, B]',
        ' - [A, depends_on, B]\n - [A, depends_on, B]',
        ' - [A, depends_on, B]\n - {subject: A, predicate: depends_on, object: B}']]),
    'parse_count': batch(parse, [doc('memory_relations:\n' + '\n'.join(
        f' - [A{i}, depends_on, B]' for i in range(n))) for n in [0, 64, 65]]),
    'parse_quote': batch(parse, [doc('memory_relations:\n - [A, depends_on, B] #' + 'x' * n)
                                for n in [4072, 4073, 4074, 4096]]),
    # Multi-line flow and block edges pin the quoted span (start to end mark lines).
    'parse_multiline_quote': batch(parse, [doc(body) for body in MULTILINE_EDGES]),
    'parse_size': batch(parse, [doc('#' + 'x' * (n - 2))
                               for n in [1048575, 1048576, 1048577]]),
    'root_validation': root_validation,
    'sources': sources,
    'status': batch(lambda pair: f.relation_status_is_active(*pair),
                    [(p, s) for p in ['verified_by', 'depends_on', 'unknown'] for s in STATUSES]),
    'metadata': metadata,
    'metadata_gate': batch(gate, [None, [], {}, {**META, 'relation_schema': 'v2'},
        {**META, 'relation_project_path': 'other'}, {**META, 'relation_document_status': None},
        *[{**META, 'relation_document_status': s} for s in [*STATUSES, '\n', '\u007f']]]),
    'entity': batch(m._entity_value, [None, 0, [], '', ' ', 'ns:A', 'a' * 4096, 'a' * 4097,
                                    '\n', '\u001f', '\u007f', '\u009f', '\u00a0', '\u2028']),
    'coalesce': batch(lambda pair: coalesce(*pair),
        [(n, mode) for n in [0, 1, 2, 8, 9, 10]
         for mode in ['proof', 'none', 'empty', 'null', 'distinct']]),
    'proof_notices': batch(lambda n: m._proof_notices(
        m._SelectionState({}, {}, set(), proofs_omitted=n)), [0, 1, 8]),
    'inactive_sql': batch(m._inactive_endpoint_sql, ['f.subject_entity_id', 'f.object_entity_id']),
    'locator_sql': batch(m._locator_path_sql, ['subject.slug', 'object.slug', '']),
    'source_marker': lambda tmp: m._memory_source(),
    'search_hint': lambda tmp: m._search_hint(['B', 'A', 'B'],
                                             ['impact', 'dependencies', 'impact'], 'missing'),
    'stamp': lambda tmp: list(m._source_stamp(SimpleNamespace(
        st_dev=1, st_ino=2, st_size=3, st_mtime_ns=4, st_ctime_ns=5))),
    'directions': lambda tmp: {name: {k: sorted(v) for k, v in value.items()}
                              for name, value in [('forward', m._FORWARD),
                                                  ('reverse', m._REVERSE)]},
    'now_format': lambda tmp: {
        'utc': datetime.fromisoformat(f._now_iso()).utcoffset().total_seconds(),
                               'microseconds': len(f._now_iso().split('.')[1].split('+')[0])},
}

RECORDS = json.loads(FIXTURE.read_text(encoding='ascii')) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
