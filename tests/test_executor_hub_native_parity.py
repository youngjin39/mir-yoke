"""Owner-captured goal bounds and execution identity match through the CLI."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import runpy
import shlex
import sqlite3
import sys
from pathlib import Path

import pytest

P1 = runpy.run_path(str(Path(__file__).with_name('test_executor_target_policy_native_parity.py')))
SUPPORT = P1['SUPPORT']
DISPATCH = P1['PARITY']['DISPATCH']
binary = P1['binary']
GOLDEN = json.loads((Path(__file__).parent / 'fixtures/executor_hub_profile.json').read_text())
GENERATOR = runpy.run_path(str(Path(__file__).resolve().parents[1] /
    'native/handoff-packet/tests/fixtures/generate_executor_hub_profile.py'))


def configure(root, bridge, *, limit=4096, version='9.8.7+fixture', bound=True,
              identity=True):
    path = root / 'config/mir-executor.local.json'
    path.parent.mkdir(exist_ok=True)
    config = json.loads(path.read_text()) if path.exists() else {}
    if limit == 'missing':
        config.pop('input_limit_bytes', None)
    else:
        config['input_limit_bytes'] = limit
    if bridge:
        source = GOLDEN['oracle_source']
        if not identity:
            source = source.replace('def job_identity(', 'def unused_identity(')
        (root / 'tools/mir_executor/local.py').write_text(source)
    else:
        (root / 'tools/mir_executor/local.py').unlink(missing_ok=True)
        policy = {'version': 1}
        if bound:
            policy['brief_profile'] = {'name': 'base_v1', 'input_bound': 'expanded_goal'}
        if identity:
            policy['job_identity'] = {'name': 'codex_mcp_v1', 'package': 'mir-agent-hub'}
            if version is not None:
                policy['job_identity']['package_version'] = version
        if len(policy) > 1:
            config['native_policy'] = policy
    if version not in (None, 'unknown'):
        dist = root / 'mir_agent_hub-9.8.7.dist-info'
        dist.mkdir(exist_ok=True)
        (dist / 'METADATA').write_text(
            f'Metadata-Version: 2.1\nName: mir-agent-hub\nVersion: {version}\n')
    path.write_text(json.dumps(config))


def seed(root, bridge, *, dispatch=True, **config):
    if dispatch:
        launcher, environment, args = DISPATCH['seed'](root, 'success', SUPPORT)
        payload = GENERATOR['brief_payload']()
        (root / 'brief.json').write_text(json.dumps(payload))
    else:
        launcher = SUPPORT['seed'](root, 'success')
        environment = SUPPORT['environment'](root, 'success', launcher)
        source = launcher.read_text().replace(
            "assert request['params']['input'] == [{'type': 'text', 'text': 'offline fixture'}]",
            "assert request['params']['input'][0]['type'] == 'text'")
        launcher.write_text(source)
        args = SUPPORT['argv']('background_success')
    configure(root, bridge, **config)
    return launcher, environment, args


def snapshot(root, launcher, result, dispatch):
    if dispatch:
        value = DISPATCH['snapshot'](root, result)
        value.pop('git_status')
    else:
        value = SUPPORT['snapshot'](root, launcher, result)
    for stream in ('stdout', 'stderr'):
        normalized = P1['stream_bytes'](getattr(result, stream), root, launcher)
        if dispatch:
            normalized = re.sub(rb"""mir-wt-[^/\\\s"']+""", b'mir-wt-<temp>', normalized)
            normalized = re.sub(rb'\b[0-9a-f]{32}\b', b'<id>', normalized)
        value[stream + '_bytes'] = normalized
    return value


def jobs(root):
    if not (root / 'tasks/jobs.db').exists():
        return []
    with sqlite3.connect(root / 'tasks/jobs.db') as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute('SELECT * FROM jobs')]


def owner_hooks(monkeypatch):
    # Restore the caller's import table after the extracted loader is bound.
    monkeypatch.setitem(sys.modules, 'mir.core.conductor.dispatch_brief', None)
    namespace = {}
    exec(GOLDEN['oracle_source'], namespace)
    namespace['DispatchBrief'].model_rebuild(_types_namespace=namespace)
    return namespace


def test_oracle_pins():
    assert GOLDEN['sha256'] == {
        'local': 'c238c92a06b687ae38a740989af069d361807a7851f21363b4ab810881e0a93d',
        'contracts': '4261212c8df5177646513775d92c286abb6dd1afb3000a1b1254cd1cac4e22fa',
        'loader': '8171f3ea0f41a84adcde60858d80a1c156a1ecb23ac58602275e0eff7edc80af',
    }


@pytest.mark.parametrize('case', GOLDEN['brief_cases'], ids=lambda case: case['name'])
def test_captured_owner_brief_oracle(tmp_path, monkeypatch, case):
    root = tmp_path / 'oracle'
    (root / 'config').mkdir(parents=True)
    (root / 'config/mir-executor.local.json').write_text(
        json.dumps({} if case['limit'] == 'missing' else {'input_limit_bytes': case['limit']}))
    namespace = owner_hooks(monkeypatch)
    argument = case['text']
    if case['payload'] is not None:
        argument = root / 'brief.json'
        argument.write_text(json.dumps(case['payload'], ensure_ascii=True, indent=2))
        if isinstance(case['limit'], (int, float)):
            assert argument.stat().st_size > case['limit']
    if 'kind' in case:
        with pytest.raises(Exception) as caught:
            namespace['validate_brief'](argument, root)
        assert type(caught.value).__name__ == case['kind']
        assert str(caught.value) == case['message']
    else:
        value = namespace['validate_brief'](argument, root)
        assert (value.model_dump(mode='json') if value is not None else None) == case['value']


@pytest.mark.parametrize('case', GOLDEN['identity_cases'])
def test_captured_owner_identity_oracle(tmp_path, monkeypatch, case):
    namespace = owner_hooks(monkeypatch)
    monkeypatch.syspath_prepend(str(tmp_path))
    if case['version'] != 'unknown':
        dist = tmp_path / 'mir_agent_hub-9.8.7.dist-info'
        dist.mkdir()
        (dist / 'METADATA').write_text(
            f"Metadata-Version: 2.1\nName: mir-agent-hub\nVersion: {case['version']}\n")
    value = namespace['job_identity'](argparse.Namespace(dispatch=case['dispatch']),
                                       tmp_path, case['prompt'], case['model'])
    assert value == case['value']


@pytest.mark.parametrize('case', GOLDEN['brief_cases'], ids=lambda case: case['name'])
def test_hub_brief_native_matches_owner(binary, tmp_path, case):
    values = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, args = seed(root, bridge, limit=case['limit'], identity=False)
        if case['payload'] is not None:
            (root / 'brief.json').write_text(
                json.dumps(case['payload'], ensure_ascii=True, indent=2))
        else:
            index = args.index('--dispatch-brief')
            del args[index:index + 2]
            args += ['--codex-args', case['text']]
        result = P1['invoke'](binary, root, environment, args)
        values.append(snapshot(root, launcher, result, True))
        assert result.returncode == (1 if 'kind' in case else 0), values[-1]
        if 'kind' in case:
            if case['name'] == 'plain_above':
                assert b'Codex input exceeds configured input_limit_bytes' in result.stderr
            else:
                assert case['message'].encode() in result.stderr
            assert not (root / 'provider-methods').exists()
        assert bool(jobs(root)) == (case['payload'] is None and case['name'] != 'plain_above'
                                   or 'kind' not in case)
    assert values[0] == values[1], values


@pytest.mark.parametrize('dispatch', [True, False], ids=['dispatch', 'background'])
@pytest.mark.parametrize('model', [None, '', '模型-é'])
@pytest.mark.parametrize('version', ['9.8.7+fixture', '漢字-é', 'unknown'])
def test_hub_identity_native_matches_owner(binary, tmp_path, dispatch, model, version):
    values = []
    prompt = 'exact café 漢字 😀\nwith trailing space '
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, args = seed(root, bridge, dispatch=dispatch, version=version,
                                           bound=False)
        for flag in (('--dispatch-brief', '--model') if dispatch else ('--codex-args',)):
            index = args.index(flag)
            del args[index:index + 2]
        args += ['--codex-args', shlex.join(['exec', prompt])]
        if model is not None:
            args += ['--model', model]
        result = P1['invoke'](binary, root, environment, args)
        values.append(snapshot(root, launcher, result, dispatch))
        assert result.returncode == (1 if dispatch and not model else 0), values[-1]
        identity = jobs(root)[0]['identity_json']
        expected = {
            'instruction_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
            'package': f'mir-agent-hub {version}', 'tool_schema': 'codex-mcp:tools/codex',
            'model_alias': model if model is not None else (
                'codex-config-default' if dispatch else 'policy-or-config-default'),
            'ceiling': 'none-v1-usage-alerting-only',
        }
        assert identity == json.dumps(expected, sort_keys=True)
        assert identity.isascii()
    assert values[0] == values[1], values


@pytest.mark.parametrize('hook', ['validate_brief', 'job_identity'])
def test_hub_duplicate_owner_rejected_before_import(binary, tmp_path, hook):
    root = tmp_path / 'native'
    launcher, environment, args = seed(root, False)
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        '(Path(__file__).resolve().parents[2] / "unexpected-import").touch()\n'
        f'def {hook}(*args): pass\n')
    result = P1['invoke'](binary, root, environment, args)
    assert result.returncode == 1
    assert hook.encode() in result.stderr
    assert b'native local policy configuration error' in result.stderr
    for path in ('unexpected-import', 'provider-methods', 'tasks/jobs.db'):
        assert not (root / path).exists()


@pytest.mark.parametrize('declared', [False, True], ids=['undeclared', 'version_absent'])
@pytest.mark.parametrize('dispatch', [True, False], ids=['dispatch', 'background'])
def test_hub_identity_retains_python_without_explicit_version(binary, tmp_path, declared, dispatch):
    root = tmp_path / 'python-owned'
    launcher, environment, args = seed(root, False, dispatch=dispatch, version=None, bound=False,
                                       identity=declared)
    (root / 'tools/mir_executor/local.py').write_text(
        'def job_identity(args, root, prompt, model):\n'
        '    return "python-owned-version-evidence"\n')
    result = P1['invoke'](binary, root, environment, args)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert jobs(root)[0]['identity_json'] == 'python-owned-version-evidence'


def test_hub_background_does_not_run_brief_bound(binary, tmp_path):
    values = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, args = seed(root, bridge, dispatch=False, limit=4.0)
        result = P1['invoke'](binary, root, environment, args)
        values.append(snapshot(root, launcher, result, False))
        assert result.returncode == 0, values[-1]
        assert (root / 'provider-started').exists()
    assert values[0] == values[1], values


@pytest.mark.parametrize('refused', [False, True], ids=['accepted', 'bound_refused'])
def test_hub_resume_revalidates_bound_and_preserves_identity(binary, tmp_path, refused):
    values = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, _ = seed(root, bridge, limit=4 if refused else 4096)
        args = DISPATCH['resume'](root, 'current')
        result = P1['invoke'](binary, root, environment, args)
        values.append(snapshot(root, launcher, result, True))
        assert result.returncode == (1 if refused else 0), values[-1]
        assert jobs(root)[0]['identity_json'] is None
        assert (root / 'provider-methods').exists() != refused
        if refused:
            assert b'delegated input exceeds 4 bytes (15)' in result.stderr
    assert values[0] == values[1], values
