"""Policy query bytes, production pin routing, and replay of the Python policy corpus."""
from __future__ import annotations

import importlib.util
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = runpy.run_path(str(ROOT / 'tests/test_executor_query_native_parity.py'))
binary = SUPPORT['binary']
install_pin = SUPPORT['install_pin']


@pytest.fixture
def home(tmp_path, binary):
    root = tmp_path / 'provider home'
    package = root / 'tools/mir_executor'
    package.mkdir(parents=True)
    for name in ('__init__.py', 'entrypoint.py', 'policy.py'):
        shutil.copy2(ROOT / 'tools/mir_executor' / name, package / name)
    for name in ('__init__.py', '__main__.py', 'cli/__init__.py',
                 'cli/__main__.py', 'cli/policy.py'):
        target = root / 'src/mir' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'src/mir' / name, target)
    install_pin(binary, root)
    (root / 'empty.json').write_text('{}', encoding='utf-8')
    return root


def invoke(home, argv, *, binary=None, python=False, environment=None, cwd=None):
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=os.pathsep.join((str(home / 'src'), str(home))),
               MIR_NATIVE_HOOKS='1', MIR_EXECUTOR_IMPL='native',
               MIR_EXECUTOR_QUERY_IMPL='python' if python else 'native',
               MIR_SUB_AGENT_POLICY=str(home / 'empty.json'))
    env.update(environment or {})
    command = ([str(binary), '--home-root', str(home), 'policy-resolve', *argv]
               if binary else [sys.executable, '-m', 'mir', 'policy', 'resolve', *argv])
    result = subprocess.run(command, cwd=cwd or home, env=env,
                            capture_output=True, check=False, timeout=20)
    return result.stdout, result.stderr, result.returncode


def compare(binary, home, argv, **kwargs):
    expected = invoke(home, argv, python=True, **kwargs)
    direct = invoke(home, argv, binary=binary, **kwargs)
    assert direct == expected or direct == (b'', b'', 64), (argv, direct, expected)
    assert invoke(home, argv, **kwargs) == expected
    return direct


@pytest.mark.parametrize('root', [None, 'relative-target', 'absolute-target'])
def test_pin_routes_before_importing_python_policy(binary, home, root):
    argv = ['--category', 'unit']
    if root:
        target = home / root
        (target / 'config').mkdir(parents=True)
        (target / 'config/model-routing.lock.json').write_text(json.dumps({
            'policy': {'routing': {'default': {'model': 'target-model'}}}}))
        argv += ['--repo-root', str(target) if root.startswith('absolute') else root]
    expected = invoke(home, argv, python=True)
    (home / 'tools/mir_executor/policy.py').write_text(
        "raise RuntimeError('Python policy imported')\n", encoding='utf-8')
    assert invoke(home, argv) == expected
    for selector in ('MIR_EXECUTOR_IMPL', 'MIR_EXECUTOR_QUERY_IMPL'):
        result = invoke(home, argv, environment={selector: 'python'})
        assert result[2] == 1 and b'Python policy imported' in result[1]


@pytest.mark.parametrize('kind', ['missing', 'old'])
def test_missing_and_older_pin_fall_back(binary, home, kind):
    argv = ['--category', 'unit']
    expected = invoke(home, argv, python=True)
    if kind == 'missing':
        (home / '.mir/bin/executor-query.json').unlink()
    else:
        # Real executable boundary for the legacy unknown-query protocol on every OS.
        # A retained baseline build additionally exercises the actual old binary.
        source = home / 'legacy_query.rs'
        source.write_text('fn main() { std::process::exit(64); }', encoding='utf-8')
        legacy = home / binary.name
        subprocess.run(['rustc', '--crate-name', 'legacy_query', str(source),
                        '-o', str(legacy)], check=True, timeout=60)
        old = os.environ.get('MIR_POLICY_OLD_BINARY')
        if old:
            shutil.copy2(old, legacy)
        shutil.rmtree(home / '.mir/bin')
        install_pin(legacy, home)
        assert invoke(home, argv, binary=legacy) == (b'', b'', 64)
    assert invoke(home, argv) == expected


CATEGORIES = list(json.loads((ROOT / 'config/model-routing.lock.json').read_text())[
    'policy']['routing']['by_category']) + ['unknown', '']
ROUTES = [None, {}, {'model': None, 'reasoning_effort': None},
          {'model': ' m\u00e9\U0001f600 ', 'reasoning_effort': ' high '},
          {'model': '\u001cmodel\u001f', 'reasoning_effort': '\u001elow'},
          {'model': 7, 'prefer': ['bad', None, {}, {'reasoning_effort': 'xhigh'}]},
          {'prefer': False}, {'prefer': [{'model': 'preferred'}, {'model': 'second'}]}]


@pytest.mark.parametrize('format', ['json', 'text'])
@pytest.mark.parametrize('route', ROUTES)
def test_generated_central_categories(binary, home, route, format):
    config = home / 'config'
    config.mkdir()
    policy = {'delegation': {'mode': 'force_codex'}, 'routing': {
        'default': {'model': 'default', 'reasoning_effort': 'medium'},
        'by_category': dict.fromkeys(CATEGORIES, route)}}
    (config / 'model-routing.lock.json').write_text(json.dumps({'policy': policy}))
    for category in CATEGORIES:
        result = compare(binary, home, ['--category=' + category, '--format=' + format])
        if route != ROUTES[4]:
            assert result[2] == 0


@pytest.mark.parametrize('payload', ['{', '[]', 'null', '\ufeff{}', '[policy]\nmode="select"',
                                    '{"mode": []}', '{"routing": {"default_model": NaN}}',
                                    '{"routing":{"default_model":"\\ud800"}}'])
@pytest.mark.parametrize('location', ['local', 'lock', 'overlay'])
def test_malformed_and_unusual_config(binary, home, payload, location):
    config = home / 'config'
    config.mkdir()
    path = {'local': config / 'sub-agent-policy.json',
            'lock': config / 'model-routing.lock.json',
            'overlay': home / 'override.toml'}[location]
    path.write_text(payload, encoding='utf-8')
    env = {'MIR_SUB_AGENT_POLICY': str(path)} if location == 'overlay' else {}
    compare(binary, home, ['--category', 'unit'], environment=env)


@pytest.mark.parametrize('argv', [[], ['--category'], ['--category', 'unit', '--format', 'bad'],
                                ['--help'], ['--category', 'unit', '--unknown'],
                                ['--category=unit', '--category=edge'], ['--cat', 'unit']])
def test_argparse_declines_preserve_python_bytes(binary, home, argv):
    compare(binary, home, argv)


@pytest.mark.parametrize('root', [None, '.', 'child', 'absent', 'child/..'])
def test_relative_absent_and_cross_repository_root(binary, home, root):
    (home / 'child').mkdir()
    argv = ['--category', 'unit', '--format', 'text']
    if root is not None:
        argv += ['--repo-root', root]
    assert compare(binary, home, argv)[2] == 0


@pytest.mark.parametrize('overlay', ['missing', 'relative', 'tilde', 'unset'])
def test_overlay_path_and_account_home(binary, home, overlay):
    environment = {'HOME': str(home), 'USERPROFILE': str(home)}
    if overlay == 'missing':
        environment['MIR_SUB_AGENT_POLICY'] = str(home / 'absent.json')
    elif overlay == 'relative':
        environment['MIR_SUB_AGENT_POLICY'] = 'empty.json'
    elif overlay == 'tilde':
        environment['MIR_SUB_AGENT_POLICY'] = '~/empty.json'
    else:
        environment['MIR_SUB_AGENT_POLICY'] = ''
    compare(binary, home, ['--category', 'unit'], environment=environment)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX double-root spelling')
def test_double_root_warning_declines(binary, home):
    assert compare(binary, home, ['--category', 'unit'], environment={
        'MIR_SUB_AGENT_POLICY': '//mir-query-absent-policy.json',
    }) == (b'', b'', 64)


# Reuse every original test and its parametrization; each loader call also checks
# real policy CLI bytes for the same files and environment. Original assertions
# remain the oracle for injected default_global_policy_path seams.
_spec = importlib.util.spec_from_file_location(
    'policy_reference_cases', ROOT / 'tools/mir_executor/tests/test_policy.py')
_reference = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_reference)
for _name in dir(_reference):
    if _name.startswith('test_'):
        if (os.name == 'nt' and _name
                == 'test_adr88_default_global_policy_path_is_the_rendered_harness_policy'):
            continue  # The original imports Unix-only pwd; Windows is checked below.
        globals()['test_replay_' + _name[5:]] = getattr(_reference, _name)


@pytest.fixture(autouse=True)
def replay_policy_loader(request, monkeypatch):
    if not request.node.name.startswith('test_replay_'):
        return
    binary = request.getfixturevalue('binary')
    home = request.getfixturevalue('home')
    original = _reference.load_sub_agent_policy
    from tools.mir_executor import policy as policy_module

    # Match the original corpus's autouse conftest, which isolates the host fallback.
    monkeypatch.delenv('MIR_SUB_AGENT_POLICY', raising=False)
    monkeypatch.setattr(policy_module, 'default_global_policy_path',
                        lambda: home / 'absent-global-policy.json')

    def checked(root):
        result = original(root)
        environment = {'MIR_SUB_AGENT_POLICY': os.environ.get(
            'MIR_SUB_AGENT_POLICY', str(home / 'empty.json'))}
        for category in ('unit', 'architecture', 'missing'):
            for format in ('json', 'text'):
                compare(binary, home, ['--category', category, '--format', format,
                                       '--repo-root', str(root)], environment=environment)
        return result

    monkeypatch.setattr(_reference, 'load_sub_agent_policy', checked)

    def checked_run(command, **kwargs):
        assert command[1:5] == ['-m', 'mir', 'policy', 'resolve']
        compare(binary, home, command[5:], environment={
            'MIR_SUB_AGENT_POLICY': kwargs['env']['MIR_SUB_AGENT_POLICY']})
        return subprocess.run(command, **kwargs)

    monkeypatch.setattr(_reference, 'subprocess', SimpleNamespace(run=checked_run))


@pytest.mark.skipif(os.name != 'nt', reason='Windows account-home branch')
def test_windows_profile_fallback_ignores_home(binary, home):
    profile = home / 'account'
    rendered = profile / '.mir/model-routing/sub-agent-policy.json'
    rendered.parent.mkdir(parents=True)
    rendered.write_text(json.dumps({'routing': {'default': {'model': 'profile-model'}}}))
    assert compare(binary, home, ['--category', 'unit'], environment={
        'USERPROFILE': str(profile), 'HOME': str(home / 'wrong'),
        'MIR_SUB_AGENT_POLICY': '',
    })[2] == 0


@pytest.mark.skipif(os.name != 'nt', reason='Windows account-home branch')
def test_windows_empty_profile_declines_to_python(binary, home):
    assert compare(binary, home, ['--category', 'unit'], environment={
        'USERPROFILE': '', 'MIR_SUB_AGENT_POLICY': '',
    }) == (b'', b'', 64)
