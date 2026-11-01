"""Native query admission runs before the executor's heavyweight imports."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name == 'nt', reason='POSIX shell launcher fixtures')


def _install(root, body='echo native-query; exit 0\n'):
    executable = root / '.mir/bin/executor-query'
    executable.parent.mkdir(parents=True)
    executable.write_text('#!/bin/sh\n' + body)
    executable.chmod(0o755)
    (root / 'tools/mir_executor').mkdir(parents=True)
    manifest = root / '.mir/bin/executor-query.json'
    manifest.write_text(json.dumps({
        'path': '.mir/bin/executor-query',
        'sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
    }))
    return executable, manifest


@pytest.mark.parametrize('route', ['module', 'mir'])
def test_native_query_uses_both_production_routes_without_heavy_imports(tmp_path, route):
    _install(tmp_path)
    for name in ('__init__.py', '__main__.py', 'entrypoint.py'):
        shutil.copy2(ROOT / 'tools/mir_executor' / name, tmp_path / 'tools/mir_executor' / name)
    # A blocked import proves the launch point is before cli/executor/dispatch.
    code = '''
import importlib.abc, runpy, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"tools.mir_executor.cli", "tools.mir_executor.executor"}:
            raise AssertionError("heavy executor imported")
sys.meta_path.insert(0, Block())
sys.argv = ["mir", *sys.argv[1:]]
runpy.run_module(MODULE, run_name="__main__")
'''.replace('MODULE', repr('tools.mir_executor' if route == 'module' else 'mir.cli'))
    args = ([] if route == 'module' else ['executor']) + [
        'list-jobs', '--repo-root', str(tmp_path),
    ]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tmp_path), str(ROOT / 'src')]))
    env.pop('MIR_EXECUTOR_QUERY_IMPL', None)
    env.pop('MIR_NATIVE_HOOKS', None)
    result = subprocess.run([sys.executable, '-c', code, *args], env=env,
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'native-query\n'
    assert not (tmp_path / 'tasks/jobs.db').exists()


@pytest.mark.parametrize('guard', [
    'decline', 'spawn', 'hash', 'pin', 'symlink', 'python', 'disabled', 'mutation',
    'cross_target', 'encoding', 'pin_symlink', 'manifest_only',
])
def test_unsafe_or_unsupported_native_query_falls_back_unchanged(
    tmp_path, monkeypatch, capsys, guard,
):
    executable, manifest = _install(tmp_path, 'echo must-not-leak; exit 64\n')
    monkeypatch.delenv('MIR_EXECUTOR_QUERY_IMPL', raising=False)
    monkeypatch.delenv('MIR_NATIVE_HOOKS', raising=False)
    argv = ['status', '--repo-root', str(tmp_path), '--job-id', 'job']
    if guard == 'spawn':
        executable.chmod(0o644)
    elif guard == 'hash':
        executable.write_text('changed')
    elif guard == 'pin':
        manifest.write_text('{}')
    elif guard == 'symlink':
        original = executable.with_name('original')
        executable.rename(original)
        executable.symlink_to(original)
    elif guard == 'pin_symlink':
        original = manifest.with_name('original.json')
        manifest.rename(original)
        manifest.symlink_to(original)
    elif guard == 'manifest_only':
        legacy = tmp_path / 'tools/mir_executor/COMMON_MANIFEST.json'
        legacy.write_text(json.dumps({'native_query': json.loads(manifest.read_text())}))
        manifest.unlink()
    elif guard == 'python':
        monkeypatch.setenv('MIR_EXECUTOR_QUERY_IMPL', 'python')
    elif guard == 'disabled':
        monkeypatch.setenv('MIR_NATIVE_HOOKS', '0')
    elif guard == 'mutation':
        argv[0] = 'cancel'
    elif guard == 'encoding':
        monkeypatch.setattr(sys, 'stdout', types.SimpleNamespace(encoding='ascii'))
    calls = []
    monkeypatch.setitem(sys.modules, 'tools.mir_executor.cli', types.SimpleNamespace(
        main=lambda args: calls.append(args) or 7,
    ))
    entrypoint = importlib.import_module('tools.mir_executor.entrypoint')
    if guard != 'cross_target':
        monkeypatch.setattr(entrypoint, '_HOME_ROOT', tmp_path)
    native_calls = []
    run = subprocess.run

    def record_run(*args, **kwargs):
        native_calls.append(args[0])
        return run(*args, **kwargs)

    monkeypatch.setattr(subprocess, 'run', record_run)
    assert entrypoint.main(argv) == 7
    assert calls == [argv]
    assert len(native_calls) == (1 if guard in {'decline', 'spawn'} else 0)
    assert capsys.readouterr() == ('', '')


def test_native_exit_status_and_streams_are_forwarded(tmp_path, monkeypatch, capsys):
    _install(tmp_path, 'echo output; echo error >&2; exit 1\n')
    monkeypatch.delenv('MIR_EXECUTOR_QUERY_IMPL', raising=False)
    monkeypatch.delenv('MIR_NATIVE_HOOKS', raising=False)
    entrypoint = importlib.import_module('tools.mir_executor.entrypoint')
    monkeypatch.setattr(entrypoint, '_HOME_ROOT', tmp_path)
    assert entrypoint.main(['result', '--repo-root', str(tmp_path), '--job-id', 'x']) == 1
    output = capsys.readouterr()
    assert output.out == 'output\n'
    assert output.err == 'error\n'


@pytest.mark.parametrize('route', ['module', 'mir'])
def test_native_output_bytes_survive_production_entrypoints(tmp_path, route):
    _install(tmp_path, "printf '\\377\\376'; printf '\\375' >&2\n")
    for name in ('__init__.py', '__main__.py', 'entrypoint.py'):
        shutil.copy2(ROOT / 'tools/mir_executor' / name, tmp_path / 'tools/mir_executor' / name)
    command = [sys.executable, '-m', 'tools.mir_executor' if route == 'module' else 'mir.cli']
    if route == 'mir':
        command.append('executor')
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tmp_path), str(ROOT / 'src')]))
    env.pop('MIR_EXECUTOR_QUERY_IMPL', None)
    env.pop('MIR_NATIVE_HOOKS', None)
    result = subprocess.run(command + ['list-jobs'], env=env, cwd=tmp_path, capture_output=True)
    assert result.returncode == 0
    assert result.stdout == b'\xff\xfe'
    assert result.stderr == b'\xfd'
