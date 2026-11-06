"""B08 oracle captured from the unmodified reference, never from the Rust port."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from mir.cli.context import _profile_context_lines, _profile_search_scopes
from mir.core.context import profile_task_context as p

FIXTURE = Path(__file__).parent / '../native/handoff-packet/tests/fixtures/w2/b08-task-context.json'
PROFILE = '''[repo]
slug = "sample"
repository_type = "library"
purpose = "  small   project  "
technology_stack = ["Rust", "Python", ""]
[paths]
architecture_refs = ["design.md", "design.md", "../escape", "/invalid"]
configuration_paths = ["config.toml"]
verification_paths = ["tests"]
workflow_refs = ["workflow.md"]
exception_refs = ["risk.md"]
code_paths = ["src", "bad/../path"]
non_code_paths = ["docs"]
protected_paths = ["src/private"]
generated_paths = ["src/generated"]
[preserve]
agent_memory_paths = ["keep"]
extra_docs = ["docs/keep.md"]
empty = []
false = false
[boundaries]
live_runtime = ["runtime"]
secrets = ["secret"]
external = "none"
[gates]
z = true
a = true
numeric = 1
no = false
'''


def _git(tmp, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME='Fixture', GIT_COMMITTER_NAME='Fixture',
               GIT_AUTHOR_EMAIL='fixture@example.invalid',
               GIT_COMMITTER_EMAIL='fixture@example.invalid',
               GIT_AUTHOR_DATE='2000-01-01T00:00:00+0000',
               GIT_COMMITTER_DATE='2000-01-01T00:00:00+0000', LC_ALL='C')
    return subprocess.run(['git', *args], cwd=tmp, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def _setup(tmp, body):
    (tmp / '.mir').mkdir()
    (tmp / '.mir/repo-profile.toml').write_text(body, encoding='utf-8')
    for name in ('design.md', 'config.toml', 'workflow.md', 'risk.md', 'src/a.py'):
        path = tmp / name
        path.parent.mkdir(exist_ok=True)
        path.write_text('reference\n', encoding='ascii')
    for name in ('tests', 'docs'):
        (tmp / name).mkdir()


def _profile(body=PROFILE, query='', targets=(), risk='normal'):
    def run(tmp):
        if body is not None:
            _setup(tmp, body)
        context = p.build_profile_task_context(tmp, query=query, target_paths=targets, risk=risk)
        return [context, _profile_context_lines(context), _profile_search_scopes(context)]
    return run


def _snapshot(mode):
    def run(tmp):
        _setup(tmp, '')
        _git(tmp, 'init', '-b', 'fixture')
        if mode == 'unborn':
            return p._freshness(tmp, '', ['src'])
        _git(tmp, 'add', '.')
        _git(tmp, 'commit', '-m', 'baseline')
        base = _git(tmp, 'rev-parse', 'HEAD')
        if mode in ('advanced', 'selected_commit'):
            (tmp / ('src/a.py' if mode == 'selected_commit' else 'other')).write_text('next')
            _git(tmp, 'add', '.')
            _git(tmp, 'commit', '-m', 'advance')
        if mode == 'dirty':
            (tmp / 'src/a.py').write_text('unstaged')
            (tmp / 'src/staged').write_text('staged')
            _git(tmp, 'add', 'src/staged')
            for i in range(55):
                (tmp / f'src/untracked-{i:02}').write_text('new')
        if mode == 'diverged':
            base = _git(tmp, 'commit-tree', _git(tmp, 'write-tree'), '-m', 'unrelated')
        baseline = {'invalid': 'BAD', 'missing': '0' * 40}.get(mode, base)
        profile = f'[repo]\nprofile_base_commit = "{baseline}"\n[paths]\ncode_paths = ["src"]\n'
        (tmp / '.mir/repo-profile.toml').write_text(profile)
        context = p.build_profile_task_context(tmp, query='code',
                                              target_paths=() if mode == 'container' else ('src',))
        return [p._git_output(tmp, ['branch', '--show-current']),
                p._git_output(tmp, ['status', '--porcelain']),
                p._git_paths(tmp, ['ls-files', '-z']), p._changed_paths(tmp, baseline),
                p._freshness(tmp, baseline, ['src', 'src']), context,
                _profile_context_lines(context), _profile_search_scopes(context)]
    return run


def _unsafe(tmp):
    _setup(tmp, '[paths]\narchitecture_refs=["escape"]')
    (tmp / 'escape').symlink_to(tmp.parent, target_is_directory=True)
    context = p.build_profile_task_context(tmp, query='docs')
    return [context, _profile_context_lines(context), _profile_search_scopes(context)]


def _states(tmp):
    tmp = tmp / 'root'
    tmp.mkdir()
    _setup(tmp, '')
    (tmp / 'escape').symlink_to(tmp.parent, target_is_directory=True)
    return {path: p._reference_state(tmp, path) for path in
            ('design.md', 'docs', 'missing', '*.md', 'nothing*', 'escape', 'escape/*', '../')}


CASES = {
    'profile.absent': _profile(None), 'profile.empty': _profile(''),
    'profile.malformed': _profile('[repo'), 'profile.unknown': _profile('[unknown]\nx = 1'),
    'profile.wrong_sections': _profile('repo=1\npaths=[]\npreserve="x"\nboundaries=0\ngates=false'),
    'profile.default': _profile(), 'profile.high': _profile(risk='high'),
    'profile.low': _profile(risk='low'), 'profile.bad_risk': _profile(risk='critical'),
    'profile.targets': _profile(targets=('src/private/a', 'src/generated/a', 'keep',
                                       'docs/keep.md', 'runtime', 'secret', '../bad', '/bad')),
    'profile.long': _profile(PROFILE.replace('small   project', 'x' * 4000)),
    'profile.many_refs': _profile('[paths]\narchitecture_refs=[' + ','.join(
        json.dumps(f'file-{i:02}') for i in range(60)) + ']'),
    'helpers.strings': lambda tmp: [p._string_list(v) for v in
                                   (None, 'x', [], [' x ', '', ' ', 2, False, 'a'])],
    'helpers.normalise': lambda tmp: [p._normalise_repo_path(v) for v in
                                     ('', ' ', '././a\\b', '../x', '/a', 'a/../b', '.', 'a//b')],
    'helpers.matches': lambda tmp: [[a, b, p._path_matches(a, b)] for a, b in
                                   [('src', 'src/a'), ('src/a', 'src'), ('a', 'ab'),
                                    ('src/*.py', 'src/x.txt'), ('x?.py', 'xa.py'),
                                    ('x[ab]', 'xc'), ('../x', 'x'), ('a', '/a')]],
    'helpers.query': lambda tmp: sorted(p._query_terms('CODE a x_y test-42 \u00c9cole')),
    'helpers.query_ref': lambda tmp: [p._query_matches_ref(set(t), k, v) for t, k, v in
                                     [(['ab'], 'code', 'ab'), (['fig'], 'configuration', 'x'),
                                      ([], 'code', 'src'), (['src'], 'code', 'SRC/a')]],
    'helpers.states': _states, 'profile.unsafe': _unsafe,
    'helpers.git_outside': lambda tmp: [p._git_output(tmp, ['rev-parse', 'HEAD']),
                                       p._git_paths(tmp, ['ls-files', '-z']),
                                       p._changed_paths(tmp, 'bad'), p._freshness(tmp, '', [])],
    'helpers.invalid': lambda tmp: p._empty_invalid_context('q', 'high', 'warning'),
    'header.scopes': lambda tmp: _profile_search_scopes({'task': {'target_paths': ['a', 'a']},
        'selected_refs': [None, {}, {'path': 1}, {'path': ''},
                          {'path': 'src', 'kind': 'code_scope'},
                          {'path': 'doc', 'kind': 'non_code_scope'},
                          {'path': 'a'}, {'path': 'b'}]}),
}
for _section in ('repo', 'paths', 'preserve', 'boundaries', 'gates'):
    _parts = PROFILE.split('[' + _section + ']')
    CASES[f'profile.without_{_section}'] = _profile(
        _parts[0] + ('[' + _parts[1].split('[', 1)[1] if '[' in _parts[1] else ''))
for _query in ('code', 'docs', 'config', 'test', 'workflow', 'risk', 'design', 'unmatched'):
    CASES[f'query.{_query}'] = _profile(query=_query)
for _target in ('src/a.py', 'docs/a.md', 'config.toml', 'tests/a',
                'workflow.md', 'risk.md', 'other'):
    CASES[f'target.{_target}'] = _profile(targets=(_target, _target))
for _mode in ('unborn', 'current', 'advanced', 'selected_commit', 'dirty', 'invalid',
              'missing', 'diverged', 'container'):
    CASES[f'snapshot.{_mode}'] = _snapshot(_mode)


def observe(case, tmp: Path) -> dict:
    try:
        return json.loads(json.dumps({'value': case(tmp)}).replace(str(tmp), '<tmp>'))
    except Exception as exc:  # noqa: BLE001 - freeze reference exceptions
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}


RECORDS = json.loads(FIXTURE.read_text(encoding='ascii')) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
