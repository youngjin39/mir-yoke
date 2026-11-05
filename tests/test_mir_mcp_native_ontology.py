"""Byte-for-byte native ontology oracles and explicit forwarding boundaries."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_mir_mcp_native_core import ROOT, SCRIPT, request, run, wire

REFERENCE = [sys.executable, '-I', '-B', str(SCRIPT)]
TOOLS = [('ontology_validate', {}), ('ontology_lookup', {'query': 'sample'}),
         ('ontology_impact', {'paths': ['source.py']})]


@pytest.fixture(scope='session')
def ontology_native(tmp_path_factory):
    configured = os.environ.get('MIR_MCP_NATIVE_BINARY')
    if configured:
        binary = Path(configured)
    else:
        if shutil.which('cargo') is None:
            pytest.skip('cargo unavailable')
        target = tmp_path_factory.mktemp('ontology-target')
        env = {**os.environ, 'CARGO_TARGET_DIR': str(target)}
        command = ['cargo', 'build', '--locked']
        if env.get('MIR_HANDOFF_CARGO_OFFLINE') == '1':
            command.append('--offline')
        subprocess.run(command, cwd=ROOT / 'native/mir-mcp', env=env,
                       check=True, timeout=120)
        binary = target / 'debug' / ('mir-mcp.exe' if os.name == 'nt' else 'mir-mcp')
    assert binary.is_file()
    # Every ordinary oracle also proves that Python forwarding is unnecessary.
    return [str(binary), '--reference-python', sys.executable,
            '--reference-script', str(binary.parent / 'unavailable-reference.py')]


def mapping_write(target, mapping):
    (target / '.mir/ontology-map.json').write_text(
        json.dumps(mapping, ensure_ascii=False), encoding='utf-8')


@pytest.fixture
def ontology_target(tmp_path):
    target = tmp_path / 'work tree'
    (target / '.mir').mkdir(parents=True)
    (target / '.mir/repo-profile.toml').write_text('slug = "fixture"\n', encoding='utf-8')
    (target / 'source.py').write_text('def sample():\n    pass\n', encoding='utf-8')
    (target / 'check.json').write_text('{"sample": true}\n', encoding='utf-8')
    mapping_write(target, {
        'contract': {'id': 'mir.common-semantics', 'version': '1.1.0'},
        'domain': {'concepts': [
            {'name': 'sample first', 'ref': 'source.py'},
            {'name': 'sample second', 'ref': 'missing.txt'},
            {'label': 'sample third', 'ref': 'check.json#sample'},
        ], 'invariants': [{'name': 'sample invariant', 'ref': 'source.py'}]},
        'questions': [{'label': 'sample question', 'evidence': ['source.py', 'source.py']}],
    })
    return target


def call(command, target, name, arguments=None):
    return run(command, wire(request('tools/call', {'name': name, 'arguments': {
        'target_root': str(target), **(arguments or {})}})))


def parity(native, target, name, arguments=None):
    expected = call(REFERENCE, target, name, arguments)
    assert call(native, target, name, arguments) == expected
    return json.loads(expected)['result']['structuredContent']


@pytest.mark.parametrize('name,arguments', TOOLS)
def test_native_ontology_without_reference(ontology_native, ontology_target, name, arguments):
    result = parity(ontology_native, ontology_target, name, arguments)
    assert result['ok'] is True
    if name == 'ontology_validate':
        assert result['data']['valid'] is False
        assert result['data']['counts']['errors'] > 0


@pytest.mark.parametrize('scope', ['contract', 'mapping', 'both'])
def test_validate_scope(ontology_native, ontology_target, scope):
    result = parity(ontology_native, ontology_target, 'ontology_validate', {'scope': scope})
    assert result['ok'] is True
    assert result['data']['valid'] is (scope == 'contract')


def test_valid_mapping(ontology_native, ontology_target):
    contract = json.loads((ROOT / 'plugins/mir-mcp/ontology/references/common-contract.json')
                          .read_text(encoding='utf-8'))
    mapping_write(ontology_target, {
        'schema': 'mir-semantic-mapping/v1',
        'contract': {'id': contract['contract_id'], 'version': contract['version'],
                     'version_range': '>=1.0.0 <2.0.0'},
        'namespace': 'fixture', 'canonical_index': ['source.py'],
        'concepts': {item['id']: {'status': 'not_applicable', 'reason': 'fixture'}
                     for item in contract['concepts']},
        'vocabularies': [], 'relations': [],
        'domain': {'concepts': [], 'relations': [], 'invariants': []},
        'questions': [{'id': f'q{i}', 'question': 'sample?', 'evidence': ['source.py']}
                      for i in range(3)],
        'error_cases': [], 'knowledge_supply': {'memory_keeper': 'not_connected'},
        'entrypoints': ['source.py'],
    })
    result = parity(ontology_native, ontology_target, 'ontology_validate')
    assert result['data']['valid'] is True
    assert result['data']['counts']['errors'] == 0


@pytest.mark.parametrize('query', ['sample', 'SAMPLE first', 'sample_first', '!!!', 'absent'])
def test_lookup_terms_order_labels(ontology_native, ontology_target, query):
    result = parity(ontology_native, ontology_target, 'ontology_lookup',
                    {'query': query, 'limit': 16})
    assert result['ok'] is True
    if query == 'sample':
        matches = result['data']['matches']
        assert [item['label'] for item in matches[:3]] == [
            'sample first', 'sample second', 'sample third']


@pytest.mark.parametrize('paths', [['source.py'], ['missing.txt'], ['.mir/ontology-map.json'],
                                 ['source.py', 'check.json'], ['unrelated']])
def test_impact_selection(ontology_native, ontology_target, paths):
    result = parity(ontology_native, ontology_target, 'ontology_impact', {'paths': paths})
    assert result['ok'] is True
    assert result['data']['revalidate'] is ('.mir/ontology-map.json' in paths)
    assert result['data']['stale_refs']
    if paths == ['source.py']:
        assert result['data']['undeclared_check_links']


def test_impact_declared_checks_and_directory_selection(ontology_native, ontology_target):
    (ontology_target / 'test_sample.py').write_text('def test_sample(): pass\n', encoding='utf-8')
    (ontology_target / 'src').mkdir()
    (ontology_target / 'src/source.py').write_text('sample = True\n', encoding='utf-8')
    mapping_write(ontology_target, {
        'domain': {'invariants': [{'ref': 'src', 'check': 'test_sample.py'}]},
        'error_cases': [{'status': 'covered', 'check': 'test_sample.py'}],
    })
    result = parity(ontology_native, ontology_target, 'ontology_impact',
                    {'paths': ['src/source.py']})
    assert result['data']['checks_to_run'] == ['test_sample.py']
    assert result['data']['undeclared_check_links'] == []
    assert result['data']['stale_refs'] == []


@pytest.mark.parametrize('name,arguments', TOOLS)
@pytest.mark.parametrize('extra', [{'page_size': 0}, {'page_size': True}, {'page_size': 65},
                                 {'cursor': ''}, {'unknown': 1}])
def test_schema_errors(ontology_native, ontology_target, name, arguments, extra):
    result = parity(ontology_native, ontology_target, name, {**arguments, **extra})
    assert result['error'] == {'code': 'E_SCHEMA'}


@pytest.mark.parametrize('name,arguments', [
    ('ontology_validate', {'scope': 'unknown'}), ('ontology_lookup', {'query': ''}),
    ('ontology_lookup', {'query': 'x', 'limit': 17}),
    ('ontology_impact', {'paths': []}), ('ontology_impact', {'paths': ['x', 'x']}),
    ('ontology_impact', {'paths': [False]}),
])
def test_tool_specific_schema(ontology_native, ontology_target, name, arguments):
    result = parity(ontology_native, ontology_target, name, arguments)
    assert result['error'] == {'code': 'E_SCHEMA'}


@pytest.mark.parametrize('raw,code', [(None, 'E_IO'), ('{', 'E_FORMAT'),
                                   ('[]', 'E_FORMAT'), ('{"contract":[]}', 'E_FORMAT'),
                                   ('{"contract":{"version":1}}', 'E_FORMAT'),
                                   ('{"a":1,"a":2}', 'E_FORMAT')])
@pytest.mark.parametrize('name,arguments', TOOLS)
def test_mapping_errors(ontology_native, ontology_target, name, arguments, raw, code):
    path = ontology_target / '.mir/ontology-map.json'
    if raw is None:
        path.unlink()
    else:
        path.write_text(raw, encoding='utf-8')
    result = parity(ontology_native, ontology_target, name, arguments)
    assert result['error'] == {'code': code}


@pytest.mark.parametrize('ref,code', [('.env', 'E_PROTECTED'), ('../outside', 'E_PATH')])
@pytest.mark.parametrize('name,arguments', TOOLS)
def test_all_declared_refs_are_guarded(
    ontology_native, ontology_target, name, arguments, ref, code,
):
    mapping_write(ontology_target, {'domain': {'concepts': [{'name': 'unmatched', 'ref': ref}]}})
    result = parity(ontology_native, ontology_target, name, arguments)
    assert result['error'] == {'code': code}


@pytest.mark.parametrize('name,arguments', TOOLS)
def test_profile_protection(ontology_native, ontology_target, name, arguments):
    (ontology_target / '.mir/repo-profile.toml').write_text(
        'slug="fixture"\nprotected_paths=["source.py"]\n', encoding='utf-8')
    result = parity(ontology_native, ontology_target, name, arguments)
    assert result['error'] == {'code': 'E_PROTECTED'}


@pytest.mark.parametrize('name,arguments', TOOLS)
def test_mapping_symlink_refusal(ontology_native, ontology_target, tmp_path, name, arguments):
    mapping = ontology_target / '.mir/ontology-map.json'
    outside = tmp_path / 'outside.json'
    outside.write_bytes(mapping.read_bytes())
    mapping.unlink()
    try:
        mapping.symlink_to(outside)
    except OSError as error:
        pytest.skip(f'symlinks unavailable: {error}')
    result = parity(ontology_native, ontology_target, name, arguments)
    assert result['error'] == {'code': 'E_PATH'}


@pytest.mark.parametrize('name,arguments', TOOLS)
def test_pagination_and_stale_cursor(ontology_native, ontology_target, name, arguments):
    arguments = {**arguments, 'page_size': 1}
    first = parity(ontology_native, ontology_target, name, arguments)
    cursor = first['next_cursor']
    assert cursor
    second = parity(ontology_native, ontology_target, name, {**arguments, 'cursor': cursor})
    assert second['ok'] is True
    (ontology_target / '.mir/ontology-map.json').write_text('{}', encoding='utf-8')
    stale = parity(ontology_native, ontology_target, name, {**arguments, 'cursor': cursor})
    assert stale['error'] == {'code': 'E_CURSOR'}


@pytest.mark.parametrize('name,arguments', TOOLS)
def test_invalid_cursor(ontology_native, ontology_target, name, arguments):
    result = parity(ontology_native, ontology_target, name, {**arguments, 'cursor': 'invalid'})
    assert result['error'] == {'code': 'E_CURSOR'}


@pytest.mark.parametrize('query,label', [('strasse', 'Stra\u00dfe'),
                                       ('\ud55c\uae00', 'sample \ud55c\uae00'),
                                       ('sample', 'sample \ud55c\uae00')])
def test_unicode_reference_parity(ontology_native, ontology_target, query, label):
    mapping_write(ontology_target, {'domain': {'concepts': [
        {'name': label, 'ref': 'source.py'}]}})
    command = [*ontology_native[:-1], str(SCRIPT)]
    result = parity(command, ontology_target, 'ontology_lookup', {'query': query})
    assert result['data']['matches'][0]['label'] == label


@pytest.mark.parametrize('case', ['unicode-query', 'unicode-text', 'unicode-pointer', 'relations',
                                 'regex-anchor', 'covered-check', 'unicode-line',
                                 'semver-overflow', 'float-lookup', 'integer-overflow',
                                 'unicode-profile', 'float-impact'])
def test_explicit_reference_forwarding(ontology_native, ontology_target, tmp_path, case):
    sentinel = tmp_path / 'sentinel.py'
    log = tmp_path / 'forwarded.json'
    sentinel.write_text(
        'import json, sys\nfrom pathlib import Path\n'
        f'raw = sys.stdin.readline(); Path({str(log)!r}).write_text(raw)\n'
        'request = json.loads(raw)\n'
        'print(json.dumps({"jsonrpc":"2.0","id":request["id"],'
        '"result":{"forwarded":True}},separators=(",",":")))\n', encoding='utf-8')
    name, arguments = 'ontology_lookup', {'query': 'sample'}
    if case == 'unicode-query':
        arguments['query'] = 'stra\u00dfe'
    elif case == 'unicode-text':
        mapping_write(ontology_target, {'domain': {'concepts': [
            {'name': 'sample \ud55c\uae00', 'ref': 'source.py'}]}})
    elif case == 'unicode-pointer':
        mapping_write(ontology_target, {'concepts': {'\ud55c\uae00': {'name': 'sample'}}})
    elif case == 'relations':
        name, arguments = 'relations_query', {'anchor': 'REQ', 'purpose': 'implementation'}
    elif case in ('regex-anchor', 'covered-check', 'unicode-line'):
        name, arguments = 'ontology_impact', {'paths': ['source.py']}
        entry = {'name': 'sample', 'ref': 'source.py#sample'}
        if case == 'covered-check':
            entry = {'name': 'sample', 'ref': 'source.py', 'check': 'source.py#sample'}
        elif case == 'unicode-line':
            entry['ref'] = 'source.py:\u0661'
        mapping_write(ontology_target, {'domain': {'invariants': [entry]}})
    elif case == 'semver-overflow':
        name, arguments = 'ontology_validate', {}
        mapping_write(ontology_target, {'contract': {'version': '18446744073709551616.1.0'}})
    elif case == 'float-impact':
        name, arguments = 'ontology_impact', {'paths': ['source.py']}
        mapping_write(ontology_target, {'domain': {'invariants': [
            {'ref': 1e-7, 'evidence': ['source.py']}]}})
    elif case == 'unicode-profile':
        name, arguments = 'ontology_validate', {}
        (ontology_target / '.mir/repo-profile.toml').write_text(
            'slug="\ud55c\uae00"\n', encoding='utf-8')
    else:
        mapping_write(ontology_target, {'domain': {'concepts': [
            {'name': 'sample', 'value': 1e-7 if case == 'float-lookup' else 2 ** 80,
             'ref': 'source.py'}]}})
    raw = call([*ontology_native[:-1], str(sentinel)], ontology_target, name, arguments)
    assert json.loads(raw)['result'] == {'forwarded': True}
    forwarded = json.loads(log.read_text())
    assert forwarded['params']['name'] == name
    assert forwarded['params']['arguments'] == {'target_root': str(ontology_target), **arguments}


@pytest.mark.parametrize('patch', [
    {'schema': False}, {'namespace': 'wrong'}, {'concepts': []},
    {'concepts': {'intent': {'status': 'mapped', 'local': [None]}}},
    {'contract': {'version': '1.0.0', 'version_range': '>=1.0.0 <2.0.0'}},
    {'contract': {'version': '1.2.0', 'version_range': '>=1.0.0 <2.0.0'}},
    {'contract': {'version': '1.1.0-rc.1', 'version_range': '>=1.0.0 <2.0.0'}},
    {'contract': {'version': '1.1.0', 'version_range': '>=2.0.0 <3.0.0'}},
    {'contract': {'version': '1.1.0', 'sha256': 'wrong'}},
    {'relations': [{'common': [], 'local': '', 'from': [], 'to': '*'}]},
    {'relations': [{'common': 'implements', 'local': 'x', 'from': [], 'to': []}]},
    {'vocabularies': [{'name': '', 'ref': 'source.py', 'values': {
        'a': {'unknown': 'bad'}, 'b': {}, 'c': {'local_only': '', 'x': 'y'}}}]},
    {'questions': [None, {'id': '', 'question': '', 'evidence': []}]},
    {'domain': {'invariants': [{'ref': 'check.json#sample', 'check': 'source.py:99'}]}},
    {'error_cases': [{'id': 'unknown', 'status': 'covered', 'check': 'missing.txt'}]},
    {'knowledge_supply': {'memory_keeper': 'connected', 'binding': 'wrong'}},
    {'canonical_index': [None, {'ref': 'source.py'}]},
])
def test_mapping_semantic_variants(ontology_native, ontology_target, patch):
    mapping = json.loads((ontology_target / '.mir/ontology-map.json').read_text())
    mapping.update(patch)
    mapping_write(ontology_target, mapping)
    parity(ontology_native, ontology_target, 'ontology_validate')


@pytest.mark.parametrize('name,args', TOOLS)
def test_invalid_mapping_utf8(ontology_native, ontology_target, name, args):
    (ontology_target / '.mir/ontology-map.json').write_bytes(bytes([255]))
    result = parity(ontology_native, ontology_target, name, args)
    assert result['error'] == {'code': 'E_IO'}


def test_covered_line_overflow_forwarding(ontology_native, ontology_target, tmp_path):
    mapping_write(ontology_target, {'domain': {'invariants': [
        {'ref': 'source.py', 'check': 'source.py:18446744073709551616'}]}})
    command = [*ontology_native[:-1], str(SCRIPT)]
    result = parity(command, ontology_target, 'ontology_impact', {'paths': ['source.py']})
    assert result['data']['stale_refs']
    # A broken reference proves this path requests forwarding.
    failed = call(ontology_native, ontology_target, 'ontology_impact', {'paths': ['source.py']})
    assert json.loads(failed)['result']['structuredContent']['error'] == {'code': 'E_IO'}
