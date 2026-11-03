"""Exercise finite target admission against synthetic Python local-hook oracles.

All repositories, registry rows and hook effects are disposable fixture data.
The oracle executes through the retained native Python bridge; declarative cases
execute the same native CLI with no local.py. Cross-root alias redirection has a
separate gate because the historical native bridge refuses post-hook redirects.
"""
from __future__ import annotations

import json
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PARITY = runpy.run_path(str(ROOT / 'tests/test_executor_execute_native_parity.py'))
SUPPORT = PARITY['SUPPORT']
binary = PARITY['binary']
trace_details = PARITY['trace_details']

# Finite equivalents of Hermes/Janus/SMD/Wolha/Harness admission, without
# consumer names, application packages, or a live family registry.
ORACLE = r'''import json
import pathlib
import subprocess
import sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / 'oracle-policy.json').read_text(encoding='utf-8'))
def fail(failure, values):
    message = failure['message'].format(**values)
    if failure.get('stderr'):
        print(failure['stderr'].format(**values), file=sys.stderr, end='')
    kind = failure['kind']
    if kind == 'SystemExit':
        raise SystemExit(int(message))
    raise {'ValueError': ValueError, 'ImportError': ImportError,
           'ModuleNotFoundError': ModuleNotFoundError}[kind](message)
def git_root(root):
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                            capture_output=True, text=True, check=False)
    return pathlib.Path(result.stdout.strip()).resolve() if result.returncode == 0 else None
def evaluate(args, target, authorization=False):
    family = getattr(args, 'family', None)
    requested = pathlib.Path(target).resolve()
    cwd = pathlib.Path.cwd().resolve()
    values = dict(family=family, family_repr=repr(family), cwd=str(cwd),
                  config_root=str(ROOT), requested_root=str(requested))
    policy = POLICY
    rule = policy.get('family')
    if family is not None and rule:
        if rule['mode'] == 'reject':
            fail(rule['failure'], values)
        normalized = family
        if rule.get('normalization') == 'lower_underscores':
            normalized = normalized.lower().replace('_', '-')
        elif rule.get('normalization') == 'strip_lower':
            normalized = normalized.strip().lower()
        aliases = rule['aliases']
        values.update(normalized_repr=repr(normalized), known=', '.join(sorted(aliases)))
        if 'unavailable' in rule:
            fail(rule['unavailable'], values)
        if normalized not in aliases:
            key_error = rule.get('unknown_key_error', '{normalized_repr}').format(**values)
            values['key_error'] = str(KeyError(key_error))
            fail(rule['unknown'], values)
        family_root = pathlib.Path(aliases[normalized])
        if not family_root.is_absolute():
            family_root = ROOT / family_root
        family_root = family_root.resolve()
        values['family_root'] = str(family_root)
        if rule['mode'] == 'require_current':
            if family_root != requested:
                fail(rule['root_conflict'], values)
        else:
            if 'root_conflict' in rule and requested not in (cwd, family_root):
                fail(rule['root_conflict'], values)
            if not authorization:
                args.repo_root = family_root
    if 'repository_local' in policy:
        target_root = git_root(requested)
        if target_root is not None and (git_root(cwd) != target_root or requested != target_root):
            fail(policy['repository_local'], values)
def pre_execute(args, repo_root):
    evaluate(args, args.repo_root)
'''

REJECT = {'kind': 'ValueError', 'message': 'Family {family_repr} is unavailable.'}
SYSTEM_EXIT = {'kind': 'SystemExit', 'message': '1',
               'stderr': '[mir_executor] Unknown family slug: {family_repr}. No registry.\n'}
UNKNOWN = {'kind': 'ValueError', 'message': 'Unknown family {family_repr}; known: {known}.'}
CONFLICT = {'kind': 'ValueError',
            'message': '--family {family_repr} resolves to {family_root}, not {requested_root}'}
LOCAL = {'kind': 'ValueError', 'message': 'Run from the target repository Git root.'}
CASES = ('no_family', 'reject', 'reject_exit', 'alias', 'alias_normalized', 'alias_unknown',
         'resolver_unavailable', 'resolver_import_error', 'alias_root_conflict',
         'require_current', 'require_current_conflict', 'repository_local',
         'repository_subdirectory', 'repository_other', 'alias_strip', 'alias_key_error')


def policy_for(case):
    if case in ('no_family', 'reject', 'reject_exit'):
        return {'family': {'mode': 'reject',
                           'failure': SYSTEM_EXIT if case == 'reject_exit' else REJECT}}
    if case.startswith('repository_'):
        return {'repository_local': LOCAL}
    rule = {'mode': 'require_current' if case.startswith('require_current') else 'alias_map',
            'aliases': {'sample': '.'}, 'unknown': UNKNOWN, 'root_conflict': CONFLICT}
    if case == 'alias_normalized':
        rule.update(aliases={'sample-project': '.'}, normalization='lower_underscores')
    if case == 'alias_strip':
        rule['normalization'] = 'strip_lower'
    if case == 'alias_key_error':
        rule.update(unknown={'kind': 'ValueError', 'message': 'Unknown: {key_error}'},
                    unknown_key_error='Unknown family slug: {family_repr}. Known slugs: {known}')
    if case in ('resolver_unavailable', 'resolver_import_error'):
        rule.update(aliases={}, unavailable=(
            {'kind': 'ImportError', 'message': 'Synthetic resolver is unavailable.'}
            if case == 'resolver_import_error' else
            {'kind': 'SystemExit', 'message': '1',
             'stderr': '[mir_executor] family mode unavailable: reference-only resolver\n'}))
    if case == 'require_current_conflict':
        rule['aliases'] = {'sample': 'other'}
    return {'family': rule}


def configure(root, policy, bridge):
    path = root / 'config/mir-executor.local.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({} if bridge else {
        'native_policy': {'version': 1, 'target_admission': policy}}), encoding='utf-8')
    local = root / 'tools/mir_executor/local.py'
    if bridge:
        (root / 'oracle-policy.json').write_text(json.dumps(policy), encoding='utf-8')
        local.write_text(ORACLE + (
            '\ndef authorize_target(home_root, target_root, args):\n'
            '    evaluate(args, target_root, authorization=True)\n'
            if policy.get('authorize_target') else ''), encoding='utf-8')
    else:
        local.unlink(missing_ok=True)


def invoke(binary, root, environment, arguments, *, cwd=None):
    environment = environment.copy()
    environment['MIR_EXECUTOR_PYTHON'] = sys.executable
    return subprocess.run([str(binary), '--home-root', str(root), *arguments],
                          cwd=cwd or root, env=environment, capture_output=True,
                          timeout=45, check=False)


def stream_bytes(value, root, launcher):
    # Mask only fixture identity and nondeterministic runtime values. Preserve
    # every other byte, including CRLF and trailing whitespace.
    for path, token in ((launcher, b'<codex>'), (root, b'<root>')):
        value = value.replace(repr(str(path))[1:-1].encode(), token)
        value = value.replace(str(path).encode(), token)
    value = re.sub(rb'duration=\d+\.\d+s', b'duration=<duration>s', value)
    return re.sub(rb'(?<=\[BACKGROUND\] job_id=)[0-9a-f]{32}', b'<job-id>', value)


@pytest.mark.parametrize('case', CASES)
def test_target_admission_matches_python_bridge(binary, tmp_path, case):
    snapshots = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher = SUPPORT['seed'](root, 'success')
        policy = policy_for(case)
        configure(root, policy, bridge)
        arguments = SUPPORT['argv']('background_success')
        initial = root
        before = (root / 'tasks/tdd.json').read_bytes()
        if case not in ('no_family', 'repository_local', 'repository_subdirectory',
                        'repository_other'):
            family = {'alias_unknown': 'missing', 'alias_normalized': 'SAMPLE_PROJECT',
                      'alias_strip': ' SAMPLE ',
                      'alias_key_error': "missing'\ud55c\uae00"}.get(case, 'sample')
            arguments += ['--family', family]
        if case in ('alias_root_conflict', 'repository_other'):
            other = root / 'other'
            other.mkdir()
            subprocess.run(['git', 'init', '--quiet', str(other)], check=True, capture_output=True)
            arguments += ['--repo-root', str(other)]
            initial = other
            if case == 'alias_root_conflict':
                policy['family']['aliases'] = {'sample': str(root)}
            shutil.copytree(root / 'tools', other / 'tools', dirs_exist_ok=True)
            configure(other, policy, bridge)
        if case == 'repository_subdirectory':
            initial = root / 'subdir'
            initial.mkdir()
            arguments += ['--repo-root', str(initial)]
            shutil.copytree(root / 'tools', initial / 'tools')
            configure(initial, policy, bridge)
        result = invoke(binary, initial, SUPPORT['environment'](root, 'success', launcher),
                        arguments, cwd=root)
        snapshot = SUPPORT['snapshot'](root, launcher, result)
        snapshot['stdout_bytes'] = stream_bytes(result.stdout, root, launcher)
        snapshot['stderr_bytes'] = stream_bytes(result.stderr, root, launcher)
        snapshots.append(snapshot)
        admitted = case in ('no_family', 'alias', 'alias_normalized', 'require_current',
                            'repository_local', 'alias_strip')
        assert result.returncode == (0 if admitted else 1), (
            case, bridge, snapshot, trace_details())
        assert (root / 'provider-started').exists() == admitted
        assert bool(snapshot['jobs']) == admitted
        if not admitted:
            assert snapshot['stdout'] == ''
            assert (root / 'tasks/tdd.json').read_bytes() == before
    assert snapshots[0] == snapshots[1], (case, snapshots, trace_details())


def test_native_policy_rejects_covered_python_hooks_before_import(binary, tmp_path):
    root = tmp_path / 'conflicting-owner'
    launcher = SUPPORT['seed'](root, 'success')
    configure(root, policy_for('reject'), False)
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        '(Path(__file__).resolve().parents[2] / "unexpected-import").touch()\n'
        'def pre_execute(args, root):\n'
        '    raise RuntimeError("duplicate owner ran")\n', encoding='utf-8')
    result = invoke(binary, root, SUPPORT['environment'](root, 'success', launcher),
                    SUPPORT['argv']('success'))
    assert result.returncode == 1, (result.stderr, trace_details())
    assert b'pre_execute' in result.stderr
    for path in ('unexpected-import', 'provider-started', 'tasks/jobs.db'):
        assert not (root / path).exists(), (path, result.stderr)


def test_native_only_target_policy_never_starts_python_bridge(binary, tmp_path):
    root = tmp_path / 'no-bridge'
    launcher = SUPPORT['seed'](root, 'success')
    configure(root, policy_for('reject'), False)
    environment = SUPPORT['environment'](root, 'success', launcher)
    environment['MIR_EXECUTOR_PYTHON'] = str(root / 'absent-python-interpreter')
    result = subprocess.run([str(binary), '--home-root', str(root), *SUPPORT['argv']('success')],
                            cwd=root, env=environment, capture_output=True, timeout=45, check=False)
    assert result.returncode == 0, (result.stdout, result.stderr, trace_details())
    assert (root / 'provider-started').exists()


@pytest.mark.parametrize(('initial_hook', 'computed'), [
    (None, False), ('writer_scope', False), ('on_job_event', False),
    ('writer_scope', True), ('on_job_event', True),
])
def test_native_cross_root_alias_resolves_before_writer_and_job_creation(
        binary, tmp_path, initial_hook, computed):
    home = tmp_path / 'home'
    home_launcher = SUPPORT['seed'](home, 'success')
    target = tmp_path / 'target'
    launcher = SUPPORT['seed'](target, 'success')
    configure(home, {'family': {'mode': 'alias_map', 'aliases': {'sample': str(target)},
                               'unknown': UNKNOWN, 'root_conflict': CONFLICT}}, False)
    if initial_hook:
        path = home / 'config/mir-executor.local.json'
        config = json.loads(path.read_text())
        # The initial host must never start: hook ownership belongs to the
        # selected target, whose policy and bridge are validated independently.
        config['native_policy']['hooks'] = {
            'executable': 'unused-initial-host', 'argv': [], 'sha256': '0' * 64,
            'hooks': [initial_hook]}
        path.write_text(json.dumps(config), encoding='utf-8')
    configure(target, {}, False)
    (target / 'tools/mir_executor/local.py').write_text(
        'from contextlib import contextmanager\n'
        'from pathlib import Path\n'
        '@contextmanager\n'
        'def writer_scope(root):\n'
        '    assert not (root / "tasks/jobs.db").exists()\n'
        '    (root / "writer-root").write_text(str(root.resolve()), encoding="utf-8")\n'
        '    with (root / "writer-effects").open("a") as stream:\n'
        '        stream.write("enter\\n")\n'
        '    try:\n'
        '        yield\n'
        '    finally:\n'
        '        with (root / "writer-effects").open("a") as stream:\n'
        '            stream.write("exit\\n")\n', encoding='utf-8')
    local = target / 'tools/mir_executor/local.py'
    source = local.read_text(encoding='utf-8')
    if initial_hook == 'on_job_event':
        source += ('def on_job_event(event, payload):\n'
                   '    root = Path(__file__).resolve().parents[2]\n'
                   '    with (root / "event-effects").open("a") as stream:\n'
                   '        stream.write(event + "\\n")\n')
    if computed:
        source = source.replace('def writer_scope(', 'def lease(')
        source += "globals()['writer' + '_scope'] = lease\n"
        if initial_hook == 'on_job_event':
            source = source.replace('def on_job_event(', 'def observe(')
            source += "globals()['on_job' + '_event'] = observe\n"
    local.write_text(source, encoding='utf-8')
    environment = SUPPORT['environment'](target, 'success', launcher)
    # Like the Python executor, the provider thread keeps the invoking cwd
    # (the fixture server asserts thread cwd == EXECUTE_FIXTURE_ROOT).
    environment['EXECUTE_FIXTURE_ROOT'] = str(home)
    result = invoke(binary, home, environment,
                    SUPPORT['argv']('background_success') + ['--family', 'sample'])
    assert result.returncode == 0, (result.stdout, result.stderr, trace_details())
    assert not (home / 'tasks/jobs.db').exists()
    assert (home / 'provider-started').exists()
    assert (target / 'tasks/jobs.db').exists()
    assert not (target / 'provider-started').exists()
    assert (target / 'writer-root').read_text(encoding='utf-8') == str(target.resolve())
    assert (target / 'writer-effects').read_text().splitlines() == ['enter', 'exit']
    if initial_hook == 'on_job_event':
        assert (target / 'event-effects').read_text().splitlines() == ['job_inserted']
    assert SUPPORT['snapshot'](home, home_launcher, result)['jobs'] == []


@pytest.mark.parametrize('section', ['target_admission', 'verifier_aliases', 'agent_route'])
@pytest.mark.parametrize('computed', [False, True])
def test_cross_root_initial_declarative_coverage_still_rejects_target_python(
        binary, tmp_path, section, computed):
    home, target = tmp_path / 'home', tmp_path / 'target'
    SUPPORT['seed'](home, 'success')
    launcher = SUPPORT['seed'](target, 'success')
    configure(home, {'family': {'mode': 'alias_map', 'aliases': {'sample': str(target)},
                               'unknown': UNKNOWN}}, False)
    path = home / 'config/mir-executor.local.json'
    config = json.loads(path.read_text())
    if section == 'verifier_aliases':
        config['native_policy'][section] = {'configuration_root': 'initial'}
    elif section == 'agent_route':
        config['native_policy'][section] = {
            'source': 'codex', 'criteria': 'declared', 'backend': 'policy',
            'sandbox': 'read_only', 'invalid_lock': 'empty'}
    path.write_text(json.dumps(config), encoding='utf-8')
    # No selected native declaration: rejection must come from the initial
    # declarative policy, including computed exports discovered only in hello.
    (target / 'config').mkdir(exist_ok=True)
    (target / 'config/mir-executor.local.json').write_text('{}', encoding='utf-8')
    name = 'resolve_agent_route' if section == 'agent_route' else 'pre_execute'
    export = 'computed_export' if computed else name
    source = ('from pathlib import Path\n'
              f'def {export}(*args):\n'
              '    (Path(__file__).resolve().parents[2] / "declarative-effect").touch()\n')
    if computed:
        left, right = name.rsplit('_', 1)
        source += f"globals()[{left!r} + '_{right}'] = computed_export\n"
        assert name not in source
    (target / 'tools/mir_executor/local.py').write_text(source, encoding='utf-8')
    result = invoke(binary, home, SUPPORT['environment'](target, 'success', launcher),
                    SUPPORT['argv']('background_success') + ['--family', 'sample'])
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert name.encode() + b' is also present in local.py' in result.stderr
    for root in (home, target):
        for path in ('declarative-effect', 'tasks/jobs.db', 'provider-started'):
            assert not (root / path).exists(), (path, result.stderr)


@pytest.mark.parametrize('authorize_alias_target', [False, True])
def test_invoking_home_reauthorizes_alias_target(binary, tmp_path, authorize_alias_target):
    home = tmp_path / 'home'
    launcher = SUPPORT['seed'](home, 'success')
    target = tmp_path / 'target'
    SUPPORT['seed'](target, 'success')
    if authorize_alias_target:
        policy = {'family': {'mode': 'alias_map', 'aliases': {'sample': str(target)},
                             'unknown': UNKNOWN}, 'repository_local': LOCAL,
                  'authorize_target': True}
        arguments = SUPPORT['argv']('success') + ['--family', 'sample']
    else:
        policy = {'repository_local': LOCAL, 'authorize_target': True}
        arguments = SUPPORT['argv']('success') + ['--repo-root', str(target)]
    configure(home, policy, False)
    configure(target, {}, False)
    result = invoke(binary, home, SUPPORT['environment'](home, 'success', launcher), arguments)
    assert result.returncode == 1, (result.stdout, result.stderr, trace_details())
    prefix = 'argument parse error: ' if authorize_alias_target else ''
    assert result.stderr == (
        f'[mir_executor] {prefix}authorize_target refused {target}: ValueError: '
        'Run from the target repository Git root.\n').encode()
    for root in (home, target):
        for path in ('tasks/jobs.db', 'provider-started'):
            assert not (root / path).exists()


def test_legacy_malformed_config_preserves_pre_execute_effects(binary, tmp_path):
    root = tmp_path / 'legacy-config'
    launcher = SUPPORT['seed'](root, 'success')
    (root / 'config').mkdir(exist_ok=True)
    (root / 'config/mir-executor.local.json').write_text('{broken', encoding='utf-8')
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        'def pre_execute(args, root):\n'
        '    (Path(root) / "legacy-pre-execute").touch()\n', encoding='utf-8')
    result = invoke(binary, root, SUPPORT['environment'](root, 'success', launcher),
                    SUPPORT['argv']('success'))
    assert result.returncode == 1, (result.stdout, result.stderr, trace_details())
    assert (root / 'legacy-pre-execute').exists(), result.stderr
    assert not (root / 'provider-started').exists()
    assert not (root / 'tasks/jobs.db').exists()


def test_resume_applies_native_admission_like_bridge(binary, tmp_path):
    import sqlite3
    from contextlib import closing

    dispatch = PARITY['DISPATCH']
    snapshots = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, _ = dispatch['seed'](root, 'current', SUPPORT)
        arguments = dispatch['resume'](root, 'current')
        with closing(sqlite3.connect(root / 'tasks/jobs.db')) as connection, connection:
            connection.execute('UPDATE jobs SET family=?', ('sample',))
        configure(root, policy_for('reject'), bridge)
        result = invoke(binary, root, environment, arguments)
        snapshot = dispatch['snapshot'](root, result)
        snapshot['stdout_bytes'] = stream_bytes(result.stdout, root, launcher)
        snapshot['stderr_bytes'] = stream_bytes(result.stderr, root, launcher)
        # Source/config files intentionally differ; execution effects must match.
        snapshot.pop('git_status')
        snapshots.append(snapshot)
        assert result.returncode == 1, (result.stdout, result.stderr)
        assert b'Family' in result.stderr
        assert not (root / 'provider-methods').exists()
    assert snapshots[0] == snapshots[1], snapshots


@pytest.mark.parametrize('declaration', [
    {'version': 2, 'target_admission': {}},
    {'version': 1, 'target_admission': {}, 'unknown': True},
])
def test_invalid_policy_fails_closed_without_python(binary, tmp_path, declaration):
    root = tmp_path / 'invalid-policy'
    launcher = SUPPORT['seed'](root, 'success')
    configure(root, {}, False)
    (root / 'config/mir-executor.local.json').write_text(
        json.dumps({'native_policy': declaration}), encoding='utf-8')
    environment = SUPPORT['environment'](root, 'success', launcher)
    environment['MIR_EXECUTOR_PYTHON'] = str(root / 'missing-interpreter')
    result = subprocess.run([str(binary), '--home-root', str(root),
                             *SUPPORT['argv']('success')], cwd=root, env=environment,
                            capture_output=True, timeout=45, check=False)
    assert result.returncode == 1
    assert b'native local policy configuration error' in result.stderr
    assert not (root / 'provider-started').exists()
    assert not (root / 'tasks/jobs.db').exists()
