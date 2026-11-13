"""Supplementary offline dispatch faults; called by the Stage D capture seed.

All injections operate below the supplied synthetic home. This module does not
invoke a provider, run a capture, or alter the production executor implementation.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def cases():
    return [{'name': 'fault-' + name} for name in (
        'branch-collision', 'worktree-path-collision', 'worktree-add',
        'private-evidence-directory', 'private-evidence-link', 'commit',
        'cleanup-remove', 'cleanup-branch', 'verification-cleanup',
        'merge-checkout', 'merge-rollback', 'finalize-lock-timeout',
        'review-pass', 'review-malformed', 'review-extra-key', 'review-findings',
        'verifier-empty-argument', 'verifier-missing', 'verifier-invalid',
        'verifier-env-invalid', 'denied-harness', 'secret-path', 'out-allowlist',
        'before-run', 'after-run', 'provider-hook-refusal',
        'provider-hook-none', 'provider-hook-blocked', 'provider-hook-invalid',
        'parser-extension', 'parser-extension-computed', 'parser-extension-refusal',
        'late-event', 'identity-refusal', 'identity-invalid', 'render-exception',
        'main-moved', 'dispatch-moved', 'dispatch-dirty',
        'artifacts-parent-swap-to-outside',
    )]


GIT_WRAPPER = r'''import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(os.environ['EXECUTE_FIXTURE_ROOT'])
real = os.environ['DISPATCH_FAULT_REAL_GIT']
mode = os.environ['DISPATCH_FIXTURE_MODE']
args = sys.argv[1:]
command = list(args)
git_root = Path.cwd()
while command and command[0] == '-C':
    git_root = Path(command[1])
    command = command[2:]
while command and command[0] == '--literal-pathspecs':
    command = command[1:]

def marker(event):
    with (root / 'fault-git-events').open('a') as stream:
        stream.write(json.dumps([event, command]) + '\n')

def fail():
    marker('refused')
    print('offline git fault', file=sys.stderr)
    sys.exit(73)

add = command[:2] == ['worktree', 'add']
dispatch_add = add and '-b' in command and any(
    value.startswith('mir-dispatch/') for value in command)
remove = command[:2] == ['worktree', 'remove']
verify_remove = remove and any('mir-verify-' in value for value in command)
dispatch_remove = remove and not verify_remove
if mode == 'fault-worktree-add' and dispatch_add:
    fail()
if mode == 'fault-commit' and command[:1] == ['commit']:
    fail()
if mode == 'fault-cleanup-remove' and dispatch_remove:
    fail()
if mode == 'fault-cleanup-branch' and command[:2] == ['branch', '-D']:
    fail()
if mode == 'fault-verification-cleanup' and verify_remove:
    fail()
if mode in ('fault-merge-checkout', 'fault-merge-rollback') and (
        git_root.resolve() == root.resolve() and command[:1] == ['checkout']):
    (root / 'code.txt').write_text('partial merge\n')
    (root / 'fault-merge-started').touch()
    fail()
if mode == 'fault-merge-rollback' and (root / 'fault-merge-started').exists() and (
        git_root.resolve() == root.resolve() and command[:1] == ['restore']):
    fail()
if dispatch_add and mode == 'fault-worktree-path-collision':
    Path(command[-2]).write_text('occupied worktree path\n')
    marker('occupied')
if dispatch_add and mode in ('fault-private-evidence-directory',
                              'fault-private-evidence-link'):
    result = subprocess.run([real, *args], check=False)
    if result.returncode:
        sys.exit(result.returncode)
    evidence = Path(command[-2]) / '.mir-dispatch'
    evidence.mkdir(exist_ok=True)
    if mode == 'fault-private-evidence-directory':
        (evidence / 'brief.md').mkdir()
    else:
        (evidence / 'brief.md').symlink_to(root / 'fault-outside' / 'canary')
    marker('evidence-blocker')
    sys.exit(0)
os.execv(real, [real, *args])
'''


def _append(local, text):
    with local.open('a', encoding='utf-8') as stream:
        stream.write('\n' + text + '\n')


def _option(argv, flag, value):
    if flag in argv:
        argv[argv.index(flag) + 1] = str(value)
    else:
        argv.extend((flag, str(value)))


def _server(home, review):
    """Replace only the fake server's read-only result, keeping its wire protocol."""
    for path in (home / 'server.py', home / 'fake-codex'):
        text = path.read_text(encoding='utf-8')
        start = text.index('        if review:\n')
        end = text.index('        else:\n', start)
        text = (text[:start] + '        if review:\n            text = '
                + repr(review) + '\n' + text[end:])
        path.write_text(text, encoding='utf-8')


def apply(home, case, env, argv, config, local):
    """Apply one case after base seeding and before saving the local config."""
    name = case['name']
    if not name.startswith('fault-'):
        return
    home, local = Path(home), Path(local)
    (home / 'fault-setup').write_text(name + '\n', encoding='ascii')
    outside = home / 'fault-outside'
    outside.mkdir()
    (outside / 'canary').write_text('outside must remain unchanged\n', encoding='ascii')
    real_git = shutil.which('git')
    if real_git is None:
        raise RuntimeError('offline git executable unavailable')
    env['DISPATCH_FAULT_REAL_GIT'] = real_git
    wrapper = home / 'fake-bin' / 'git'
    wrapper.write_text('#!/usr/bin/env python3\n' + GIT_WRAPPER, encoding='utf-8')
    wrapper.chmod(0o755)
    # The base seed has already placed fake-bin first; do not add external tools.
    if str(wrapper.parent) not in env['PATH'].split(os.pathsep):
        env['PATH'] = str(wrapper.parent) + os.pathsep + env['PATH']

    if name == 'fault-branch-collision':
        _append(local, '''_fault_event = on_job_event
def on_job_event(event, payload):
    _fault_event(event, payload)
    if event == 'job_inserted':
        import subprocess
        subprocess.run(['git', '-C', str(ROOT), 'branch',
                        'mir-dispatch/' + payload['job_id'], 'HEAD'], check=True)
        (ROOT / 'fault-collision-created').touch()
''')
    if name == 'fault-finalize-lock-timeout':
        _option(argv, '--finalize-lock-timeout', '0')
        _append(local, '''@contextmanager
def writer_scope(root):
    import fcntl
    lock = ROOT / '.mir' / 'dispatch-finalize.lock'
    lock.parent.mkdir(exist_ok=True)
    with lock.open('a+') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        (ROOT / 'fault-lock-held').touch()
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
''')
    if name.startswith('fault-review-'):
        config['require_review'] = True
        review = {
            'fault-review-pass': {'verdict': 'pass', 'reason': 'offline approved', 'findings': []},
            'fault-review-extra-key': {'verdict': 'pass', 'reason': 'offline approved',
                                      'findings': [], 'extra': True},
            'fault-review-findings': {'verdict': 'pass', 'reason': 'offline findings',
                                     'findings': ['offline finding']},
        }
        _server(home, 'not-json' if name == 'fault-review-malformed'
                else json.dumps(review[name], sort_keys=True))
    if name == 'fault-verifier-empty-argument':
        config['verifiers']['offline'] = [sys.executable, '']
    if name == 'fault-verifier-missing':
        config['verifiers']['offline'] = [str(home / 'missing-verifier')]
    if name == 'fault-verifier-invalid':
        config['verifiers']['offline'] = []
    if name == 'fault-verifier-env-invalid':
        config['verifier_env'] = 'offline-invalid'
    if name == 'fault-secret-path':
        profile = home / '.mir' / 'repo-profile.toml'
        profile.parent.mkdir(exist_ok=True)
        profile.write_text('[boundaries]\nsecrets = ["code.txt"]\n', encoding='ascii')
    if name == 'fault-out-allowlist':
        _option(argv, '--allow-path', 'other.txt')
    if name == 'fault-denied-harness':
        # .gitignore only tracks code.txt; force-add the denied path explicitly.
        _append(local, '''def after_run(worktree, attempt, result):
    import subprocess
    path = worktree.path / 'docs' / 'offline-denied.txt'
    path.parent.mkdir(exist_ok=True)
    path.write_text('offline denied change\\n')
    subprocess.run(['git', '-C', str(worktree.path), 'add', '-f',
                    'docs/offline-denied.txt'], check=True)
''')
        argv.extend(('--allow-path', 'docs/'))

    hooks = {
        'fault-before-run': 'def before_run(*args):\n    raise ValueError("offline before_run")',
        'fault-after-run': 'def after_run(*args):\n    raise ValueError("offline after_run")',
        'fault-provider-hook-refusal': '''def after_provider_call(*args):
    raise ValueError("offline provider hook")''',
        'fault-provider-hook-none': '''def after_provider_call(result, metadata):
    record("provider_observed")
    return None''',
        'fault-provider-hook-blocked': '''def after_provider_call(result, metadata):
    from dataclasses import replace
    return replace(result, exit_code=9, retryable=False, blocked_reason='offline budget')''',
        'fault-provider-hook-invalid': 'def after_provider_call(*args):\n    return object()',
        'fault-identity-refusal': '''def job_identity(*args):
    raise ValueError("offline identity")''',
        'fault-identity-invalid': 'def job_identity(*args):\n    return object()',
        'fault-render-exception': '''def render_brief(*args):
    raise RuntimeError("offline render")''',
        'fault-parser-extension': '''def register_execute_options(parser):
    parser.add_argument('--offline-option')''',
        'fault-parser-extension-computed': '''def _offline_options(parser):
    parser.add_argument('--offline-option')
globals()['register_' + 'execute_options'] = _offline_options''',
        'fault-parser-extension-refusal': '''def register_execute_options(parser):
    raise ValueError('offline parser')''',
        'fault-late-event': '''_fault_event = on_job_event
def on_job_event(event, payload):
    _fault_event(event, payload)
    if event == 'dispatch_finalized':
        raise ValueError('offline late event')''',
        'fault-dispatch-moved': '''def after_run(worktree, attempt, result):
    # Independent review runs after source_commit was captured.
    (ROOT / 'fault-dispatch-path').write_text(str(worktree.path))''',
        'fault-artifacts-parent-swap-to-outside': '''def after_run(worktree, attempt, result):
    parent = ROOT / 'artifact-container'
    parent.rmdir()
    parent.symlink_to(ROOT / 'fault-outside', target_is_directory=True)
    (ROOT / 'fault-parent-swapped').touch()''',
    }
    if name in hooks:
        _append(local, hooks[name])
    if name == 'fault-parser-extension':
        argv.extend(('--offline-option', 'offline-value'))
    if name in ('fault-main-moved', 'fault-dispatch-dirty'):
        config['verifier_env'] = 'inherit'
    if name == 'fault-main-moved':
        config['verifiers']['offline'] = [sys.executable, '-c',
            'import subprocess; subprocess.run([' + repr(real_git) + ', "-C", ' + repr(str(home))
            + ', "commit", "--allow-empty", "-qm", "offline main moved"], check=True)']
    if name == 'fault-dispatch-dirty':
        config['verifiers']['offline'] = [sys.executable, '-c',
            'from pathlib import Path; import subprocess; root=Path(' + repr(str(home))
            + '); rows=subprocess.check_output([' + repr(real_git)
            + ',"-C",str(root),"worktree","list",'
              '"--porcelain"]).decode().splitlines(); paths=[row[9:] for row in rows '
              'if row.startswith("worktree ") and "mir-wt-" in row]; '
              '[Path(path,"code.txt").write_text("late dirty\\n") for path in paths]']
    if name == 'fault-dispatch-moved':
        config['require_review'] = True
        _server(home, json.dumps({'verdict': 'pass', 'reason': 'offline approved', 'findings': []}))
        # This is synthetic server code, executed only for its read-only review.
        for path in (home / 'server.py', home / 'fake-codex'):
            text = path.read_text(encoding='utf-8').replace(
                '        if review:\n',
                '        if review:\n            import subprocess\n'
                '            subprocess.run(["git", "-C", str(cwd), "commit", '
                '"--allow-empty", "-qm", "offline dispatch moved"], check=True)\n')
            path.write_text(text, encoding='utf-8')
    if name == 'fault-artifacts-parent-swap-to-outside':
        (home / 'artifact-container').mkdir()
        _option(argv, '--artifacts-dir', home / 'artifact-container' / 'artifacts')
