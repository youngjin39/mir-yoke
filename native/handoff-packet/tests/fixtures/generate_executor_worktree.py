"""Capture E6 worktree observations from the unchanged Python reference."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor.dispatch import persist_dispatch_artifacts  # noqa: E402
from tools.mir_executor.worktree import (  # noqa: E402
    child_env,
    cleanup_worktree,
    create_dispatch_worktree,
)


def git(repo, *args):
    return subprocess.run(
        ['git', '-C', str(repo), *args], check=True, capture_output=True, text=True,
    ).stdout.strip()


def capture(root, name):
    repo = root / name
    repo.mkdir()
    git(repo, 'init', '-q')
    git(repo, 'config', 'core.autocrlf', 'false')
    git(repo, 'config', 'user.name', 'Fixture')
    git(repo, 'config', 'user.email', 'fixture@example.invalid')
    files = {'code [literal].txt': 'initial\n', '.gitignore': '.mir/\n'}
    for path, text in files.items():
        (repo / path).write_text(text, encoding='utf-8')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'fixture')
    (repo / '.mir').mkdir()
    profile = '[repo]\nrepository_type = "fixture"\n'
    (repo / '.mir/repo-profile.toml').write_text(profile, encoding='utf-8')
    brief = 'hello token=private-value\n'
    wt = create_dispatch_worktree(
        repo, 'fixture', brief_text=brief, worktrees_root=root / (name + ' trees'),
    )
    artifacts = {
        'result.json': '{"token":"private-value","ok":true,"nested":["Bearer private-value"]}',
        'events.jsonl': '{"password":"private-value"}\n\n{"text":"normal"}\n',
        'reviewer.json': '{"ok":true}',
        'dispatch-events.jsonl': '{"api_key":"private-value"}\n',
    }
    for path, text in artifacts.items():
        (wt.path / '.mir-dispatch' / path).write_text(text, encoding='utf-8')
    output = persist_dispatch_artifacts(wt, repo, root / (name + ' artifacts'))
    status = json.loads(wt.status_path.read_text())
    status['base_commit'] = '<BASE>'
    observed = {
        'brief': wt.brief_path.read_text(), 'status': status,
        'profile': (wt.path / '.mir/repo-profile.toml').read_text(),
        'branch': git(wt.path, 'branch', '--show-current'),
        'artifacts': {p.name: p.read_text() for p in output.iterdir() if p.name != 'status.json'},
        'private_mode': oct(wt.brief_path.stat().st_mode & 0o777),
        'tracked': git(wt.path, 'ls-files', '-z'),
        'git_status': git(wt.path, 'status', '--porcelain', '-z'),
    }
    cleanup_worktree(wt)
    observed['removed'] = not wt.path.exists()
    observed['branch_removed'] = not git(repo, 'branch', '--list', wt.branch)
    git(repo, 'branch', 'mir-dispatch/existing')
    try:
        create_dispatch_worktree(repo, 'existing', worktrees_root=root / (name + ' trees'))
    except subprocess.CalledProcessError as exc:
        observed['refusal_stderr'] = exc.stderr
    return {'name': name, 'files': files, 'profile': profile, 'brief': brief,
            'artifacts': artifacts, 'expected': observed}


def main():
    scratch = os.environ.get('MIR_NATIVE_TEST_SCRATCH')
    with tempfile.TemporaryDirectory(prefix='python-e6-', dir=scratch) as tmp:
        root = pathlib.Path(tmp)
        cases = [capture(root, name) for name in ['space repo', 'unicode-\u03bb-\ud55c']]
        env_repo = root / 'env'
        (env_repo / 'config').mkdir(parents=True)
        source = {'PATH': '/fixture/bin', 'HOME': '/fixture/home', 'API_TOKEN': 'hidden',
                  'EXTRA': 'explicit', 'CODEX_EVENTS_FILE': 'caller-events'}
        env_cases = []
        for config, force in [({}, False), ({}, True), ({'child_env_filter': True,
                              'child_env_extra_keys': ['EXTRA']}, False)]:
            (env_repo / 'config/mir-executor.local.json').write_text(json.dumps(config))
            env_cases.append({'config': config, 'force': force, 'source': source,
                              'expected': child_env(env_repo, source, filter_credentials=force)})
    pathlib.Path(__file__).with_name('executor_worktree.json').write_text(
        json.dumps({'cases': cases, 'env': env_cases}, indent=2, ensure_ascii=True) + '\n',
        encoding='utf-8')


if __name__ == '__main__':
    main()
