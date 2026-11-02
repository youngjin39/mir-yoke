"""Compare direct native execution with offline Python process/state oracles."""
from __future__ import annotations

import json
import os
import runpy
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / 'native/handoff-packet'
SUPPORT = runpy.run_path(str(ROOT / 'tests/fixtures/executor_execute_support.py'))
GOLDEN = json.loads((ROOT / 'tests/fixtures/executor_execute.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def binary():
    if shutil.which('cargo') is None:
        pytest.skip('cargo unavailable')
    command = ['cargo', 'build', '--release', '--locked', '--bin', 'executor-query']
    if os.environ.get('MIR_HANDOFF_CARGO_OFFLINE') == '1':
        command.append('--offline')
    subprocess.run(command, cwd=CRATE, check=True)
    target = Path(os.environ.get('CARGO_TARGET_DIR', 'target'))
    if not target.is_absolute():
        target = CRATE / target
    return target / 'release' / ('executor-query.exe' if os.name == 'nt' else 'executor-query')


@pytest.mark.parametrize('case', SUPPORT['CASES'])
def test_execute_fixture_matches_python(tmp_path, case):
    assert SUPPORT['run_case'](tmp_path / 'python home', case) == GOLDEN[case]


@pytest.mark.parametrize('case', SUPPORT['CASES'])
def test_execute_native_matches_python_fixture(binary, tmp_path, case):
    assert SUPPORT['run_case'](tmp_path / 'native home', case, binary) == GOLDEN[case]


@pytest.mark.parametrize('arguments', [
    ['execute', '--dispatch'], ['resume', '--job-id', 'fixture'],
    ['execute', '--unknown'], ['execute', '--backend', 'claude'],
])
def test_execute_declines_unsupported_command_before_effects(binary, tmp_path, arguments):
    root = tmp_path / 'decline home'
    launcher = SUPPORT['seed'](root, 'success')
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        "root = Path(__file__).resolve().parents[2]\n"
        'def pre_execute(*args):\n'
        "    (root / 'unexpected-pre-execute').touch()\n"
        'def writer_scope(*args):\n'
        "    (root / 'unexpected-writer-scope').touch()\n", encoding='utf-8')
    before = (root / 'tasks/tdd.json').read_bytes()
    completed = subprocess.run([str(binary), '--home-root', str(root), *arguments],
                               cwd=root, env=SUPPORT['environment'](root, 'success', launcher),
                               capture_output=True, timeout=45, check=False)
    assert (completed.stdout, completed.stderr, completed.returncode) == (b'', b'', 64)
    assert (root / 'tasks/tdd.json').read_bytes() == before
    assert not (root / 'tasks/jobs.db').exists()
    assert not (root / 'provider-started').exists()
    assert not (root / 'unexpected-pre-execute').exists()
    assert not (root / 'unexpected-writer-scope').exists()


def test_execute_declines_dynamic_local_options_before_effects(binary, tmp_path):
    root = tmp_path / 'dynamic options home'
    launcher = SUPPORT['seed'](root, 'success')
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        "root = Path(__file__).resolve().parents[2]\n"
        "(root / 'unexpected-import').touch()\n"
        'def register_execute_options(parser):\n'
        "    parser.add_argument('--project-review', action='store_true')\n"
        'def pre_execute(*args):\n'
        "    (root / 'unexpected-pre-execute').touch()\n"
        'def writer_scope(*args):\n'
        "    (root / 'unexpected-writer-scope').touch()\n", encoding='utf-8')
    before = (root / 'tasks/tdd.json').read_bytes()
    completed = subprocess.run([str(binary), '--home-root', str(root),
                                *SUPPORT['argv']('success')], cwd=root,
                               env=SUPPORT['environment'](root, 'success', launcher),
                               capture_output=True, timeout=45, check=False)
    assert (completed.stdout, completed.stderr, completed.returncode) == (b'', b'', 64)
    assert (root / 'tasks/tdd.json').read_bytes() == before
    for path in ('tasks/jobs.db', 'provider-started', 'unexpected-pre-execute',
                 'unexpected-writer-scope', 'unexpected-import'):
        assert not (root / path).exists()


@pytest.mark.parametrize(
    'effect', ['import_failure', 'dynamic_options', 'dispatch_change', 'root_redirect'],
)
def test_execute_effectful_local_failure_is_final(binary, tmp_path, effect):
    root = tmp_path / 'effectful home'
    launcher = SUPPORT['seed'](root, 'success')
    source = ('from pathlib import Path\n'
              "root = Path(__file__).resolve().parents[2]\n")
    if effect in ('import_failure', 'dynamic_options'):
        source += ("with (root / 'local-effects').open('a') as stream:\n"
                   "    stream.write('import\\n')\n"
                   )
        source += ("raise RuntimeError('offline import refusal')\n" if effect == 'import_failure'
                   else "globals()['register_' + 'execute_options'] = lambda parser: None\n")
    else:
        source += ('def pre_execute(args, repo_root):\n'
                   "    with (root / 'local-effects').open('a') as stream:\n"
                   "        stream.write('pre_execute\\n')\n")
        source += ("    args.dispatch = True\n" if effect == 'dispatch_change' else
                   "    args.repo_root = root / 'redirected-target'\n")
    (root / 'tools/mir_executor/local.py').write_text(source, encoding='utf-8')
    before = (root / 'tasks/tdd.json').read_bytes()
    completed = subprocess.run([str(binary), '--home-root', str(root),
                                *SUPPORT['argv']('success')], cwd=root,
                               env=SUPPORT['environment'](root, 'success', launcher),
                               capture_output=True, timeout=45, check=False)
    assert completed.returncode == 1, (completed.stdout, completed.stderr)
    assert completed.stderr
    assert completed.stdout == b''
    assert (root / 'local-effects').read_text().splitlines() == [
        'import' if effect in ('import_failure', 'dynamic_options') else 'pre_execute']
    assert (root / 'tasks/tdd.json').read_bytes() == before
    assert not (root / 'tasks/jobs.db').exists()
    assert not (root / 'provider-started').exists()


@pytest.mark.parametrize('case', ['cross_target', 'malformed_json', 'NaN', 'Infinity',
                                  '-Infinity', '1e400'])
def test_execute_declines_unsupported_root_or_ledger_before_import(binary, tmp_path, case):
    root = tmp_path / 'preflight home'
    launcher = SUPPORT['seed'](root, 'success')
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        "root = Path(__file__).resolve().parents[2]\n"
        "(root / 'unexpected-import').touch()\n", encoding='utf-8')
    ledger = root / 'tasks/tdd.json'
    arguments = SUPPORT['argv']('success')
    if case == 'cross_target':
        target = tmp_path / 'other target'
        target.mkdir()
        arguments += ['--repo-root', str(target)]
    elif case == 'malformed_json':
        ledger.write_text('{broken json', encoding='utf-8')
    else:
        original = ledger.read_text(encoding='utf-8')
        ledger.write_text(original.rstrip()[:-1] + ', "extended_number": ' + case + '}\n',
                          encoding='utf-8')
    before = ledger.read_bytes()
    completed = subprocess.run([str(binary), '--home-root', str(root), *arguments], cwd=root,
                               env=SUPPORT['environment'](root, 'success', launcher),
                               capture_output=True, timeout=45, check=False)
    assert (completed.stdout, completed.stderr, completed.returncode) == (b'', b'', 64)
    assert ledger.read_bytes() == before
    for path in ('unexpected-import', 'provider-started', 'tasks/jobs.db'):
        assert not (root / path).exists()


@pytest.mark.parametrize('implementation', ['python', 'native'])
def test_background_id_is_flushed_before_provider_completion(request, tmp_path, implementation):
    binary = request.getfixturevalue('binary') if implementation == 'native' else None
    root = tmp_path / 'background home'
    launcher = SUPPORT['seed'](root, 'background_success')
    command = ([str(binary), '--home-root', str(root)] if implementation == 'native' else
               [sys.executable, '-m', 'tools.mir_executor'])
    environment = SUPPORT['environment'](root, 'background_success', launcher)
    environment['EXECUTE_FIXTURE_GATE'] = '1'
    output = root / 'stdout'
    errors = root / 'stderr'
    with output.open('wb') as stdout, errors.open('wb') as stderr:
        process = subprocess.Popen(command + SUPPORT['argv']('background_success'), cwd=root,
                                   env=environment, stdout=stdout, stderr=stderr)
        try:
            deadline = time.monotonic() + 30
            while b'\n' not in output.read_bytes() and process.poll() is None:
                assert time.monotonic() < deadline, 'background job ID was not flushed'
                time.sleep(0.01)
            line = output.read_bytes().decode('utf-8').strip()
            assert line.startswith('[BACKGROUND] job_id='), errors.read_bytes()
            assert process.poll() is None, errors.read_bytes()
            connection = sqlite3.connect(root / 'tasks/jobs.db')
            try:
                assert connection.execute('SELECT job_id, status FROM jobs').fetchone() == (
                    line.split('=', 1)[1], 'running')
            finally:
                connection.close()
            (root / 'provider-release').write_text('release', encoding='utf-8')
            assert process.wait(timeout=45) == 0, errors.read_bytes()
        finally:
            (root / 'provider-release').touch()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    completed = subprocess.CompletedProcess(command, process.returncode,
                                            output.read_bytes(), errors.read_bytes())
    assert SUPPORT['snapshot'](root, launcher, completed) == GOLDEN['background_success']
