"""Closed native hook declarations also validate through the Python config reader."""
from __future__ import annotations

import copy
import json
import runpy
import sys
from pathlib import Path

import pytest

from tools.mir_executor.local_hooks import local_config

PARITY = runpy.run_path(
    str(Path(__file__).with_name('test_executor_target_policy_native_parity.py')))
binary = PARITY['binary']


def declaration():
    return {'executable': 'tools/hook-host', 'argv': ['--stdio'], 'sha256': 'a' * 64,
            'hooks': ['writer_scope', 'on_job_event']}


def read_config(tmp_path, hooks):
    path = tmp_path / 'config/mir-executor.local.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'native_policy': {'version': 1, 'hooks': hooks}}))
    return local_config(tmp_path)


@pytest.mark.parametrize(('key', 'bad'), [
    ('executable', ''), ('executable', '/bin/host'), ('executable', '../host'),
    ('executable', 'tools/../host'), ('executable', 'tools/./host'),
    ('executable', '.'), ('executable', 'tools/\0host'),
    ('executable', True), ('argv', '--stdio'), ('argv', [1]), ('argv', ['bad\0argument']),
    ('sha256', 'a' * 63),
    ('sha256', 'g' * 64), ('hooks', []), ('hooks', ['writer_scope', 'writer_scope']),
    ('hooks', ['pre_execute']), ('hooks', [True]), ('hooks', 'writer_scope'),
    ('unknown', True),
])
def test_python_config_rejects_invalid_native_hooks(tmp_path, key, bad):
    hooks = declaration()
    hooks[key] = bad
    with pytest.raises(ValueError, match='native_policy'):
        read_config(tmp_path, hooks)


@pytest.mark.parametrize('key', ['executable', 'argv', 'sha256', 'hooks'])
def test_python_config_requires_native_hook_fields(tmp_path, key):
    hooks = declaration()
    del hooks[key]
    with pytest.raises(ValueError, match='native_policy'):
        read_config(tmp_path, hooks)


@pytest.mark.parametrize('hooks', [None, True, []])
def test_python_config_rejects_nonobject_native_hooks(tmp_path, hooks):
    with pytest.raises(ValueError, match='native_policy'):
        read_config(tmp_path, hooks)


def test_python_config_rejects_platform_path_anchors_and_traversal(tmp_path):
    paths = ['/hook', '../hook', 'tools/./hook']
    if sys.platform == 'win32':
        paths.extend([r'C:hook', r'C:\hook', r'\hook', r'\\server\share\hook',
                      r'tools\..\hook', r'tools\.\hook'])
    for path in paths:
        hooks = declaration()
        hooks['executable'] = path
        with pytest.raises(ValueError, match='native_policy'):
            read_config(tmp_path, hooks)


def test_python_config_preserves_valid_native_hooks(tmp_path):
    hooks = declaration()
    assert read_config(tmp_path, hooks)['native_policy']['hooks'] == hooks
    hooks = copy.deepcopy(hooks)
    hooks.update(argv=[], sha256='A' * 64, hooks=['on_job_event'])
    assert read_config(tmp_path, hooks)['native_policy']['hooks'] == hooks


def test_python_config_without_hooks_keeps_legacy_semantics(tmp_path):
    path = tmp_path / 'config/mir-executor.local.json'
    path.parent.mkdir()
    value = {'verifiers': {'check': ['check']}, 'native_policy': {'legacy': True}}
    path.write_text(json.dumps(value))
    assert local_config(tmp_path) == value


@pytest.mark.parametrize('name', ['writer_scope', 'on_job_event'])
def test_native_hooks_reject_python_ownership_before_import(binary, tmp_path, name):
    support = PARITY['SUPPORT']
    root = tmp_path / 'conflicting-hook'
    launcher = support['seed'](root, 'success')
    PARITY['configure'](root, {}, False)
    config = root / 'config/mir-executor.local.json'
    config.write_text(json.dumps({'native_policy': {'version': 1, 'hooks': declaration()}}))
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        '(Path(__file__).resolve().parents[2] / "unexpected-import").touch()\n'
        f'def {name}(*args):\n    raise RuntimeError("duplicate owner ran")\n')
    result = PARITY['invoke'](binary, root, support['environment'](root, 'success', launcher),
                              support['argv']('success'))
    assert result.returncode == 1, result.stderr
    assert name.encode() in result.stderr
    for path in ('unexpected-import', 'provider-started', 'tasks/jobs.db'):
        assert not (root / path).exists(), (path, result.stderr)
