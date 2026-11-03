"""Python callers retain the pinned native host's lease and wire contracts."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time

import pytest

from tools.mir_executor import local_hooks
from tools.mir_executor.native_hooks import NativeHookError

PROTOCOL = 'mir-executor.hooks@1'

# A real persistent executable makes acquisition, process cleanup and exact bytes
# observable without a provider or the Rust binary being installed.
HOST = r'''
import json, os, pathlib, subprocess, sys, time
root = pathlib.Path.cwd()
mode = sys.argv[1]
(root / 'host.pid').write_text(str(os.getpid()))
def send(value):
    print(json.dumps(value, ensure_ascii=False, separators=(',', ':')), flush=True)
hooks = ['writer_scope', 'on_job_event']
if mode == 'hello-hang':
    time.sleep(60)
if mode == 'missing-hook':
    hooks.pop()
send({'version': 'wrong' if mode == 'bad-hello' else 'mir-executor.hooks@1', 'hooks': hooks})
if mode == 'blocked-stdin':
    time.sleep(60)
for raw in sys.stdin.buffer:
    with (root / 'requests.jsonl').open('ab') as log:
        log.write(raw)
    request = json.loads(raw)
    hook = request['hook']
    params = request['params']
    if mode == 'tree-hang':
        subprocess.Popen([sys.executable, '-c',
            "import pathlib,time; p=pathlib.Path('heartbeat'); "
            "\nwhile True:\n p.open('ab').write(b'x'); time.sleep(.02)"])
        time.sleep(60)
    if mode == 'hang':
        time.sleep(60)
    if mode == 'crash':
        sys.exit(7)
    if mode == 'partial':
        sys.stdout.write('{')
        sys.stdout.flush()
        time.sleep(60)
    if mode == 'oversized':
        print('x' * 1048576, flush=True)
        continue
    if mode == 'depth':
        print('[' * 70 + 'null' + ']' * 70, flush=True)
        continue
    reply = {'version': 'mir-executor.hooks@1', 'id': request['id'], 'ok': True,
             'result': {'params': params}}
    if hook == 'writer_enter':
        (root / 'lease').write_text('held')
        reply['result'] = {'token': '' if mode == 'empty-token' else 'opaque-token'}
    if hook == 'writer_exit':
        assert params['token'] == 'opaque-token'
        (root / 'lease').unlink()
        reply['result'] = None
    if mode == 'refuse' and hook == 'writer_enter':
        reply.update(ok=False, error={'type': 'LeaseBusy', 'message': 'writer refused'})
    if mode == 'event-refuse' and hook == 'on_job_event':
        reply.update(ok=False, error={'type': 'EventStoreError', 'message': 'event refused'})
    if mode == 'wrong-id':
        reply['id'] += 1
    if mode == 'bad-version':
        reply['version'] = 'wrong'
    if mode == 'bad-error':
        reply.update(ok=False, error={'message': 'missing type'})
    if mode == 'missing-result':
        reply.pop('result')
    send(reply)
'''


@pytest.fixture
def host(tmp_path, monkeypatch):
    if os.name == 'nt':
        pytest.skip('fixture host uses a POSIX executable shebang')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PATH', os.path.dirname(sys.executable) + os.pathsep + os.environ['PATH'])
    def build(mode='echo'):
        executable = tmp_path / 'hook-host'
        executable.write_text('#!/usr/bin/env python3\n' + HOST, encoding='utf-8')
        executable.chmod(0o755)
        config = {'executable': executable.name, 'argv': [mode],
                  'sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
                  'hooks': ['writer_scope', 'on_job_event']}
        directory = tmp_path / 'config'
        directory.mkdir(exist_ok=True)
        (directory / 'mir-executor.local.json').write_text(json.dumps({
            'native_policy': {'version': 1, 'hooks': config}}), encoding='utf-8')
        return tmp_path, config
    return build


def requests(root):
    path = root / 'requests.jsonl'
    return [json.loads(line) for line in path.read_bytes().splitlines()] if path.exists() else []


def session(root, config, **kwargs):
    from tools.mir_executor.native_hooks import HookSession
    return HookSession(root, config, **kwargs)


def assert_reaped(root):
    pid = root / 'host.pid'
    if pid.exists():
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid.read_text()), 0)


def test_native_writer_holds_one_lease_across_nested_work(host):
    root, _ = host()
    with local_hooks.writer_scope(root):
        assert (root / 'lease').exists()
        with local_hooks.writer_scope(root):
            assert [r['hook'] for r in requests(root)] == ['writer_enter']
        assert (root / 'lease').exists()
    frames = requests(root)
    assert [r['hook'] for r in frames] == ['writer_enter', 'writer_exit']
    assert frames[-1]['params']['outcome'] == 'clean'
    assert frames[0]['params']['invocation_id'] == frames[1]['params']['invocation_id']
    assert not (root / 'lease').exists()
    assert_reaped(root)


@pytest.mark.parametrize('error,outcome', [(ValueError('work failed'), 'unclean'),
                                         (asyncio.CancelledError(), 'uncertain')])
def test_native_writer_teardown_records_work_outcome(host, error, outcome):
    root, _ = host()
    with pytest.raises(type(error)):
        with local_hooks.writer_scope(root):
            raise error
    assert requests(root)[-1]['params']['outcome'] == outcome
    assert not (root / 'lease').exists()
    assert_reaped(root)


@pytest.mark.parametrize('mode', ['refuse', 'wrong-id', 'empty-token', 'bad-error'])
def test_native_writer_refusal_or_protocol_failure_blocks_work(host, mode):
    root, _ = host(mode)
    with pytest.raises((NativeHookError, ValueError)) as caught:
        with local_hooks.writer_scope(root):
            (root / 'work-started').touch()
    assert not (root / 'work-started').exists()
    if mode == 'refuse':
        assert isinstance(caught.value, NativeHookError)
        assert type(caught.value).__name__ == 'LeaseBusy'
        assert 'writer refused' in str(caught.value)
    assert_reaped(root)


def test_native_events_keep_lifecycle_order_context_and_plain_json(host):
    from argparse import Namespace

    root, _ = host()
    errors = []
    with local_hooks.writer_scope(root), local_hooks.job_event_scope(root, 'job-1', errors):
        for event in ['job_inserted', 'job_resumed', 'dispatch_state', 'dispatch_finalized']:
            local_hooks.emit_job_event(root, event, {
                'repo_root': root, 'args': Namespace(mode='plain'), 'dispatch_id': 'attempt-1'})
    frames = requests(root)
    assert [r['hook'] for r in frames] == ['writer_enter'] + ['on_job_event'] * 4 + ['writer_exit']
    events = [r['params'] for r in frames[1:-1]]
    assert [p['event'] for p in events] == [
        'job_inserted', 'job_resumed', 'dispatch_state', 'dispatch_finalized']
    assert all(p['job_id'] == 'job-1' and p['attempt_id'] == 'attempt-1' for p in events)
    assert all(p['payload']['repo_root'] == str(root) for p in events)
    assert all(p['payload']['args'] == {'mode': 'plain'} for p in events)
    assert errors == []


def test_native_event_failures_keep_early_closed_late_recorded_policy(host, capsys):
    root, _ = host('event-refuse')
    errors = []
    with local_hooks.writer_scope(root):
        for event in ['job_inserted', 'job_resumed']:
            with pytest.raises(Exception, match='event refused'):
                local_hooks.emit_job_event(root, event, {})
        local_hooks.emit_job_event(root, 'dispatch_finalized', {}, errors=errors)
    assert len(errors) == 1 and 'EventStoreError' in errors[0]
    assert 'event refused' in capsys.readouterr().err


def test_native_wire_is_rust_sorted_compact_utf8_and_preserves_reply(host):
    root, config = host()
    client = session(root, config)
    try:
        params = {'z': '\ud55c\uae00', 'a': {'z': 2, 'a': 1}}
        reply = client.call('on_job_event', params)
        assert reply == {'version': PROTOCOL, 'id': 1, 'ok': True, 'result': {'params': params}}
        expected = {'hook': 'on_job_event', 'id': 1, 'params': params, 'version': PROTOCOL}
        assert (root / 'requests.jsonl').read_bytes() == (
            json.dumps(expected, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n'
        ).encode('utf-8')
    finally:
        client.close()
    assert_reaped(root)


def test_native_session_preserves_target_refusal_envelope(host):
    root, config = host('refuse')
    client = session(root, config)
    try:
        reply = client.call('writer_enter', {})
        assert reply['ok'] is False
        assert reply['error'] == {'type': 'LeaseBusy', 'message': 'writer refused'}
        assert reply['id'] == 1 and reply['version'] == PROTOCOL
    finally:
        client.close()
    assert_reaped(root)


def test_native_deadline_covers_blocked_stdin_write(host):
    root, config = host('blocked-stdin')
    client = session(root, config, timeout=0.15)
    start = time.monotonic()
    with pytest.raises(NativeHookError, match='timeout'):
        client.call('on_job_event', {'data': 'x' * 800000})
    assert time.monotonic() - start < 3
    assert requests(root) == []
    client.close()
    assert_reaped(root)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process-group heartbeat fixture')
def test_native_deadline_stops_descendant_heartbeat(host):
    root, config = host('tree-hang')
    client = session(root, config, timeout=0.3)
    with pytest.raises(NativeHookError, match='timeout'):
        client.call('on_job_event', {})
    client.close()
    heartbeat = root / 'heartbeat'
    assert heartbeat.exists() and heartbeat.stat().st_size > 0
    time.sleep(0.05)
    previous = heartbeat.read_bytes()
    time.sleep(0.08)
    assert heartbeat.read_bytes() == previous
    assert_reaped(root)


@pytest.mark.parametrize('mode', ['bad-hello', 'missing-hook', 'hello-hang'])
def test_native_hello_rejection_or_deadline_reaps_host(host, mode):
    root, config = host(mode)
    start = time.monotonic()
    with pytest.raises((NativeHookError, ValueError)):
        session(root, config, timeout=0.15)
    assert time.monotonic() - start < 3
    assert_reaped(root)


@pytest.mark.parametrize('mode', ['wrong-id', 'bad-version', 'bad-error', 'missing-result',
                                 'oversized', 'depth', 'partial', 'hang', 'crash'])
def test_native_bad_response_closes_without_retry_and_reaps(host, mode):
    root, config = host(mode)
    client = session(root, config, timeout=0.15)
    try:
        with pytest.raises((NativeHookError, ValueError)):
            client.call('on_job_event', {})
        with pytest.raises((NativeHookError, ValueError)):
            client.call('on_job_event', {})
        assert len(requests(root)) == 1
    finally:
        client.close()
    assert_reaped(root)


@pytest.mark.parametrize('case', ['digest', 'symlink', 'parent', 'absolute'])
def test_native_executable_admission_happens_before_spawn(host, case):
    root, config = host()
    if case == 'digest':
        config['sha256'] = '0' * 64
    elif case == 'symlink':
        link = root / 'alias'
        link.symlink_to(root / config['executable'])
        config['executable'] = link.name
    elif case == 'parent':
        config['executable'] = '../hook-host'
    else:
        config['executable'] = str(root / config['executable'])
    with pytest.raises((NativeHookError, ValueError)):
        session(root, config)
    assert not (root / 'host.pid').exists()


@pytest.mark.parametrize('case', ['oversized', 'depth', 'unserved', 'nonfinite'])
def test_native_bad_request_is_not_sent(host, case):
    root, config = host()
    client = session(root, config)
    params = {'data': 'x' * 1048576} if case == 'oversized' else {}
    if case == 'depth':
        for _ in range(70):
            params = [params]
    if case == 'nonfinite':
        params = {'data': float('nan')}
    try:
        with pytest.raises((NativeHookError, ValueError)):
            client.call('unknown' if case == 'unserved' else 'on_job_event', params)
        assert requests(root) == []
    finally:
        client.close()
    assert_reaped(root)


@pytest.mark.parametrize('backend', ['codex', 'claude'])
def test_run_agent_async_provider_observes_native_lease(host, monkeypatch, backend):
    from types import SimpleNamespace

    from tools.mir_executor import executor
    from tools.mir_executor.dispatch import AgentRoute

    root, _ = host()
    seen = []
    monkeypatch.setattr(executor, '_guard_codex_main_worktree', lambda *a: None)

    def observe():
        assert (root / 'lease').exists()
        assert [r['hook'] for r in requests(root)] == ['writer_enter']
        seen.append('provider')

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            observe()
            return self

        def __exit__(self, *args):
            assert (root / 'lease').exists()

        def call_codex(self, **kwargs):
            return SimpleNamespace(content_text='answer', raw_result={})

    class Process:
        returncode = 0

        async def communicate(self, prompt):
            observe()
            return b'answer', b''

    async def spawn(*args, **kwargs):
        return Process()

    monkeypatch.setattr(executor, 'CodexMcpClient', Client)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    selected = AgentRoute('worker', backend, 'model', 'high', 'agent.md',
                          'digest', 'instructions', 'workspace-write')
    api = executor.MirExecutor(root, agent_route=selected)

    async def exercise():
        with local_hooks.writer_scope(root):
            result = await api.run_agent_async(['task'])
            assert (root / 'lease').exists()
            return result

    assert asyncio.run(exercise()).stdout == 'answer'
    assert seen == ['provider']
    assert [r['hook'] for r in requests(root)] == ['writer_enter', 'writer_exit']
    assert_reaped(root)


def test_run_agent_async_cancellation_keeps_native_lease_until_provider_cleanup(host, monkeypatch):
    import threading

    from tools.mir_executor import executor
    from tools.mir_executor.dispatch import AgentRoute

    root, _ = host()
    started, release = threading.Event(), threading.Event()
    monkeypatch.setattr(executor, '_guard_codex_main_worktree', lambda *a: None)

    class Process:
        returncode = None

        async def communicate(self, prompt):
            assert (root / 'lease').exists()
            started.set()
            await asyncio.Future()

        def terminate(self):
            self.returncode = -15

        async def wait(self):
            await asyncio.to_thread(release.wait, 3)
            return self.returncode

    async def spawn(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    selected = AgentRoute('worker', 'claude', 'model', 'high', 'agent.md',
                          'digest', 'instructions', 'workspace-write')
    api = executor.MirExecutor(root, agent_route=selected)

    async def exercise():
        async def outer():
            with local_hooks.writer_scope(root):
                await api.run_agent_async(['task'])

        task = asyncio.create_task(outer())
        try:
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel()
            await asyncio.sleep(0.02)
            task.cancel()
            await asyncio.sleep(0.02)
            assert (root / 'lease').exists()
            assert [r['hook'] for r in requests(root)] == ['writer_enter']
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(exercise())
    assert requests(root)[-1]['params']['outcome'] == 'uncertain'
    assert not (root / 'lease').exists()
    assert_reaped(root)
