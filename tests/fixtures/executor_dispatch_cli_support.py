"""Offline full-CLI dispatch fixtures, sharing the direct-execute seed and schema."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import sys

SERVER = r'''import json
import os
import sys
from pathlib import Path
root = Path(os.environ['EXECUTE_FIXTURE_ROOT'])
mode = os.environ['DISPATCH_FIXTURE_MODE']
def send(value):
    print(json.dumps(value), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    with (root / 'provider-methods').open('a') as stream:
        stream.write(method + '\n')
    if method == 'initialize':
        send({'id': request['id'], 'result': {'userAgent': 'offline-dispatch/1'}})
    elif method == 'thread/start':
        cwd = Path(request['params']['cwd'])
        review = request['params']['sandbox'] == 'read-only'
        send({'id': request['id'], 'result': {'thread': {'id': 'fixture-thread'},
                                             'model': 'offline-fixture'}})
    elif method == 'turn/start':
        if review:
            text = json.dumps({'verdict': 'fail', 'reason': 'offline rejection',
                               'findings': ['offline finding']})
        else:
            (cwd / 'code.txt').write_text('delegated change\n')
            text = 'offline dispatch complete'
        send({'id': request['id'], 'result': {'turn': {'id': 'fixture-turn'}}})
        send({'method': 'turn/completed', 'params': {'threadId': 'fixture-thread',
              'turn': {'id': 'fixture-turn', 'status': 'completed', 'items': [
                  {'id': 'fixture-item', 'type': 'agentMessage', 'text': text}]}}})
'''

CLAUDE_SERVER = r'''import os
from pathlib import Path
root = Path(os.environ['EXECUTE_FIXTURE_ROOT'])
with (root / 'provider-methods').open('a') as stream:
    stream.write('claude-headless\n')
Path('code.txt').write_text('delegated change\n')
print('offline dispatch complete')
'''

HOOKS = r'''import json
import os
from pathlib import Path
from contextlib import contextmanager
ROOT = Path(__file__).resolve().parents[2]
receipt = os.environ.get('MIR_EXECUTOR_OWNED_RECEIPT')
if receipt:
    assert Path(receipt).read_bytes() == b'owned'
    (ROOT / 'native-imported').touch()
def record(event, payload=None):
    with (ROOT / 'hook-events').open('a') as stream:
        stream.write(json.dumps([event, payload], default=str, sort_keys=True) + '\n')
def pre_execute(args, root):
    receipt = os.environ.get('MIR_EXECUTOR_OWNED_RECEIPT')
    if receipt:
        assert Path(receipt).read_bytes() == b'owned'
        (ROOT / 'native-owned').touch()
    record('pre_execute')
@contextmanager
def writer_scope(root):
    record('writer_enter')
    try:
        yield
    finally:
        record('writer_exit')
def on_job_event(event, payload):
    record(event, {key: value for key, value in payload.items() if key != 'args'})
def after_run(worktree, attempt, result):
    if os.environ['DISPATCH_FIXTURE_MODE'] == 'hook_failure':
        raise RuntimeError('offline after_run failure')
'''


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def seed(root, case, support):
    launcher = support['seed'](root, 'success')
    (root / 'server.py').write_text(SERVER, encoding='utf-8')
    if launcher.suffix != '.cmd':
        launcher.write_text('#!/usr/bin/env python3\n' + SERVER, encoding='utf-8')
    (root / 'tools/mir_executor/local.py').write_text(HOOKS, encoding='utf-8')
    config = {'verifiers': {'offline': [sys.executable, '-c', 'pass']},
              'require_review': case == 'review_reject'}
    (root / 'config').mkdir(exist_ok=True)
    (root / 'config/mir-executor.local.json').write_text(json.dumps(config), encoding='utf-8')
    (root / 'brief.json').write_text('{"expanded_goal":"offline fixture"}', encoding='utf-8')
    (root / '.gitignore').write_text('*\n!code.txt\n!.gitignore\n', encoding='utf-8')
    (root / 'code.txt').write_text('initial\n', encoding='utf-8')
    git(root, 'config', 'user.name', 'Fixture')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    git(root, 'add', 'code.txt', '.gitignore')
    git(root, 'commit', '-qm', 'offline fixture')
    environment = support['environment'](root, 'success', launcher)
    environment['DISPATCH_FIXTURE_MODE'] = case
    environment['TMPDIR'] = str(root)
    environment.pop('MIR_EXECUTOR_EXECUTE_IMPL', None)
    arguments = ['execute', '--dispatch', '--dispatch-brief', str(root / 'brief.json'),
                 '--model', 'offline-fixture', '--reasoning-effort', 'medium',
                 '--allow-path', 'other.txt' if case == 'gate_block' else 'code.txt',
                 '--verify-cmd', 'offline', '--artifacts-dir', str(root / 'artifacts')]
    if case == 'relative_artifacts':
        arguments[-1] = 'artifacts'
    if case in ('claude_success', 'claude_invalid_timeout'):
        (root / 'offline-policy.json').write_text('{"mode":"select"}', encoding='utf-8')
        server = root / 'claude-server.py'
        server.write_text(CLAUDE_SERVER, encoding='utf-8')
        claude = root / ('fake-claude.cmd' if launcher.suffix == '.cmd' else 'fake-claude')
        claude.write_text(f'@"{sys.executable}" "{server}" %*\n' if claude.suffix == '.cmd'
                          else '#!/usr/bin/env python3\n' + CLAUDE_SERVER, encoding='utf-8')
        claude.chmod(0o755)
        environment['CLAUDE_BIN'] = str(claude)
        arguments += ['--execution-backend', 'claude']
        if case == 'claude_invalid_timeout':
            arguments += ['--timeout=-1']
    if case == 'finalize_rollback':
        # Fail the actual Git checkout after the merge gate; rollback must restore code.txt.
        hook = root / '.git/hooks/post-checkout'
        hook.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\n'
                        'import sys\n'
                        'if Path(".git").is_dir() and not Path("checkout-failed").exists():\n'
                        '    Path("checkout-failed").touch()\n'
                        '    Path("code.txt").write_text("partial change\\n")\n'
                        '    sys.exit(1)\n',
                        encoding='utf-8')
        hook.chmod(0o755)
    return launcher, environment, arguments


def resume(root, mode):
    from tools.mir_executor.jobs import JobRecord, JobRegistry

    brief = root / 'brief.json'
    options = {
        'dispatch_brief': str(brief),
        'brief_sha256': hashlib.sha256(brief.read_bytes()).hexdigest(),
        'allow_paths': ['code.txt'], 'verify_cmds': ['offline'], 'expect_changes': True,
        'model': 'offline-fixture', 'reasoning_effort': 'medium',
        'execution_backend': 'codex', 'artifacts_dir': str(root / 'artifacts'),
    }
    registry = JobRegistry(root / 'tasks/jobs.db')
    registry.insert(JobRecord(
        job_id='resume-fixture', change_id='old-dispatch', category='unit', family=None,
        repo_root=str(root), codex_args=['offline fixture'], timeout_seconds=60,
        status='failed', dispatch_brief_path=str(brief), execution_backend='codex',
        resolved_model='offline-fixture', resolved_reasoning_effort='medium',
        dispatch_options_json=None if mode == 'legacy' else json.dumps(options),
    ))
    registry.close()
    if mode == 'changed_brief':
        brief.write_text('{"expanded_goal":"changed goal"}', encoding='utf-8')
    return ['resume', '--job-id', 'resume-fixture']


def snapshot(root, completed):
    def normalize(text):
        roots = {str(root), root.as_posix(), repr(str(root))[1:-1],
                 str(root).replace('\\', '\\\\'), str(root).replace('\\', '\\\\\\\\')}
        for spelling in sorted(roots, key=len, reverse=True):
            text = text.replace(spelling, '<root>')
        text = re.sub(r'mir-wt-[^/\\\s"\']+', 'mir-wt-<temp>', text)
        text = re.sub(r'\b[0-9a-f]{32}\b', '<id>', text)
        text = re.sub(r'\b[0-9a-f]{40}\b', '<commit>', text)
        text = re.sub(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)',
                      '<timestamp>', text)
        text = re.sub(r'("(?:duration_s|elapsed_seconds|duration_seconds)":\s*)[\d.eE+-]+',
                      r'\1"<duration>"', text)
        return text

    jobs = []
    if (root / 'tasks/jobs.db').exists():
        connection = sqlite3.connect(root / 'tasks/jobs.db')
        try:
            connection.row_factory = sqlite3.Row
            jobs = [dict(row) for row in connection.execute('SELECT * FROM jobs ORDER BY job_id')]
        finally:
            connection.close()
    artifacts = {}
    for path in sorted((root / 'artifacts').rglob('*')):
        if path.is_file():
            artifacts[normalize(str(path.relative_to(root)))] = normalize(path.read_text())
    return {
        'code': completed.returncode,
        'stdout': normalize(completed.stdout.decode()),
        'stderr': normalize(completed.stderr.decode()),
        'jobs': normalize(json.dumps(jobs, sort_keys=True)),
        'events': normalize((root / 'hook-events').read_text())
        if (root / 'hook-events').exists() else '',
        'provider_methods': (root / 'provider-methods').read_text()
        if (root / 'provider-methods').exists() else '',
        'git_diff': normalize(git(root, 'diff', 'HEAD', '--', 'code.txt').decode()),
        'git_status': normalize(git(root, 'status', '--porcelain').decode()),
        'worktrees': normalize(git(root, 'worktree', 'list', '--porcelain').decode()),
        'code_text': (root / 'code.txt').read_text(),
        'artifacts': artifacts,
    }
