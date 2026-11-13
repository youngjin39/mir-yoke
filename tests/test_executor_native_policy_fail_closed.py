"""Python command admission must never bypass declared native policy."""
from __future__ import annotations

import json
import os
import runpy
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PARITY = runpy.run_path(str(ROOT / 'tests/test_executor_execute_native_parity.py'))
SUPPORT = PARITY['SUPPORT']
binary = PARITY['binary']
DIRECT = {case['name']: case['expected'] for case in json.loads(
    (ROOT / 'tests/fixtures/executor_direct.json').read_text(encoding='ascii'))['cases']}
SECTIONS = {
    'target_admission': {},
    'verifier_aliases': {'configuration_root': 'initial'},
    'agent_route': {'source': 'codex', 'criteria': 'declared', 'backend': 'policy',
                    'sandbox': 'read_only', 'invalid_lock': 'empty'},
    'hooks': {'executable': 'tools/hook-host', 'argv': [], 'sha256': '0' * 64,
              'hooks': ['writer_scope', 'on_job_event']},
}
POISON = ("from pathlib import Path\n"
          "root = Path(__file__).resolve().parents[2]\n"
          "(root / 'unexpected-import').touch()\n")


def declare(root, section):
    config = root / 'config/mir-executor.local.json'
    config.parent.mkdir(exist_ok=True)
    config.write_text(json.dumps({'native_policy': {'version': 1, section: SECTIONS[section]}}))


def seed(root):
    launcher = SUPPORT['seed'](root, 'success')
    environment = SUPPORT['environment'](root, 'success', launcher)
    environment['MIR_EXECUTOR_IMPL'] = 'python'
    environment['TMPDIR'] = str(root.parent)
    return environment


def arguments(command):
    if command == 'resume':
        return ['resume', '--job-id', 'saved']
    args = SUPPORT['argv']('success')
    return args + ({'execute': [], 'background': ['--background'],
                    'dispatch': ['--dispatch']}[command])


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode)
            for p in root.rglob('*') if p.is_file()
            and '.git' not in p.parts and '__pycache__' not in p.parts}


def invoke(root, environment, args):
    return subprocess.run([sys.executable, '-m', 'tools.mir_executor', *args], cwd=root,
                          env=environment, capture_output=True, timeout=45, check=False)


def assert_refusal(result, repository):
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert result.stdout == b''
    assert result.stderr == (
        f'[mir_executor] {repository} declares native_policy; '
        f'the native executor is required{os.linesep}').encode()


@pytest.mark.parametrize('section', SECTIONS)
@pytest.mark.parametrize('command', ['execute', 'background', 'dispatch', 'resume'])
@pytest.mark.parametrize('location', ['target', 'home'])
def test_python_policy_commands_refuse_before_any_effect(tmp_path, section, command, location):
    home = tmp_path / 'home'
    environment = seed(home)
    target = home
    if location == 'home':
        target = tmp_path / 'target'
        seed(target)
    declared = home if location == 'home' else target
    declare(declared, section)
    for root in {home, target}:
        (root / 'tools/mir_executor/local.py').write_text(POISON)
    before = snapshot(tmp_path)
    result = invoke(home, environment, arguments(command) + ['--repo-root', str(target)])
    assert_refusal(result, declared)
    assert snapshot(tmp_path) == before


def saved_job(home, target):
    from tools.mir_executor.jobs import JobRecord, JobRegistry

    brief = home / 'brief.json'
    brief.write_text('{"expanded_goal":"offline task"}')
    registry = JobRegistry(home / 'tasks/jobs.db')
    registry.insert(JobRecord(job_id='saved', change_id='fixture', category='unit',
                              repo_root=str(target), codex_args=['exec', 'offline task'],
                              family=None, timeout_seconds=60,
                              status='completed', started_at='2026-01-01T00:00:00Z',
                              dispatch_brief_path=str(brief)))
    registry.close()


@pytest.mark.parametrize('section', SECTIONS)
def test_resume_checks_saved_target_before_home_hooks_or_registry_writes(tmp_path, section):
    home, target = tmp_path / 'home', tmp_path / 'target'
    environment = seed(home)
    seed(target)
    declare(target, section)
    saved_job(home, target)
    for root in (home, target):
        (root / 'tools/mir_executor/local.py').write_text(POISON)
    database = home / 'tasks/jobs.db'
    database.chmod(0o640)  # Even reopening the writable registry is an effect.
    before = snapshot(tmp_path)
    result = invoke(home, environment, arguments('resume'))
    assert_refusal(result, target)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('section', SECTIONS)
@pytest.mark.parametrize('command', ['status', 'result', 'list-jobs', 'cancel', 'sweep', 'help'])
def test_commands_without_native_owned_hooks_remain_available(tmp_path, section, command):
    home = tmp_path / 'home'
    environment = seed(home)
    declare(home, section)
    saved_job(home, home)
    (home / 'tools/mir_executor/local.py').write_text(POISON)
    args = ['--help'] if command == 'help' else [command]
    if command in ('status', 'result', 'cancel'):
        args += ['--job-id', 'saved']
    result = invoke(home, environment, args)
    if command == 'sweep':
        # MIR_EXECUTOR_IMPL=python selects the retired Python sweep: refuse.
        assert result.returncode == 2, (result.stdout, result.stderr)
        assert b'Python sweep is retired' in result.stderr
    else:
        assert result.returncode == 0, (result.stdout, result.stderr)
    assert not (home / 'unexpected-import').exists()
    assert not (home / 'provider-started').exists()


@pytest.mark.parametrize('command', ['status', 'result', 'list-jobs', 'cancel', 'sweep'])
def test_cross_root_home_admission_is_guarded_even_for_queries(tmp_path, command):
    home, target = tmp_path / 'home', tmp_path / 'target'
    environment = seed(home)
    seed(target)
    declare(home, 'target_admission')
    (home / 'tools/mir_executor/local.py').write_text(POISON)
    args = [command, '--repo-root', str(target)]
    if command in ('status', 'result', 'cancel'):
        args += ['--job-id', 'saved']
    before = snapshot(tmp_path)
    result = invoke(home, environment, args)
    if command == 'sweep':
        assert result.returncode == 2 and b'Python sweep is retired' in result.stderr
    else:
        assert_refusal(result, home)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('value', [None, False, {}, {'version': 99}])
def test_declaration_presence_not_truthiness_is_the_boundary(tmp_path, value):
    home = tmp_path / 'home'
    environment = seed(home)
    config = home / 'config'
    config.mkdir()
    (config / 'mir-executor.local.json').write_text(json.dumps({'native_policy': value}))
    (home / 'tools/mir_executor/local.py').write_text(POISON)
    before = snapshot(tmp_path)
    assert_refusal(invoke(home, environment, arguments('execute')), home)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('content', [b'{"verifiers":', b'\xff', b'[1, 2]'])
@pytest.mark.parametrize('command', ['list-jobs', 'help'])
def test_unrelated_legacy_config_stays_lazy(binary, tmp_path, content, command):
    if command == 'list-jobs':
        home, _, environment = PARITY['pinned_home'](binary, tmp_path)
        environment['MIR_EXECUTOR_IMPL'] = 'python'
    else:
        home = tmp_path / 'home'
        environment = seed(home)
    config = home / 'config'
    config.mkdir()
    (config / 'mir-executor.local.json').write_bytes(content)
    args = ['--help'] if command == 'help' else [command]
    result = invoke(home, environment, args)
    assert result.returncode == 0, (result.stdout, result.stderr)


def test_parser_selected_native_target_is_guarded_before_its_import(tmp_path):
    home, target = tmp_path / 'home', tmp_path / 'selected'
    environment = seed(home)
    seed(target)
    declare(target, 'agent_route')
    (home / 'tools/mir_executor/local.py').write_text(
        'from pathlib import Path\n'
        'def register_execute_options(parser):\n'
        "    parser.add_argument('--selected-root', dest='repo_root', type=Path)\n")
    (target / 'tools/mir_executor/local.py').write_text(POISON)
    before = snapshot(tmp_path)
    assert_refusal(invoke(home, environment, arguments('execute') + [
        '--selected-root', str(target)]), target)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('case', ['unknown', 'help', 'dynamic_options', 'ledger', 'cross_root',
                                  'interpreter', 'resume_options', 'resume_parser',
                                  'resume_interpreter', 'resume_saved_root', 'resume_source_read',
                                  'non_utf8_provider', 'admission_value', 'receipt'])
def test_native_ownership_and_named_compatibility_refusals(binary, tmp_path, case):
    home, launcher, environment = PARITY['pinned_home'](binary, tmp_path)
    environment['TMPDIR'] = str(tmp_path)
    declare(home, 'agent_route')
    args = arguments('execute')
    source = (POISON + "with (root / 'import-count').open('a') as stream:\n"
              "    stream.write('import\\n')\n")
    if case == 'unknown':
        args += ['--unknown']
    elif case == 'help':
        args += ['--help']
    elif case in ('dynamic_options', 'resume_parser'):
        source += 'def register_execute_options(parser):\n    pass\n'
    elif case == 'ledger':
        ledger = home / 'tasks/tdd.json'
        ledger.write_text(ledger.read_text().replace('"planned"', 'NaN'))
    elif case == 'cross_root':
        target = tmp_path / 'target'
        seed(target)
        args += ['--repo-root', str(target)]
    elif case == 'admission_value':
        args += ['--timeout', 'not-an-integer']
    elif case == 'non_utf8_provider':
        if os.name == 'nt':
            pytest.skip('POSIX non-UTF8 environment')
        environment['CODEX_BIN'] = os.fsdecode(b'codex-\xff')
    elif case == 'receipt':
        if os.name == 'nt':
            pytest.skip('POSIX receipt wrapper')
        import hashlib

        receipt = tmp_path / 'unwritable-receipt'
        receipt.mkdir()
        environment['MIR_EXECUTOR_OWNED_RECEIPT'] = str(receipt)
        executable = home / '.mir/bin/executor-query'
        original = executable.with_name('current-native')
        executable.rename(original)
        executable.write_text('#!/bin/sh\n'
                              f'export MIR_EXECUTOR_OWNED_RECEIPT={shlex.quote(str(receipt))}\n'
                              f'exec {shlex.quote(str(original))} "$@"\n')
        executable.chmod(0o755)
        (executable.parent / 'executor-query.json').write_text(json.dumps({
            'path': '.mir/bin/executor-query',
            'sha256': hashlib.sha256(executable.read_bytes()).hexdigest()}))
    if case.startswith('resume_'):
        saved_job(home, home)
        args = arguments('resume')
        if case == 'resume_options':
            args += ['--unknown']
        elif case == 'resume_saved_root':
            # Use a real different root, so native declines before policy admission.
            target = tmp_path / 'target'
            seed(target)
            from tools.mir_executor.jobs import JobRegistry

            registry = JobRegistry(home / 'tasks/jobs.db')
            registry._conn.execute('UPDATE jobs SET repo_root = ?', (str(target),))
            registry._conn.commit()
            registry.close()
    if case in ('interpreter', 'resume_interpreter'):
        environment['MIR_EXECUTOR_PYTHON'] = str(tmp_path / 'missing-python')
        environment['PATH'] = ''
    local = home / 'tools/mir_executor/local.py'
    if case == 'resume_source_read':
        local.mkdir()
    else:
        local.write_text(source)
    before = snapshot(tmp_path)
    # Enabled invoking-home local.py is the named compatibility route. Its
    # Python policy guard must refuse before importing or mutating anything.
    result = invoke(home, environment, args)
    if case in ('unknown', 'admission_value', 'resume_options'):
        # Malformed arguments surface as argparse errors; nothing runs either way.
        assert result.returncode == 2, (result.stdout, result.stderr)
        assert b'error:' in result.stderr and b'native executor' not in result.stderr
    elif case == 'help':
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert result.stdout.startswith(b'usage: ')
    else:
        assert_refusal(result, home)
    assert snapshot(tmp_path) == before
    direct = subprocess.run([str(binary), '--home-root', str(home), *args], cwd=home,
                            env=environment, capture_output=True, timeout=45, check=False)
    owned = {'unknown', 'help', 'ledger', 'cross_root', 'interpreter',
             'non_utf8_provider', 'admission_value'}
    if case not in owned:
        assert (direct.returncode, direct.stdout, direct.stderr) == (64, b'', b'')
        assert snapshot(tmp_path) == before
        return
    if case in ('unknown', 'help', 'admission_value'):
        expected = DIRECT['invalid-timeout' if case == 'admission_value' else case]
        assert direct.returncode == expected['exit']
        for stream in ('stdout', 'stderr'):
            actual = SUPPORT['normalize'](getattr(direct, stream).decode(), home, launcher)
            frozen = bytes.fromhex(expected[stream + '_hex']).decode()
            if case == 'admission_value':
                frozen = frozen.replace("'bad'", "'not-an-integer'")
            assert actual == frozen
        assert snapshot(tmp_path) == before
        return
    changed = []
    if case in ('ledger', 'cross_root'):
        assert direct.returncode == 0 and direct.stderr == b''
        output = SUPPORT['normalize'](direct.stdout.decode(), home, launcher)
        expected = bytes.fromhex(DIRECT['success']['stdout_hex']).decode()
        if case == 'ledger':
            expected = expected.replace("previous_status='planned'", 'previous_status=nan')
        assert output == expected
        ledger = (target if case == 'cross_root' else home) / 'tasks/tdd.json'
        rendered = SUPPORT['normalize'](ledger.read_text(), home, launcher)
        assert rendered.encode().hex() == DIRECT['success']['storage']['tasks/tdd.json']['bytes']
        methods = (home / 'provider-methods').read_text().splitlines()
        assert methods == ['initialize', 'initialized', 'thread/start', 'turn/start']
        assert (home / 'provider-started').read_text() == 'started'
        changed += [ledger, home / 'provider-methods', home / 'provider-started']
    elif case == 'interpreter':
        message = os.strerror(2)
        if os.name == 'nt':
            import ctypes

            message = ctypes.FormatError(2).strip()
        assert (direct.returncode, direct.stdout, direct.stderr) == (
            1, b'', f'[mir_executor] local bridge I/O: {message} (os error 2)\n'.encode())
    else:
        assert (direct.returncode, direct.stdout, direct.stderr) == (
            1, b'', b"[mir_executor] FileNotFoundError: Codex binary not found: "
            b"'codex-\\udcff'. Set CODEX_BIN to the full path of the codex executable.\n")
    if case != 'interpreter':
        assert (home / 'unexpected-import').exists()
        assert (home / 'import-count').read_text() == 'import\n'
        changed += [home / 'unexpected-import', home / 'import-count']
    if case not in ('ledger', 'cross_root'):
        assert not (home / 'provider-started').exists()
    after = snapshot(tmp_path)
    for path in changed:
        key = str(path.relative_to(tmp_path))
        before.pop(key, None)
        after.pop(key, None)
    assert after == before


def test_native_admission_remains_final_and_keeps_uncovered_bridge_hooks(binary, tmp_path):
    home, _, environment = PARITY['pinned_home'](binary, tmp_path)
    environment['TMPDIR'] = str(tmp_path)
    declare(home, 'agent_route')
    (home / 'tools/mir_executor/local.py').write_text(
        'def pre_execute(args, root):\n'
        "    (root / 'bridge-served').write_text('native-admitted')\n")
    before = snapshot(tmp_path)
    assert_refusal(invoke(home, environment, arguments('execute')), home)
    assert snapshot(tmp_path) == before
    result = subprocess.run([str(binary), '--home-root', str(home), *arguments('execute')],
                            cwd=home, env=environment, capture_output=True, timeout=45,
                            check=False)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert (home / 'bridge-served').read_text() == 'native-admitted'
    assert (home / 'provider-started').exists()


@pytest.mark.parametrize('case', ['source_read', 'bridge_hello'])
def test_native_owned_failures_never_retry_python(binary, tmp_path, case):
    home, _, environment = PARITY['pinned_home'](binary, tmp_path)
    environment['TMPDIR'] = str(tmp_path)
    declare(home, 'agent_route')
    local = home / 'tools/mir_executor/local.py'
    if case == 'source_read':
        local.mkdir()
    else:
        if os.name == 'nt':
            pytest.skip('POSIX interpreter fixture')
        local.write_text(POISON)
        interpreter = tmp_path / 'no-hello'
        interpreter.write_text('#!/bin/sh\nexit 0\n')
        interpreter.chmod(0o755)
        environment['MIR_EXECUTOR_PYTHON'] = str(interpreter)
    before = snapshot(tmp_path)
    assert_refusal(invoke(home, environment, arguments('execute')), home)
    assert snapshot(tmp_path) == before
    result = subprocess.run([str(binary), '--home-root', str(home), *arguments('execute')],
                            cwd=home, env=environment, capture_output=True, timeout=45,
                            check=False)
    expected = 'local bridge protocol: unexpected end of frame'
    if case == 'source_read':
        with pytest.raises(OSError) as failure:
            local.read_bytes()
        error = failure.value
        number, message = error.errno, error.strerror
        if os.name == 'nt':
            import ctypes

            number = error.winerror
            message = ctypes.FormatError(number).strip()
        expected = (f'native local policy configuration error: {message} '
                    f'(os error {number})')
    assert (result.returncode, result.stdout, result.stderr) == (
        1, b'', f'[mir_executor] {expected}\n'.encode())
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('selector', ['MIR_EXECUTOR_IMPL', 'MIR_EXECUTOR_EXECUTE_IMPL',
                                     'MIR_EXECUTOR_DISPATCH_IMPL', 'MIR_NATIVE_HOOKS',
                                     'missing_pin', 'older_decline'])
def test_pinned_caller_fallbacks_refuse(binary, tmp_path, selector):
    home, _, environment = PARITY['pinned_home'](binary, tmp_path)
    environment['TMPDIR'] = str(tmp_path)
    declare(home, 'target_admission')
    (home / 'tools/mir_executor/local.py').write_text(POISON)
    if selector == 'missing_pin':
        (home / '.mir/bin/executor-query.json').unlink()
    elif selector == 'older_decline':
        # A protocol-compatible old binary that declines without a receipt.
        if os.name == 'nt':
            pytest.skip('POSIX executable fixture')
        import hashlib

        executable = home / '.mir/bin/executor-query'
        executable.write_text('#!/bin/sh\nexit 64\n')
        (executable.parent / 'executor-query.json').write_text(json.dumps({
            'path': '.mir/bin/executor-query',
            'sha256': hashlib.sha256(executable.read_bytes()).hexdigest()}))
    else:
        environment[selector] = '0' if selector == 'MIR_NATIVE_HOOKS' else 'python'
    before = snapshot(tmp_path)
    assert_refusal(invoke(home, environment, arguments('dispatch')), home)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('section', SECTIONS)
def test_malformed_arguments_report_argparse_errors_before_the_refusal(tmp_path, section):
    home = tmp_path / 'home'
    environment = seed(home)
    declare(home, section)
    (home / 'tools/mir_executor/local.py').write_text(POISON)
    before = snapshot(tmp_path)
    result = invoke(home, environment, ['execute', '--change-id', 'x', '--category', 'bogus'])
    assert result.returncode == 2, (result.stdout, result.stderr)
    diagnostic = result.stderr.decode()
    assert "argument --category: invalid choice: 'bogus'" in diagnostic
    assert 'native executor is required' not in diagnostic
    assert snapshot(tmp_path) == before
