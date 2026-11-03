"""Native command hooks preserve Python bridge bytes, registry rows and lease order."""
from __future__ import annotations

import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PARITY = runpy.run_path(str(ROOT / 'tests/test_executor_target_policy_native_parity.py'))
SUPPORT = PARITY['SUPPORT']
DISPATCH = PARITY['PARITY']['DISPATCH']
binary = PARITY['binary']

COMMON = r'''import json
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def pre_execute(args, root):
    (ROOT / 'remaining-hook-ran').touch()
def after_provider_call(result, metadata):
    assert (ROOT / 'lease').read_bytes() == b'held'
    (ROOT / 'after-provider-inside-lease').touch()
def after_run(worktree, attempt, result):
    assert (ROOT / 'lease').read_bytes() == b'held'
    (ROOT / 'after-run-inside-lease').touch()
'''
ORACLE = r'''
from contextlib import contextmanager
def record(hook, params):
    with (ROOT / 'wire.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'hook': hook, 'params': params}, default=str) + '\n')
def refuse(name):
    if os.environ.get('MIR_HOOK_FIXTURE_FAIL') == name:
        raise RuntimeError('offline hook refusal')
@contextmanager
def writer_scope(root):
    record('writer_enter', {})
    refuse('writer_enter')
    assert not (ROOT / 'lease').exists()
    (ROOT / 'lease').write_bytes(b'held')
    try:
        yield
    finally:
        record('writer_exit', {})
        (ROOT / 'lease').unlink()
        refuse('writer_exit')
def on_job_event(event, payload):
    assert (ROOT / 'lease').read_bytes() == b'held'
    record('on_job_event', {'event': event, 'payload': {
        key: value for key, value in payload.items() if key != 'args'}})
    refuse(event)
'''


@pytest.fixture(scope='module')
def hook_fixture(binary):
    command = ['cargo', 'build', '--release', '--locked', '--example', 'hook_fixture']
    if os.environ.get('MIR_HANDOFF_CARGO_OFFLINE') == '1':
        command.append('--offline')
    subprocess.run(command, cwd=ROOT / 'native/handoff-packet', check=True)
    return binary.parent / 'examples' / ('hook_fixture.exe' if os.name == 'nt'
                                         else 'hook_fixture')


def configure(root, fixture, bridge, native_hooks=('writer_scope', 'on_job_event')):
    local = root / 'tools/mir_executor/local.py'
    shared, _, writer_event = ORACLE.partition('@contextmanager')
    writer, _, event = writer_event.partition('def on_job_event')
    source = COMMON + shared
    if bridge or 'writer_scope' not in native_hooks:
        source += '@contextmanager' + writer
    if bridge or 'on_job_event' not in native_hooks:
        source += 'def on_job_event' + event
    local.write_text(source, encoding='utf-8')
    if bridge:
        return
    executable = root / fixture.name
    shutil.copy2(fixture, executable)
    path = root / 'config/mir-executor.local.json'
    path.parent.mkdir(exist_ok=True)
    config = json.loads(path.read_text()) if path.exists() else {}
    config['native_policy'] = {'version': 1, 'hooks': {
        'executable': executable.name, 'argv': ['command', str(root / 'hook-started')],
        'sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'hooks': list(native_hooks)}}
    path.write_text(json.dumps(config), encoding='utf-8')


def seed(root, flow, failure):
    if flow == 'execute':
        launcher = SUPPORT['seed'](root, 'success')
        environment = SUPPORT['environment'](root, 'success', launcher)
        arguments = SUPPORT['argv']('background_success')
    else:
        launcher, environment, arguments = DISPATCH['seed'](root, 'current', SUPPORT)
        if flow == 'resume':
            arguments = DISPATCH['resume'](root, 'current')
    environment.update(MIR_HOOK_FIXTURE_LOG=str(root / 'wire.jsonl'),
                       MIR_HOOK_FIXTURE_LEASE=str(root / 'lease'),
                       MIR_HOOK_FIXTURE_FAIL=failure)
    # The real provider checks the lease before processing its first request.
    server = root / 'server.py'
    source = server.read_text(encoding='utf-8')
    source = source.replace("root = Path(os.environ['EXECUTE_FIXTURE_ROOT'])",
                            "root = Path(os.environ['EXECUTE_FIXTURE_ROOT'])\n"
                            "assert (root / 'lease').read_bytes() == b'held'\n"
                            "(root / 'provider-inside-lease').touch()")
    server.write_text(source, encoding='utf-8')
    if launcher.suffix != '.cmd':
        launcher.write_text('#!/usr/bin/env python3\n' + source, encoding='utf-8')
    return launcher, environment, arguments


def normalize_bytes(value, root, launcher):
    value = PARITY['stream_bytes'](value, root, launcher)
    # Dispatch has generated worktree paths, commit IDs, job IDs and UTC stamps.
    value = value.replace(root.as_posix().encode(), b'<root>')
    value = re.sub(rb'mir-wt-[^/\\\s"\']+', b'mir-wt-<temp>', value)
    value = re.sub(rb'\b[0-9a-f]{32}\b', b'<id>', value)
    value = re.sub(rb'\b[0-9a-f]{40}\b', b'<commit>', value)
    return re.sub(rb'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)',
                  b'<timestamp>', value)


def requests(root):
    path = root / 'wire.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def event_projection(root, launcher, wire):
    events = []
    for request in wire:
        hook, params = request['hook'], request['params']
        event = {'hook': hook}
        if hook == 'on_job_event':
            event.update(event=params['event'], payload={
                key: value for key, value in params['payload'].items() if key != 'args'})
        events.append(json.loads(normalize_bytes(
            json.dumps(event, sort_keys=True).encode(), root, launcher)))
    return events


def assert_native_context(root, wire, failure, code):
    invocation_ids = set()
    for request in wire:
        params = request['params']
        assert params['repo_root'] == str(root)
        assert params['cwd'] == str(root)
        assert isinstance(params['invocation_id'], str) and params['invocation_id']
        invocation_ids.add(params['invocation_id'])
        if request['hook'] in ('writer_enter', 'writer_exit'):
            assert params['job_id'] is None
            assert params['attempt_id'] is None
        else:
            assert params['job_id'] == params['payload']['job_id']
            assert params['attempt_id'] == params['payload'].get('dispatch_id')
        if request['hook'] == 'writer_exit':
            assert params['token'] == 'opaque'
            assert params['outcome'] == ('clean' if code == 0 or failure == 'writer_exit'
                                          else 'unclean')
    assert len(invocation_ids) == 1


CASES = [(flow, failure) for flow in ('execute', 'dispatch', 'resume')
         for failure in ('', 'writer_enter', 'writer_exit',
                         'job_resumed' if flow == 'resume' else 'job_inserted')]
CASES += [('dispatch', 'dispatch_state'), ('resume', 'dispatch_state')]


@pytest.mark.parametrize(('flow', 'failure'), CASES)
def test_command_hooks_match_python_bridge(binary, hook_fixture, tmp_path, flow, failure,
                                          native_hooks=('writer_scope', 'on_job_event')):
    snapshots = []
    for bridge in (True, False):
        root = tmp_path / ('bridge' if bridge else 'native')
        launcher, environment, arguments = seed(root, flow, failure)
        configure(root, hook_fixture, bridge, native_hooks)
        environment['MIR_HOOK_FIXTURE_HOOKS'] = json.dumps(list(native_hooks))
        result = PARITY['invoke'](binary, root, environment, arguments)
        snapshot = (SUPPORT['snapshot'](root, launcher, result) if flow == 'execute'
                    else DISPATCH['snapshot'](root, result))
        if flow != 'execute':
            snapshot.pop('git_status')  # Config/fixture sources intentionally differ.
        snapshot.update(stdout_bytes=normalize_bytes(result.stdout, root, launcher),
                        stderr_bytes=normalize_bytes(result.stderr, root, launcher))
        wire = requests(root)
        snapshot['wire'] = event_projection(root, launcher, wire)
        snapshots.append(snapshot)
        expected_failure = failure and failure != 'dispatch_state'
        assert result.returncode == (1 if expected_failure else 0), (flow, failure, snapshot)
        assert not (root / 'lease').exists()
        assert (root / 'remaining-hook-ran').exists() == (failure != 'writer_enter')
        hooks = [request['hook'] for request in wire]
        assert hooks[0] == 'writer_enter'
        assert hooks.count('writer_enter') == 1
        assert hooks.count('writer_exit') == (0 if failure == 'writer_enter' else 1)
        if failure != 'writer_enter':
            assert hooks[-1] == 'writer_exit'
        admitted = failure not in ('writer_enter', 'job_inserted', 'job_resumed')
        assert (root / 'provider-inside-lease').exists() == admitted
        if admitted:
            marker = ('after-provider-inside-lease' if flow == 'execute'
                      else 'after-run-inside-lease')
            assert (root / marker).exists()
        if flow != 'execute' and admitted:
            assert any(request['params'].get('event') == 'dispatch_state' for request in wire)
        events = [request['params']['event'] for request in wire
                  if request['hook'] == 'on_job_event']
        if failure != 'writer_enter':
            assert events[0] == ('job_resumed' if flow == 'resume' else 'job_inserted')
        jobs = snapshot['jobs'] if flow == 'execute' else json.loads(snapshot['jobs'])
        if jobs:
            assert jobs[0]['status'] == ('completed' if admitted else 'failed')
            if flow == 'resume':
                assert jobs[0]['resume_count'] == (1 if admitted else 0)
        if failure in ('job_inserted', 'job_resumed'):
            assert jobs
        if failure == 'dispatch_state':
            assert (b'on_job_event dispatch_state: RuntimeError: offline hook refusal'
                    in result.stderr)
            assert 'on_job_event dispatch_state: RuntimeError: offline hook refusal' in (
                jobs[0]['stderr'])
        if not bridge:
            assert_native_context(root, [r for r in wire if 'invocation_id' in r['params']],
                                  failure, result.returncode)
    assert snapshots[0] == snapshots[1], (flow, failure, snapshots)


def test_digest_mismatch_never_starts_hook_child_or_provider(binary, hook_fixture, tmp_path):
    root = tmp_path / 'bad-pin'
    launcher, environment, arguments = seed(root, 'execute', '')
    configure(root, hook_fixture, False)
    config = root / 'config/mir-executor.local.json'
    value = json.loads(config.read_text())
    value['native_policy']['hooks']['sha256'] = '0' * 64
    config.write_text(json.dumps(value), encoding='utf-8')
    result = PARITY['invoke'](binary, root, environment, arguments)
    assert result.returncode == 1
    assert result.stdout == b''
    assert result.stderr == b'[mir_executor] native hook executable SHA-256 mismatch\n'
    for name in ('hook-started', 'wire.jsonl', 'lease', 'provider-methods', 'tasks/jobs.db'):
        assert not (root / name).exists(), (name, result.stderr)


def test_native_hooks_execute_without_a_python_bridge(binary, hook_fixture, tmp_path):
    root = tmp_path / 'native-only'
    launcher, environment, arguments = seed(root, 'execute', '')
    configure(root, hook_fixture, False)
    (root / 'tools/mir_executor/local.py').unlink()
    # The provider remains a real Python process; only bridge startup is forbidden.
    environment['MIR_EXECUTOR_PYTHON'] = str(root / 'absent-bridge-interpreter')
    result = subprocess.run([str(binary), '--home-root', str(root), *arguments],
                            cwd=root, env=environment, capture_output=True, timeout=45,
                            check=False)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert (root / 'provider-inside-lease').exists()
    assert not (root / 'lease').exists()
    assert [request['hook'] for request in requests(root)] == [
        'writer_enter', 'on_job_event', 'writer_exit']


@pytest.mark.parametrize('native_hooks', [('writer_scope',), ('on_job_event',)])
def test_selective_native_ownership_keeps_other_hook_in_bridge(
        binary, hook_fixture, tmp_path, native_hooks):
    test_command_hooks_match_python_bridge(binary, hook_fixture, tmp_path, 'dispatch', '',
                                          native_hooks)


@pytest.mark.parametrize('name', ['writer_scope', 'on_job_event'])
@pytest.mark.parametrize('computed', [False, True])
@pytest.mark.parametrize('duplicate', [False, True])
def test_cross_root_selected_native_hook_owns_only_its_target(
        binary, hook_fixture, tmp_path, name, computed, duplicate):
    home, target = tmp_path / 'home', tmp_path / 'target'
    SUPPORT['seed'](home, 'success')
    launcher = SUPPORT['seed'](target, 'success')
    PARITY['configure'](home, {'family': {
        'mode': 'alias_map', 'aliases': {'sample': str(target)},
        'unknown': PARITY['UNKNOWN']}}, False)
    configure(target, hook_fixture, False, (name,))
    local = target / 'tools/mir_executor/local.py'
    # Initial P1 still owns pre_execute across roots. Keep the other bridge
    # callbacks, including the unselected lifecycle hook, on the target.
    source = local.read_text(encoding='utf-8').replace(
        "def pre_execute(args, root):\n    (ROOT / 'remaining-hook-ran').touch()\n", '')
    if duplicate:
        export = 'conflicting_export' if computed else name
        source += (f'\ndef {export}(*args):\n'
                   '    (ROOT / "duplicate-effect").touch()\n'
                   '    raise RuntimeError("duplicate owner ran")\n')
        if computed:
            left, right = name.rsplit('_', 1)
            source += f"globals()[{left!r} + '_{right}'] = conflicting_export\n"
            assert name not in source  # Only the real bridge hello reveals it.
    elif computed:
        other = 'on_job_event' if name == 'writer_scope' else 'writer_scope'
        source = source.replace(f'def {other}(', 'def retained_export(')
        source = source.replace("'on_job_event'", "'on_job' + '_event'")
        left, right = other.rsplit('_', 1)
        source += f"globals()[{left!r} + '_{right}'] = retained_export\n"
        assert other not in source
    local.write_text(source, encoding='utf-8')
    # A Python hook in the initial repository must not compete with the selected
    # target's native owner, including a computed initial export.
    initial_export = 'unused_export' if computed else name
    initial = ('from pathlib import Path\n'
               f'def {initial_export}(*args):\n'
               '    (Path(__file__).resolve().parents[2] / "initial-effect").touch()\n'
               '    raise RuntimeError("initial owner ran")\n')
    if computed:
        left, right = name.rsplit('_', 1)
        initial += f"globals()[{left!r} + '_{right}'] = unused_export\n"
    (home / 'tools/mir_executor/local.py').write_text(initial, encoding='utf-8')
    environment = SUPPORT['environment'](target, 'success', launcher)
    environment.update(EXECUTE_FIXTURE_ROOT=str(home),
                       MIR_HOOK_FIXTURE_HOOKS=json.dumps([name]),
                       MIR_HOOK_FIXTURE_LOG=str(target / 'wire.jsonl'),
                       MIR_HOOK_FIXTURE_LEASE=str(target / 'lease'))
    result = PARITY['invoke'](binary, home, environment,
                             SUPPORT['argv']('background_success') + ['--family', 'sample'])
    assert not (home / 'initial-effect').exists()
    assert not (home / 'tasks/jobs.db').exists()
    assert not (target / 'duplicate-effect').exists()
    if duplicate:
        assert result.returncode == 1, (result.stdout, result.stderr)
        assert name.encode() + b' is also present in local.py' in result.stderr
        for path in ('hook-started', 'lease', 'wire.jsonl', 'tasks/jobs.db'):
            assert not (target / path).exists(), (path, result.stderr)
        assert not (home / 'provider-started').exists()
    else:
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert (home / 'provider-started').exists()
        assert (target / 'tasks/jobs.db').exists()
        assert not (target / 'lease').exists()
        assert (target / 'after-provider-inside-lease').exists()
        wire = requests(target)
        assert [r['hook'] for r in wire] == ['writer_enter', 'on_job_event', 'writer_exit']
        for request in wire:
            if 'repo_root' in request['params']:
                assert request['params']['repo_root'] == str(target)
                assert request['params']['cwd'] == str(home)


@pytest.mark.parametrize('failure', ['writer_enter', 'job_inserted'])
def test_pinned_entrypoint_keeps_hook_failure_final(binary, hook_fixture, tmp_path, failure):
    root = tmp_path / 'pinned'
    launcher, environment, arguments = seed(root, 'execute', failure)
    configure(root, hook_fixture, False)
    destination = root / '.mir/bin' / binary.name
    destination.parent.mkdir(parents=True)
    shutil.copy2(binary, destination)
    (destination.parent / 'executor-query.json').write_text(json.dumps({
        'path': '.mir/bin/' + binary.name,
        'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}), encoding='utf-8')
    local = root / 'tools/mir_executor/local.py'
    with local.open('a', encoding='utf-8') as stream:
        stream.write("\nassert Path(os.environ['MIR_EXECUTOR_OWNED_RECEIPT']).read_bytes() "
                     "== b'owned'\n(ROOT / 'receipt-observed').touch()\n")
    (root / 'tools/mir_executor/cli.py').write_text(
        "raise RuntimeError('unexpected Python fallback after hook effect')\n", encoding='utf-8')
    environment.pop('MIR_EXECUTOR_EXECUTE_IMPL', None)
    result = PARITY['PARITY']['invoke_pinned'](root, environment, arguments, capture_output=True)
    assert result.returncode == 1
    context = b'RuntimeError' if failure == 'writer_enter' else b'background insert failed'
    # Admission refusal writes its bytes directly; post-insert diagnostics use
    # the executor's platform text writer. Compare each exact wire spelling.
    newline = b'\n' if failure == 'writer_enter' else os.linesep.encode()
    assert result.stderr == b'[mir_executor] ' + context + b': offline hook refusal' + newline
    assert (root / 'receipt-observed').exists()
    assert not (root / 'provider-methods').exists()
    assert not (root / 'lease').exists()
    assert [r['hook'] for r in requests(root)] == (
        ['writer_enter'] if failure == 'writer_enter' else
        ['writer_enter', 'on_job_event', 'writer_exit'])
