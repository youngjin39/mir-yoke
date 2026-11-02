"""Generate normalized process-byte and durable-state oracles using the Python CLI.

Run with a caller-owned scratch directory; no provider, consumer, or memory DB is used.
Only paths, elapsed durations, generated IDs, UTC timestamps, and platform CRLF
line endings are normalized. Other bytes retain Python repr and JSON spelling.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent
CASES = ('success', 'error', 'timeout', 'async_success', 'background_success',
         'cancel_before_start', 'validate_brief_raises', 'provider_replacement', 'input_limit',
         'hook_order', 'missing_identity', 'partial_identity', 'unknown_change',
         'timeout_range', 'codex_args_file', 'input_file_limit', 'pre_execute_refusal',
         'ledger_revalidation')


def seed(root: Path, case: str):
    root.mkdir(parents=True)
    (root / 'offline-policy.json').write_text('{}\n', encoding='utf-8')
    subprocess.run(['git', 'init', '--quiet', str(root)], check=True, capture_output=True)
    package = root / 'tools/mir_executor'
    package.mkdir(parents=True)
    for source in (ROOT / 'tools/mir_executor').glob('*.py'):
        if source.name != 'local.py':
            shutil.copy2(source, package / source.name)
    tasks = root / 'tasks'
    tasks.mkdir()
    (tasks / 'tdd.json').write_text(json.dumps({'changes': [{
        'id': 'fixture', 'preserved': 'keep', 'categories': {'unit': {
            'status': 'planned', 'verifier': 'preserved-verifier', 'notes': 'initial'}}
    }]}, indent=2) + '\n', encoding='utf-8')
    shutil.copy2(FIXTURES / 'executor_execute_server.py', root / 'server.py')
    (root / 'prompt.txt').write_text('offline fixture', encoding='utf-8')
    if os.name == 'nt':
        launcher = root / 'fake-codex.cmd'
        launcher.write_text(f'@"{sys.executable}" "{root / "server.py"}" %*\n', encoding='utf-8')
    else:
        launcher = root / 'fake-codex'
        launcher.write_text('#!/usr/bin/env python3\n' +
                            (root / 'server.py').read_text(encoding='utf-8'), encoding='utf-8')
        launcher.chmod(0o755)
    if case in ('hook_order', 'pre_execute_refusal'):
        (package / 'local.py').write_text(
            'import json\n'
            'from contextlib import contextmanager\n'
            'from pathlib import Path\n'
            "root = Path(__file__).resolve().parents[2]\n"
            'def record(value):\n'
            "    with (root / 'hook-events').open('a', encoding='utf-8') as stream:\n"
            "        stream.write(json.dumps(value, sort_keys=True) + '\\n')\n"
            'def pre_execute(args, repo_root):\n'
            "    record('pre_execute')\n"
            '@contextmanager\n'
            'def writer_scope(repo_root):\n'
            "    record('writer_enter')\n"
            '    try:\n'
            '        yield\n'
            '    finally:\n'
            "        record('writer_exit')\n"
            'def after_provider_call(result, metadata):\n'
            "    assert metadata.pop('elapsed_seconds') >= 0\n"
            "    record({'after_provider_call': metadata})\n", encoding='utf-8')
        if case == 'pre_execute_refusal':
            local = package / 'local.py'
            local.write_text(local.read_text(encoding='utf-8').replace(
                "record('pre_execute')\n",
                "record('pre_execute')\n    raise ValueError('offline local refusal')\n"),
                encoding='utf-8')
    elif case == 'ledger_revalidation':
        (package / 'local.py').write_text(
            'import json\n'
            'from pathlib import Path\n'
            'def after_provider_call(result, metadata):\n'
            "    path = Path(__file__).resolve().parents[2] / 'tasks/tdd.json'\n"
            "    ledger = json.loads(path.read_text(encoding='utf-8'))\n"
            "    ledger['changes'][0]['categories']['unit']['status'] = 'not_applicable'\n"
            "    path.write_text(json.dumps(ledger, indent=2) + '\\n', encoding='utf-8')\n",
            encoding='utf-8')
    elif case == 'validate_brief_raises':
        (package / 'local.py').write_text(
            "def validate_brief(*args):\n    raise ValueError('unexpected brief validation')\n",
            encoding='utf-8')
    elif case == 'provider_replacement':
        (package / 'local.py').write_text(
            'from tools.mir_executor.executor import SubprocessResult\n'
            'def after_provider_call(result, metadata):\n'
            "    assert metadata['attempt'] == 1\n"
            "    assert metadata['model'] == 'offline-fixture'\n"
            "    return SubprocessResult(7, 'replacement output', 'budget exceeded', 0.0, "
            "['fixture-replacement'])\n", encoding='utf-8')
    elif case == 'cancel_before_start':
        (package / 'local.py').write_text(
            'from tools.mir_executor.jobs import JobRegistry\n'
            'def on_job_event(event, payload):\n'
            "    if event == 'job_inserted':\n"
            "        registry = JobRegistry(payload['jobs_db'])\n"
            "        registry.cancel(payload['job_id'])\n"
            '        registry.close()\n', encoding='utf-8')
    elif case in ('input_limit', 'input_file_limit', 'timeout_range'):
        (root / 'config').mkdir()
        (root / 'config/mir-executor.local.json').write_text(
            '{"timeout_seconds_range": [2, 5]}\n' if case == 'timeout_range' else
            '{"input_limit_bytes": 4}\n', encoding='utf-8')
    return launcher


def argv(case: str):
    result = ['execute', '--change-id', 'fixture', '--category', 'unit',
              '--codex-args', "exec 'offline fixture'"]
    if case == 'missing_identity':
        result = ['execute', '--codex-args', "exec 'offline fixture'"]
    elif case == 'partial_identity':
        result = ['execute', '--change-id', 'fixture', '--codex-args', "exec 'offline fixture'"]
    elif case == 'unknown_change':
        result[result.index('fixture')] = 'missing'
    if case in ('codex_args_file', 'input_file_limit'):
        result[-2:] = ['--codex-args-file', 'prompt.txt']
    if case in ('timeout', 'timeout_range'):
        result += ['--timeout', '1']
    if case == 'async_success':
        result += ['--async']
    if case in ('background_success', 'cancel_before_start'):
        result += ['--background']
    return result


def environment(root, case, launcher):
    return dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(root),
                MIR_EXECUTOR_QUERY_IMPL='python', MIR_EXECUTOR_EXECUTE_IMPL='python',
                MIR_SUB_AGENT_POLICY=str(root / 'offline-policy.json'),
                MIR_CODEX_MAIN='1', CODEX_BIN=str(launcher),
                EXECUTE_FIXTURE_ROOT=str(root),
                EXECUTE_FIXTURE_MODE='error' if case == 'error' else
                'timeout' if case == 'timeout' else 'success')


def normalize(value, root, launcher):
    # Replace repr-escaped Windows paths before ordinary raw paths.
    for old, new in ((repr(str(launcher))[1:-1], '<codex>'), (str(launcher), '<codex>'),
                     (repr(str(root))[1:-1], '<root>'), (str(root), '<root>')):
        value = value.replace(old, new)
    value = value.replace('\r\n', '\n')
    value = re.sub(r'duration=\d+\.\d+s', 'duration=<duration>s', value)
    return re.sub(r'(?<=\[BACKGROUND\] job_id=)[0-9a-f]{32}', '<job-id>', value)


def snapshot(root, launcher, completed):
    ledger = (root / 'tasks/tdd.json').read_text(encoding='utf-8')
    jobs = []
    database = root / 'tasks/jobs.db'
    if database.exists():
        connection = sqlite3.connect(database)
        try:
            connection.row_factory = sqlite3.Row
            for row in connection.execute('SELECT * FROM jobs ORDER BY job_id'):
                item = dict(row)
                for key in ('job_id', 'started_at', 'completed_at', 'duration_seconds'):
                    if item.get(key) is not None:
                        item[key] = {'job_id': '<job-id>', 'duration_seconds': '<duration>'}.get(
                            key, '<timestamp>')
                item['repo_root'] = '<root>'
                jobs.append(item)
        finally:
            connection.close()
    return {
        'stdout': normalize(completed.stdout.decode('utf-8'), root, launcher),
        'stderr': normalize(completed.stderr.decode('utf-8'), root, launcher),
        'code': completed.returncode,
        'ledger': normalize(ledger, root, launcher),
        'jobs': jobs,
        'provider_methods': (root / 'provider-methods').read_text(encoding='utf-8').splitlines()
        if (root / 'provider-methods').exists() else [],
        'hook_events': [json.loads(line) for line in
                        (root / 'hook-events').read_text(encoding='utf-8').splitlines()]
        if (root / 'hook-events').exists() else [],
    }


def run_case(root, case, binary=None):
    launcher = seed(root, case)
    command = ([str(binary), '--home-root', str(root)] if binary is not None else
               [sys.executable, '-m', 'tools.mir_executor'])
    completed = subprocess.run(command + argv(case), cwd=root,
                               env=environment(root, case, launcher),
                               capture_output=True, timeout=45, check=False)
    return snapshot(root, launcher, completed)


def generate(scratch):
    return {case: run_case(scratch / case, case) for case in CASES}


if __name__ == '__main__':
    print(json.dumps(generate(Path(sys.argv[1]).resolve()), indent=2, ensure_ascii=False))
