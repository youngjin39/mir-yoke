"""Explicit common-code sync, isolation and local extension contracts."""
from __future__ import annotations

import hashlib
import importlib
import json
import subprocess

import pytest


def _git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'source'
    pkg = root / 'tools/mir_executor'
    pkg.mkdir(parents=True)
    (pkg / '__init__.py').write_text('')
    (pkg / 'policy.py').write_text('VALUE = 2\n')
    (pkg / 'local.py').write_text('PRIVATE = True\n')
    (pkg / 'tests/local').mkdir(parents=True)
    (pkg / 'tests/local/test_private.py').write_text('LOCAL = True\n')
    _git(root, 'init', '-q')
    _git(root, 'add', '.')
    _git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
         'commit', '-qm', 'source')
    return root


def _target(tmp_path):
    root = tmp_path / 'target'
    pkg = root / 'tools/mir_executor'
    pkg.mkdir(parents=True)
    (pkg / 'policy.py').write_text('VALUE = 1\n')
    (pkg / 'local.py').write_text('PRIVATE = 99\n')
    (pkg / 'custom.py').write_text('CUSTOM = True\n')
    (pkg / 'tests/local').mkdir(parents=True)
    (pkg / 'tests/local/test_private.py').write_text('PRIVATE_TEST = True\n')
    (root / 'config').mkdir()
    (root / 'config/mir-executor.local.json').write_text('{"require_review":true}\n')
    _git(root, 'init', '-q')
    _git(root, 'add', '.')
    _git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
         'commit', '-qm', 'target')
    return root


def _api():
    return importlib.import_module('tools.executor_sync')


def test_should_generate_hashes_without_local_files(source):
    manifest = _api().generate_manifest(source)
    assert manifest['source_commit'] == 'SOURCE_COMMIT'
    assert manifest['files'] == {
        'tools/mir_executor/__init__.py': hashlib.sha256(b'').hexdigest(),
        'tools/mir_executor/policy.py': hashlib.sha256(b'VALUE = 2\n').hexdigest(),
    }
    assert json.loads((source / 'config/mir-executor-common.json').read_text()) == manifest


def test_should_show_per_file_dry_run_without_writes(source, tmp_path):
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    before = {p.relative_to(target): p.read_bytes() for p in target.rglob('*')
              if p.is_file() and '.git' not in p.parts}
    report = api.sync(target, source_root=source)
    assert 'tools/mir_executor/policy.py' in report
    assert 'changed' in report and 'COMMON_MANIFEST.json' in report
    after = {p.relative_to(target): p.read_bytes() for p in target.rglob('*')
             if p.is_file() and '.git' not in p.parts}
    assert before == after


def test_should_apply_only_common_files_and_preserve_local_data(source, tmp_path):
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    preserved = [target / 'tools/mir_executor/local.py',
                 target / 'tools/mir_executor/custom.py',
                 target / 'tools/mir_executor/tests/local/test_private.py',
                 target / 'config/mir-executor.local.json']
    before = [p.read_bytes() for p in preserved]
    api.sync(target, source_root=source, apply=True)
    assert (target / 'tools/mir_executor/policy.py').read_text() == 'VALUE = 2\n'
    assert [p.read_bytes() for p in preserved] == before
    expected = dict(api._read_manifest(source / api.SOURCE_MANIFEST),
                    source_commit=_git(source, 'rev-parse', 'HEAD').stdout.decode().strip())
    assert (target / api.CONSUMER_MANIFEST).read_bytes() == (
        json.dumps(expected, indent=2, sort_keys=True) + '\n'
    ).encode()
    assert api.check(target, source_root=source) == []


def test_should_refuse_dirty_common_files(source, tmp_path):
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    (target / 'tools/mir_executor/policy.py').write_text('DIRTY = True\n')
    with pytest.raises(ValueError, match='dirty'):
        api.sync(target, source_root=source, apply=True)
    assert (target / 'tools/mir_executor/policy.py').read_text() == 'DIRTY = True\n'


def test_should_detect_local_and_source_drift(source, tmp_path):
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    api.sync(target, source_root=source, apply=True)
    (target / 'tools/mir_executor/policy.py').write_text('EDIT = True\n')
    assert any('policy.py' in item for item in api.check(target, source_root=None))
    (target / 'tools/mir_executor/policy.py').write_text('VALUE = 2\n')
    (source / 'tools/mir_executor/policy.py').write_text('VALUE = 3\n')
    assert any('source' in item and 'policy.py' in item
               for item in api.check(target, source_root=source))


def test_should_refuse_symlink_targets(source, tmp_path):
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    outside = tmp_path / 'outside.py'
    outside.write_text('DO NOT WRITE\n')
    (target / 'tools/mir_executor/policy.py').unlink()
    (target / 'tools/mir_executor/policy.py').symlink_to(outside)
    with pytest.raises(ValueError, match='symlink'):
        api.sync(target, source_root=source, apply=True)
    assert outside.read_text() == 'DO NOT WRITE\n'


def _native_source(source, monkeypatch, *, target='aarch64-apple-darwin', name='executor-query'):
    from mir.core.capabilities import native

    monkeypatch.setattr(native, 'host_target', lambda: target)
    artifact = source / name
    artifact.write_bytes(b'#!/bin/sh\necho query\n')
    lock = {
        'plugins': {'mir-core': {}},
        'native_artifacts': {name: {
            'plugin': 'mir-core', 'install_path': f'bin/{name}',
            'targets': {target: {
                'url': str(artifact), 'size': artifact.stat().st_size,
                'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }},
        }},
    }
    (source / '.mir').mkdir()
    (source / '.mir/capability-lock.json').write_text(json.dumps(lock))
    return lock


@pytest.mark.parametrize('host', ['aarch64-apple-darwin', 'x86_64-pc-windows-msvc'])
def test_should_install_provider_pinned_query_with_common_sync(source, tmp_path, monkeypatch, host):
    lock = _native_source(source, monkeypatch, target=host)
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    api.sync(target, source_root=source, apply=True)
    manifest = json.loads((target / 'tools/mir_executor/COMMON_MANIFEST.json').read_text())
    relative = '.mir/bin/executor-query' + ('.exe' if 'windows' in host else '')
    pin = lock['native_artifacts']['executor-query']['targets'][host]
    assert 'native_query' not in manifest
    expected = dict(api._read_manifest(source / api.SOURCE_MANIFEST),
                    source_commit=_git(source, 'rev-parse', 'HEAD').stdout.decode().strip())
    assert (target / api.CONSUMER_MANIFEST).read_bytes() == (
        json.dumps(expected, indent=2, sort_keys=True) + '\n'
    ).encode()
    assert json.loads((target / '.mir/bin/executor-query.json').read_text()) == {
        'path': relative, 'sha256': pin['sha256'],
    }
    assert api.check(target, source_root=None) == []
    executable = target / relative
    assert executable.read_bytes() == (source / 'executor-query').read_bytes()
    assert executable.stat().st_mode & 0o111


@pytest.mark.parametrize('guard', ['missing_host', 'hash', 'disabled', 'symlink'])
def test_should_omit_native_pin_after_failed_or_unavailable_delivery(
    source, tmp_path, monkeypatch, guard,
):
    lock = _native_source(source, monkeypatch)
    pin = lock['native_artifacts']['executor-query']['targets']['aarch64-apple-darwin']
    if guard == 'missing_host':
        lock['native_artifacts']['executor-query']['targets'] = {}
    elif guard == 'hash':
        pin['sha256'] = '0' * 64
    elif guard == 'disabled':
        monkeypatch.setenv('MIR_CAPABILITY_NATIVE_ARTIFACTS', '0')
    (source / '.mir/capability-lock.json').write_text(json.dumps(lock))
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    old = target / 'tools/mir_executor/COMMON_MANIFEST.json'
    old.write_text(json.dumps({'native_query': {
        'path': '.mir/bin/executor-query', 'sha256': 'f' * 64,
    }}))
    _git(target, 'add', '.')
    _git(target, '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
         'commit', '-qm', 'old pin')
    local_pin = target / '.mir/bin/executor-query.json'
    if guard != 'symlink':
        local_pin.parent.mkdir(parents=True)
        local_pin.write_text('{}')
    if guard == 'symlink':
        outside = tmp_path / 'outside'
        outside.mkdir()
        (target / '.mir').symlink_to(outside, target_is_directory=True)
    api.sync(target, source_root=source, apply=True)
    manifest = json.loads(old.read_text())
    assert 'native_query' not in manifest
    assert not local_pin.exists()
    assert not (target / '.mir/bin/executor-query').exists()


def test_should_never_install_native_artifact_during_dry_run(source, tmp_path, monkeypatch):
    _native_source(source, monkeypatch)
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    api.sync(target, source_root=source)
    assert not (target / '.mir').exists()


def test_should_detect_tampered_installed_query(source, tmp_path, monkeypatch):
    _native_source(source, monkeypatch)
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    api.sync(target, source_root=source, apply=True)
    (target / '.mir/bin/executor-query').write_bytes(b'tampered')
    assert any('native query drift' in error for error in api.check(target, source_root=None))


def test_should_reject_unsafe_manifest_paths(source, tmp_path):
    api = _api()
    api.generate_manifest(source)
    config = source / 'config/mir-executor-common.json'
    data = json.loads(config.read_text())
    data['files']['../outside.py'] = hashlib.sha256(b'').hexdigest()
    config.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='common path'):
        api.sync(_target(tmp_path), source_root=source, apply=True)


def test_should_use_defaults_when_local_module_absent(tmp_path):
    hooks = importlib.import_module('tools.mir_executor.local_hooks')
    assert hooks.local_config(tmp_path) == {}
    assert hooks.invoke_hook(tmp_path, 'pre_execute', object(), tmp_path) is None
    with hooks.writer_scope(tmp_path):
        pass


def test_should_call_repo_hooks_without_cross_repo_leakage(tmp_path):
    hooks = importlib.import_module('tools.mir_executor.local_hooks')
    for name, model in [('first', 'first-model'), ('second', 'second-model')]:
        root = tmp_path / name
        pkg = root / 'tools/mir_executor'
        pkg.mkdir(parents=True)
        (pkg / 'local.py').write_text(
            f'def resolve_route_key(repo_root, key):\n    return ({model!r}, "high")\n'
        )
        assert hooks.invoke_hook(root, 'resolve_route_key', root, 'key') == (model, 'high')


def test_should_load_local_config_and_fail_on_invalid_data(tmp_path):
    hooks = importlib.import_module('tools.mir_executor.local_hooks')
    config = tmp_path / 'config/mir-executor.local.json'
    config.parent.mkdir()
    config.write_text('{"codex_sandbox_default":"read-only","input_limit_bytes":5}')
    assert hooks.local_config(tmp_path)['input_limit_bytes'] == 5
    config.write_text('[]')
    with pytest.raises(ValueError, match='object'):
        hooks.local_config(tmp_path)


def test_should_preserve_repo_tests_outside_the_tiny_common_contract(source):
    pkg = source / 'tools/mir_executor'
    (pkg / 'tests/test_repo_specific.py').write_text('REPO_TEST = True\n')
    (pkg / 'tests/test_common_manifest.py').write_text('COMMON_TEST = True\n')
    manifest = _api().generate_manifest(source)
    assert 'tools/mir_executor/tests/test_repo_specific.py' not in manifest['files']
    assert 'tools/mir_executor/tests/test_common_manifest.py' in manifest['files']


def test_should_leave_git_index_unchanged_during_dry_run(source, tmp_path):
    import os

    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    index = target / '.git/index'
    before = index.read_bytes()
    common = target / 'tools/mir_executor/policy.py'
    stat = common.stat()
    os.utime(common, ns=(stat.st_atime_ns, stat.st_mtime_ns + 20_000_000_000))
    api.sync(target, source_root=source)
    assert index.read_bytes() == before


@pytest.mark.parametrize('name', ['executor-query', 'delegation-gate'])
def test_should_remove_stale_local_pin_when_host_artifact_disappears(
    source, tmp_path, monkeypatch, name,
):
    lock = _native_source(source, monkeypatch, name=name)
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    api.sync(target, source_root=source, apply=True)
    manifest = (target / api.CONSUMER_MANIFEST).read_bytes()
    pin = target / f'.mir/bin/{name}.json'
    assert pin.is_file()
    _git(target, 'add', 'tools')
    _git(target, '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
         'commit', '-qm', 'common sync')
    lock['native_artifacts'][name]['targets'] = {}
    (source / '.mir/capability-lock.json').write_text(json.dumps(lock))
    before = pin.read_bytes()
    api.sync(target, source_root=source)
    assert pin.read_bytes() == before
    api.sync(target, source_root=source, apply=True)
    assert not pin.exists()
    assert (target / f'.mir/bin/{name}').is_file()
    assert (target / api.CONSUMER_MANIFEST).read_bytes() == manifest
    assert api.check(target, source_root=None) == []


@pytest.mark.parametrize('state', ['absent', 'invalid', 'symlink', 'legacy_manifest'])
def test_should_check_only_present_local_pin(source, tmp_path, state):
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    api.sync(target, source_root=source, apply=True)
    pin = target / '.mir/bin/executor-query.json'
    if state in {'invalid', 'symlink'}:
        pin.parent.mkdir(parents=True, exist_ok=True)
        if state == 'invalid':
            pin.write_text('{}')
        else:
            pin.symlink_to(pin.parent / 'missing.json')
    if state == 'legacy_manifest':
        manifest = target / api.CONSUMER_MANIFEST
        data = json.loads(manifest.read_text())
        data['native_query'] = {'path': '.mir/bin/executor-query', 'sha256': 'f' * 64}
        manifest.write_text(json.dumps(data))
    errors = api.check(target, source_root=None)
    assert errors == ([] if state in {'absent', 'legacy_manifest'}
                      else ['native query drift: executor-query'])


def test_should_preserve_pin_if_atomic_replace_fails(tmp_path, monkeypatch):
    import pathlib

    api = _api()
    parent = tmp_path / '.mir/bin'
    parent.mkdir(parents=True)
    pin = parent / 'executor-query.json'
    pin.write_bytes(b'old pin')

    def fail_replace(self, target):
        assert target == pin
        assert pin.read_bytes() == b'old pin'
        assert json.loads(self.read_text()) == {
            'path': '.mir/bin/executor-query', 'sha256': 'a' * 64,
        }
        raise OSError('replace failed')

    monkeypatch.setattr(pathlib.Path, 'replace', fail_replace)
    with pytest.raises(OSError, match='replace failed'):
        api._write_query_pin(tmp_path, {'path': '.mir/bin/executor-query', 'sha256': 'a' * 64})
    assert list(parent.iterdir()) == [pin]
    assert pin.read_bytes() == b'old pin'


@pytest.mark.parametrize('host', ['aarch64-apple-darwin', 'x86_64-pc-windows-msvc'])
def test_should_install_provider_pinned_delegation_gate(source, tmp_path, monkeypatch, host):
    lock = _native_source(source, monkeypatch, target=host, name='delegation-gate')
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    assert api.main(['--target', str(target), '--source-root', str(source), '--apply']) == 0
    relative = '.mir/bin/delegation-gate' + ('.exe' if 'windows' in host else '')
    pin = lock['native_artifacts']['delegation-gate']['targets'][host]
    assert json.loads((target / '.mir/bin/delegation-gate.json').read_text()) == {
        'path': relative, 'sha256': pin['sha256'],
    }
    binary = target / relative
    assert binary.read_bytes() == (source / 'delegation-gate').read_bytes()
    assert binary.stat().st_mode & 0o111
    assert api.check(target, source_root=None) == []
    binary.write_bytes(b'tampered')
    assert api.check(target, source_root=None) == ['native gate drift: delegation-gate']


@pytest.mark.parametrize('guard', ['missing_host', 'hash', 'disabled', 'symlink'])
def test_should_omit_unavailable_delegation_gate_pin(source, tmp_path, monkeypatch, guard):
    lock = _native_source(source, monkeypatch, name='delegation-gate')
    record = lock['native_artifacts']['delegation-gate']
    if guard == 'missing_host':
        record['targets'] = {}
    elif guard == 'hash':
        record['targets']['aarch64-apple-darwin']['sha256'] = '0' * 64
    elif guard == 'disabled':
        monkeypatch.setenv('MIR_CAPABILITY_NATIVE_ARTIFACTS', '0')
    (source / '.mir/capability-lock.json').write_text(json.dumps(lock))
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    if guard == 'symlink':
        outside = tmp_path / 'outside'
        outside.mkdir()
        (target / '.mir').symlink_to(outside, target_is_directory=True)
    else:
        pin = target / '.mir/bin/delegation-gate.json'
        pin.parent.mkdir(parents=True)
        pin.write_text('{}')
    api.sync(target, source_root=source, apply=True)
    assert not (target / '.mir/bin/delegation-gate.json').exists()
    assert not (target / '.mir/bin/delegation-gate').exists()
    assert api.check(target, source_root=None) == []


def test_should_never_install_delegation_gate_during_dry_run(source, tmp_path, monkeypatch):
    _native_source(source, monkeypatch, name='delegation-gate')
    api = _api()
    api.generate_manifest(source)
    target = _target(tmp_path)
    api.sync(target, source_root=source)
    assert not (target / '.mir').exists()
