"""Native handoff IO and Git oracles against the standalone Python server."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest
import test_mir_mcp_git as git_oracle
from test_mir_mcp_git import setup_git
from test_mir_mcp_native_core import SCRIPT, request, run, wire
from test_mir_mcp_native_core import native as native

REFERENCE = [sys.executable, '-I', '-B', str(SCRIPT)]


def test_native_worker_is_argv_only_and_cannot_forward(native, tmp_path):
    payload = wire(request('tools/call', {'name': 'ontology_lookup', 'arguments': {
        'target_root': str(tmp_path), 'paths': ['file']}}))
    reply = json.loads(run([native[0], '--internal-native'], payload))
    assert reply['result']['structuredContent']['error'] == {'code': 'E_SCHEMA'}
    bad = subprocess.run([native[0], '--internal-native', 'extra'], input=payload,
                         capture_output=True, timeout=5)
    assert bad.returncode == 2 and bad.stdout == b'' and bad.stderr == b''


@pytest.mark.parametrize('committed', [False, True])
def test_handoff_envelope_boundary_differential(native, target, committed):
    directory = target
    for i in range(8):
        directory = directory / (str(i) + 'a' * 95)
    directory.mkdir(parents=True)
    paths = []
    for i in range(16):
        source = directory / f'source-{i}.txt'
        source.write_bytes(b'fixture\n')
        paths.append(source.relative_to(target).as_posix())
    if committed:
        setup_git(target, 'init', '-q')
        setup_git(target, 'add', '--', '.')
        setup_git(target, 'commit', '-qm', 'fixture')
    expected = call(REFERENCE, target, paths, page_size=16)
    actual = call(native, target, paths, page_size=16)
    assert semantic(actual) == semantic(expected)
    result = json.loads(actual)['result']['structuredContent']
    if committed:
        assert 0 < len(result['data']['sources']) < 16
        assert result['next_cursor']
        assert len(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode()) <= 15360
        observed = result['data']['observed_at']
        frozen = json.loads(expected)['result']['structuredContent']['data']['observed_at']
        assert actual.replace(observed.encode(), frozen.encode(), 1) == expected
    else:
        assert result['error'] == {'code': 'E_LIMIT'}
        assert actual == expected


@pytest.mark.skipif(sys.platform == 'win32', reason='Windows root syntax rejects controls')
def test_root_nul_matches_reference(native, tmp_path):
    root = str(tmp_path) + '/invalid\0root'
    expected = call(REFERENCE, root, ['file'])
    assert json.loads(expected)['result']['structuredContent']['error'] == {'code': 'E_FORMAT'}
    assert call(native, root, ['file']) == expected


def call(command, root, paths, **extra):
    payload = wire(request('tools/call', {'name': 'handoff_pins', 'arguments': {
        'target_root': str(root), 'paths': paths, **extra}}))
    return run(command, payload)


def semantic(raw):
    """Normalize only the observation clock and elapsed Git times, also in the text content."""
    if isinstance(raw, bytes):
        raw = raw.decode()
    reply = json.loads(re.sub(r'after \d+(?:\.\d+)? s', 'after <elapsed> s', raw))
    result = reply.get('result', {})
    structured = result.get('structuredContent')
    if structured and isinstance(structured.get('data'), dict):
        structured['data'].pop('observed_at', None)
    for content in result.get('content', []):
        if content.get('type') == 'text':
            value = json.loads(content['text'])
            if isinstance(value.get('data'), dict):
                value['data'].pop('observed_at', None)
            content['text'] = json.dumps(value, sort_keys=True)
    return reply


@pytest.fixture
def target(tmp_path):
    root = tmp_path / 'work tree'
    (root / '.mir').mkdir(parents=True)
    (root / '.mir/repo-profile.toml').write_text('slug = "fixture"\n')
    (root / '.mir/ontology-map.json').write_text(json.dumps({
        'contract': {'id': 'mir.common-semantics', 'version': '1.1.0'},
        'domain': {'concepts': [{'name': 'source', 'ref': 'source.txt'}]},
    }))
    (root / 'source.txt').write_bytes(b'source\r\n\x1a\x00\xff')
    (root / 'second.txt').write_bytes(b'second\n')
    return root


@pytest.mark.parametrize('state', ['plain', 'unborn', 'committed', 'modified'])
def test_handoff_is_native_without_reference(native, target, tmp_path, state):
    if state != 'plain':
        setup_git(target, 'init', '-q')
    if state in ('committed', 'modified'):
        setup_git(target, 'add', '--', '.')
        setup_git(target, 'commit', '-qm', 'fixture')
    if state == 'modified':
        (target / 'source.txt').write_bytes(b'changed\n')
    command = [*native[:-1], str(tmp_path / 'nonexistent-reference.py')]
    paths = ['source.txt', 'second.txt', 'missing.txt']
    expected = call(REFERENCE, target, paths)
    actual = call(command, target, paths)
    assert semantic(actual) == semantic(expected)
    pins = json.loads(actual)['result']['structuredContent']['data']
    assert pins['sources'][0]['sha256'] == hashlib.sha256(
        (target / 'source.txt').read_bytes()).hexdigest()
    assert pins['sources'][2]['sha256'] is None
    assert pins['sources'][2]['revision'] is None
    assert any(item.startswith('missing.txt:') for item in pins['unknowns'])
    if state in ('committed', 'modified'):
        assert pins['head'] == setup_git(target, 'rev-parse', 'HEAD')
        assert pins['sources'][0]['modified_vs_head'] is (state == 'modified')
    else:
        assert pins['head'] is None


@pytest.mark.parametrize('case', ['builtin', 'profile', 'external-link', 'internal-link'])
def test_handoff_refusal_bytes_and_recovery(native, target, tmp_path, case):
    if case == 'builtin':
        path, code = '.env', 'E_PROTECTED'
        (target / path).write_text('DO_NOT_DISCLOSE_SENTINEL')
    elif case == 'profile':
        path, code = 'source.txt', 'E_PROTECTED'
        (target / '.mir/repo-profile.toml').write_text('protected_paths=["source.txt"]\n')
    else:
        path, code = 'link', 'E_PATH'
        outside = tmp_path / 'outside'
        outside.write_text('DO_NOT_DISCLOSE_SENTINEL')
        (target / path).symlink_to(outside if case == 'external-link' else target / 'source.txt')
    payload = wire(request('tools/call', {'name': 'handoff_pins', 'arguments': {
        'target_root': str(target), 'paths': [path]}})) + wire(request())
    expected = run(REFERENCE, payload)
    assert run([*native[:-1], str(tmp_path / 'nonexistent-reference.py')], payload) == expected
    replies = [json.loads(line) for line in expected.splitlines()]
    assert replies[0]['result']['structuredContent']['error'] == {'code': code}
    assert replies[1]['result']['tools']
    assert b'DO_NOT_DISCLOSE_SENTINEL' not in expected


@pytest.mark.parametrize('committed', [False, True])
def test_handoff_stateless_cross_runtime_continuation(native, target, committed):
    if committed:
        setup_git(target, 'init', '-q')
        setup_git(target, 'add', '--', '.')
        setup_git(target, 'commit', '-qm', 'fixture')
    paths = ['source.txt', 'second.txt', 'missing.txt']
    first = call(REFERENCE, target, paths, page_size=1)
    assert semantic(call(native, target, paths, page_size=1)) == semantic(first)
    cursor = json.loads(first)['result']['structuredContent']['next_cursor']
    assert cursor
    for path in paths[1:]:
        # Each invocation starts a new process; either runtime can consume the cursor.
        expected = call(REFERENCE, target, paths, page_size=1, cursor=cursor)
        actual = call(native, target, paths, page_size=1, cursor=cursor)
        assert semantic(actual) == semantic(expected)
        data = json.loads(actual)['result']['structuredContent']
        assert [source['path'] for source in data['data']['sources']] == [path]
        cursor = data['next_cursor']
    assert cursor is None
    cursor = json.loads(first)['result']['structuredContent']['next_cursor']
    for extra in ({'page_size': 2}, {'paths': paths[::-1]}):
        changed_paths = extra.get('paths', paths)
        arguments = {'page_size': 1,
                     **{key: value for key, value in extra.items() if key != 'paths'}}
        expected = call(REFERENCE, target, changed_paths, cursor=cursor, **arguments)
        assert call(native, target, changed_paths, cursor=cursor, **arguments) == expected
        assert json.loads(expected)['result']['structuredContent']['error'] == {'code': 'E_CURSOR'}
    (target / 'source.txt').write_bytes(b'changed\n')
    expected = call(REFERENCE, target, paths, page_size=1, cursor=cursor)
    assert call(native, target, paths, page_size=1, cursor=cursor) == expected
    assert json.loads(expected)['result']['structuredContent']['error'] == {'code': 'E_CURSOR'}


def test_existing_git_protocol_command_oracle(native, tmp_path, monkeypatch):
    import test_mir_mcp_git as oracle

    setup_git(tmp_path, 'init', '-q')
    (tmp_path / 'source.txt').write_bytes(b'source\n')
    setup_git(tmp_path, 'add', '--', 'source.txt')
    setup_git(tmp_path, 'commit', '-qm', 'initial')
    original = subprocess.run

    def native_run(command, **kwargs):
        return original(native if command[-1] == str(SCRIPT) else command, **kwargs)

    monkeypatch.setattr(oracle, 'subprocess', SimpleNamespace(run=native_run))
    oracle.test_protocol_should_report_commit_pins_and_only_dirty_for_protected_change(
        sys.executable, tmp_path)


def test_handoff_missing_mapping_keeps_available_source_pin(native, target, tmp_path):
    (target / '.mir/ontology-map.json').unlink()
    expected = call(REFERENCE, target, ['source.txt'])
    actual = call([*native[:-1], str(tmp_path / 'no-reference.py')], target, ['source.txt'])
    assert semantic(actual) == semantic(expected)
    pins = json.loads(actual)['result']['structuredContent']['data']
    assert pins['mapping_sha256'] is None
    assert pins['sources'][0]['sha256'] == hashlib.sha256(
        (target / 'source.txt').read_bytes()).hexdigest()
    assert any(pin['pin'] == 'mapping.digest' and pin['availability'] == 'unknown'
               for pin in pins['pin_inventory'])


@pytest.mark.parametrize('path', ['.env', 'nested/credentials.json', 'cert.pem'])
def test_existing_security_command_oracle(native, tmp_path, monkeypatch, path):
    import test_mir_mcp_security as oracle

    # Preserve the existing process oracle, including its sentinel/output checks.
    target = oracle.target.__wrapped__(tmp_path)
    original = subprocess.run

    def native_run(command, **kwargs):
        return original(native if command[-1] == str(SCRIPT) else command, **kwargs)

    monkeypatch.setattr(oracle, 'subprocess', SimpleNamespace(run=native_run))
    oracle.test_protected_direct_and_indirect(sys.executable, target, path)


def test_existing_limits_command_oracle(native, tmp_path, monkeypatch):
    import test_mir_mcp_limits as oracle

    original = subprocess.run

    def native_run(command, **kwargs):
        return original(native if command[-1] == str(SCRIPT) else command, **kwargs)

    monkeypatch.setattr(oracle, 'subprocess', SimpleNamespace(run=native_run))
    oracle.test_output_cap_and_stateless_cursor_bindings(sys.executable, tmp_path)


@pytest.mark.skipif(sys.platform != 'win32', reason='requires native Windows path handling')
@pytest.mark.parametrize('path', ['.env::$DATA', 'NUL.txt', 'name.'])
def test_windows_unsafe_handoff_slot_bytes(native, tmp_path, path):
    # The existing Windows guard oracle covers injected Python handle races; this
    # process oracle exercises the same unsafe names through the native wire route.
    expected = call(REFERENCE, tmp_path, [path])
    assert call(native, tmp_path, [path]) == expected
    assert json.loads(expected)['result']['structuredContent']['error']['code'] in (
        'E_PATH', 'E_PROTECTED')


@pytest.fixture
def independent(native, tmp_path):
    return [*native[:-1], str(tmp_path / 'reference-must-not-run.py')]


@pytest.mark.parametrize('kind', ['relative', 'parent', 'missing', 'file'])
def test_handoff_invalid_roots_without_reference(independent, target, tmp_path, kind):
    roots = {'relative': 'relative', 'parent': str(target / '..' / target.name),
             'missing': str(tmp_path / 'missing'), 'file': str(target / 'source.txt')}
    expected = call(REFERENCE, roots[kind], ['source.txt'])
    assert call(independent, roots[kind], ['source.txt']) == expected
    code = 'E_IO' if kind in ('missing', 'file') else 'E_PATH'
    assert json.loads(expected)['result']['structuredContent']['error'] == {'code': code}


@pytest.mark.parametrize('path', ['../outside', 'nested/../../outside', '/absolute'])
def test_handoff_parent_and_absolute_slots_without_reference(independent, target, path):
    expected = call(REFERENCE, target, [path])
    assert call(independent, target, [path]) == expected
    assert json.loads(expected)['result']['structuredContent']['error'] == {'code': 'E_PATH'}


@pytest.mark.skipif(sys.platform == 'win32', reason='requires a POSIX FIFO')
def test_handoff_fifo_refuses_without_blocking(independent, target):
    import os
    import time

    os.mkfifo(target / 'fifo')
    expected = call(REFERENCE, target, ['fifo'])
    start = time.monotonic()
    actual = call(independent, target, ['fifo'])
    assert time.monotonic() - start < 2
    assert actual == expected
    assert json.loads(actual)['result']['structuredContent']['error'] == {'code': 'E_PATH'}


@pytest.mark.parametrize('profile,code', [
    ('malformed = [', 'E_FORMAT'),
    ('[paths]\nprotected_paths="source.txt"\n', 'E_FORMAT'),
    ('paths = "invalid"\n', 'E_FORMAT'),
    ('[safety]\nsecret_paths=[false]\n', 'E_FORMAT'),
    ('protected_paths=["source.txt"]\n', 'E_PROTECTED'),
    ('[paths]\nprotected_paths=["source.txt"]\n', 'E_PROTECTED'),
    ('[paths]\nsecret_paths=["source.txt"]\n', 'E_PROTECTED'),
    ('[safety]\nprotected_paths=["source.txt"]\n', 'E_PROTECTED'),
    ('[safety]\nsecret_paths=["source.txt"]\n', 'E_PROTECTED'),
    ('[boundaries]\nsecrets=["source.txt"]\n', 'E_PROTECTED'),
])
def test_handoff_profiles_without_reference(independent, target, profile, code):
    (target / '.mir/repo-profile.toml').write_text(profile)
    expected = call(REFERENCE, target, ['source.txt'])
    assert call(independent, target, ['source.txt']) == expected
    assert json.loads(expected)['result']['structuredContent']['error'] == {'code': code}


@pytest.mark.parametrize('size', [1048576, 1048577])
def test_handoff_source_byte_limit_without_reference(independent, target, size):
    (target / 'source.txt').write_bytes(b'x' * size)
    expected = call(REFERENCE, target, ['source.txt'])
    actual = call(independent, target, ['source.txt'])
    if size > 1048576:
        assert actual == expected
        assert json.loads(actual)['result']['structuredContent']['error'] == {'code': 'E_LIMIT'}
    else:
        assert semantic(actual) == semantic(expected)
        pins = json.loads(actual)['result']['structuredContent']['data']
        assert pins['sources'][0]['sha256'] == hashlib.sha256(b'x' * size).hexdigest()


@pytest.mark.parametrize('mapping,code', [
    ('{"contract":{"id":"a","id":"b"}}', 'E_FORMAT'),
    ('{"contract":[]}', 'E_FORMAT'),
    ('{"contract":{"version":1}}', 'E_FORMAT'),
    ('{"domain":{"concepts":[{"ref":"../outside"}]}}', 'E_PATH'),
    ('{"domain":{"concepts":[{"ref":".env"}]}}', 'E_PROTECTED'),
    ('{"domain":{"concepts":[{"ref":"source.txt"},{"ref":"source.txt"}]}}', None),
])
def test_handoff_mapping_refs_without_reference(independent, target, mapping, code):
    (target / '.mir/ontology-map.json').write_text(mapping)
    expected = call(REFERENCE, target, ['source.txt'])
    actual = call(independent, target, ['source.txt'])
    if code:
        assert actual == expected
        assert json.loads(actual)['result']['structuredContent']['error'] == {'code': code}
    else:
        assert semantic(actual) == semantic(expected)
        assert len(json.loads(actual)['result']['structuredContent']['data']['sources']) == 1


@pytest.mark.parametrize('paths,extra', [
    (['source.txt'], {'page_size': True}),
    (['source.txt'], {'page_size': 1.0}),
    (['source.txt'], {'page_size': 0}),
    (['source.txt'], {'page_size': 65}),
    (['source.txt', 'source.txt'], {}),
    ([True], {}), ([1.0], {}), ([''], {}), ('source.txt', {}),
])
def test_handoff_schema_without_reference(independent, target, paths, extra):
    expected = call(REFERENCE, target, paths, **extra)
    assert call(independent, target, paths, **extra) == expected
    assert json.loads(expected)['result']['structuredContent']['error'] == {'code': 'E_SCHEMA'}


def oracle_cases(function, parameter):
    """Reuse the maintained Git preflight matrix through a native process boundary."""
    return next(mark.args[1] for mark in function.pytestmark
                if mark.name == 'parametrize' and mark.args[0] == parameter)


def assert_preflight_partial(command, target):
    expected = call(REFERENCE, target, ['source.txt'])
    actual = call(command, target, ['source.txt'])
    assert semantic(actual) == semantic(expected)
    structured = json.loads(actual)['result']['structuredContent']
    assert structured['ok'] is False
    assert structured['error'] == {'code': 'E_GIT'}
    pins = structured['data']
    assert pins['head'] is None and pins['dirty'] is None
    source = pins['sources'][0]
    assert source['sha256'] == hashlib.sha256((target / 'source.txt').read_bytes()).hexdigest()
    assert source['revision'] is None and source['modified_vs_head'] is None
    assert pins['mapping_sha256'] == hashlib.sha256(
        (target / '.mir/ontology-map.json').read_bytes()).hexdigest()
    assert 'SENTINEL' not in actual.decode()


@pytest.mark.parametrize('config', oracle_cases(
    git_oracle.test_should_refuse_unsafe_or_unparsed_config, 'config'))
def test_handoff_git_unsafe_config_without_reference(independent, target, config):
    metadata = git_oracle.git_directory(target)
    (metadata / 'config').write_text(config)
    assert_preflight_partial(independent, target)


@pytest.mark.parametrize('relative', oracle_cases(
    git_oracle.test_should_refuse_metadata_redirections, 'relative'))
def test_handoff_git_metadata_redirection_without_reference(independent, target, relative):
    git_oracle.git_directory(target)
    pointer = target / relative
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text('/outside/SENTINEL\n')
    assert_preflight_partial(independent, target)


@pytest.mark.parametrize('relative', oracle_cases(
    git_oracle.test_should_refuse_fixed_metadata_symlinks, 'relative'))
def test_handoff_git_metadata_symlink_without_reference(independent, target, tmp_path, relative):
    metadata = git_oracle.git_directory(target)
    path = target / relative
    if path.is_dir():
        path.rename(metadata / (path.name + '-original'))
    elif path.exists():
        path.unlink()
    outside = tmp_path / 'outside'
    outside.write_text('DO_NOT_DISCLOSE_SENTINEL')
    path.symlink_to(outside)
    assert_preflight_partial(independent, target)


@pytest.mark.parametrize('kind', oracle_cases(
    git_oracle.test_should_refuse_nonlocal_git_directory, 'kind'))
def test_handoff_git_nonlocal_metadata_without_reference(independent, target, tmp_path, kind):
    if kind == 'gitfile':
        (target / '.git').write_text('gitdir: /outside/SENTINEL\n')
    elif kind == 'symlink':
        outside = git_oracle.git_directory(tmp_path / 'outside')
        (target / '.git').symlink_to(outside, target_is_directory=True)
    elif kind == 'special':
        import os

        os.mkfifo(target / '.git')
    assert_preflight_partial(independent, target)


@pytest.mark.parametrize('section,key', oracle_cases(
    git_oracle.test_should_refuse_git_config_read_redirections, 'section,key'))
@pytest.mark.parametrize('value', oracle_cases(
    git_oracle.test_should_refuse_git_config_read_redirections, 'value'))
def test_handoff_git_config_read_redirection_without_reference(
    independent, target, section, key, value
):
    metadata = git_oracle.git_directory(target)
    (metadata / 'config').write_text(f'[{section}]\n{key} = {value}\n')
    assert_preflight_partial(independent, target)


def test_handoff_git_detached_refs_symlink_without_reference(independent, target):
    metadata = git_oracle.git_directory(target)
    (metadata / 'HEAD').write_text('a' * 40 + '\n')
    refs = metadata / 'refs'
    original = metadata / 'refs-original'
    refs.rename(original)
    refs.symlink_to(original, target_is_directory=True)
    assert_preflight_partial(independent, target)
