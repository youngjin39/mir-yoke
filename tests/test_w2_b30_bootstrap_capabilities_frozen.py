"""B30 bootstrap capability oracle captured only from unmodified Python."""
import contextlib
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from mir.cli import bootstrap as M
from mir.cli import capability
from mir.core.capabilities import native

FIXTURE = (Path(__file__).parents[1] /
           'native/handoff-packet/tests/fixtures/w2/b30-bootstrap-capabilities.json')
CASES = {}


def compact(value):
    body = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
    return {'len': len(body), 'sha256': hashlib.sha256(body).hexdigest()} if len(body) > 512 else (
        body.decode('ascii') if isinstance(value, bytes) else value)


def put(tmp, name, value):
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding='ascii')


def observe(case, tmp):
    calls = []
    def run(argv, **kwargs):
        calls.append([argv, kwargs.get('cwd'), kwargs.get('stdin')])
        return SimpleNamespace(returncode=1 if (tmp / 'fail').exists() else 0,
                               stdout=(tmp / 'stdout').read_text() if (tmp / 'stdout').exists()
                               else '', stderr='denied' if (tmp / 'stderr').exists() else '')
    with mock.patch.object(M.subprocess, 'run', side_effect=run):
        try:
            result = {'value': case(tmp)}
        except Exception as exc:  # noqa: BLE001 - freeze reference errors
            result = {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}
    result['files'] = {p.relative_to(tmp).as_posix(): compact(p.read_bytes())
                       for p in sorted(tmp.rglob('*')) if p.is_file()}
    result['calls'] = calls
    result = json.loads(json.dumps(result, default=str).replace(str(tmp), '<tmp>'))
    if 'value' in result:
        result['value'] = compact(result['value'])
    return result


def release(tmp, paths):
    put(tmp, 'config/adopter-payload.json', {'files': [
        {'path': p, 'sha256': hashlib.sha256((tmp / p).read_bytes()).hexdigest()} for p in paths]})


def source():
    return dict(source={'url': 'https://example.invalid/provider', 'ref': 'v1'},
                profiles={'aliases': {'hybrid_pipeline': 'code_app'}, 'packs': {
                    p: {'agents': ['agents/main.md', 'agents/worker.md'], 'plugins': ['tools']}
                    for p in M._PROFILE_CHOICES}}, plugins={'tools': {'skills': ['design']}})


def catalog(tmp, profile, mode):
    data = dict(catalog={'agents': {'main': {'role': 'control_plane',
                'recommended_skills': ['design', 'unused']}, 'worker': {'role': 'execution'}},
                'skills': {'design': {'status': 'local'}, 'unused': {}}},
                templates={v: {'default_skill_pack': {'core': ['design', 'unused']},
                               'tracked_paths': {'harness_structure': ['plugins/local', 'docs/']}}
                           for v in M._CATALOG_TEMPLATE_BY_PROFILE.values()},
                repositories_dir='repos', repositories=['provider'])
    if mode == 'inventory':
        data['catalog'] = None
    if mode in ('agents', 'skills'):
        data['catalog'][mode] = {}
    if mode == 'roles':
        data['catalog']['agents']['worker']['role'] = 'control_plane'
    if mode == 'template':
        data['templates'] = {}
    caps = source()
    if mode == 'pack':
        caps['profiles']['packs']['code_app'] = None
    put(tmp, 'config/capability-sources.json', caps)
    put(tmp, 'config/repo-agent-management.json', '[' if mode == 'invalid' else
        [] if mode == 'object' else data)
    release(tmp, ['config/repo-agent-management.json'])
    if mode == 'authored':
        put(tmp, 'config/repo-agent-management.json', {'authored': True})
    if mode == 'absent':
        (tmp / 'config/repo-agent-management.json').unlink()
    if mode == 'unmatched':
        put(tmp, 'config/adopter-payload.json', {})
    if mode == 'agent_file':
        put(tmp, 'agents/main.md', 'Authored agent body\n')
    return M._compile_adopter_agent_catalog(tmp, profile)


def reset(tmp, mode, task=False):
    paths = (['tasks/' + p for p in ['change_log.md', 'checklist.md',
             'handoffs/session-handoff-LATEST.md', 'intent.json', 'plan.md', 'tdd.json']]
             if task else ['CLAUDE.md', '.ai-harness/bluebricks.md', '.mir/boundary.md'])
    for path in paths:
        put(tmp, path, 'provider\n')
    release(tmp, paths)
    if mode in ('authored', 'authored_generator'):
        for path in paths:
            put(tmp, path, 'authored\n')
    if mode == 'absent':
        for path in paths:
            (tmp / path).unlink()
    if mode in ('success', 'failure', 'stdout', 'unknown', 'authored_generator'):
        put(tmp, 'scripts/generate_codex_derivatives.sh', 'fake generator')
    if mode in ('failure', 'stdout', 'unknown', 'authored_generator'):
        put(tmp, 'fail', '')
    if mode == 'failure':
        put(tmp, 'stderr', '')
    if mode == 'stdout':
        put(tmp, 'stdout', 'stdout failure\n')
    return (M._reset_provider_task_state(tmp, 'Build product') if task else
            M._reset_provider_contract_state(tmp, 'product', 'code_app', 'Build product'))


def load(tmp, mode):
    data = source()
    changes = {'empty': {}, 'object': [], 'source': {'source': []},
               'url': {'source': {'ref': 'v1'}}, 'ref': {'source': {'url': 'u'}},
               'profiles': {'profiles': {}}, 'profiles_type': {'profiles': []},
               'packs': {'profiles': {'packs': []}}, 'missing_pack': {'profiles': {'packs': {}}}}
    data = changes[mode] if mode in ('empty', 'object') else {**data, **changes.get(mode, {})}
    if mode != 'missing':
        put(tmp, 'config/capability-sources.json', '{' if mode == 'invalid' else data)
    return M._load_capability_sources(tmp, 'code_app')


def lock(tmp, mode):
    data = dict(schema_version=1, source={'commit': 'a' * 40}, plugins={'z': {}, 'a': {}},
                agents={'worker': {}, 'main': {}}, profile='code_app',
                registration={'status': 'active'})
    if mode == 'inactive':
        data['registration'] = {'status': 'pending'}
    if mode == 'registration':
        data['registration'] = []
    if mode in ('commit', 'uppercase', 'plugins', 'source'):
        data[mode if mode in ('plugins', 'source') else 'source'] = (
            {} if mode in ('plugins', 'source') else {'commit': 'A' * 40 if mode == 'uppercase'
                                                     else 'short'})
    if mode == 'long_commit':
        data['source'] = {'commit': 'a' * 41}
    if mode == 'agents_list':
        data['agents'] = ['worker', 'main']
    if mode.startswith('native'):
        data['native_artifacts'] = {} if mode == 'native_valid' else []
        if mode == 'native_config':
            put(tmp, 'config/capability-sources.json', {})
    if mode != 'missing':
        put(tmp, '.mir/capability-lock.json', '{' if mode == 'invalid' else
            [] if mode == 'object' else data)


def capability_case(tmp, operation, mode):
    calls = []
    lock(tmp, mode)
    def main(argv):
        calls.append(argv)
        if mode == 'output':
            print('sync refused')
        return 7 if mode in ('output', 'silent') else 0
    receipt = None if mode == 'no_receipt' else {'status': 'ready' if mode == 'prior_ready'
                                               else 'restart_required'}
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(capability, 'main', side_effect=main))
        if mode == 'import':
            stack.enter_context(mock.patch.dict(sys.modules, {'mir.cli.capability': None}))
            stack.enter_context(mock.patch.object(M, '__package__', 'missing_package'))
        if mode == 'native_error':
            stack.enter_context(mock.patch.object(native, 'validate_artifacts',
                                                  side_effect=ValueError('artifact refused')))
        value = (M._activate_capabilities(tmp, 'code_app') if operation == 'activate' else
                 M._finalize_capabilities(tmp, receipt) if operation == 'finalize' else
                 M._capability_lock_evidence(tmp))
    return [value, calls]


for profile in M._PROFILE_CHOICES:
    for mode in ['matched', 'agent_file', 'authored', 'absent']:
        CASES[f'catalog.{profile}.{mode}'] = lambda tmp, p=profile, m=mode: catalog(tmp, p, m)
for mode in ['invalid', 'object', 'inventory', 'agents', 'skills', 'roles', 'template',
             'unmatched', 'pack']:
    CASES[f'catalog.{mode}'] = lambda tmp, m=mode: catalog(tmp, 'code_app', m)
for mode in ['authored', 'absent', 'no_generator', 'success', 'failure', 'stdout', 'unknown',
             'authored_generator']:
    CASES[f'contract.{mode}'] = lambda tmp, m=mode: reset(tmp, m)
for mode in ['matched', 'authored', 'absent']:
    CASES[f'tasks.{mode}'] = lambda tmp, m=mode: reset(tmp, m, True)
for mode in ['valid', 'missing', 'invalid', 'empty', 'object', 'source', 'url', 'ref',
             'profiles', 'profiles_type', 'packs', 'missing_pack']:
    CASES[f'load.{mode}'] = lambda tmp, m=mode: load(tmp, m)
for operation, modes in [('lock', ['valid', 'missing', 'invalid', 'object', 'commit', 'uppercase',
                                  'plugins', 'source', 'native', 'native_valid', 'native_config',
                                  'native_error']),
                         ('activate', ['valid', 'missing', 'output', 'silent', 'import']),
                         ('finalize', ['valid', 'inactive', 'registration', 'commit', 'missing',
                                       'output', 'silent', 'import', 'no_receipt', 'prior_ready'])]:
    for mode in modes:
        CASES[f'{operation}.{mode}'] = lambda tmp, o=operation, m=mode: capability_case(tmp, o, m)
for mode in ('long_commit', 'agents_list'):
    CASES[f'lock.{mode}'] = lambda tmp, m=mode: capability_case(tmp, 'lock', m)
RECORDS = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
