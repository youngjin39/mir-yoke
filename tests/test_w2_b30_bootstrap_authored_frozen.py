"""B30 authored bootstrap oracle captured from unmodified Python, never from a port."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from mir.cli import bootstrap as M

FIXTURE = (Path(__file__).parents[1] /
           'native/handoff-packet/tests/fixtures/w2/b30-bootstrap-authored.json')
CASES = {}
ONBOARDING = dict(schema_version=1, profile='content_workspace', archives=[
    dict(path='notes', kind='directory')], scan={})
PROVIDER = 'https://example.invalid/provider.git'


def compact(value):
    text = json.dumps(value, sort_keys=True)
    return value if len(text) <= 512 else dict(len=len(text), sha256=hashlib.sha256(
        text.encode()).hexdigest())


def observe(case, tmp):
    try:
        with mock.patch.object(Path, 'home', return_value=tmp), \
                mock.patch.object(M.subprocess, 'run', side_effect=AssertionError('unexpected')):
            return {'value': compact(json.loads(json.dumps(case(tmp))))}
    except Exception as exc:  # noqa: BLE001 - freeze reference errors
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}


def put(tmp, name, body):
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def fake(tmp, call, replies):
    calls = []
    def run(argv, **kw):
        calls.append([argv, str(kw.get('cwd')).replace(str(tmp), '<tmp>'),
                      kw.get('stdin'), kw.get('input')])
        code, output = replies[len(calls) - 1]
        return SimpleNamespace(returncode=code, stdout=output, stderr='')
    with mock.patch.object(M.subprocess, 'run', side_effect=run):
        value = call()
    return [value, calls]


def profile(tmp, mode):
    body = M._repo_profile_text(tmp, 'sample', 'code_app', 'Build tools', ['Rust'])
    changes = {'invalid': '[', 'no_repo': '', 'repo_type': 'repo=1',
               'execution_type': 'execution=1\n' + body.split('[execution]')[0],
               'gates_type': 'gates=1\n' + body.split('[gates]')[0]}
    replacements = {'identity': ('Build tools', 'TODO'), 'stack': ('["Rust"]', '"Rust"'),
                    'mismatch': ('non_code_profile = "code_app"', 'non_code_profile = "other"'),
                    'memory': ('requires_memory_store = true', 'requires_memory_store = false'),
                    'capabilities': ('requires_global_capabilities = true',
                                     'requires_global_capabilities = false')}
    if mode in replacements:
        body = body.replace(*replacements[mode])
    path = tmp / 'profile.toml'
    if mode != 'missing':
        put(tmp, 'profile.toml', changes.get(mode, body))
    try:
        return json.loads(json.dumps(M._validate_existing_profile(path, 'code_app')).replace(
            str(tmp), '<tmp>'))
    except ValueError as exc:
        raise ValueError(str(exc).replace(str(tmp), '<tmp>')) from exc


def authored(tmp, mode):
    content = mode.startswith('content')
    if mode.startswith(('dir_file:', 'dir_link:')):
        kind, name = mode.split(':')
        if kind == 'dir_file':
            put(tmp, name, 'blocked')
        else:
            (tmp / 'target').mkdir()
            (tmp / name).symlink_to(tmp / 'target')
    if mode == 'kept':
        for name in ['harness_a.toml', '.mir/repo-profile.toml', 'tasks/tdd.json', 'tasks/plan.md']:
            put(tmp, name, 'authored')
    if mode == 'content_kept':
        put(tmp, 'docs/project-purpose.md', 'authored purpose')
        put(tmp, 'config/content-onboarding.json', json.dumps({**ONBOARDING, 'extra': True}))
    if mode == 'content_invalid':
        put(tmp, 'config/content-onboarding.json', '{}')
    if mode == 'replace':
        put(tmp, 'CLAUDE.md', 'Provider contract')
        digest = hashlib.sha256(b'Provider contract').hexdigest()
        put(tmp, 'config/adopter-payload.json',
            json.dumps(dict(files=[dict(path='CLAUDE.md', sha256=digest)])))
    result = fake(tmp, lambda: M._ensure_authored_files(tmp, 'sample',
        'content_workspace' if content else 'code_app', 'Build tools', ['Rust'],
        ONBOARDING if content else None, 'Purpose\n' if content else None,
        replace_provider_profile=mode == 'replace'),
        [(0, 'a' * 40)] if mode != 'bad_commit' else [(0, 'invalid')])
    files = {p.relative_to(tmp).as_posix(): compact(p.read_text().replace(str(tmp), '<tmp>'))
             for p in sorted(tmp.rglob('*')) if p.is_file()}
    return [result, files]


def payload(tmp, body):
    if body is not None:
        put(tmp, 'config/adopter-payload.json', body)
    return M._release_payload_digests(tmp)


def safe(tmp, mode):
    path = tmp / 'file'
    if mode in ('file', 'link', 'nested', 'escape'):
        put(tmp, 'file', 'body')
    if mode == 'directory':
        path.mkdir()
    if mode in ('link', 'escape'):
        (tmp / 'link').symlink_to(path if mode == 'link' else tmp.parent)
        path = tmp / 'link'
    if mode == 'nested':
        (tmp / 'link').symlink_to(tmp)
        path = tmp / 'link/file'
    return M._is_safe_existing_project_file(tmp, path)


def release(tmp, mode):
    boundary = dict(schema_version=1, provider_markers=['provider'],
                    provider_text_markers=[dict(path='CLAUDE.md', contains='Provider')])
    put(tmp, 'provider', 'marker')
    put(tmp, 'CLAUDE.md', 'Provider contract')
    controls = ['config/adopter-boundary.json', 'config/adopter-payload.json']
    put(tmp, controls[0], json.dumps(boundary))
    put(tmp, controls[1], json.dumps(dict(files=[dict(path='CLAUDE.md', sha256=
        hashlib.sha256(b'Provider contract').hexdigest())])))
    replies = [(0, 'a' * 40)] + [(0, (tmp / p).read_bytes()) for p in controls]
    if mode in ('git_error', 'bad_commit'):
        replies[0] = (1, '') if mode == 'git_error' else (0, 'invalid')
    if mode == 'show_error':
        replies[1] = (1, b'')
    if mode == 'show_error_same':
        replies[1] = (1, replies[1][1])
    if mode == 'control_changed':
        replies[2] = (0, b'different')
    if mode in ('contract_changed', 'rewrite_changed'):
        put(tmp, 'CLAUDE.md', 'Authored')
    if mode == 'no_marker':
        (tmp / 'provider').unlink()
    if mode == 'no_text':
        boundary['provider_text_markers'] = []
        put(tmp, controls[0], json.dumps(boundary))
        replies[1] = (0, (tmp / controls[0]).read_bytes())
    if mode == 'invalid_boundary':
        put(tmp, controls[0], '{}')
    if mode.startswith('rewrite'):
        value = M._rewrite_release_matched(tmp, {'CLAUDE.md': 'Product', 'missing': 'new'})
        return [value, (tmp / 'CLAUDE.md').read_text()]
    return fake(tmp, lambda: M._is_raw_provider_checkout(tmp), replies)


def ownership(tmp, mode):
    body = {'source': {'url': PROVIDER}}
    if mode != 'missing':
        put(tmp, 'config/capability-sources.json', '{' if mode == 'invalid' else json.dumps(
            {} if mode == 'no_source' else body))
    replies = [(0, '')]
    if mode == 'git_error':
        replies = [(1, '')]
    if mode in ('foreign', 'provider', 'push_error', 'mixed'):
        replies = [(0, ' origin \n'), (1, '') if mode == 'push_error' else
                   (0, 'git@example.invalid:provider.git\n' if mode == 'provider' else
                    'https://example.invalid/product.git\n')]
    if mode == 'mixed':
        replies = [(0, 'z\na\n'), (0, PROVIDER + '\nDISABLED\n'), (0, 'DISABLED\n')]
    if mode == 'git_error_output':
        replies = [(1, ' origin \n'), (0, 'https://example.invalid/product.git\n')]
    return fake(tmp, lambda: M._source_control_ownership(tmp), replies)


for p in M._PROFILE_CHOICES:
    CASES['memory.' + p] = lambda tmp, p=p: M._memory_config_text('sample', p, ONBOARDING)
    CASES['contract.' + p] = lambda tmp, p=p: M._product_contract_text('sample', p, 'Build tools')
    for i, stack in enumerate([[], ['Rust'], ['Rust', 'SQL', '\u00e9']]):
        CASES[f'profile_text.{p}.{i}'] = lambda tmp, p=p, s=stack: M._repo_profile_text(
            tmp, 'sample-project', p, 'Build "tools"\n\u00e9', s, base_commit='b' * 40).replace(
                str(tmp), '<tmp>')
CASES['memory.no_onboarding'] = lambda tmp: M._memory_config_text(
    'sample', 'content_workspace', None)
for prefix, function, modes in [
    ('validate', profile, ['valid', 'missing', 'invalid', 'no_repo', 'repo_type', 'identity',
                         'stack', 'mismatch', 'execution_type', 'gates_type',
                         'memory', 'capabilities']),
    ('authored', authored, ['fresh', 'kept', 'bad_commit', 'content',
                           'content_kept', 'content_invalid', 'replace'] +
     [f'{kind}:{name}' for kind in ['dir_file', 'dir_link']
      for name in ['.mir', 'docs', 'tasks', '.ai-harness']]),
    ('safe', safe, ['file', 'missing', 'directory', 'link', 'nested', 'escape']),
    ('release', release, ['valid', 'git_error', 'bad_commit', 'show_error', 'control_changed',
                         'contract_changed', 'no_marker', 'no_text', 'invalid_boundary',
                         'rewrite', 'rewrite_changed', 'show_error_same']),
    ('ownership', ownership, ['missing', 'invalid', 'no_source', 'none', 'git_error', 'foreign',
                             'provider', 'push_error', 'mixed', 'git_error_output'])]:
    for mode in modes:
        CASES[f'{prefix}.{mode}'] = lambda tmp, f=function, m=mode: f(tmp, m)
for i, body in enumerate([None, '{', '[]', '{}', '{"files":[null,1,{}, {"path":"a",'
                         '"sha256":2},{"path":"a","sha256":"last"}]}']):
    CASES[f'payload.{i}'] = lambda tmp, b=body: payload(tmp, b)
CASES['urls'] = lambda tmp: [M._normalise_git_url(v) for v in [PROVIDER, 'SSH://u@EXAMPLE.invalid:22/a.git',
    'git@example.invalid:a.git/', 'https://EXAMPLE.invalid:443/a.git', 'ssh://host:123/a.git',
    'https://host:bad/a.git', 'https://[invalid', '', ' nonsense ', 'C:\\repo.git',
    'https://user:pass@host/A.git/?q=x']]
CASES['urls_edge'] = lambda tmp: [M._normalise_git_url(v) for v in ['a/b@host:x/y', 'dir/sub:x',
    ' \x1chost:a.git\x1f', 'https://ho\tst/a.git', 'https://host:+1/a.git', 'ssh://a/b@host/c.git']]
RECORDS = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
