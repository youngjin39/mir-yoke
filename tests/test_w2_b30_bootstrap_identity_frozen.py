"""B30 bootstrap oracle captured from unmodified Python, never from a port."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from mir.cli import bootstrap as M

FIXTURE = (Path(__file__).parents[1] /
           'native/handoff-packet/tests/fixtures/w2/b30-bootstrap-identity.json')
CASES = {}

def observe(case, tmp):
    calls = []
    def run(argv, **kwargs):
        calls.append([argv, str(kwargs.get('cwd')), kwargs.get('input')])
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    try:
        with mock.patch.object(M.subprocess, 'run', side_effect=run), \
                mock.patch.object(Path, 'home', return_value=tmp):
            value = json.loads(json.dumps(case(tmp), default=str).replace(str(tmp), '<tmp>'))
        assert not calls, calls
        text = json.dumps(value, sort_keys=True)
        return {'value': value if len(text) <= 512 else
                {'len': len(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()}}
    except Exception as exc:  # noqa: BLE001 - freeze reference errors
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}

def parse(tmp, args):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(Path, 'cwd', return_value=tmp), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            return vars(M._parse(args))
        except SystemExit as exc:
            return [exc.code, out.getvalue(), err.getvalue()]

def storage(tmp, mode):
    root, disk = tmp / 'project', tmp / 'storage'
    env = {k: str(disk / v) for k, v in M._EXTERNAL_STORAGE_PATHS.items()}
    env.update(MIR_BOOTSTRAP_RUNTIME_ID='runtime', UV_PROJECT_ENVIRONMENT=str(root / '.venv'),
               UV_TOOL_DIR=str(disk / 'mir/cli/runtime/tools'),
               UV_TOOL_BIN_DIR=str(disk / 'mir/cli/runtime/bin'))
    if mode == 'unset':
        env = {}
    if mode in ('wrong', 'missing_runtime'):
        env.update({k: str(tmp / 'wrong') for k in env} if mode == 'wrong' else
                   {'MIR_BOOTSTRAP_RUNTIME_ID': ''})
    def stat(path, **kwargs):
        if mode == 'stat_error':
            raise OSError('scripted stat failure')
        return SimpleNamespace(st_dev=2 if (mode == 'different' and path != root or
            mode == 'payload_device' and path == disk / 'uv/cache') else 1)
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.dict(M.os.environ, env, clear=True))
        stack.enter_context(mock.patch.object(Path, 'resolve', lambda p, **kw: p))
        stack.enter_context(mock.patch.object(Path, 'expanduser', lambda p: p))
        stack.enter_context(mock.patch.object(Path, 'is_dir', lambda p:
            mode != 'not_directory' and (mode != 'missing_dirs' or p == disk)))
        stack.enter_context(mock.patch.object(M.os, 'access', return_value=mode != 'unwritable'))
        stack.enter_context(mock.patch.object(M.os, 'stat', side_effect=stat))
        return M._storage_preflight(root, None if mode == 'default' else disk)

def content(tmp, action, value=None):
    root = tmp / 'project'
    root.mkdir()
    files = {'notes/a.md': 'searchable alpha', 'notes/b.PDF': 'binary', 'notes/c.exe': 'ignored',
             'other.txt': 'another record', 'docs/skip.md': 'hidden', '.hidden/a.md': 'hidden',
             'README.md': 'hidden', 'empty/x.bin': 'ignored'}
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    if action == 'relative':
        return M._project_relative(root, str(root / 'notes') if value == 'absolute' else value)
    if action in ('discover', 'supported', 'scan'):
        if value in ('symlink', 'nested_symlink', 'escape_link'):
            (root / ('notes/link' if value == 'nested_symlink' else 'link')).symlink_to(
                tmp if value == 'escape_link' else root / 'notes', target_is_directory=True)
        leaf = 'notes' if value == 'nested_symlink' else value or 'notes'
        path = root / ('link' if value in ('symlink', 'escape_link') else leaf)
        return (M._scan_content_candidates(root) if action == 'scan' else
                getattr(M, '_' + ('discoverable' if action == 'discover' else 'supported') +
                        '_content_files')(root, path))
    if action == 'archives':
        if value == ['n=../escape']:
            (tmp / 'escape').mkdir()
            (tmp / 'escape/a.md').write_text('searchable')
        if value == ['n=link']:
            (root / 'link').symlink_to(root / 'notes', target_is_directory=True)
        if value == ['n=short.txt']:
            (root / 'short.txt').write_text('tiny')
        if value == ['bad=invalid.txt']:
            (root / 'invalid.txt').write_bytes(b'\xff')
        return M._parse_content_archives(root, value)
    return M._build_content_onboarding(root, 'Curate records', ['text'], value)

def load(tmp, value):
    path = tmp / 'manifest.json'
    if value != 'missing':
        path.write_bytes(value if isinstance(value, bytes) else value.encode())
    return M._load_content_onboarding(path)

for name, args in [('help', ['--help']), ('missing_profile', []), ('defaults', ['--profile', 'x']),
        ('unknown', ['--profile', 'x', '--unknown']),
        ('full', ['--profile', 'content_workspace', '--project-root', 'project', '--slug', 'slug',
                  '--purpose', 'Curate', '--stack', 'a,b', '--stack', 'c', '--archive', 'a=notes',
                  '--storage-root', 'storage', '--json', '--finalize', '--architecture-initialized',
                  '--skip-capability-activation', '--allow-incomplete'])] + [
        ('missing_' + opt[2:], ['--profile', 'x', opt]) for opt in
        ['--project-root', '--slug', '--profile', '--purpose', '--stack', '--archive',
         '--storage-root']] + [('value_' + opt, ['--profile', 'x', '--' + opt + '=x']) for opt in
        ['json', 'finalize', 'architecture-initialized', 'skip-capability-activation',
         'allow-incomplete']]:
    CASES['parse.' + name] = lambda tmp, a=args: parse(tmp, a)
for mode in ['default', 'valid', 'not_directory', 'unwritable', 'unset', 'wrong',
             'missing_runtime', 'missing_dirs', 'different', 'payload_device', 'stat_error']:
    CASES['storage.' + mode] = lambda tmp, m=mode: storage(tmp, m)
for i, value in enumerate([' Mixed SLUG! ', '', '___', 'a' * 64, 'a' * 65, '\u00e9',
                           'a__b-c', 'PROJECT']):
    CASES[f'slug.{i}'] = lambda tmp, v=value: M._normalise_slug(v)
for i, values in enumerate([[], [' a,b ', 'b,,C', 'a'], ['TODO', 'todo'], [' , ']]):
    CASES[f'stack.{i}'] = lambda tmp, v=values: M._normalise_stack(v)
for i, pair in enumerate([(None, []), (' ', ['text']), ('a\nb', ['text']), ('a\rb', ['text']),
        ('TODO mission', ['text']), ('Curate records', []), ('Curate records', ['unknown', 'TODO']),
        ('Curate records', ['text']), ('Curate records', [''])]):
    CASES[f'identity.{i}'] = lambda tmp, p=pair: M._validate_project_identity(*p)
for action, values in {
    'relative': ['notes/../other.txt', '.', '', '../escape', 'absolute'],
    'discover': ['notes', 'other.txt', 'missing', 'symlink', 'nested_symlink', 'escape_link'],
    'supported': ['notes', 'other.txt', 'notes/b.PDF', 'missing'],
    'scan': [None, 'symlink'],
    'archives': [[], [' Notes = notes '], ['one=other.txt'], ['bad'], ['!=notes'],
                 ['n=notes', 'n=other.txt'], ['n=missing'], ['n=empty'], ['n=notes/b.PDF'],
                 ['n=notes', 'm=notes/a.md'], ['n=notes/a.md', 'm=notes'],
                 ['n=other.txt', 'm=other.txt'], ['n=../escape'], ['n=.'],
                 ['bad=invalid.txt'], ['n=notes/c.exe'], ['n=short.txt'], ['n=link']],
    'build': [[], ['n=notes'], ['n=notes/a.md', 'm=other.txt']],
}.items():
    for i, value in enumerate(values):
        CASES[f'{action}.{i}'] = lambda tmp, a=action, v=value: content(tmp, a, v)
for i, body in enumerate(['small alpha searchable', 'TODO placeholder unknown', '123456',
                          '\u00e9\u00e9\u00e9\u00e9\u00e9\u00e9', 'tiny']):
    CASES[f'query.{i}'] = lambda tmp, b=body: M._acceptance_query(b, 'notes')
CASES['definition.text'] = lambda tmp: M._project_definition_text('Curate records', ['a', 'b'])
MANIFEST = dict(schema_version=1, profile='content_workspace', archives=[{}], scan={})
for i, value in enumerate(['missing', '{', '[]', '{}', b'\xff'] + [json.dumps(v) for v in
        [MANIFEST, {**MANIFEST, 'schema_version': 2}, {**MANIFEST, 'profile': 'code_app'},
         {**MANIFEST, 'archives': []}, {**MANIFEST, 'archives': {}},
         {**MANIFEST, 'scan': []}, {**MANIFEST, 'scan': {'unclassified': ['notes']}}]]):
    CASES[f'load.{i}'] = lambda tmp, v=value: load(tmp, v)
for i, archives in enumerate([[], [None, {}, {'path': 'notes', 'kind': 'directory'},
        {'path': 'one.md', 'kind': 'file'}, {'path': 'one.md', 'kind': 'file'}]]):
    CASES[f'globs.{i}'] = lambda tmp, a=archives: M._content_archive_globs({'archives': a})
for i, archives in enumerate([[], [None, {'classification': 'project-definition'},
        {'classification': 'notes', 'path': 'notes'}], [{}]]):
    CASES[f'args.{i}'] = lambda tmp, a=archives: M._content_archive_args({'archives': a})

RECORDS = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}

def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)

@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
