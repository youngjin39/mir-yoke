"""Synthetic provider lifecycle contract; no installed binaries or real repositories."""
import hashlib
import json
import os
import shlex
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HOST = r'''
import json, os, signal, subprocess, sys, time
from pathlib import Path
root = Path(__file__).parent
def emit(value):
    print(json.dumps(value), flush=True)
def wait(name):
    until = time.monotonic() + 25
    while not (root / name).exists():
        assert time.monotonic() < until
        time.sleep(.01)
if sys.argv[1] == 'descendant':
    (root / 'descendant.pid').write_text(str(os.getpid()))
    wait('late-release')
    (root / 'late-effect').write_text('child still owns effects')
    sys.exit(0)
if sys.argv[1] == 'hooks':
    (root / 'hooks.pid').write_text(str(os.getpid()))
    emit({'version':'mir-executor.hooks@1', 'hooks':['writer_scope']})
    for line in sys.stdin:
        q = json.loads(line)
        if q['hook'] == 'writer_exit' and (root / 'provider.pid').exists():
            try:
                os.kill(int((root / 'provider.pid').read_text()), 0)
                state = 'alive'
            except ProcessLookupError:
                state = 'reaped'
            (root / 'provider-at-exit').write_text(state)
        with (root / 'hooks.jsonl').open('a') as out:
            out.write(json.dumps(q) + '\n')
        if q['hook'] == 'writer_exit' and (root / 'mode').read_text() == 'double':
            os.kill(os.getppid(), signal.SIGINT)
        if q['hook'] == 'writer_enter':
            (root / 'lease').write_text('opaque-token')
            result = {'token':'opaque-token'}
            if (root / 'mode').read_text() == 'early-term':
                os.kill(os.getppid(), signal.SIGTERM)
        else:
            assert q['params']['token'] == 'opaque-token'
            if q['params']['outcome'] != 'uncertain':
                (root / 'lease').unlink()
            result = None
        emit({'version':'mir-executor.hooks@1','id':q['id'],'ok':True,'result':result})
    sys.exit(0)
(root / 'provider.pid').write_text(str(os.getpid()))
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
mode = (root / 'mode').read_text()
with (root / 'providers').open('a') as out:
    out.write(str(os.getpid()) + '\n')
is_review = mode.startswith('reviewer-') and len((root / 'providers').read_text().splitlines()) == 2
cwd = root
for line in sys.stdin:
    q = json.loads(line)
    method = q['method']
    if method == 'thread/start':
        cwd = Path(q['params']['cwd'])
    if method == 'initialize' and mode.endswith('init-live') and (
            not mode.startswith('reviewer-') or is_review):
        subprocess.Popen([sys.executable, '-I', __file__, 'descendant'])
        wait('descendant.pid')
        (root / 'running').touch()
        wait('finish')
        emit({'id':q['id'], 'error':{'code':-1, 'message':'synthetic initialize failure'}})
        wait('finish')
        continue
    if method == 'initialized':
        continue
    result = {'userAgent':'fixture'} if method == 'initialize' else (
        {'thread':{'id':'thread'}} if method == 'thread/start' else {'turn':{'id':'turn'}})
    emit({'id':q['id'],'result':result})
    if method == 'turn/start':
        if (mode in ('descendant', 'dispatch-descendant')
                or (is_review and mode == 'reviewer-descendant')):
            subprocess.Popen([sys.executable, '-I', __file__, 'descendant'])
            wait('descendant.pid')
        if (mode.startswith(('dispatch-', 'reviewer-'))
                and mode != 'dispatch-term' and not is_review):
            (cwd / 'code.txt').write_text('changed by synthetic writer\n')
        if not mode.startswith('reviewer-') or is_review:
            (root / 'running').touch()
            wait('finish')
        text = ('{"verdict":"pass","reason":"ok","findings":[]}' if is_review
                else 'late provider output')
        emit({'method':'turn/completed','params':{'threadId':'thread','turn':{
            'id':'turn','status':'completed','items':[{
                'type':'agentMessage','id':'message','text':text}]}}})
'''


def wait(check):
    deadline = time.monotonic() + 15
    while not check():
        assert time.monotonic() < deadline, "synthetic barrier timed out"
        time.sleep(.01)


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def run(binary, root, mode):
    for folder in ('home', 'tmp', 'config', 'bin', 'tasks'):
        (root / folder).mkdir()
    (root / 'host.py').write_text(HOST)
    launcher = root / 'bin/fake'
    launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable)
                        + ' -I ' + shlex.quote(str(root / 'host.py')) + ' "$@"\n')
    launcher.chmod(0o755)
    (root / 'bin/git').symlink_to('/usr/bin/git')
    (root / 'config/mir-executor.local.json').write_text(json.dumps({
        'native_policy': {'version': 1, 'hooks': {
            'executable': 'bin/fake', 'argv': ['hooks'],
            'sha256': hashlib.sha256(launcher.read_bytes()).hexdigest(),
            'hooks': ['writer_scope']}}}))
    (root / 'tasks/tdd.json').write_text(json.dumps({'changes': [{
        'id': 'change', 'categories': {'unit': {'status': 'planned'}}}]}))
    (root / 'mode').write_text(mode)
    env = {'HOME': str(root / 'home'), 'TMPDIR': str(root / 'tmp'),
           'PATH': str(root / 'bin'), 'CODEX_BIN': str(launcher), 'MIR_CODEX_MAIN': '1',
           'MIR_EXECUTOR_OWNED_RECEIPT': str(root / 'receipt')}
    subprocess.run(['/usr/bin/git', 'init', str(root)], cwd=root, env=env,
                   check=True, capture_output=True)
    extra = []
    if mode.startswith(('dispatch-', 'reviewer-')):
        config_path = root / 'config/mir-executor.local.json'
        config = json.loads(config_path.read_text())
        config.update(require_review=mode.startswith('reviewer-'),
                      verifiers={'offline': ['/usr/bin/true']})
        config_path.write_text(json.dumps(config))
        (root / 'policy.json').write_text('{"mode":"force_codex"}')
        (root / 'config/model-routing.lock.json').write_text('{"policy":{"mode":"force_codex"}}')
        env['MIR_SUB_AGENT_POLICY'] = str(root / 'policy.json')
        (root / 'brief.json').write_text('{"expanded_goal":"offline goal"}')
        (root / 'code.txt').write_text('initial\n')
        (root / '.gitignore').write_text('*\n!code.txt\n!.gitignore\n')
        for argv in (['add', 'code.txt', '.gitignore'],
                     ['-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                      'commit', '-qm', 'synthetic']):
            subprocess.run(['/usr/bin/git', *argv], cwd=root, env=env,
                           check=True, capture_output=True)
        for name in ('uv', 'claude'):
            fake = root / 'bin' / name
            fake.write_text('#!/bin/sh\nexit 97\n')
            fake.chmod(0o755)
        extra = ['--dispatch', '--dispatch-brief', 'brief.json', '--model', 'offline',
                 '--reasoning-effort', 'medium', '--allow-path', 'code.txt',
                 '--verify-cmd', 'offline', '--artifacts-dir', 'artifacts',
                 '--max-codex-attempts', '2' if mode == 'dispatch-term' else '1']
    worker = subprocess.Popen([binary, '--home-root', str(root), '--jobs-db',
                               str(root / 'jobs.db'), 'execute', '--repo-root', str(root),
                               '--change-id', 'change', '--category', 'unit',
                               '--codex-args=fixture', '--background', '--timeout=20', *extra],
                              cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              start_new_session=True)
    try:
        if mode == 'early-term':
            wait(lambda: worker.poll() is not None)
        else:
            wait(lambda: (root / 'running').exists() or worker.poll() is not None)
            assert worker.poll() is None, worker.communicate()
        with sqlite3.connect(root / 'jobs.db') as db:
            job, status = db.execute('SELECT job_id,status FROM jobs').fetchone()
        assert status == 'running'
        if mode in ('term', 'int', 'double', 'dispatch-term', 'reviewer-term'):
            worker.send_signal(signal.SIGINT if mode == 'int' else signal.SIGTERM)
        elif mode != 'early-term':
            (root / 'finish').touch()
        out, err = worker.communicate(timeout=15)
        expected = {'term': 143, 'early-term': 143, 'int': 130, 'double': 143,
                    'dispatch-term': 143, 'reviewer-term': 143, 'init-live': 1,
                    'dispatch-init-live': 1, 'reviewer-init-live': 1}.get(mode, 0)
        expected_out = (b'' if mode in ('dispatch-term', 'reviewer-term')
                        else f'[BACKGROUND] job_id={job}\n'.encode())
        if (mode.startswith(('dispatch-', 'reviewer-'))
                and mode not in ('dispatch-term', 'reviewer-term')):
            assert worker.returncode == expected, (worker.returncode, out, err)
            assert len((root / 'providers').read_text().splitlines()) == (
                2 if mode.startswith('reviewer-') else 1)
            if mode.endswith('descendant'):
                assert (root / 'code.txt').read_text() == 'changed by synthetic writer\n'
        else:
            assert (worker.returncode, out, err) == (
                expected, expected_out, b''), (worker.returncode, out, err)
        if mode != 'early-term':
            assert not alive(int((root / 'provider.pid').read_text()))
        else:
            assert not (root / 'provider.pid').exists()
        hooks = [json.loads(line) for line in (root / 'hooks.jsonl').read_text().splitlines()]
        assert [h['hook'] for h in hooks] == ['writer_enter', 'writer_exit'], hooks
        assert hooks[-1]['params']['token'] == 'opaque-token'
        if mode != 'early-term':
            assert (root / 'provider-at-exit').read_text() == 'reaped'
        outcome = hooks[-1]['params']['outcome']
        if mode.endswith(('descendant', 'init-live')):
            assert alive(int((root / 'descendant.pid').read_text()))
            (root / 'late-release').touch()
            wait(lambda: (root / 'late-effect').exists())
            assert outcome == 'uncertain', hooks
        else:
            assert outcome == ('clean' if mode == 'complete' else 'unclean'), hooks
        assert (root / 'lease').exists() == (outcome == 'uncertain')
        if mode == 'dispatch-term':
            for events in root.rglob('events.jsonl'):
                assert not any('exit_code' in json.loads(line)
                               for line in events.read_text().splitlines()), events.read_text()
        if mode in ('term', 'int', 'early-term', 'double', 'dispatch-term', 'reviewer-term'):
            with sqlite3.connect(root / 'jobs.db') as db:
                assert db.execute('SELECT status,exit_code,stdout,stderr FROM jobs').fetchone() == (
                    'running', None, None, None)
        if mode == 'reviewer-term':
            files = sorted(p.name for p in (root / 'artifacts').rglob('*') if p.is_file())
            assert files == ['dispatch-events.jsonl'], files
    finally:
        for name in ('provider.pid', 'descendant.pid', 'hooks.pid'):
            marker = root / name
            if marker.exists():
                try:
                    os.kill(int(marker.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        try:
            os.killpg(worker.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        worker.communicate(timeout=10)


if __name__ == '__main__':
    run(sys.argv[1], Path(sys.argv[2]), sys.argv[3])
