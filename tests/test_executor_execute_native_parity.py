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
TRACE = runpy.run_path(str(ROOT / "tests/support/executor_decline_trace.py"))
decline_trace = TRACE["decline_trace"]
trace_details = TRACE["trace_details"]
SUPPORT = runpy.run_path(str(ROOT / 'tests/fixtures/executor_execute_support.py'))
DISPATCH = runpy.run_path(str(ROOT / 'tests/fixtures/executor_dispatch_cli_support.py'))
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
    assert SUPPORT['run_case'](tmp_path / 'python home', case) == GOLDEN[case], trace_details()


@pytest.mark.parametrize('case', SUPPORT['CASES'])
def test_execute_native_matches_python_fixture(binary, tmp_path, case):
    assert SUPPORT['run_case'](tmp_path / 'native home', case, binary) == GOLDEN[case], (
        trace_details()
    )


@pytest.mark.parametrize('arguments', [
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
    assert (completed.stdout, completed.stderr, completed.returncode) == (b'', b'', 64), (
        trace_details()
    )
    assert (root / 'tasks/tdd.json').read_bytes() == before, trace_details()
    assert not (root / 'tasks/jobs.db').exists(), trace_details()
    assert not (root / 'provider-started').exists(), trace_details()
    assert not (root / 'unexpected-pre-execute').exists(), trace_details()
    assert not (root / 'unexpected-writer-scope').exists(), trace_details()


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
    assert (completed.stdout, completed.stderr, completed.returncode) == (b'', b'', 64), (
        trace_details()
    )
    assert (root / 'tasks/tdd.json').read_bytes() == before, trace_details()
    for path in ('tasks/jobs.db', 'provider-started', 'unexpected-pre-execute',
                 'unexpected-writer-scope', 'unexpected-import'):
        assert not (root / path).exists(), trace_details()


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
    assert completed.returncode == 1, ((completed.stdout, completed.stderr), trace_details())
    assert completed.stderr, trace_details()
    assert completed.stdout == b'', trace_details()
    assert (root / 'local-effects').read_text().splitlines() == [
        'import' if effect in ('import_failure', 'dynamic_options') else 'pre_execute'], (
        trace_details()
    )
    assert (root / 'tasks/tdd.json').read_bytes() == before, trace_details()
    assert not (root / 'tasks/jobs.db').exists(), trace_details()
    assert not (root / 'provider-started').exists(), trace_details()


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
    assert (completed.stdout, completed.stderr, completed.returncode) == (b'', b'', 64), (
        trace_details()
    )
    assert ledger.read_bytes() == before, trace_details()
    for path in ('unexpected-import', 'provider-started', 'tasks/jobs.db'):
        assert not (root / path).exists(), trace_details()


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
                assert time.monotonic() < deadline, (
                    ('background job ID was not flushed', trace_details())
                )
                time.sleep(0.01)
            line = output.read_bytes().decode('utf-8').strip()
            assert line.startswith('[BACKGROUND] job_id='), (errors.read_bytes(), trace_details())
            assert process.poll() is None, (errors.read_bytes(), trace_details())
            connection = sqlite3.connect(root / 'tasks/jobs.db')
            try:
                assert connection.execute('SELECT job_id, status FROM jobs').fetchone() == (
                    line.split('=', 1)[1], 'running'), trace_details()
            finally:
                connection.close()
            (root / 'provider-release').write_text('release', encoding='utf-8')
            assert process.wait(timeout=45) == 0, (errors.read_bytes(), trace_details())
        finally:
            (root / 'provider-release').touch()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    completed = subprocess.CompletedProcess(command, process.returncode,
                                            output.read_bytes(), errors.read_bytes())
    assert SUPPORT['snapshot'](root, launcher, completed) == GOLDEN['background_success'], (
        trace_details()
    )


def pinned_home(binary, tmp_path, case='success'):
    import hashlib

    root = tmp_path / 'pinned home'
    launcher = SUPPORT['seed'](root, case)
    destination = root / '.mir/bin' / binary.name
    destination.parent.mkdir(parents=True)
    shutil.copy2(binary, destination)
    (destination.parent / 'executor-query.json').write_text(json.dumps({
        'path': destination.relative_to(root).as_posix(),
        'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
    }), encoding='utf-8')
    environment = SUPPORT['environment'](root, case, launcher)
    for key in ('MIR_EXECUTOR_IMPL', 'MIR_EXECUTOR_QUERY_IMPL', 'MIR_EXECUTOR_EXECUTE_IMPL',
                'MIR_EXECUTOR_CANCEL_IMPL', 'MIR_EXECUTOR_DISPATCH_IMPL',
                'MIR_EXECUTOR_RESUME_IMPL', 'MIR_EXECUTOR_SWEEP_IMPL', 'MIR_NATIVE_HOOKS'):
        environment.pop(key, None)
    return root, launcher, environment


@pytest.mark.parametrize('case', ['success', 'claude_success', 'claude_invalid_timeout',
                                  'relative_artifacts',
                                  'gate_block', 'review_reject',
                                  'finalize_rollback', 'hook_failure',
                                  'current', 'legacy', 'changed_brief'])
def test_pinned_dispatch_and_resume_match_python(binary, tmp_path, case):
    import hashlib

    snapshots = []
    for implementation in ('python', 'native'):
        root = tmp_path / implementation
        _, environment, arguments = DISPATCH['seed'](root, case, SUPPORT)
        if case in ('current', 'legacy', 'changed_brief'):
            arguments = DISPATCH['resume'](root, case)
        destination = root / '.mir/bin' / binary.name
        destination.parent.mkdir(parents=True)
        shutil.copy2(binary, destination)
        (destination.parent / 'executor-query.json').write_text(json.dumps({
            'path': destination.relative_to(root).as_posix(),
            'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
        }), encoding='utf-8')
        for selector in ('MIR_EXECUTOR_IMPL', 'MIR_EXECUTOR_DISPATCH_IMPL',
                         'MIR_EXECUTOR_RESUME_IMPL', 'MIR_NATIVE_HOOKS'):
            environment.pop(selector, None)
        if implementation == 'python':
            environment['MIR_EXECUTOR_IMPL'] = 'python'
        elif case == 'changed_brief':
            (root / 'tools/mir_executor/cli.py').write_text(
                "raise RuntimeError('unexpected Python resume fallback')\n", encoding='utf-8')
        result = invoke_pinned(root, environment, arguments, capture_output=True)
        snapshots.append(DISPATCH['snapshot'](root, result))
        if case != 'changed_brief':
            assert (root / 'native-owned').exists() == (implementation == 'native'), (
                (result.stderr, trace_details())
            )
        if case in ('success', 'claude_success'):
            assert result.returncode == 0, (result.stderr, trace_details())
            assert (root / 'code.txt').read_text() == 'delegated change\n', trace_details()
        if case == 'finalize_rollback':
            assert result.returncode == 1, (result.stderr, trace_details())
            assert (root / 'code.txt').read_text() == 'initial\n', trace_details()
        if case == 'claude_invalid_timeout':
            assert result.returncode == 1, (result.stderr, trace_details())
            assert not (root / 'provider-methods').exists(), trace_details()
            assert not (root / 'artifacts').exists(), trace_details()
        if case == 'review_reject':
            assert result.returncode == 1, (result.stderr, trace_details())
            assert b'offline rejection' in result.stdout, trace_details()
            assert (root / 'code.txt').read_text() == 'initial\n', trace_details()
            assert snapshots[-1]['provider_methods'].count('thread/start') == 2, trace_details()
        if case == 'hook_failure':
            assert result.returncode == 1, (result.stderr, trace_details())
            events = [json.loads(line)[0] for line in
                      (root / 'hook-events').read_text().splitlines()]
            assert events.count('dispatch_failed') == 1, trace_details()
            assert (root / 'code.txt').read_text() == 'initial\n', trace_details()
            connection = sqlite3.connect(root / 'tasks/jobs.db')
            try:
                assert connection.execute('SELECT status,stderr FROM jobs').fetchall() == [
                    ('failed', 'offline after_run failure')], trace_details()
            finally:
                connection.close()
    assert snapshots[0] == snapshots[1], trace_details()


def invoke_pinned(root, environment, arguments, **kwargs):
    return subprocess.run([sys.executable, '-m', 'tools.mir_executor', *arguments],
                          cwd=root, env=environment, timeout=60, check=False,
                          **kwargs)


def test_dispatch_failed_receipt_declines_before_local_import(binary, tmp_path):
    root = tmp_path / 'receipt-home'
    _, environment, arguments = DISPATCH['seed'](root, 'success', SUPPORT)
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        "(Path(__file__).resolve().parents[2] / 'native-imported').touch()\n",
        encoding='utf-8')
    receipt = tmp_path / 'unwritable-receipt'
    receipt.mkdir()
    environment['MIR_EXECUTOR_OWNED_RECEIPT'] = str(receipt)
    result = subprocess.run([str(binary), '--home-root', str(root), *arguments],
                            cwd=root, env=environment, capture_output=True, timeout=60)
    assert (result.returncode, result.stdout, result.stderr) == (64, b'', b''), trace_details()
    for path in ('native-imported', 'hook-events', 'provider-methods', 'tasks/jobs.db'):
        assert not (root / path).exists(), trace_details()
    assert (root / 'code.txt').read_text() == 'initial\n', trace_details()


@pytest.mark.parametrize('case', SUPPORT['CASES'])
def test_pinned_execute_matches_fixture(binary, tmp_path, case):
    root, launcher, environment = pinned_home(binary, tmp_path, case)
    completed = invoke_pinned(root, environment, SUPPORT['argv'](case), capture_output=True)
    assert SUPPORT['snapshot'](root, launcher, completed) == GOLDEN[case], trace_details()


@pytest.mark.parametrize('selector', [None, 'MIR_EXECUTOR_IMPL', 'MIR_EXECUTOR_EXECUTE_IMPL',
                                      'MIR_NATIVE_HOOKS'])
def test_pinned_execute_routes_before_python_import(binary, tmp_path, selector):
    root, _, environment = pinned_home(binary, tmp_path)
    (root / 'tools/mir_executor/cli.py').write_text(
        "raise RuntimeError('python route selected')\n", encoding='utf-8')
    if selector:
        environment[selector] = '0' if selector == 'MIR_NATIVE_HOOKS' else 'python'
    result = invoke_pinned(root, environment, SUPPORT['argv']('success'), capture_output=True)
    assert result.returncode == (1 if selector else 0), (result.stderr, trace_details())
    assert (b'python route selected' in result.stderr) == bool(selector), trace_details()
    assert (root / 'provider-started').exists() == (selector is None), trace_details()


def test_pinned_execute_declines_dynamic_options(binary, tmp_path):
    root, _, environment = pinned_home(binary, tmp_path)
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        "root = Path(__file__).resolve().parents[2]\n"
        'def register_execute_options(parser):\n'
        "    parser.add_argument('--project-route')\n"
        'def pre_execute(args, root):\n'
        "    assert args.project_route == 'offline'\n"
        "    (root / 'python-route').touch()\n", encoding='utf-8')
    result = invoke_pinned(root, environment,
                           SUPPORT['argv']('success') + ['--project-route', 'offline'],
                           capture_output=True)
    assert result.returncode == 0, (result.stderr, trace_details())
    assert (root / 'python-route').exists(), trace_details()


@pytest.fixture(scope='module')
def older_binary(tmp_path_factory):
    directory = tmp_path_factory.mktemp('older-binary')
    source = directory / 'older.rs'
    source.write_text('fn main() { std::process::exit(64); }', encoding='utf-8')
    binary = directory / ('executor-query.exe' if os.name == 'nt' else 'executor-query')
    subprocess.run(['rustc', str(source), '-o', str(binary)], check=True)
    return binary


@pytest.mark.parametrize('command', ['execute', 'cancel', 'dispatch', 'resume', 'sweep'])
def test_pinned_older_binary_declines_to_python(older_binary, tmp_path, command):
    root, launcher, environment = pinned_home(older_binary, tmp_path)
    arguments = {'execute': SUPPORT['argv']('success'),
                 'dispatch': ['execute', '--dispatch'],
                 'cancel': ['cancel', '--job-id', 'missing'],
                 'resume': ['resume', '--job-id', 'missing'],
                 'sweep': ['sweep', '--repo-root', str(root)]}[command]
    result = invoke_pinned(root, environment, arguments, capture_output=True)
    if command == 'execute':
        assert SUPPORT['snapshot'](root, launcher, result) == GOLDEN['success'], trace_details()
        assert (root / 'provider-started').exists(), trace_details()
    else:
        reference_environment = dict(environment, MIR_EXECUTOR_IMPL='python')
        reference = invoke_pinned(root, reference_environment, arguments, capture_output=True)
        assert (result.returncode, result.stdout, result.stderr) == (
            reference.returncode, reference.stdout, reference.stderr), trace_details()


@pytest.mark.parametrize('command', ['execute', 'cancel'])
@pytest.mark.parametrize('writable', [True, False])
def test_native_owned_receipt_precedes_effects(binary, tmp_path, command, writable):
    root, _, environment = pinned_home(binary, tmp_path)
    if command == 'execute':
        (root / 'tools/mir_executor/local.py').write_text(
            'from pathlib import Path\n'
            "(Path(__file__).resolve().parents[2] / 'hook-imported').touch()\n",
            encoding='utf-8')
    receipt = tmp_path / 'receipt'
    if not writable:
        receipt.mkdir()
    environment['MIR_EXECUTOR_OWNED_RECEIPT'] = str(receipt)
    arguments = (SUPPORT['argv']('success') if command == 'execute'
                 else ['cancel', '--job-id', 'missing'])
    result = subprocess.run([str(binary), '--home-root', str(root), *arguments],
                            cwd=root, env=environment, capture_output=True, timeout=60)
    if writable:
        assert receipt.read_bytes() == b'owned', trace_details()
        assert result.returncode != 64, trace_details()
    else:
        assert (result.returncode, result.stdout, result.stderr) == (64, b'', b''), trace_details()
        assert not (root / 'provider-started').exists(), trace_details()
        assert not (root / 'tasks/jobs.db').exists(), trace_details()
        assert not (root / 'hook-imported').exists(), trace_details()


@pytest.mark.parametrize('code', [7, 64])
def test_pinned_execute_owned_failure_never_retries(binary, tmp_path, code):
    root, _, environment = pinned_home(binary, tmp_path)
    (root / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        "root = Path(__file__).resolve().parents[2]\n"
        'def pre_execute(args, repo_root):\n'
        "    with (root / 'effects').open('a') as stream:\n"
        "        stream.write('once\\n')\n"
        'def after_provider_call(result, metadata):\n'
        f'    result.exit_code = {code}\n'
        '    return result\n', encoding='utf-8')
    result = invoke_pinned(root, environment, SUPPORT['argv']('success'), capture_output=True)
    assert result.returncode == code, (result.stderr, trace_details())
    assert b'[RESULT]' in result.stdout, trace_details()
    assert (root / 'effects').read_text().splitlines() == ['once'], trace_details()


def test_pinned_execute_ordered_live_streams(binary, tmp_path):
    root, _, environment = pinned_home(binary, tmp_path)
    (root / 'tools/mir_executor/local.py').write_text(
        'import os\n'
        'def pre_execute(args, root):\n'
        "    os.write(2, b'first\\n')\n"
        "    os.write(2, b'second\\n')\n"
        "    os.write(2, b'third\\n')\n",
        encoding='utf-8')
    environment['EXECUTE_FIXTURE_GATE'] = '1'
    output = root / 'combined-output'
    with output.open('wb') as stream:
        process = subprocess.Popen([sys.executable, '-m', 'tools.mir_executor',
                                    *SUPPORT['argv']('background_success')], cwd=root,
                                   env=environment, stdin=subprocess.PIPE,
                                   stdout=stream, stderr=stream)
        try:
            deadline = time.monotonic() + 30
            while b'[BACKGROUND]' not in output.read_bytes():
                assert process.poll() is None, (output.read_bytes(), trace_details())
                assert time.monotonic() < deadline, (
                    ('output buffered until completion', trace_details())
                )
                time.sleep(0.02)
            assert output.read_bytes().startswith(b'first\nsecond\nthird\n'), trace_details()
            (root / 'provider-release').touch()
            assert process.wait(timeout=45) == 0, trace_details()
        finally:
            (root / 'provider-release').touch()
            process.stdin.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX process signals; Windows cleanup unit tested')
@pytest.mark.parametrize('number', [2, 15])
@pytest.mark.parametrize('implementation', ['native', 'python'])
def test_pinned_execute_interrupt_preserves_python_job_state(
    binary, tmp_path, number, implementation,
):
    root, _, environment = pinned_home(binary, tmp_path, 'background_success')
    if implementation == 'python':
        environment['MIR_EXECUTOR_IMPL'] = 'python'
    environment['EXECUTE_FIXTURE_GATE'] = '1'
    output = root / 'interrupted-output'
    with output.open('wb') as stream:
        process = subprocess.Popen([sys.executable, '-m', 'tools.mir_executor',
                                    *SUPPORT['argv']('background_success')], cwd=root,
                                   env=environment, stdout=stream, stderr=stream,
                                   start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while not (root / 'provider-started').exists():
                assert process.poll() is None, (output.read_bytes(), trace_details())
                assert time.monotonic() < deadline, ('provider did not start', trace_details())
                time.sleep(0.02)
            # Target the entrypoint alone: it must forward to its native child.
            process.send_signal(number)
            time.sleep(0.2)
            (root / 'provider-release').touch()
            code = process.wait(timeout=45)
            assert code in (128 + number, -number), (output.read_bytes(), trace_details())
        finally:
            (root / 'provider-release').touch()
            try:
                os.killpg(process.pid, 9)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
    connection = sqlite3.connect(root / 'tasks/jobs.db')
    try:
        assert connection.execute('SELECT status, exit_code FROM jobs').fetchall() == [
            ('running', None)], trace_details()
    finally:
        connection.close()
    assert json.loads((root / 'tasks/tdd.json').read_text())['changes'][0]['categories'][
        'unit']['status'] == 'planned', trace_details()


def test_pinned_entrypoint_passes_binary_stdin_without_buffering(binary, tmp_path):
    root, _, environment = pinned_home(binary, tmp_path)
    # The native execute command does not consume stdin. Adapt only the child
    # executable to a portable byte echo, preserving all Popen descriptor options.
    (root / 'sitecustomize.py').write_text(
        'import subprocess, sys\n'
        'original = subprocess.Popen\n'
        'def echo(command, **kwargs):\n'
        "    assert command[0].endswith(('executor-query', 'executor-query.exe'))\n"
        '    return original([sys.executable, "-c", '
        '"import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"], **kwargs)\n'
        'subprocess.Popen = echo\n', encoding='utf-8')
    payload = b'first\x00\xff\nsecond\r\n'
    result = invoke_pinned(root, environment, SUPPORT['argv']('success'),
                           input=payload, capture_output=True)
    assert result.returncode == 0, (result.stderr, trace_details())
    assert result.stdout == payload, trace_details()
    assert not (root / 'provider-started').exists(), trace_details()


@pytest.mark.parametrize('guard', ['hash', 'pin', 'link', 'encoding'])
@pytest.mark.parametrize('command', ['execute', 'cancel'])
def test_pinned_mutation_routes_keep_admission_guards(binary, tmp_path, guard, command):
    root, _, environment = pinned_home(binary, tmp_path)
    (root / 'tools/mir_executor/cli.py').write_text(
        "raise RuntimeError('python guard fallback')\n", encoding='utf-8')
    destination = root / '.mir/bin' / binary.name
    if guard == 'hash':
        destination.write_bytes(b'changed')
    elif guard == 'pin':
        (destination.parent / 'executor-query.json').write_text('{}', encoding='utf-8')
    elif guard == 'link':
        original = destination.with_name('original')
        destination.rename(original)
        try:
            destination.symlink_to(original)
        except OSError:
            pytest.skip('symlink privilege unavailable')
    elif guard == 'encoding':
        environment['PYTHONIOENCODING'] = 'ascii'
    arguments = SUPPORT['argv']('success') if command == 'execute' else [
        'cancel', '--job-id', 'missing']
    result = invoke_pinned(root, environment, arguments, capture_output=True)
    assert result.returncode == 1, trace_details()
    assert b'python guard fallback' in result.stderr, trace_details()
    assert not (root / 'provider-started').exists(), trace_details()


@pytest.mark.parametrize('dynamic', [False, True])
def test_dispatch_missing_agent_matches_python_fallback_route(binary, tmp_path, dynamic):
    root = tmp_path / 'agent-route-home'
    _, environment, arguments = DISPATCH['seed'](root, 'success', SUPPORT)
    receipt = root / 'ownership'
    environment['MIR_EXECUTOR_OWNED_RECEIPT'] = str(receipt)
    if dynamic:
        with (root / 'tools/mir_executor/local.py').open('a', encoding='utf-8') as stream:
            stream.write("\ndef validate_brief(*args):\n"
                         "    return {'target_agent': 'offline-agent'}\n")
    else:
        (root / 'brief.json').write_text(
            '{"expanded_goal":"offline fixture","target_agent":"offline-agent"}',
            encoding='utf-8')
    result = subprocess.run([str(binary), '--home-root', str(root), *arguments],
                            cwd=root, env=environment, capture_output=True, timeout=60)
    assert result.returncode == 0, (result.stderr, trace_details())
    assert receipt.read_bytes() == b'owned', trace_details()
    assert b'no definition for target agent' in result.stderr, trace_details()
    assert (root / 'tasks/jobs.db').exists(), trace_details()
    assert (root / 'provider-methods').exists(), trace_details()
