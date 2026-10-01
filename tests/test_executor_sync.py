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
    manifest = json.loads((target / 'tools/mir_executor/COMMON_MANIFEST.json').read_text())
    assert manifest['source_commit'] == _git(source, 'rev-parse', 'HEAD').stdout.decode().strip()
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
