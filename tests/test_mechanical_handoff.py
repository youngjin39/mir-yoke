"""Offline contracts for stateless common mechanical handoff hooks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import locale
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'plugins/mir-lifecycle-hooks/skills/runtime-continuity'
HANDLER = SKILL / 'scripts/handoff_packet.py'
HANDLER_PYTHON = os.environ.get('MIR_HANDOFF_TEST_PYTHON', sys.executable)
PROMPT = (
    'Write a handoff for another agent.\n'
    'Sources: src/example.py\n'
    'May: read src/example.py; report findings\n'
    'May not: edit files; run tests\n'
    'Exclude: PRIVATE-CANARY-42\n'
)
PINS = 'handoff pins:\n' + json.dumps({
    'repository_root': '/example', 'head': 'a' * 40,
    'mapping_path': '.mir/ontology-map.json', 'mapping_version': '1.1.0',
    'mapping_sha256': 'b' * 64, 'contract_id': 'mir.common-semantics',
    'contract_version': '1.1.0', 'contract_sha256': 'c' * 64,
    'sources': [{'path': 'src/example.py', 'revision': 'd' * 40, 'sha256': 'e' * 64}],
    'observed_at': '2026-10-22T01:02:03Z', 'unknowns': [],
    'pin_inventory': [],
}, indent=2)


def module():
    spec = importlib.util.spec_from_file_location('handoff_packet', HANDLER)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.mark.parametrize('invalid', [False, True])
def test_should_decode_pin_runner_output_as_utf8_with_cp949_locale(
        tmp_path, monkeypatch, invalid):
    hook = module()
    monkeypatch.setattr(hook, 'repository_root', lambda event: tmp_path)
    monkeypatch.setattr(locale, 'getpreferredencoding', lambda *args: 'cp949')
    monkeypatch.setattr(locale, 'getencoding', lambda: 'cp949', raising=False)
    monkeypatch.setenv('PYTHONUTF8', '0')
    monkeypatch.setenv('PYTHONIOENCODING', 'cp949')
    # Write bytes so the child's output is independent of its own locale and stdio encoding.
    output = 'handoff pins:\n{"path": "\ud55c\uae00'.encode()
    output += (b'\xff' if invalid else b'') + b'"}\n'
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts/mir_ontology.py').write_text(
        'import sys\n'
        f'sys.stdout.buffer.write({output!r})\n'
        "sys.stderr.buffer.write(b'\\xff')\n",
        encoding='utf-8',
    )
    pins = hook.run_pins({}, {'excluded': []}, paths=[])
    expected = '\ud55c\uae00' + ('\ufffd' if invalid else '')
    assert json.loads(pins.split('\n', 1)[1]) == {'path': expected}


def test_should_read_bounded_transcript_tail_on_windows_without_posix_flags(tmp_path, monkeypatch):
    hook = module()
    monkeypatch.setattr(hook, '_WINDOWS', True, raising=False)
    monkeypatch.delattr(os, 'O_NOFOLLOW', raising=False)
    monkeypatch.delattr(os, 'O_NONBLOCK', raising=False)
    monkeypatch.setattr(hook, 'LIMIT', 32)
    transcript = tmp_path / 'session.jsonl'
    transcript.write_bytes(b'{"discard": "' + b'x' * 64 + b'"}\n{"keep": 1}\n')
    assert hook.transcript_records({'transcript_path': str(transcript)}) == [{'keep': 1}]


@pytest.mark.parametrize('mode,attributes', [
    (stat.S_IFLNK, 0), (stat.S_IFREG, stat.FILE_ATTRIBUTE_REPARSE_POINT), (stat.S_IFDIR, 0),
])
def test_should_refuse_windows_transcript_links_and_non_files_before_open(
        tmp_path, monkeypatch, mode, attributes):
    hook = module()
    monkeypatch.setattr(hook, '_WINDOWS', True, raising=False)
    monkeypatch.setattr(Path, 'lstat', lambda path: SimpleNamespace(
        st_mode=mode, st_file_attributes=attributes))

    def forbidden_open(*args, **kwargs):
        pytest.fail('unsafe transcript must be refused before opening')

    monkeypatch.setattr(os, 'open', forbidden_open)
    monkeypatch.setattr(Path, 'open', forbidden_open)
    with pytest.raises(ValueError):
        hook.transcript_records({'transcript_path': str(tmp_path / 'session.jsonl')})


@pytest.mark.parametrize('field', ['st_dev', 'st_ino'])
def test_should_refuse_windows_transcript_identity_change_and_close_fd(
    tmp_path, monkeypatch, field,
):
    hook = module()
    monkeypatch.setattr(hook, '_WINDOWS', True, raising=False)
    transcript = tmp_path / 'session.jsonl'
    transcript.write_text('{}\n')
    original = os.fstat
    descriptors = []

    def replaced_file(fd):
        descriptors.append(fd)
        observed = original(fd)
        values = {key: getattr(observed, key) for key in ('st_mode', 'st_dev', 'st_ino')}
        values[field] += 1
        return SimpleNamespace(**values)

    monkeypatch.setattr(os, 'fstat', replaced_file)
    with pytest.raises(ValueError, match='transcript.*changed'):
        hook.transcript_records({'transcript_path': str(transcript)})
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        original(descriptors[0])


@pytest.mark.parametrize('taskkill_result', ['success', 'failure', 'missing', 'timeout'])
@pytest.mark.parametrize('drain_timeout', [False, True])
def test_should_kill_windows_pin_runner_tree_and_bound_cleanup(
        tmp_path, monkeypatch, taskkill_result, drain_timeout):
    hook = module()
    monkeypatch.setattr(hook, '_WINDOWS', True, raising=False)
    monkeypatch.setattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 512, raising=False)
    monkeypatch.setenv('SystemRoot', str(tmp_path / 'Windows root'))
    monkeypatch.setattr(hook, 'repository_root', lambda event: tmp_path)
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts/mir_ontology.py').write_text('')
    calls = []

    class Process:
        pid = 1234

        def communicate(self, timeout=None):
            calls.append(('communicate', timeout))
            assert timeout is not None, 'cleanup must have a finite timeout'
            if timeout == 0.1 or drain_timeout:
                raise subprocess.TimeoutExpired('runner', timeout)
            return '', ''

        def kill(self):
            calls.append('kill')

        def wait(self, timeout=None):
            calls.append(('wait', timeout))
            assert timeout is not None
            raise subprocess.TimeoutExpired('runner', timeout)

    def popen(argv, **kwargs):
        calls.append(('popen', argv, kwargs))
        return Process()

    def taskkill(argv, **kwargs):
        calls.append(('taskkill', argv, kwargs))
        if taskkill_result == 'missing':
            raise OSError('taskkill unavailable')
        if taskkill_result == 'timeout':
            raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
        return SimpleNamespace(returncode=int(taskkill_result == 'failure'))

    monkeypatch.setattr(subprocess, 'Popen', popen)
    monkeypatch.setattr(subprocess, 'run', taskkill)
    monkeypatch.setattr(os, 'killpg', lambda *args: pytest.fail('POSIX killpg on Windows'),
                        raising=False)
    with pytest.raises(ValueError, match='pin runner timed out'):
        hook.run_pins({}, {'excluded': []}, paths=[], timeout=0.1)
    _, argv, options = calls[0]
    runner = str(tmp_path / 'scripts/mir_ontology.py')
    assert argv == [sys.executable, runner, 'mapping', '--handoff']
    assert options['creationflags'] == subprocess.CREATE_NEW_PROCESS_GROUP
    assert not options.get('start_new_session', False)
    _, argv, options = next(call for call in calls if call[0] == 'taskkill')
    assert argv == [str(tmp_path / 'Windows root/System32/taskkill.exe'),
                    '/T', '/F', '/PID', '1234']
    assert not options.get('shell', False)
    assert 0 < options['timeout'] <= 1
    assert calls.index('kill') > next(i for i, call in enumerate(calls) if call[0] == 'taskkill')
    assert ('communicate', 1) in calls
    if drain_timeout:
        assert ('wait', 1) in calls


@pytest.mark.skipif(sys.platform != 'win32', reason='requires native Windows filesystem')
def test_should_read_native_windows_transcript_and_refuse_symlink(tmp_path):
    hook = module()
    transcript = tmp_path / 'session.jsonl'
    transcript.write_bytes(b'{"keep": 1}\n')
    assert hook.transcript_records({'transcript_path': str(transcript)}) == [{'keep': 1}]
    link = tmp_path / 'link.jsonl'
    try:
        link.symlink_to(transcript)
    except OSError as exc:
        pytest.skip('Windows symlink creation unavailable: ' + str(exc))
    with pytest.raises(ValueError):
        hook.transcript_records({'transcript_path': str(link)})


@pytest.mark.skipif(sys.platform != 'win32', reason='requires native Windows process tree')
def test_should_kill_native_windows_pin_runner_child(tmp_path):
    import ctypes
    from ctypes import wintypes

    hook = module()
    (tmp_path / '.git').mkdir()
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts/mir_ontology.py').write_text(
        'import subprocess, sys, time\n'
        'from pathlib import Path\n'
        'child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n'
        'Path("child.pid").write_text(str(child.pid))\n'
        'time.sleep(60)\n')
    with pytest.raises(ValueError, match='pin runner timed out'):
        hook.run_pins({'cwd': str(tmp_path)}, {'excluded': []}, paths=[], timeout=2)
    pid = int((tmp_path / 'child.pid').read_text())
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        assert ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: process is gone
        return
    try:
        status = kernel.WaitForSingleObject(handle, 0)
        if status != 0:
            subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/taskkill.exe'),
                            '/T', '/F', '/PID', str(pid)], timeout=2, check=False)
        assert status == 0  # WAIT_OBJECT_0: the child exited, including inherited pipe handles
    finally:
        kernel.CloseHandle(handle)


PIN_NAMES = ['repository_root', 'head', 'mapping.identity', 'mapping.version',
             'mapping.digest', 'contract.identity', 'contract.version', 'contract.digest',
             'sources[0].digest', 'sources[0].revision']
SELF_CHECK = '; '.join(
    ['field ' + name + '=present' for name in ['qualified target', 'lifecycle', 'temporal',
     'epistemic', 'verification', 'evidence', 'unknowns', 'may', 'may not']]
    + ['pin ' + name + '=parent-supplied' for name in PIN_NAMES])


def packet(pins=PINS):
    return (
        'Qualified target: example:review\n'
        'Prompt SHA256: ' + hashlib.sha256(PROMPT.encode()).hexdigest() + '\n'
        'Lifecycle: review\nTemporal: current\nEpistemic: parent-supplied\n'
        'Verification: unchecked\n'
        + pins + '\n'
        'Evidence: parent-supplied prompt; observed 2026-10-22T01:02:03Z\n'
        'Unknowns: recipient verification pending\n'
        'May: read src/example.py; report findings\n'
        'May not: edit files; run tests\n'
        'Self-check: ' + SELF_CHECK + '\n'
    )


@pytest.mark.parametrize(('prompt', 'expected'), [
    (PROMPT, True),
    ('Prepare a brief for the next agent.', True),
    ('Delegate this review to a worker agent.', True),
    ('\ub2e4\ub978 \uc5d0\uc774\uc804\ud2b8\uc5d0\uac8c \uc804\ub2ec\ud560 '
     '\ud578\ub4dc\uc624\ud504\ub97c \uc791\uc131\ud574 \uc8fc\uc138\uc694.', True),
    ('\uc774 \uc791\uc5c5\uc744 \ub2e4\ub978 \uc5d0\uc774\uc804\ud2b8\uc5d0\uac8c '
     '\ub118\uae38 \uc9c0\uc2dc\ubb38\uc744 \uc791\uc131\ud574\uc918.', True),
    ('\ud558\uc704 \uc5d0\uc774\uc804\ud2b8\uc5d0\uac8c \ub9e1\uae38 \uc778\uacc4'
     '\ubb38\uc744 \uc368\uc918.', True),
    ('\ub2e4\ub978 \uc5d0\uc774\uc804\ud2b8\uac00 \uc791\uc131\ud55c \uc9c0\uc2dc'
     '\ubb38\uc744 \uac80\ud1a0\ud574\uc918.', False),
    ('\ud558\uc704 \uc5d0\uc774\uc804\ud2b8\ub294 \ub744\uc6b0\uc9c0 \ub9d0\uace0 '
     '\ud30c\uc77c\uc744 \uc218\uc815\ud558\uc9c0 \ub9d0\uace0 \ub2f5\ubcc0\ub9cc '
     '\ud574\uc918.', False),
    ('\ud6c4\uc18d \uc791\uc5c5 \uc9c0\uc2dc\ubb38\uc744 \ub2e4\ub978 \uc5d0\uc774'
     '\uc804\ud2b8\uc5d0\uac8c \ub118\uae30\ub824\uace0 \ud574.', True),
    ('Review the handoff parser code.', False),
    ('Do not write a handoff for another agent.', False),
    ('Explain why another agent might write a handoff.', False),
    ('Fix this bug.', False),
    ('```\nWrite a handoff for another agent.\n```\nReview this quote.', False),
    ('> Write a handoff for another agent.\nExplain this quote.', False),
])
def test_should_detect_only_explicit_agent_handoff_requests(prompt, expected):
    assert module().detect(prompt) is expected


def test_should_preserve_verbatim_owner_sections_without_implicit_permissions():
    owner = module().owner_sections(PROMPT)
    assert owner['may'] == 'read src/example.py; report findings'
    assert owner['may_not'] == 'edit files; run tests'
    assert owner['excluded'] == ['PRIVATE-CANARY-42']
    assert module().owner_sections('Prepare a brief for another agent.')['may'] == ''


@pytest.mark.parametrize(('body', 'defect'), [
    (packet().replace('a' * 40, 'aaaaaaa'), 'supplied pins'),
    (packet().replace(PINS, ''), 'supplied pins'),
    (packet().replace('May: read src/example.py;', 'May: edit files;'), 'extra may: edit files'),
    (packet() + '\nWrapper: PRIVATE-CANARY-42', 'excluded item'),
    (packet().replace('Temporal: current\n', ''), 'temporal'),
    (packet().replace('Evidence: parent-supplied prompt; observed 2026-10-22T01:02:03Z',
                      'Evidence: found it'), 'evidence provenance/time'),
    (packet().replace('Unknowns: recipient verification pending\n', ''), 'unknowns'),
    (packet().replace('May not: edit files; run tests\n', ''), 'may not'),
    (packet().replace('Self-check: ' + SELF_CHECK + '\n', ''),
     'self-check'),
    (packet().replace('Qualified target: example:review', 'Qualified target: review'),
     'qualified target'),
])
def test_should_name_clear_packet_defects(body, defect):
    defects = module().check_packet(body, {'pins': PINS, 'owner': module().owner_sections(PROMPT)})
    assert any(defect in item for item in defects), defects


def test_should_accept_clean_packet_and_reject_ungranted_may():
    hook = module()
    state = {'pins': PINS, 'owner': hook.owner_sections(PROMPT)}
    assert hook.check_packet(packet(), state) == []
    state['owner']['may'] = ''
    assert 'extra may: edit files' in hook.check_packet(
        packet().replace('May: read src/example.py;', 'May: edit files;'), state)


@pytest.fixture
def runtime(tmp_path):
    state = tmp_path / 'state'
    state.mkdir()
    repo = tmp_path / 'repo'
    (repo / 'scripts').mkdir(parents=True)
    (repo / '.git').mkdir()
    runner = repo / 'scripts/mir_ontology.py'
    runner.write_text(
        'import sys\n'
        'assert sys.argv[1:] == ["mapping", "--handoff", "src/example.py"]\n'
        f'print({PINS!r})\n'
    )
    env = {key: value for key, value in os.environ.items()
           if key not in {'MIR_HANDOFF_STATE_DIR', 'MIR_HANDOFF_RUNNER'}}
    env['PYTHONDONTWRITEBYTECODE'] = '1'

    def run(event, **extra):
        transcript = Path(extra.get('transcript_path', repo / 'native-session.jsonl'))
        if event == 'UserPromptSubmit':
            transcript.write_text(json.dumps({'type': 'user', 'message': {
                'content': extra.get('prompt', '')}}) + '\n')
        elif isinstance(extra.get('last_assistant_message'), str):
            with transcript.open('a') as stream:
                stream.write(json.dumps({'type': 'assistant', 'message': {
                    'content': extra['last_assistant_message']}}) + '\n')
        extra.setdefault('transcript_path', str(transcript))
        payload = {'hook_event_name': event, 'cwd': str(repo), 'session_id': 'session-1',
                   'stop_hook_active': False, **extra}
        result = subprocess.run([HANDLER_PYTHON, str(HANDLER)], input=json.dumps(payload),
                                text=True, capture_output=True, env=env, check=False)
        assert result.returncode in {0, 2}, result.stderr
        return result

    return run, state, repo


@pytest.mark.parametrize('runtime_shape', ['claude', 'codex'])
def test_should_supply_exact_pins_and_check_once_for_both_runtime_shapes(runtime, runtime_shape):
    run, state, repo = runtime
    supplied = run('UserPromptSubmit', prompt=PROMPT)
    assert supplied.returncode == 0, supplied.stderr
    context = json.loads(supplied.stdout)['hookSpecificOutput']['additionalContext']
    assert PINS in context
    assert 'copy verbatim; do not add permissions' in context
    assert 'May: read src/example.py; report findings' in context
    assert 'May not: edit files; run tests' in context
    assert list(state.iterdir()) == []
    bad = packet().replace('a' * 40, 'aaaaaaa')
    if runtime_shape == 'claude':
        stop = {'last_assistant_message': bad}
    else:
        transcript = repo / 'rollout.jsonl'
        transcript.write_text(json.dumps({'type': 'event_msg', 'payload': {
            'type': 'user_message', 'message': PROMPT}}) + '\n' + json.dumps({
            'type': 'response_item', 'payload': {
            'type': 'message', 'role': 'assistant', 'phase': 'final_answer',
            'content': [{'type': 'output_text', 'text': bad}],
        }}) + '\n')
        stop = {'transcript_path': str(transcript)}
    blocked = run('Stop', **stop)
    assert json.loads(blocked.stdout)['decision'] == 'block'
    assert 'supplied pins' in json.loads(blocked.stdout)['reason']
    retry = run('Stop', **stop, stop_hook_active=True)
    assert retry.returncode == 0
    assert 'decision' not in json.loads(retry.stdout or '{}')
    assert 'WARNING' in retry.stderr + retry.stdout
    # New user turn resets the one-shot guard.
    run('UserPromptSubmit', prompt=PROMPT)
    clean = run('Stop', last_assistant_message=packet())
    assert clean.returncode == 0 and clean.stdout == '' and clean.stderr == ''


def test_should_leave_ordinary_turns_untouched_and_clear_previous_context(runtime):
    run, state, _ = runtime
    assert run('UserPromptSubmit', prompt='Fix this bug.').stdout == ''
    assert list(state.iterdir()) == []
    run('UserPromptSubmit', prompt=PROMPT)
    assert run('UserPromptSubmit', prompt='Thanks.').stdout == ''
    assert run('Stop', last_assistant_message=packet()).stdout == ''
    assert list(state.iterdir()) == []


def test_should_fail_open_visibly_on_runner_or_transcript_errors(runtime):
    run, state, repo = runtime
    (repo / 'scripts/mir_ontology.py').write_text('raise RuntimeError("private-data")\n')
    failed = run('UserPromptSubmit', prompt=PROMPT)
    assert failed.returncode == 0
    assert 'WARNING' in failed.stdout + failed.stderr
    assert 'private-data' not in failed.stdout + failed.stderr
    context = json.loads(failed.stdout)['hookSpecificOutput']['additionalContext']
    assert 'May: read src/example.py; report findings' in context
    assert 'unavailable pins:' in context
    assert list(state.iterdir()) == []
    failed = run('Stop', transcript_path=str(repo / 'absent.jsonl'))
    assert failed.returncode == 0 and 'WARNING' in failed.stdout + failed.stderr


def test_should_skip_runner_when_owner_forbids_commands(runtime):
    run, state, repo = runtime
    (repo / 'scripts/mir_ontology.py').write_text('raise AssertionError("must not execute")\n')
    for restriction in ['May not: run commands', 'Do not run commands.']:
        stopped = run('UserPromptSubmit', prompt=PROMPT + restriction + '\n')
        assert stopped.returncode == 0
        assert 'unavailable' in stopped.stdout
        assert list(state.iterdir()) == []


def test_should_not_check_non_packet_outputs_or_loop_on_native_retry(runtime):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    assert run('Stop', last_assistant_message='I need the target name.').stdout == ''
    retry = run('Stop', last_assistant_message=packet().replace(PINS, ''), stop_hook_active=True)
    assert 'decision' not in json.loads(retry.stdout or '{}')


def test_should_fail_open_visibly_for_bad_payload_or_missing_native_cwd():
    env = {key: value for key, value in os.environ.items() if key != 'MIR_HANDOFF_STATE_DIR'}
    for payload in [json.dumps({'hook_event_name': 'UserPromptSubmit', 'prompt': PROMPT}), '{']:
        result = subprocess.run([HANDLER_PYTHON, str(HANDLER)], input=payload,
                                text=True, capture_output=True, env=env, check=False)
        assert result.returncode == 0
        assert 'WARNING' in result.stdout + result.stderr


def test_should_register_common_events_without_changing_session_start():
    active = json.loads((ROOT / 'plugins/mir-lifecycle-hooks/hooks/hooks.json').read_text())
    assert set(active['hooks']) == {'SessionStart', 'UserPromptSubmit', 'Stop', 'PreToolUse'}
    for name in ('UserPromptSubmit', 'Stop', 'PreToolUse'):
        command = active['hooks'][name][0]['hooks'][0]
        assert command['timeout'] == 8
        assert 'handoff_packet.py' in command['command']
    assert active['hooks']['SessionStart'][0]['hooks'][0]['timeout'] == 2


def test_should_reject_missing_owner_restriction_and_duplicate_pin_blocks():
    hook = module()
    state = {'pins': PINS, 'owner': hook.owner_sections(PROMPT)}
    assert any('owner restriction' in defect for defect in hook.check_packet(
        packet().replace('May not: edit files; run tests', 'May not: none'), state))
    assert any('duplicate' in defect for defect in hook.check_packet(packet() + '\n' + PINS, state))


def test_should_require_individual_pin_and_field_self_checks():
    hook = module()
    state = {'pins': PINS, 'owner': hook.owner_sections(PROMPT)}
    assert any('self-check' in defect for defect in hook.check_packet(
        packet().replace('Self-check: ' + SELF_CHECK,
                         'Self-check: complete'), state))


def test_should_ignore_packet_when_current_transcript_prompt_hash_differs(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    transcript = repo / 'session.jsonl'
    transcript.write_text(json.dumps({'type': 'user', 'message': {
        'role': 'user', 'content': 'Prepare a brief for another agent. Inspect only.',
    }}) + '\n')
    result = run('Stop', transcript_path=str(transcript), last_assistant_message=packet())
    assert result.returncode == 0 and 'decision' not in json.loads(result.stdout or '{}')
    assert 'WARNING' in result.stdout + result.stderr


@pytest.mark.parametrize('restriction', [
    'Do not run commands.', 'No commands.',
])
def test_should_recognize_unlabeled_owner_restrictions(runtime, restriction):
    run, state, repo = runtime
    (repo / 'scripts/mir_ontology.py').write_text('raise AssertionError("must not run")\n')
    result = run('UserPromptSubmit', prompt=PROMPT + restriction)
    assert 'owner forbids' in result.stdout
    assert not list(state.iterdir())


def test_should_not_echo_excluded_item_in_extra_permission_diagnostic():
    hook = module()
    defects = hook.check_packet(packet() + '\nMay: forward PRIVATE-CANARY-42',
                                {'pins': PINS, 'owner': hook.owner_sections(PROMPT)})
    assert defects and 'PRIVATE-CANARY-42' not in '\n'.join(defects)


def test_should_inventory_each_unknown_pin_in_self_check():
    hook = module()
    missing = PINS.replace('"unknowns": []', '"unknowns": ["head: unavailable"]')
    defects = hook.check_packet(packet(missing),
                                {'pins': missing, 'owner': hook.owner_sections(PROMPT)})
    assert 'unchecked pin gap: head: unavailable' in defects


def test_should_fail_open_without_leaking_malformed_transcript(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    (repo / 'native-session.jsonl').write_text('{private-data')
    result = run('Stop')
    assert result.returncode == 0 and 'WARNING' in result.stdout + result.stderr
    assert 'private-data' not in result.stdout + result.stderr


def test_should_use_owner_prompt_instead_of_claude_tool_result_records(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    transcript = repo / 'native-session.jsonl'
    with transcript.open('a') as stream:
        stream.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': [
            {'type': 'tool_result', 'tool_use_id': 'tool-1', 'content': 'done'},
        ]}}) + '\n')
        stream.write(json.dumps({'type': 'assistant', 'message': {'content': [
            {'type': 'text', 'text': packet().replace(PINS, '')},
        ]}}) + '\n')
    result = run('Stop')
    assert json.loads(result.stdout)['decision'] == 'block'


def test_should_reject_inline_permission_enlargement_in_enclosing_text():
    hook = module()
    defects = hook.check_packet(packet() + '\nYou may edit files.',
                                {'pins': PINS, 'owner': hook.owner_sections(PROMPT)})
    assert 'extra may: edit files' in defects


@pytest.mark.parametrize('field', ['Lifecycle', 'Temporal', 'Epistemic', 'Verification',
                                  'Evidence', 'Unknowns'])
def test_should_reject_empty_envelope_values(field):
    hook = module()
    import re
    body = re.sub(rf'(?m)^{field}:.*$', field + ':', packet())
    assert hook.check_packet(body, {'pins': PINS, 'owner': hook.owner_sections(PROMPT)})


def test_should_keep_ordinary_turn_silent_without_adapter(runtime):
    run, state, _ = runtime
    state.rmdir()
    result = run('UserPromptSubmit', prompt='Fix this bug.')
    assert result.stdout == result.stderr == ''
    stopped = run('Stop', last_assistant_message='Done.')
    assert stopped.stdout == stopped.stderr == ''


@pytest.mark.parametrize('source', ['../outside.py', '.env.local', 'secrets/key', '.mir/memory.db'])
def test_should_refuse_protected_or_escaping_sources_without_running_runner(runtime, source):
    run, state, repo = runtime
    (repo / 'scripts/mir_ontology.py').write_text('raise AssertionError("must not run")\n')
    result = run('UserPromptSubmit', prompt=PROMPT.replace('src/example.py', source))
    assert result.returncode == 0 and 'WARNING' in result.stdout
    assert list(state.iterdir()) == []


def test_should_fail_open_within_budget_when_pin_runner_hangs(runtime):
    run, state, repo = runtime
    (repo / 'scripts/mir_ontology.py').write_text('import time\ntime.sleep(30)\n')
    result = run('UserPromptSubmit', prompt=PROMPT)
    assert result.returncode == 0 and 'WARNING' in result.stdout
    assert list(state.iterdir()) == []


def test_should_supply_real_repository_runner_pins_without_network(tmp_path):
    import hashlib

    state = tmp_path / 'runtime-state'
    state.mkdir()
    source = 'plugins/mir-lifecycle-hooks/hooks/runtime_continuity.py'
    payload = {'hook_event_name': 'UserPromptSubmit', 'cwd': str(ROOT),
               'session_id': 'real-runner-offline', 'prompt': (
                   'Prepare a handoff for another agent.\nSources: ' + source
                   + '\nMay: read and report\nMay not: edit project files\n')}
    env = {**os.environ, 'MIR_HANDOFF_STATE_DIR': str(state), 'PYTHONDONTWRITEBYTECODE': '1'}
    env.pop('MIR_HANDOFF_RUNNER', None)
    result = subprocess.run([HANDLER_PYTHON, str(HANDLER)], input=json.dumps(payload),
                            text=True, capture_output=True, env=env, check=False, timeout=8)
    assert result.returncode == 0 and result.stderr == ''
    context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    cached = context.split('handoff pins:\n', 1)[1].split('\nOwner boundary', 1)[0]
    assert not list(state.iterdir())
    pins, _ = json.JSONDecoder().raw_decode(cached)
    assert pins['repository_root'] == str(ROOT)
    assert len(pins['head']) == 40
    assert pins['contract_version'] == '1.1.0'
    assert pins['sources'][0]['sha256'] == hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    assert pins['pin_inventory']


@pytest.mark.parametrize('grant', [
    'edit files', 'write scratch', 'run tests', 'execute checks', 'install packages',
    'commit changes', 'push', 'access network', 'delegate to another agent',
    '\uc218\uc815', '\ud30c\uc77c \uc4f0\uae30', '\ud14c\uc2a4\ud2b8 \uc2e4\ud589',
    '\uac80\uc99d \uc218\ud589', '\uc124\uce58', '\ucee4\ubc0b', '\ud478\uc2dc',
    '\ub124\ud2b8\uc6cc\ud06c \uc811\uadfc',
    '\ub2e4\ub978 \uc5d0\uc774\uc804\ud2b8\uc5d0\uac8c \uc704\uc784',
])
def test_should_reject_unlabeled_owner_authority_enlargement_in_both_languages(grant):
    hook = module()
    owner = hook.owner_sections('Prepare a brief for another agent.')
    body = packet().replace('May: read src/example.py; report findings', 'May: ' + grant)
    assert 'extra may: ' + grant in hook.check_packet(body, {'pins': PINS, 'owner': owner})


@pytest.mark.parametrize('grant', ['read src/example.py', 'inspect source',
                                  '\uc18c\uc2a4 \uc77d\uae30', '\ud30c\uc77c \uc5f4\ub78c'])
def test_should_allow_read_inspect_only_without_explicit_owner_grant(grant):
    hook = module()
    body = packet().replace('May: read src/example.py; report findings', 'May: ' + grant)
    assert hook.check_packet(body, {'pins': PINS, 'owner': hook.owner_sections(
        'Prepare a brief for another agent.')}) == []


def test_should_forward_unlabeled_korean_prohibition():
    hook = module()
    restriction = '\uc218\uc815\ud558\uc9c0 \ub9d0\uace0 \uc77d\uae30\ub9cc \ud558\uc138\uc694.'
    owner = hook.owner_sections('Prepare a brief for another agent.\n' + restriction)
    assert restriction in owner['may_not']
    assert restriction in hook.context_text(owner)


def test_should_forward_only_the_prohibiting_sentence():
    hook = module()
    task = '\ubc31\uc5c5 \ubcf5\uc6d0 \uc548\ub0b4\ub97c \uac1c\uc120\ud558\ub824\uace0 \ud574.'
    restriction = (
        '\ud30c\uc77c\uc744 \uc218\uc815\ud558\uc9c0 \ub9d0\uace0 \ub2f5\ubcc0\ub9cc '
        '\ud574\uc918.'
    )
    owner = hook.owner_sections(
        'Prepare a brief for another agent. ' + task + restriction)
    assert restriction in owner['may_not']
    assert task not in owner['may_not']
    dotted = '\ubcf4\ud638 \uacbd\ub85c CONTEXT.md\ub294 \uc5f4\uc9c0 \ub9d0\uc544\uc918.'
    assert dotted in hook.owner_sections(task + dotted)['may_not']


def test_should_run_without_state_adapter_and_resolve_nested_cwd(runtime):
    run, state, repo = runtime
    nested = repo / 'src/deep'
    nested.mkdir(parents=True)
    result = run('UserPromptSubmit', prompt=PROMPT, cwd=str(nested))
    assert PINS in json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    assert result.stderr == '' and not list(state.iterdir())


def test_should_allow_pin_supply_with_no_file_writes_granted(runtime):
    run, state, _ = runtime
    result = run('UserPromptSubmit', prompt=PROMPT + '\nDo not write scratch files.')
    assert PINS in json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    assert not list(state.iterdir())


def test_should_recompute_pins_on_stop_and_reject_stale_source(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    runner = repo / 'scripts/mir_ontology.py'
    runner.write_text('print(' + repr(PINS.replace('e' * 64, 'f' * 64)) + ')\n')
    result = run('Stop', last_assistant_message=packet())
    assert json.loads(result.stdout)['decision'] == 'block'
    assert 'supplied pins' in json.loads(result.stdout)['reason']


def test_should_guard_exact_prompt_hash_without_state(runtime):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    changed = packet().replace(hashlib.sha256(PROMPT.encode()).hexdigest(), 'f' * 64)
    result = run('Stop', last_assistant_message=changed)
    assert 'decision' not in json.loads(result.stdout or '{}')
    assert 'WARNING' in result.stdout + result.stderr


def test_should_ignore_native_assistant_hint_and_use_transcript_tail(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    transcript = repo / 'native-session.jsonl'
    with transcript.open('a') as stream:
        stream.write(json.dumps({'type': 'assistant', 'message': {
            'content': packet().replace(PINS, '')}}) + '\n')
    # Direct payload hint is stale; explicit transcript is authoritative for Stop.
    result = run('Stop', transcript_path=str(transcript), last_assistant_message=None)
    assert json.loads(result.stdout)['decision'] == 'block'


def test_should_not_run_runner_for_ordinary_turns(monkeypatch):
    hook = module()
    def forbidden(*args, **kwargs):
        raise AssertionError('ordinary supply must perform detection only')
    monkeypatch.setattr(hook.subprocess, 'Popen', forbidden)
    hook.supply({'prompt': 'Review the handoff parser code.'})


def test_should_accept_original_pin_time_after_fresh_runner_observation(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    fresh = PINS.replace('2026-10-22T01:02:03Z', '2026-10-22T01:02:04Z')
    (repo / 'scripts/mir_ontology.py').write_text('print(' + repr(fresh) + ')\n')
    result = run('Stop', last_assistant_message=packet())
    assert result.stdout == result.stderr == ''


def test_should_name_each_changed_pin_in_repair(runtime):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    result = run('Stop', last_assistant_message=packet().replace('e' * 64, 'f' * 64))
    assert '/sources/0/sha256' in json.loads(result.stdout)['reason']


def test_should_fail_open_if_prompt_is_outside_transcript_tail(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    transcript = repo / 'native-session.jsonl'
    with transcript.open('a') as stream:
        stream.write(json.dumps({'type': 'irrelevant', 'value': 'x' * (1024 * 1024)}) + '\n')
        stream.write(json.dumps({'type': 'assistant', 'message': {'content': packet()}}) + '\n')
    result = run('Stop')
    assert 'WARNING' in result.stdout + result.stderr
    assert 'decision' not in json.loads(result.stdout)


def test_should_require_retry_guard_before_blocking(runtime):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    result = run('Stop', last_assistant_message=packet().replace(PINS, ''), stop_hook_active=None)
    assert 'WARNING' in result.stdout + result.stderr
    assert 'decision' not in json.loads(result.stdout)


def test_should_skip_absent_root_runner_with_visible_warning(runtime):
    run, _, repo = runtime
    (repo / 'scripts/mir_ontology.py').unlink()
    result = run('UserPromptSubmit', prompt=PROMPT)
    assert 'WARNING' in result.stdout + result.stderr
    assert 'unavailable pins:' in result.stdout


def test_should_not_reuse_prior_assistant_after_new_user_prompt(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    transcript = repo / 'native-session.jsonl'
    with transcript.open('a') as stream:
        stream.write(json.dumps({'type': 'assistant', 'message': {'content': packet()}}) + '\n')
        stream.write(json.dumps({'type': 'user', 'message': {'content': 'Thanks.'}}) + '\n')
    result = run('Stop')
    assert result.stdout == result.stderr == ''


def test_should_not_detect_explicit_korean_handoff_prohibition():
    assert not module().detect(
        '\ub2e4\ub978 \uc5d0\uc774\uc804\ud2b8\uc5d0\uac8c \ud578\ub4dc\uc624\ud504\ub97c '
        '\uc791\uc131\ud558\uc9c0 \ub9c8\uc138\uc694.')


def test_should_reject_grants_in_non_may_labeled_enclosing_authority():
    hook = module()
    state = {'pins': PINS, 'owner': hook.owner_sections(PROMPT)}
    defects = hook.check_packet(packet() + '\nThe recipient may execute checks.', state)
    assert 'extra may: execute checks' in defects


def test_should_check_translated_packet_without_english_labels(runtime):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    pins = PINS.split('handoff pins:\n', 1)[1]
    translated = ('## \ud578\ub4dc\uc624\ud504 \uc9c0\uc2dc\ubb38: example\n'
                  '### 0. pins\n```json\n' + pins + '\n```\n'
                  '### 7. \uad8c\ud55c\n- \ud5c8\uc6a9: \ud30c\uc77c \uc218\uc815\n')
    result = json.loads(run('Stop', last_assistant_message=translated).stdout)
    assert result['decision'] == 'block'
    assert 'missing qualified target' in result['reason']


def test_should_check_native_final_message_when_transcript_lags(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    transcript = repo / 'native-session.jsonl'
    with transcript.open('a') as stream:
        stream.write(json.dumps({'type': 'assistant', 'message': {
            'content': 'Reading the sources now.'}}) + '\n')
    payload = {'hook_event_name': 'Stop', 'cwd': str(repo), 'session_id': 'session-1',
               'stop_hook_active': False, 'transcript_path': str(transcript),
               'last_assistant_message': packet().replace(PINS, '')}
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([HANDLER_PYTHON, str(HANDLER)], input=json.dumps(payload),
                            text=True, capture_output=True, env=env, check=False)
    assert json.loads(result.stdout)['decision'] == 'block'


def test_should_require_digest_and_revision_for_each_cited_source(runtime):
    run, _, repo = runtime
    (repo / 'src').mkdir()
    (repo / 'src/cited.py').write_text('VALUE = 1\n')
    cited = PINS.replace('src/example.py', 'src/cited.py').replace('d' * 40, '1' * 40).replace(
        'e' * 64, '2' * 64)
    (repo / 'scripts/mir_ontology.py').write_text(
        'import sys\n'
        f'print({cited!r} if sys.argv[3:] == ["src/cited.py"] else {PINS!r})\n'
    )
    run('UserPromptSubmit', prompt=PROMPT)
    body = packet() + 'Inspect src/cited.py\uc758 VALUE and src/absent.py.\n'
    result = json.loads(run('Stop', last_assistant_message=body).stdout)
    assert result['decision'] == 'block'
    assert 'missing cited-source pins' in result['reason']
    assert 'src/cited.py' in result['reason'] and 'src/absent.py' not in result['reason']
    pinned = packet() + 'Inspect src/cited.py sha256 ' + '2' * 64 + ' revision ' + '1' * 40 + '.\n'
    assert 'decision' not in json.loads(run('Stop', last_assistant_message=pinned).stdout or '{}')

@pytest.mark.parametrize('restriction', [
    (
        '\uba85\ub839\uc744 \uc2e4\ud589\ud558\uc9c0 \uc54a\uace0 \ub2f5\ubcc0'
        '\ud574 \uc8fc\uc138\uc694.'
    ), (
        '\uba85\ub839 \uc2e4\ud589 \uc5c6\uc774 \uac80\ud1a0\ud574 \uc8fc\uc138'
        '\uc694.'
    ),
    (
        '\uba85\ub839\uc740 \uc2e4\ud589\ud558\uc9c0 \ub9c8.'
    ), (
        '\uba85\ub839\uc744 \uc2e4\ud589\ud558\uc9c0 \ub9d0\uace0 \uc77d\uae30'
        '\ub9cc \ud558\uc138\uc694.'
    ),
])
def test_should_skip_both_runners_for_korean_command_prohibitions(runtime, restriction):
    run, _, repo = runtime
    (repo / 'scripts/mir_ontology.py').write_text('raise AssertionError("runner called")\n')
    prompt = PROMPT + restriction
    supplied = run('UserPromptSubmit', prompt=prompt)
    assert 'owner forbids commands' in supplied.stdout
    body = packet().replace(hashlib.sha256(PROMPT.encode()).hexdigest(),
                            hashlib.sha256(prompt.encode()).hexdigest())
    stopped = run('Stop', last_assistant_message=body + '\nInspect src/cited.py')
    assert 'owner forbids commands' in stopped.stdout


def test_should_not_extract_positive_request_with_negative_subordinate_clause():
    hook = module()
    task = (
        '\ub2e4\ub978 \uc5d0\uc774\uc804\ud2b8\uc5d0\uac8c \uc2e4\uc81c \ub370'
        '\uc774\ud130\ub97c \uc218\uc815\ud558\uc9c0 \ub9d0\ub77c\ub294 \uc81c'
        '\uc57d\uc744 \uc9c0\ud0ac \ud578\ub4dc\uc624\ud504\ub97c \uc791\uc131'
        '\ud574 \uc8fc\uc138\uc694.'
    )
    assert hook.owner_sections(task)['may_not'] == ''
    restriction = (
        '\uba85\ub839\uc744 \uc2e4\ud589\ud558\uc9c0 \ub9d0\uace0 \ub2f5\ubcc0'
        '\ub9cc \ud574 \uc8fc\uc138\uc694.'
    )
    assert restriction in hook.owner_sections(task + '\n' + restriction)['may_not']


@pytest.mark.parametrize('variant', ['labels', 'evidence', 'inventory', 'restriction',
                                   'read-only', 'future', 'qualifier'])
def test_should_accept_equivalent_packet_labels_and_safe_authority(variant):
    hook = module()
    body = packet()
    if variant == 'labels':
        body = body.replace('May:', '- **May:**').replace('May not:', '- **May not:**')
        body = body.replace('Lifecycle:', '- Lifecycle:')
    elif variant == 'evidence':
        body = body.replace('Evidence: parent-supplied prompt; observed',
                            'Evidence: Source: prompt; Time:')
    elif variant == 'inventory':
        body = body.replace('field ', '').replace('pin ', '')
    elif variant == 'restriction':
        body = body.replace('May not: edit files; run tests',
                            'May not: EDIT-FILES!; **Run tests.**')
    elif variant == 'read-only':
        body = body.replace('May: read src/example.py; report findings',
                            'May: read-only inspection of synthetic source; report findings')
    elif variant == 'future':
        body += '\nOnly after a separate owner grant, the recipient may run tests.\n'
    else:
        body += '\nMay not: the recipient may edit files only after a separate owner grant.\n'
    assert hook.check_packet(body, {'pins': PINS, 'owner': hook.owner_sections(PROMPT)}) == []


@pytest.mark.parametrize('profile', ['valid', 'broken', 'absent'])
def test_should_exclude_denied_and_profile_protected_citations(tmp_path, profile):
    hook = module()
    for name in ['src/allowed.py', 'docs/denied.md', 'docs/packet.md', 'docs/not-read.md',
                 'android/key.properties', 'private/nested/token.txt']:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('must not hash protected contents\n')
    if profile != 'absent':
        (tmp_path / '.mir').mkdir()
        (tmp_path / '.mir/repo-profile.toml').write_text(
            '[paths]\nprotected_paths = ["android/*.properties"]\n'
            '[boundaries]\nsecrets = ["private/**"]\n' if profile == 'valid' else 'broken = [')
    owner = hook.owner_sections('May not: read docs/denied.md\n')
    body = ('Inspect src/allowed.py.\nNot read: docs/not-read.md\n'
            'May not:\n- read docs/packet.md\n'
            'Unknowns: docs/denied.md android/key.properties private/nested/token.txt\n')
    expected = ['src/allowed.py']
    if profile != 'valid':
        expected += ['android/key.properties', 'private/nested/token.txt']
    assert hook.cited_paths(body, owner, tmp_path) == expected


RECIPIENT_PROMPT = 'Review this received handoff.\n' + packet()
RECIPIENT_LABELS = ('\n'.join('pin ' + name + '=parent-supplied' for name in PIN_NAMES)
                    + '\nNo local check was performed; pins are parent-supplied.')


def append_tool(repo, shape, name, arguments):
    if shape == 'claude':
        row = {'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'id': 'tool-1', 'name': name, 'input': arguments}]}}
    else:
        row = {'type': 'response_item', 'payload': {
            'type': 'function_call', 'name': name, 'arguments': json.dumps(arguments)}}
    with (repo / 'native-session.jsonl').open('a') as stream:
        stream.write(json.dumps(row) + '\n')


def test_should_supply_recipient_rule_and_block_missing_labels_once(runtime):
    run, _, _ = runtime
    supplied = run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    assert 'verified-in-repo' in supplied.stdout and 'this turn' in supplied.stdout
    blocked = run('Stop', last_assistant_message='Review complete.')
    assert json.loads(blocked.stdout)['decision'] == 'block'
    retry = run('Stop', last_assistant_message='Review complete.', stop_hook_active=True)
    assert 'decision' not in json.loads(retry.stdout or '{}')
    assert run('Stop', last_assistant_message=RECIPIENT_LABELS).stdout == ''


@pytest.mark.parametrize(('shape', 'tool', 'arguments'), [
    ('claude', 'Read', {'file_path': 'src/example.py'}),
    ('claude', 'Bash', {'command': 'cat src/example.py'}),
    ('codex', 'functions.exec_command', {'cmd': 'cat src/example.py'}),
    ('codex', 'exec_command', {
        'cmd': 'python3 scripts/mir_ontology.py mapping --handoff src/example.py'}),
])
def test_should_require_current_turn_tool_reference_for_verified_path(
    runtime, shape, tool, arguments,
):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    body = RECIPIENT_LABELS + '\nPath verified-in-repo: src/example.py'
    blocked = run('Stop', last_assistant_message=body)
    assert json.loads(blocked.stdout)['decision'] == 'block'
    append_tool(repo, shape, tool, arguments)
    assert run('Stop', last_assistant_message=body).stdout == ''
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    assert json.loads(run('Stop', last_assistant_message=body).stdout)['decision'] == 'block'


def test_should_require_reader_limitation_when_recipient_commands_forbidden(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT + '\nNo commands.')
    blocked = run('Stop', last_assistant_message=RECIPIENT_LABELS)
    assert json.loads(blocked.stdout)['decision'] == 'block'
    answer = RECIPIENT_LABELS + '\nCommands forbidden; no non-command reader was used.'
    assert run('Stop', last_assistant_message=answer).stdout == ''
    append_tool(repo, 'claude', 'Read', {'file_path': 'src/example.py'})
    assert run('Stop', last_assistant_message=RECIPIENT_LABELS).stdout == ''


COMPLETE_ARTIFACT_RULE = (
    'Re-send the complete corrected artifact as your final message; it replaces the previous '
    'one, so do not send only the changed sections.'
)


@pytest.mark.parametrize('retry', [False, True])
@pytest.mark.parametrize('receiving', [False, True])
def test_should_end_every_block_reason_with_complete_artifact_rule(capsys, retry, receiving):
    hook = module()
    hook.block(['abbreviated hex value: head'], retry, receiving, hook.owner_sections(PROMPT))
    reason = json.loads(capsys.readouterr().out)['reason']
    assert reason.endswith(COMPLETE_ARTIFACT_RULE)
    assert reason.count(COMPLETE_ARTIFACT_RULE) == 1


@pytest.mark.parametrize('mode', ['author', 'no-command', 'recipient'])
def test_should_supply_complete_artifact_rule_once(runtime, mode):
    run, _, _ = runtime
    prompt = RECIPIENT_PROMPT if mode == 'recipient' else PROMPT
    if mode == 'no-command':
        prompt += '\nNo commands.'
    result = run('UserPromptSubmit', prompt=prompt)
    context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    assert context.count(COMPLETE_ARTIFACT_RULE) == 1


@pytest.mark.parametrize('receiving', [False, True])
@pytest.mark.parametrize('shape', ['claude', 'codex'])
@pytest.mark.parametrize('absolute', [False, True])
def test_should_accept_only_current_turn_head_read_inside_root(
    runtime, receiving, shape, absolute,
):
    run, _, repo = runtime
    prompt = (RECIPIENT_PROMPT if receiving else PROMPT) + '\nNo commands.'
    body = (RECIPIENT_LABELS if receiving else NO_PIN_PACKET) + '\npin head=verified-in-repo'
    head = str(repo / '.git/HEAD') if absolute else '.git/HEAD'
    run('UserPromptSubmit', prompt=prompt)
    append_tool(repo, shape, 'Read', {'file_path': head})
    assert 'decision' not in json.loads(run('Stop', last_assistant_message=body).stdout or '{}')
    # Neither an old-turn read, another repository nor a non-Read tool verifies HEAD.
    for tool, path in [('Read', str(repo) + '-other/.git/HEAD'),
                       ('Read', '../other/.git/HEAD'),
                       ('Read', 'src/example.py'), ('Grep', head), ('Glob', head)]:
        run('UserPromptSubmit', prompt=prompt)
        append_tool(repo, shape, tool, {'file_path' if tool == 'Read' else 'path': path})
        output = json.loads(run('Stop', last_assistant_message=body).stdout)
        assert 'verified-in-repo pin lacks this-turn tool reference: head' in output['reason']


@pytest.mark.parametrize('mode', ['author-no-command', 'recipient-no-command', 'recipient'])
@pytest.mark.parametrize('tool', ['Read', 'Grep', 'Glob'])
@pytest.mark.parametrize('absolute', [False, True])
def test_should_accept_only_current_turn_repository_root_reader_inside_root(
    runtime, mode, tool, absolute,
):
    run, _, repo = runtime
    receiving = mode.startswith('recipient')
    prompt = RECIPIENT_PROMPT if receiving else PROMPT
    if mode.endswith('no-command'):
        prompt += '\nNo commands.'
    body = ((RECIPIENT_LABELS if receiving else NO_PIN_PACKET)
            + '\npin repository_root=verified-in-repo')
    key = 'file_path' if tool == 'Read' else 'path'
    path = str(repo / 'src/example.py') if absolute else 'src/example.py'
    run('UserPromptSubmit', prompt=prompt)
    append_tool(repo, 'claude', tool, {key: path})
    assert 'decision' not in json.loads(run('Stop', last_assistant_message=body).stdout or '{}')
    for outside in [str(repo) + '-other/src/example.py', '../other/src/example.py']:
        run('UserPromptSubmit', prompt=prompt)
        append_tool(repo, 'claude', tool, {key: outside})
        output = json.loads(run('Stop', last_assistant_message=body).stdout)
        assert ('verified-in-repo pin lacks this-turn tool reference: repository_root'
                in output['reason'])


@pytest.mark.parametrize('receiving', [False, True])
def test_should_accept_head_and_root_reads_but_require_contract_file_reference(runtime, receiving):
    run, _, repo = runtime
    prompt = ((RECIPIENT_PROMPT if receiving else PROMPT)
              + '\nNo commands.\ncontract_path: schema/contract.json')
    labels = (RECIPIENT_LABELS if receiving else NO_PIN_PACKET)
    body = labels + '\npin head=verified-in-repo\npin repository_root=verified-in-repo'
    run('UserPromptSubmit', prompt=prompt)
    append_tool(repo, 'claude', 'Read', {'file_path': str(repo / '.git/HEAD')})
    append_tool(repo, 'claude', 'Read', {'file_path': '.mir/ontology-map.json'})
    assert 'decision' not in json.loads(run('Stop', last_assistant_message=body).stdout or '{}')
    claims = '\n'.join('pin contract.' + key + '=verified-in-repo'
                       for key in ['identity', 'version', 'digest'])
    output = json.loads(run('Stop', last_assistant_message=body + '\n' + claims).stdout)
    for key in ['identity', 'version', 'digest']:
        assert ('verified-in-repo pin lacks this-turn tool reference: contract.' + key
                in output['reason'])
    # Author no-command packets resolve their contract path from the final artifact.
    body += '\ncontract_path: schema/contract.json\n' + claims
    append_tool(repo, 'claude', 'Read', {'file_path': 'schema/contract.json'})
    assert 'decision' not in json.loads(run('Stop', last_assistant_message=body).stdout or '{}')


@pytest.mark.parametrize('tool', ['Bash', 'shell', 'exec_command', 'functions.exec_command',
                                 'functions.shell_command'])
@pytest.mark.parametrize('recipient', [False, True])
def test_should_deny_shell_in_command_forbidden_handoff_turn(runtime, tool, recipient):
    run, _, _ = runtime
    prompt = RECIPIENT_PROMPT if recipient else PROMPT
    run('UserPromptSubmit', prompt=prompt + (
        '\n\uba85\ub839 \uc2e4\ud589 \uc5c6\uc774 \ub2f5\ubcc0\ud574 \uc8fc\uc138'
        '\uc694.'
    ))
    denied = run('PreToolUse', tool_name=tool,
                 tool_input={'command': 'echo skip', 'cmd': 'echo skip'})
    assert denied.returncode == 2
    assert json.loads(denied.stdout)['hookSpecificOutput']['permissionDecision'] == 'deny'


@pytest.mark.parametrize(('prompt', 'tool'), [
    ('Fix this bug. No commands.', 'Bash'), (PROMPT, 'Bash'),
    (PROMPT + 'No commands.', 'Read'),
])
def test_should_allow_tools_outside_no_command_shell_guard(runtime, prompt, tool):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=prompt)
    result = run('PreToolUse', tool_name=tool, tool_input={'command': 'echo skip'})
    assert result.returncode == 0 and result.stdout == ''


def test_should_fail_open_pretool_on_missing_transcript_and_use_native_prompt(runtime):
    run, _, repo = runtime
    missing = run('PreToolUse', tool_name='Bash', transcript_path=str(repo / 'absent.jsonl'))
    assert missing.returncode == 0 and 'decision' not in json.loads(missing.stdout or '{}')
    assert missing.stdout == '' and missing.stderr == ''  # silent: runs on every shell call
    denied = run('PreToolUse', prompt=PROMPT + 'No commands.', tool_name='Bash',
                 tool_input={'command': 'echo skip'})
    assert denied.returncode == 2


def test_should_not_treat_prohibition_scope_inventory_as_owner_prohibition():
    prompt = (
        '\ub300\uc0c1\uacfc \ud604\uc7ac \uc0c1\ud0dc, \ud5c8\uc6a9 \ubc94\uc704'
        '\uc640 \uae08\uc9c0 \ubc94\uc704\ub97c \ud3ec\ud568\ud574\uc11c \ub2e4'
        '\ub978 \uc5d0\uc774\uc804\ud2b8\uc5d0\uac8c \ub118\uae38 \uc9c0\uc2dc'
        '\ubb38\uc744 \uc791\uc131\ud574\uc918.'
    )
    assert module().owner_sections(prompt)['may_not'] == ''


def test_should_exclude_not_read_prose_and_heading_only_denied_scope(tmp_path):
    for name in ['docs/unread.md', 'docs/protected.md']:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text('not to be hashed')
    owner = module().owner_sections('May: read and report')
    body = 'I did not read docs/unread.md.\n### May not\n- read docs/protected.md\n'
    assert module().cited_paths(body, owner, tmp_path) == []


def test_should_accept_korean_recipient_reader_limitation(runtime):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT + (
        '\n\uba85\ub839 \uc2e4\ud589 \uc5c6\uc774 \ub2f5\ubcc0\ud574 \uc8fc\uc138'
        '\uc694.'
    ))
    answer = (RECIPIENT_LABELS
              + (
                  '\n\uba85\ub839 \uc2e4\ud589\uc774 \uae08\uc9c0\ub418\uc5b4 \ube44\uba85'
                  '\ub839 \ud30c\uc77c \uc77d\uae30 \ub3c4\uad6c\ub97c \uc0ac\uc6a9\ud558'
                  '\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.'
              ))
    assert run('Stop', last_assistant_message=answer).stdout == ''


def test_should_check_extensionless_verified_source_pin(runtime):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT.replace('src/example.py', 'src/README'))
    body = RECIPIENT_LABELS.replace('pin sources[0].digest=parent-supplied',
                                    'pin sources[0].digest=verified-in-repo')
    result = run('Stop', last_assistant_message=body)
    assert json.loads(result.stdout)['decision'] == 'block'


def test_should_not_hide_current_grant_beside_future_condition():
    hook = module()
    body = packet() + '\nYou may edit files. Only after a separate owner grant, run tests.'
    assert any(defect.startswith('extra may: edit files') for defect in hook.check_packet(
        body, {'pins': PINS, 'owner': hook.owner_sections(PROMPT)}))


def test_should_parse_qualified_may_not_heading_without_adding_grants():
    hook = module()
    body = packet().replace(
        'May not: edit files; run tests',
        'May not (\ubcc4\ub3c4 owner \uc2b9\uc778\uc774 \uc788\uc5b4\uc57c '
        '\uac00\ub2a5):\n- edit files\n- run tests')
    assert hook.check_packet(body, {'pins': PINS, 'owner': hook.owner_sections(PROMPT)}) == []


@pytest.mark.parametrize('text', [
    (
        '\uc77d\uae30\ub9cc \ud5c8\uc6a9\ub429\ub2c8\ub2e4. \uc2e4\uc81c \uc218'
        '\uc815, \uac80\uc99d \uc2e4\ud589, \ucee4\ubc0b\uc740 \uba85\uc2dc\uc801'
        '\uc73c\ub85c \uc2b9\uc778\ud574 \uc8fc\uc154\uc57c \uc9c4\ud589\ud560 '
        '\uc218 \uc788\uc2b5\ub2c8\ub2e4.'
    ),
    (
        '\uc800\uc7a5\uc18c \uc77d\uae30\uc640 \uc870\uc0ac(read/inspect only). '
        '\ud3b8\uc9d1\uacfc \ud14c\uc2a4\ud2b8\ub294 owner/Main\uc774 \uba85\uc2dc'
        '\uc801\uc73c\ub85c \uc2b9\uc778\ud574\uc57c\ub9cc \uc720\ud6a8\ud558\ub2e4'
        '.'
    ),
    (
        '\uae30\ub85d\ub41c \uacb0\uc815\uacfc \ucda9\ub3cc\ud560 \uc218 \uc788'
        '\uc2b5\ub2c8\ub2e4. \uc804\uc774 \uc815\ucc45 \ud14c\uc2a4\ud2b8\uae4c'
        '\uc9c0 \uc6d0\ud558\uc2dc\uba74 \uadf8 \uc815\ucc45\uc744 \uba3c\uc800 '
        '\uc218\ub77d\ud574\uc57c \ud569\ub2c8\ub2e4.'
    ),
])
def test_should_accept_korean_read_only_future_and_policy_caveats(text):
    hook = module()
    body = packet() + '\n' + text
    assert hook.check_packet(body, {'pins': PINS, 'owner': hook.owner_sections(PROMPT)}) == []


@pytest.mark.parametrize('marker', ['Pins:', '**Qualified target:**'])
def test_should_check_recipient_with_alternate_packet_markup(runtime, marker):
    run, _, _ = runtime
    prompt = (RECIPIENT_PROMPT.replace('handoff pins:', marker) if marker == 'Pins:'
              else RECIPIENT_PROMPT.replace('Qualified target:', marker))
    run('UserPromptSubmit', prompt=prompt)
    assert json.loads(run('Stop', last_assistant_message='Done.').stdout)['decision'] == 'block'
    assert run('Stop', last_assistant_message=RECIPIENT_LABELS).stdout == ''


def test_should_reject_same_suffix_reader_from_another_repository(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    append_tool(repo, 'claude', 'Read', {'file_path': '/another-repo/src/example.py'})
    body = RECIPIENT_LABELS.replace('sources[0].digest=parent-supplied',
                                    'sources[0].digest=verified-in-repo')
    assert json.loads(run('Stop', last_assistant_message=body).stdout)['decision'] == 'block'


@pytest.mark.parametrize('restriction', ['Commands are prohibited.', 'Commands prohibited.'])
def test_should_skip_runners_for_english_prohibited_commands(runtime, restriction):
    run, _, _ = runtime
    result = run('UserPromptSubmit', prompt=PROMPT + restriction)
    assert 'owner forbids commands' in result.stdout


def test_should_accept_read_only_may_with_separate_future_sentences():
    hook = module()
    body = packet().replace('May: read src/example.py; report findings',
                            'May: read/inspect only. Edit and tests are valid only after '
                            'a separate owner grant. This packet does not grant authority.')
    assert hook.check_packet(body, {'pins': PINS, 'owner': hook.owner_sections(PROMPT)}) == []


@pytest.mark.parametrize('shape', ['claude', 'codex'])
def test_should_recompute_pretool_owner_from_both_native_transcript_shapes(runtime, shape):
    run, _, repo = runtime
    transcript = repo / 'pretool.jsonl'
    prompt = PROMPT + 'No commands.'
    row = ({'type': 'user', 'message': {'content': prompt}} if shape == 'claude' else
           {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': prompt}})
    transcript.write_text(json.dumps(row) + '\n')
    denied = run('PreToolUse', transcript_path=str(transcript), tool_name='Bash')
    assert denied.returncode == 2


def test_should_run_all_events_on_interpreters_without_tomllib(runtime):
    """macOS /usr/bin/python3 (3.9) runs Claude hooks: a 3.11-only import must not crash them."""
    run, _, repo = runtime
    guard = ("import runpy, sys; sys.modules['tomllib'] = None; "
             "sys.version_info = (3, 9, 6); "
             f"sys.argv = [{str(HANDLER)!r}]; "
             f"runpy.run_path({str(HANDLER)!r}, run_name='__main__')")
    transcript = repo / 'native-session.jsonl'
    transcript.write_text(json.dumps({'type': 'user', 'message': {'content': PROMPT}}) + '\n')
    for payload in (
        {'hook_event_name': 'UserPromptSubmit', 'prompt': PROMPT},
        {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'tool_input': {'command': 'ls'}},
        {'hook_event_name': 'Stop', 'stop_hook_active': False, 'last_assistant_message': packet()},
    ):
        payload.update(cwd=str(repo), session_id='session-1', transcript_path=str(transcript))
        result = subprocess.run([HANDLER_PYTHON, '-c', guard], input=json.dumps(payload),
                                text=True, capture_output=True, check=False)
        assert result.stderr == (
            'mir: Python 3.11+ is required; running on 3.9.6 (upgrade python3)\n'
        )
        assert result.returncode in {0, 2}
        baseline = subprocess.run(
            [sys.executable, '-c', guard.replace('sys.version_info = (3, 9, 6); ', '')],
            input=json.dumps(payload), text=True, capture_output=True, check=False,
        )
        assert baseline.stderr == ''
        assert result.stdout == baseline.stdout
        assert result.returncode == baseline.returncode
    supplied = subprocess.run(
        [HANDLER_PYTHON, '-c', guard], text=True, capture_output=True, check=False,
        input=json.dumps({'hook_event_name': 'UserPromptSubmit', 'prompt': PROMPT, 'cwd': str(repo),
                          'session_id': 'session-1', 'transcript_path': str(transcript)}))
    assert 'Mechanical handoff packet' in supplied.stdout


# Minimal synthetic round-h regressions; no captured personal content is forwarded.
NO_PIN_PACKET = (
    '## 1. Qualified target \xb7 role\n- **\ub300\uc0c1:** `example:window`\n'
    '## \uc0c1\ud0dc\nLifecycle: current\n## \ubbf8\ud655\uc778\nnone\n'
    '## \ud5c8\uc6a9 / \uae08\uc9c0\nread only\n'
)


def no_command_turn(runtime, body, tools=()):
    run, _, repo = runtime
    (repo / 'scripts/mir_ontology.py').write_text(
        "from pathlib import Path\nPath('RUNNER_CALLED').touch()\nraise AssertionError()\n")
    run('UserPromptSubmit', prompt=PROMPT + 'No commands.\n')
    for name, arguments in tools:
        append_tool(repo, 'claude', name, arguments)
    result = run('Stop', last_assistant_message=body)
    assert not (repo / 'RUNNER_CALLED').exists()
    assert 'pins/check unavailable: owner forbids commands; no runner performed.' in result.stderr
    return result


@pytest.mark.parametrize(('body', 'defect'), [
    (NO_PIN_PACKET + '\nWrapper: PRIVATE-CANARY-42', 'excluded item #1'),
    (NO_PIN_PACKET + '\nMay: edit files', 'extra may: edit files'),
    (NO_PIN_PACKET + '\n\ud5c8\uc6a9: \ud30c\uc77c \uc218\uc815', 'extra may:'),
    (NO_PIN_PACKET + '\nVerified: .mir/ontology-map.json verified-in-repo',
     'verified-in-repo path lacks this-turn tool reference'),
    (NO_PIN_PACKET + '\npin contract.digest=verified-in-repo',
     'verified-in-repo pin lacks this-turn tool reference'),
    (NO_PIN_PACKET + '\nHEAD: abcdef123', 'abbreviated hex'),
    (NO_PIN_PACKET + '\nrevision: ' + 'a' * 39, 'abbreviated hex'),
    (NO_PIN_PACKET + '\nsha256: abcdef123', 'abbreviated hex'),
    (NO_PIN_PACKET + '\nsrc/example.py@abcdef123', 'abbreviated hex'),
])
def test_should_block_no_command_deterministic_defects_without_runner(runtime, body, defect):
    result = no_command_turn(runtime, body)
    output = json.loads(result.stdout)
    assert output.get('decision') == 'block', output
    assert defect in output['reason']
    assert 'PRIVATE-CANARY-42' not in result.stdout + result.stderr
    assert 'missing qualified target' not in output['reason']
    assert 'missing lifecycle' not in output['reason']


@pytest.mark.parametrize(('name', 'arguments'), [
    ('Read', {'file_path': '.mir/ontology-map.json'}),
    ('Grep', {'path': '.mir/ontology-map.json', 'pattern': 'contract'}),
    ('Glob', {'pattern': '.mir/ontology-map.json'}),
])
def test_should_allow_translated_no_command_packet_with_reader_and_inventoried_short_pin(
    runtime, name, arguments,
):
    body = (NO_PIN_PACKET + '\nHEAD: abcdef123\npin head=abbreviated\n'
            'pin mapping.digest=verified-in-repo .mir/ontology-map.json\n')
    result = no_command_turn(runtime, body, [(name, arguments)])
    assert 'decision' not in json.loads(result.stdout or '{}')


@pytest.mark.parametrize('heading', ['## Qualified target \xb7 role', '\ub300\uc0c1:'])
def test_should_supply_and_check_received_packet_without_pin_block(runtime, heading):
    run, _, _ = runtime
    prompt = NO_PIN_PACKET.replace('## 1. Qualified target \xb7 role', heading)
    supplied = run('UserPromptSubmit', prompt=prompt)
    assert 'Received handoff:' in supplied.stdout
    output = json.loads(run('Stop', last_assistant_message='Done.').stdout)
    assert output['decision'] == 'block'
    for name in PIN_NAMES[:8]:
        assert 'missing recipient pin label: ' + name in output['reason']
    assert module().recipient(PROMPT + prompt) is False


def test_should_require_base_and_explicitly_named_recipient_pins(runtime):
    run, _, _ = runtime
    prompt = NO_PIN_PACKET + '\npin sources[4].revision=unavailable\n'
    run('UserPromptSubmit', prompt=prompt)
    output = json.loads(run('Stop', last_assistant_message=RECIPIENT_LABELS).stdout)
    assert 'missing recipient pin label: sources[4].revision' in output['reason']


@pytest.mark.parametrize(('pin', 'path', 'command'), [
    ('sources[0].digest', 'src/example.py', 'shasum -a 256 src/example.py'),
    ('sources[0].digest', 'src/example.py', 'sha256sum src/example.py'),
    ('sources[0].digest', 'src/example.py', 'openssl dgst -sha256 src/example.py'),
    ('sources[0].digest', 'src/example.py',
     'python3 -c "import hashlib; '
     'print(hashlib.sha256(open(\'src/example.py\', \'rb\').read()).hexdigest())"'),
    ('mapping.digest', '.mir/ontology-map.json', 'sha256sum .mir/ontology-map.json'),
    ('contract.digest', 'schema/contract.json', 'shasum -a 256 schema/contract.json'),
    ('sources[0].revision', 'src/example.py', 'git log -1 --format=%H -- src/example.py'),
    ('sources[0].revision', 'src/example.py', 'git rev-list -1 HEAD -- src/example.py'),
    ('head', None, 'git rev-parse HEAD'),
    ('sources[0].digest', 'src/example.py',
     'python3 scripts/mir_ontology.py mapping --handoff src/example.py'),
])
def test_should_require_computing_command_for_verified_digest_revision_and_head(
    runtime, pin, path, command,
):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT + '\ncontract_path: schema/contract.json')
    body = RECIPIENT_LABELS.replace('pin ' + pin + '=parent-supplied',
                                    'pin ' + pin + '=verified-in-repo')
    append_tool(repo, 'claude', 'Read', {'file_path': path or str(repo)})
    rejected = json.loads(run('Stop', last_assistant_message=body).stdout)
    assert rejected['decision'] == 'block', rejected
    assert 'verified-in-repo pin lacks this-turn computation: ' + pin in rejected['reason']
    append_tool(repo, 'codex', 'exec_command', {'cmd': command})
    assert run('Stop', last_assistant_message=body).stdout == ''


@pytest.mark.parametrize('command', [
    'sha256sum src/other.py', 'git log -1 -- src/example.py',
    'python3 scripts/mir_ontology.py mapping --handoff src/other.py',
])
def test_should_not_accept_unrelated_command_as_digest_verification(runtime, command):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    append_tool(repo, 'codex', 'exec_command', {'cmd': command})
    body = RECIPIENT_LABELS.replace('sources[0].digest=parent-supplied',
                                    'sources[0].digest=verified-in-repo')
    output = json.loads(run('Stop', last_assistant_message=body).stdout)
    assert 'verified-in-repo pin lacks this-turn computation: sources[0].digest' in output['reason']


def test_should_require_stated_limitation_when_recipient_has_no_local_tools(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    labels = '\n'.join('pin ' + name + '=parent-supplied' for name in PIN_NAMES)
    output = json.loads(run('Stop', last_assistant_message=labels).stdout)
    assert 'no local check and no stated limitation' in output['reason']
    limited = labels + '\nNo local check was performed.'
    assert run('Stop', last_assistant_message=limited).stdout == ''
    append_tool(repo, 'claude', 'Read', {'file_path': 'src/example.py'})
    assert run('Stop', last_assistant_message=labels).stdout == ''


def append_block(repo, shape, reason='Repair handoff once: abbreviated hex value: head'):
    output = json.dumps({'decision': 'block', 'reason': reason})
    row = ({'type': 'system', 'subtype': 'hook_response', 'hookName': 'Stop',
            'command': 'python3 handoff_packet.py', 'stdout': output} if shape == 'claude' else
           {'type': 'event_msg', 'payload': {'type': 'hook_response', 'hook_name': 'Stop',
            'command': 'python3 handoff_packet.py', 'stdout': output}})
    with (repo / 'native-session.jsonl').open('a') as stream:
        stream.write(json.dumps(row) + '\n')


@pytest.mark.parametrize('shape', ['claude', 'codex'])
@pytest.mark.parametrize('receiving', [False, True])
def test_should_block_deterministic_defects_twice_then_always_allow(runtime, shape, receiving):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT if receiving else PROMPT)
    body = 'Done.' if receiving else packet() + '\nHEAD: abcdef123\n'
    first = run('Stop', last_assistant_message=body)
    assert json.loads(first.stdout)['decision'] == 'block'
    append_block(repo, shape, json.loads(first.stdout)['reason'])
    second = run('Stop', last_assistant_message=body, stop_hook_active=True)
    output = json.loads(second.stdout)
    assert output.get('decision') == 'block', output
    assert ('missing recipient pin label' if receiving else 'abbreviated hex') in output['reason']
    assert 'no local check' not in output['reason']
    append_block(repo, shape, output['reason'])
    third = run('Stop', last_assistant_message=body, stop_hook_active=True)
    assert 'decision' not in json.loads(third.stdout or '{}')


def test_should_only_retry_deterministic_subset_and_ignore_prior_turn_blocks(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    append_block(repo, 'claude')
    body = packet().replace('Temporal: current\n', '').replace(
        'May: read src/example.py;', 'May: edit files;')
    result = run('Stop', last_assistant_message=body, stop_hook_active=True)
    assert 'decision' not in json.loads(result.stdout or '{}')
    run('UserPromptSubmit', prompt=PROMPT)
    result = run('Stop', last_assistant_message=packet() + '\nHEAD: abcdef123',
                 stop_hook_active=True)
    assert 'decision' not in json.loads(result.stdout or '{}')


def test_should_recheck_exclusions_without_runner_on_second_no_command_block(runtime):
    run, _, repo = runtime
    body = NO_PIN_PACKET + '\nPRIVATE-CANARY-42'
    first = no_command_turn(runtime, body)
    assert json.loads(first.stdout).get('decision') == 'block'
    append_block(repo, 'claude', json.loads(first.stdout)['reason'])
    second = run('Stop', last_assistant_message=body, stop_hook_active=True)
    assert json.loads(second.stdout).get('decision') == 'block'
    assert not (repo / 'RUNNER_CALLED').exists()


def test_should_recheck_missing_cited_pins_on_second_block(runtime):
    run, _, repo = runtime
    (repo / 'src').mkdir()
    (repo / 'src/cited.py').write_text('VALUE = 1\n')
    cited = PINS.replace('src/example.py', 'src/cited.py').replace('d' * 40, '1' * 40)
    (repo / 'scripts/mir_ontology.py').write_text(
        f'import sys\nprint({cited!r} if sys.argv[3:] == ["src/cited.py"] else {PINS!r})\n')
    run('UserPromptSubmit', prompt=PROMPT)
    append_block(repo, 'claude')
    result = run('Stop', last_assistant_message=packet() + '\nInspect src/cited.py',
                 stop_hook_active=True)
    assert 'missing cited-source pins' in json.loads(result.stdout).get('reason', '')


@pytest.mark.parametrize('header', ['## handoff pins:', '### pins', '**handoff pins:**'])
def test_should_reject_supplied_pins_header_alteration(header):
    hook = module()
    result = hook.check_packet(packet().replace('handoff pins:', header),
                               {'pins': PINS, 'owner': hook.owner_sections(PROMPT)})
    assert "supplied pins header altered (keep the literal 'handoff pins:' line)" in result


def test_should_reject_altered_pins_header_after_observation_time_changes():
    hook = module()
    fresh = PINS.replace('2026-10-22T01:02:03Z', '2026-10-22T01:02:04Z')
    result = hook.check_packet(packet().replace('handoff pins:', '## handoff pins:'),
                               {'pins': fresh, 'owner': hook.owner_sections(PROMPT)})
    assert "supplied pins header altered (keep the literal 'handoff pins:' line)" in result


def test_should_block_abbreviated_revision_in_markdown_table_without_runner(runtime):
    body = NO_PIN_PACKET + '\n| path | last-change revision | sha256 |\n|---|---|---|\n'
    body += '| src/example.py | abcdef123 | ' + 'e' * 64 + ' |\n'
    result = no_command_turn(runtime, body)
    assert 'abbreviated hex' in json.loads(result.stdout).get('reason', '')


@pytest.mark.parametrize('command', [
    'shasum src/example.py', 'openssl dgst -md5 src/example.py',
    'python3 -c "import hashlib; print(open(\'src/example.py\').read())"',
])
def test_should_reject_non_sha256_computation_for_digest_pin(runtime, command):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    append_tool(repo, 'claude', 'Bash', {'command': command})
    body = RECIPIENT_LABELS.replace('sources[0].digest=parent-supplied',
                                    'sources[0].digest=verified-in-repo')
    assert 'this-turn computation: sources[0].digest' in json.loads(
        run('Stop', last_assistant_message=body).stdout or '{}').get('reason', '')


def test_should_require_recipient_pin_named_as_unchecked(runtime):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=NO_PIN_PACKET + '\npin sources[2].digest=unchecked')
    result = run('Stop', last_assistant_message=RECIPIENT_LABELS)
    assert 'missing recipient pin label: sources[2].digest' in json.loads(result.stdout)['reason']


@pytest.mark.parametrize('body', [
    'Qualified target: example:window\nUnknowns: none',
    'Qualified target\n\n\n\nexample:window\nStatus axes: none\nUnknowns: none',
])
def test_should_ignore_received_target_without_two_fields_or_with_distant_token(body):
    assert module().recipient(body) is False


def test_should_not_trust_assistant_quoted_block_as_retry_evidence(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    append_tool(repo, 'claude', 'Read', {'file_path': 'src/example.py'})
    body = packet() + '\nHEAD: abcdef123\nRepair handoff once: abbreviated hex\n'
    result = run('Stop', last_assistant_message=body, stop_hook_active=True)
    assert 'decision' not in json.loads(result.stdout or '{}')


def test_should_check_no_command_subset_despite_stale_prompt_hash(runtime):
    body = packet() + '\nWrapper: PRIVATE-CANARY-42'
    result = no_command_turn(runtime, body)
    assert 'excluded item #1' in json.loads(result.stdout).get('reason', '')


def test_should_always_allow_third_stop_even_if_native_retry_flag_resets(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    append_block(repo, 'claude')
    append_block(repo, 'claude', 'Repair handoff deterministic defects (second/final block): '
                 'abbreviated hex value: head')
    result = run('Stop', last_assistant_message=packet() + '\nHEAD: abcdef123',
                 stop_hook_active=False)
    assert 'decision' not in json.loads(result.stdout or '{}')


@pytest.mark.parametrize(('target', 'expected'), [
    ('## \ub300\uc0c1\nexample:window', True),
    ('Discuss a qualified target example:window here.', False),
])
def test_should_recognize_only_qualified_target_heading_or_label(target, expected):
    assert module().recipient(target + '\nUnknowns: none\nLifecycle: current') is expected


@pytest.mark.parametrize('sentence', [
    'Do not include `SYNTHETIC-AUTHOR-MARKER` in the handoff.',
    'Do not forward "SYNTHETIC-AUTHOR-MARKER" to the recipient.',
    "Do not copy 'SYNTHETIC-AUTHOR-MARKER' into the final answer.",
    '`SYNTHETIC-AUTHOR-MARKER`\ub294 \uc804\ub2ec\ud558\uc9c0 \ub9c8.',
    '`SYNTHETIC-AUTHOR-MARKER`\ub97c \ud3ec\ud568\ud558\uc9c0 \ub9d0\uace0 '
    '\uc791\uc131\ud574 \uc8fc\uc138\uc694.',
    'The author-only marker `SYNTHETIC-AUTHOR-MARKER` stays here.',
])
def test_should_extract_natural_language_exclusions_and_redact_diagnostics(sentence):
    hook = module()
    owner = hook.owner_sections(PROMPT + sentence)
    assert owner['excluded'] == ['PRIVATE-CANARY-42', 'SYNTHETIC-AUTHOR-MARKER']
    defects = hook.authority_defects(packet() + '\nSYNTHETIC-AUTHOR-MARKER', owner)
    assert 'excluded item #2 appears in forwarded artifact' in defects
    assert all('SYNTHETIC-AUTHOR-MARKER' not in defect for defect in defects)
    assert hook.owner_sections('Do not copy unquoted words.')['excluded'] == []
    assert hook.owner_sections('Read `public.py`; do not edit it.')['excluded'] == []
    assert hook.owner_sections('> Do not forward `example`.')['excluded'] == []


@pytest.mark.parametrize('particle', ['', '\ub294', '\uc740', '\ub97c', '\uc744',
                                      '\uc774', '\uac00'])
@pytest.mark.parametrize('verb', [
    '\uc804\ub2ec\ud558\uc9c0 \uc54a\ub294', '\uc804\ub2ec\ud558\uc9c0 \ub9d0\uace0',
    '\ud3ec\ud568\ud558\uc9c0 \uc54a\ub294', '\ud3ec\ud568\ud558\uc9c0 \ub9d0\uace0',
])
def test_should_extract_only_unquoted_korean_excluded_identifier(particle, verb):
    hook = module()
    sentence = ('\uac1c\ubc1c\uc6a9 SYNTHETIC_ALLOWED_42\ub294 \ud5c8\uc6a9\ud558\uace0 '
                'SYNTHETIC_PRIVATE_42' + particle + ' ' + verb + ' payload \uc124\uacc4')
    owner = hook.owner_sections(sentence)
    assert owner['excluded'] == ['SYNTHETIC_PRIVATE_42']
    defects = hook.authority_defects('Wrapper: SYNTHETIC_PRIVATE_42', owner)
    assert 'excluded item #1 appears in forwarded artifact' in defects
    assert all('SYNTHETIC_PRIVATE_42' not in defect for defect in defects)


@pytest.mark.parametrize('sentence', [
    'Allow SYNTHETIC_ALLOWED_42; do not forward SYNTHETIC_PRIVATE_42.',
    'Allow SYNTHETIC_ALLOWED_42; do not include SYNTHETIC_PRIVATE_42.',
    'SYNTHETIC_ALLOWED_42 is allowed; SYNTHETIC_PRIVATE_42 must not be forwarded.',
])
def test_should_extract_only_unquoted_english_excluded_identifier(sentence):
    hook = module()
    owner = hook.owner_sections(sentence)
    assert owner['excluded'] == ['SYNTHETIC_PRIVATE_42']
    assert hook.authority_defects('SYNTHETIC_PRIVATE_42', owner) == [
        'excluded item #1 appears in forwarded artifact']


@pytest.mark.parametrize('sentence', [
    'SYNTHETIC_ALLOWED_42\ub294 \ud5c8\uc6a9\ud569\ub2c8\ub2e4.',
    'Do not forward ordinary_words.',
    'Do not include abcSYNTHETIC_PRIVATE_42.',
    'Do not forward SYNTHETIC_PRIVATE_42suffix.',
    '> Do not forward SYNTHETIC_PRIVATE_42.',
    '```\nDo not include SYNTHETIC_PRIVATE_42.\n```',
])
def test_should_ignore_allowed_or_non_identifier_exclusion_examples(sentence):
    assert module().owner_sections(sentence)['excluded'] == []


@pytest.mark.parametrize(('restriction', 'expected'), [
    ('May not: modify files outside probes/.', False),
    ('May not: edit files other than the handler.', False),
    ('May not: change files under config/**.', False),
    ('May not: write files except the handler.', False),
    ('May not: modify files beyond probes/.', False),
    ('May not: edit files besides the handler.', False),
    ('May not: change files in config/**.', False),
    ('May not: write files not listed here.', False),
    ('May not: write files; only outside probes/.', True),
    ('May not: only write files in config/**.', False),
    ('May not: probes/ \uc678 \ud30c\uc77c \uc218\uc815.', False),
    ('May not: probes/ \ubc16 \ud30c\uc77c \uc218\uc815.', False),
    ('May not: handler \uc774\uc678 \ud30c\uc77c \uc218\uc815.', False),
    ('May not: handler \uc81c\uc678 \ud30c\uc77c \uc218\uc815.', False),
    ('May not: probes/ \ubc94\uc704 \ubc16 \ud30c\uc77c \uc218\uc815.', False),
    ('May not: write files.', True),
    ('No file changes', True),
    ('\ud30c\uc77c \uc218\uc815 \uae08\uc9c0', True),
    ('\ud30c\uc77c\uc744 \uc218\uc815\ud558\uc9c0 \ub9d0\uace0', True),
    ('May not: modify files outside probes/. No file changes.', True),
    ('May not: write files; edit files other than the handler.', True),
    ('May not: change files under config/**; write files.', True),
    ('No file changes.\nMay not: edit files other than the handler.', True),
])
def test_should_restrict_files_only_for_unqualified_bans(restriction, expected):
    hook = module()
    owner = hook.owner_sections(restriction)
    assert hook.files_restricted(owner) is expected
    assert bool(hook.tool_attempt_rule(owner)) is expected


@pytest.mark.parametrize('restriction', [
    'May not: modify files outside probes/.',
    'May not: edit files other than the handler.',
    'May not: change files under config/**.',
])
@pytest.mark.parametrize('tool', ['Write', 'Edit', 'functions.apply_patch'])
@pytest.mark.parametrize('receiving', [False, True])
def test_should_allow_file_tools_when_owner_only_prohibits_scoped_edits(
        runtime, restriction, tool, receiving):
    run, _, _ = runtime
    base = (RECIPIENT_PROMPT if receiving else PROMPT).replace(
        'May not: edit files; run tests\n', '')
    run('UserPromptSubmit', prompt=base + '\n' + restriction)
    result = run('PreToolUse', tool_name=tool, tool_input={})
    assert result.returncode == 0 and result.stdout == ''


@pytest.mark.parametrize('sentence', [
    'Do not run commands; answer from the sources.',
    'No commands. Read only.',
])
def test_should_detect_unlabelled_english_command_bans(runtime, sentence):
    hook = module()
    prompt = 'Write a handoff for another agent.\n' + sentence
    assert sentence.split(';')[0].split('.')[0] in hook.owner_sections(prompt)['may_not']
    assert hook.restricted(prompt)
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=prompt)
    denied = run('PreToolUse', tool_name='functions.exec_command', tool_input={'cmd': 'pwd'})
    assert denied.returncode == 2
    assert json.loads(denied.stdout)['hookSpecificOutput']['permissionDecision'] == 'deny'


def append_code_mode(repo, code):
    with (repo / 'native-session.jsonl').open('a') as stream:
        stream.write(json.dumps({'type': 'response_item', 'payload': {
            'type': 'custom_tool_call', 'name': 'exec', 'input': code}}) + '\n')


@pytest.mark.parametrize('tool', [
    'mcp__node_repl__js', 'functions.mcp__node_repl__js', 'js', 'js_reset',
    'mcp__node_repl__js_reset', 'python', 'python_repl', 'mcp__python_repl__exec',
    'mcp__python__python', 'mcp__js_repl__execute', 'mcp__javascript_repl__execute',
])
@pytest.mark.parametrize('receiving', [False, True])
def test_should_deny_interpreters_only_in_command_forbidden_handoffs(runtime, tool, receiving):
    run, _, _ = runtime
    base = RECIPIENT_PROMPT if receiving else PROMPT
    for prompt, denied in ((base + '\nNo commands.', True), (base, False),
                           ('Inspect source only. No commands.', False)):
        run('UserPromptSubmit', prompt=prompt)
        result = run('PreToolUse', tool_name=tool, tool_input={'code': '1 + 1'})
        assert result.returncode == (2 if denied else 0)
        if denied:
            output = json.loads(result.stdout)['hookSpecificOutput']
            assert output['permissionDecision'] == 'deny'
            assert ('Owner forbids commands in this handoff turn'
                    in output['permissionDecisionReason'])
        else:
            assert result.stdout == ''


@pytest.mark.parametrize('code', [
    'await tools.mcp__node_repl__js({code: "read synthetic source"});',
    'await tools.js({code: "1 + 1"});',
    'await tools.js_reset();',
    'await tools.mcp__python_repl__exec({code: "print(1)"});',
    'await tools.exec_command({cmd: "cat src/example.py"});',
    'await tools.exec_command({cmd: command});',
    'await tools.exec_command(options);',
    'await tools.shell_command({command: `cat ${path}`});',
])
@pytest.mark.parametrize('input_shape', ['raw', 'input', 'code'])
@pytest.mark.parametrize('receiving', [False, True])
def test_should_deny_static_nested_commands_but_allow_discovery(
        runtime, code, input_shape, receiving):
    run, _, _ = runtime
    base = RECIPIENT_PROMPT if receiving else PROMPT
    tool_input = code if input_shape == 'raw' else {input_shape: code}
    for prompt, denied in ((base + '\nNo commands.', True), (base, False),
                           ('Inspect source only. No commands.', False)):
        run('UserPromptSubmit', prompt=prompt)
        result = run('PreToolUse', tool_name='functions.exec', tool_input=tool_input)
        assert result.returncode == (2 if denied else 0)
    run('UserPromptSubmit', prompt=base + '\nNo commands.')
    for safe in ('text(ALL_TOOLS.filter(x => /read/.test(x.name)));',
                 'text(await tools.read_file({path: "src/example.py"}));',
                 'text(' + json.dumps(code) + '); /* ' + code + ' */\n// ' + code):
        result = run('PreToolUse', tool_name='exec', tool_input={'input': safe})
        assert result.returncode == 0 and result.stdout == ''


@pytest.mark.parametrize('shape', ['claude', 'codex', 'code-mode'])
def test_should_count_interpreters_as_commands_without_read_evidence(runtime, shape):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT + '\nNo commands.')
    code = ('const paths = ["src/example.py", "src/helper.py", "tests/example.py", '
            '"docs/example.md", "config/example.json", "scripts/example.py"]; '
            'for (const path of paths) { await fs.readFile(path, "utf8"); }')
    if shape == 'code-mode':
        # Same three-call shape as the defect capture, using synthetic source names only.
        append_code_mode(repo, 'text(ALL_TOOLS.map(x => x.name));')
        append_code_mode(repo, 'text(ALL_TOOLS.filter(x => /read/.test(x.name)));')
        append_code_mode(repo, 'await tools.mcp__node_repl__js({code: '
                         + json.dumps(code) + '});')
    else:
        append_tool(repo, shape, 'mcp__node_repl__js', {'code': code})
    hook = module()
    calls, reads, _ = hook.turn_tools({
        'cwd': str(repo), 'transcript_path': str(repo / 'native-session.jsonl')})
    assert any(name in hook.SHELL_TOOLS for name, _ in calls)
    assert reads == []


@pytest.mark.parametrize('receiving', [False, True])
def test_should_supply_interpreter_ban_and_preserve_file_only_split(runtime, receiving):
    run, _, _ = runtime
    base = (RECIPIENT_PROMPT if receiving else PROMPT).replace(
        'May not: edit files; run tests\n', '')
    result = run('UserPromptSubmit', prompt=base + '\nNo commands.')
    context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    assert 'code interpreters (for example node_repl or a Python REPL)' in context
    assert 'attempts are compliance failures even if denied.' in context
    result = run('UserPromptSubmit', prompt=base + '\nNo file changes.')
    context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    assert 'Shell tools' not in context and 'code interpreters' not in context
    assert ('Write/Edit/apply_patch and file-writing tools must not be called in this turn'
            in context)
    assert (PINS in context if not receiving else 'Received handoff' in context)


@pytest.mark.parametrize('shape', ['claude', 'codex', 'code-mode'])
@pytest.mark.parametrize('receiving', [False, True])
def test_should_require_command_ban_compliance_failure_in_artifact(runtime, shape, receiving):
    run, _, repo = runtime
    base = RECIPIENT_PROMPT if receiving else PROMPT
    run('UserPromptSubmit', prompt=base + '\nNo commands.')
    if shape == 'code-mode':
        append_code_mode(repo, 'await tools.mcp__node_repl__js({code: "1 + 1"});')
    else:
        append_tool(repo, shape, 'mcp__node_repl__js', {'code': '1 + 1'})
    body = RECIPIENT_LABELS if receiving else NO_PIN_PACKET
    result = run('Stop', last_assistant_message=body)
    reason = json.loads(result.stdout or '{}').get('reason', '')
    assert 'command-ban compliance failure' in reason
    assert 'no non-command reader was used/available' not in reason
    for acknowledgement in (
        '\nCompliance failure: executed a code interpreter under the command ban.',
        '\n\uba85\ub839 \uae08\uc9c0 \uc9c0\uc2dc \uc704\ubc18: '
        '\ucf54\ub4dc \uc778\ud130\ud504\ub9ac\ud130\ub97c \uc2e4\ud589\ud588\uc2b5\ub2c8\ub2e4.',
    ):
        repaired = run('Stop', last_assistant_message=body + acknowledgement)
        assert 'decision' not in json.loads(repaired.stdout or '{}')
    # Resetting the turn discards the earlier interpreter call.
    run('UserPromptSubmit', prompt=base + '\nNo commands.')
    append_tool(repo, 'claude', 'Read', {'file_path': 'src/example.py'})
    assert 'decision' not in json.loads(run('Stop', last_assistant_message=body).stdout or '{}')


@pytest.mark.parametrize('receiving', [False, True])
def test_should_reject_interpreter_reads_as_verified_even_after_failure_disclosure(
        runtime, receiving):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=(RECIPIENT_PROMPT if receiving else PROMPT) + '\nNo commands.')
    append_code_mode(repo, 'await tools.mcp__node_repl__js({code: '
                     '"await fs.readFile(\'src/example.py\', \'utf8\')"});')
    body = (RECIPIENT_LABELS if receiving else NO_PIN_PACKET)
    result = run('Stop', last_assistant_message=body)
    assert 'command-ban compliance failure' in json.loads(result.stdout or '{}').get('reason', '')
    body += ('\nCompliance failure: executed an interpreter under the command ban.'
             '\nPath verified-in-repo: src/example.py')
    body += '\npin repository_root=verified-in-repo\npin mapping.identity=verified-in-repo'
    reason = json.loads(run('Stop', last_assistant_message=body).stdout)['reason']
    assert 'verified-in-repo path lacks this-turn tool reference: src/example.py' in reason
    assert 'verified-in-repo pin lacks this-turn tool reference: repository_root' in reason
    assert 'verified-in-repo pin lacks this-turn tool reference: mapping.identity' in reason
    assert 'no non-command reader was used/available' not in reason


@pytest.mark.parametrize('receiving', [False, True])
def test_should_retry_command_ban_compliance_defect_once_then_allow_stop(runtime, receiving):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=(RECIPIENT_PROMPT if receiving else PROMPT) + '\nNo commands.')
    append_code_mode(repo, 'await tools.js_reset();')
    # A real reader cannot erase the command-ban failure.
    append_tool(repo, 'claude', 'Read', {'file_path': 'src/example.py'})
    body = RECIPIENT_LABELS if receiving else NO_PIN_PACKET
    append_hook_prompt(repo, 'Repair handoff once: missing field', 'stop:1:/synthetic/hooks.json')
    result = run('Stop', last_assistant_message=body, stop_hook_active=True)
    reason = json.loads(result.stdout or '{}').get('reason', '')
    assert 'second/final block' in reason and 'command-ban compliance failure' in reason
    append_hook_prompt(repo, reason, 'stop:2:/synthetic/hooks.json')
    result = run('Stop', last_assistant_message=body, stop_hook_active=True)
    assert 'decision' not in json.loads(result.stdout or '{}')


def test_should_count_code_mode_calls_as_local_checks(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    append_code_mode(repo, 'text(await tools.exec_command({cmd:"pwd"}));')
    body = RECIPIENT_LABELS.split('\nNo local check', 1)[0]
    assert run('Stop', last_assistant_message=body).stdout == ''


@pytest.mark.parametrize('code', [
    'const r = await tools.exec_command({cmd:"shasum -a 256 src/example.py\\n'
    'git log -1 src/example.py\\ngit rev-parse HEAD"}); text(r.output);',
    "await tools.exec_command({cmd:'shasum -a 256 src/example.py; "
    "git log -1 src/example.py; git rev-parse HEAD'});",
    'await Promise.allSettled([tools.exec_command({cmd:`shasum -a 256 src/example.py; '
    'git log -1 src/example.py; git rev-parse HEAD`})]);',
])
def test_should_expose_code_mode_commands_to_pin_verification(runtime, code):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    append_code_mode(repo, code)
    body = RECIPIENT_LABELS
    for name in ('head', 'sources[0].digest', 'sources[0].revision'):
        body = body.replace(name + '=parent-supplied', name + '=verified-in-repo')
    body += '\nVerified: src/example.py verified-in-repo'
    assert run('Stop', last_assistant_message=body).stdout == ''
    # Merely quoting a shell call inside JS text/comments cannot supply computation.
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    append_code_mode(repo, 'text(' + json.dumps(code) + '); /* ' + code + ' */')
    result = run('Stop', last_assistant_message=body)
    assert 'lacks this-turn computation' in json.loads(result.stdout)['reason']


def append_hook_prompt(repo, reason, run_id, shape='both'):
    text = f'<hook_prompt hook_run_id="{run_id}">{reason}</hook_prompt>'
    rows = []
    if shape in {'response', 'both'}:
        rows.append({'type': 'response_item', 'payload': {
            'type': 'message', 'id': run_id, 'role': 'user',
            'content': [{'type': 'input_text', 'text': text}]}})
    if shape in {'event', 'both'}:
        rows.append({'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': {
            'type': 'HookPrompt', 'id': run_id,
            'fragments': [{'text': reason, 'hookRunId': run_id}]}}})
    with (repo / 'native-session.jsonl').open('a') as stream:
        stream.write(''.join(json.dumps(row) + '\n' for row in rows))


@pytest.mark.parametrize('shape', ['response', 'event', 'both'])
def test_should_preserve_owner_and_count_codex_hook_prompt_once(runtime, shape):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT + 'No commands.')
    (repo / 'native-session.jsonl').write_text(json.dumps({
        'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
        'content': [{'type': 'input_text', 'text': PROMPT + 'No commands.'}]}}) + '\n')
    append_tool(repo, 'codex', 'Read', {'file_path': 'src/example.py'})
    body = NO_PIN_PACKET + '\nPRIVATE-CANARY-42'
    first = json.loads(run('Stop', last_assistant_message=body).stdout)
    append_hook_prompt(repo, first['reason'], 'stop:1:/synthetic/hooks/hooks.json', shape)
    event = {'cwd': str(repo), 'transcript_path': str(repo / 'native-session.jsonl')}
    hook = module()
    assert hook.prior_blocks(event) == 1
    assert hook.current_turn(event)[0] == PROMPT + 'No commands.'
    assert hook.turn_tools(event)[1] == ['src/example.py']
    second = json.loads(run('Stop', last_assistant_message=body, stop_hook_active=True).stdout)
    assert second.get('decision') == 'block'
    append_hook_prompt(repo, second['reason'], 'stop:2:/synthetic/hooks/hooks.json', shape)
    assert hook.prior_blocks(event) == 2
    third = run('Stop', last_assistant_message=body, stop_hook_active=True)
    assert 'decision' not in json.loads(third.stdout or '{}')
    run('UserPromptSubmit', prompt=PROMPT)
    assert hook.prior_blocks(event) is None


@pytest.mark.parametrize('quoted', [
    'Do not run the "Never run" commands above.',
    '> Do not run commands.\n```\nNo commands.\n```',
    'The packet says "Do not run commands"; compare revisions and digests.',
])
def test_should_allow_revision_checks_despite_quoted_command_examples(runtime, quoted):
    run, _, _ = runtime
    prompt = RECIPIENT_PROMPT + '\n' + quoted + '\nCompare the local revision and digest.'
    assert not module().restricted(prompt)
    run('UserPromptSubmit', prompt=prompt)
    result = run('PreToolUse', tool_name='functions.exec_command',
                 tool_input={'cmd': 'git rev-parse HEAD'})
    assert result.returncode == 0 and result.stdout == ''
    assert module().restricted(prompt + '\nDo not run commands.')


@pytest.mark.parametrize('mode', ['author', 'no-command', 'recipient'])
def test_should_reject_target_namespace_mismatch_read_only(runtime, mode):
    run, _, repo = runtime
    (repo / '.mir').mkdir()
    mapping = repo / '.mir/ontology-map.json'
    original = json.dumps({'namespace': 'local-project'})
    mapping.write_text(original)
    prompt = RECIPIENT_PROMPT if mode == 'recipient' else PROMPT
    if mode == 'no-command':
        prompt += 'No commands.'
    run('UserPromptSubmit', prompt=prompt)
    body = (packet() if mode != 'recipient' else
            'Qualified target: example:review\n' + RECIPIENT_LABELS)
    result = run('Stop', last_assistant_message=body)
    defect = 'qualified target namespace example differs from map namespace local-project'
    assert defect in json.loads(result.stdout)['reason']
    assert mapping.read_text() == original
    # Matching namespaces and parse errors must not invent a namespace defect.
    for content in (json.dumps({'namespace': 'example'}), '{bad json', '[]', '{}'):
        mapping.write_text(content)
        result = run('Stop', last_assistant_message=body)
        assert 'differs from map namespace' not in result.stdout


def test_should_accept_only_reviewed_namespace_aliases(runtime):
    run, _, repo = runtime
    (repo / '.mir').mkdir()
    mapping = repo / '.mir/ontology-map.json'
    alias = {'namespace': 'example', 'reviewed': False, 'evidence': 'docs/review.md'}
    data = {'namespace': 'local-project', 'namespace_aliases': [alias]}
    mapping.write_text(json.dumps(data))
    run('UserPromptSubmit', prompt=PROMPT + 'No commands.')
    result = run('Stop', last_assistant_message=NO_PIN_PACKET)
    assert 'differs from map namespace' in json.loads(result.stdout)['reason']
    alias['reviewed'] = True
    mapping.write_text(json.dumps(data))
    result = run('Stop', last_assistant_message=NO_PIN_PACKET)
    assert 'differs from map namespace' not in result.stdout
    alias['evidence'] = ''
    mapping.write_text(json.dumps(data))
    assert 'differs from map namespace' in run('Stop', last_assistant_message=NO_PIN_PACKET).stdout


@pytest.mark.parametrize('restriction', ['No commands.', 'No file changes.'])
@pytest.mark.parametrize('receiving', [False, True])
def test_should_supply_forbidden_tool_attempt_rule(runtime, restriction, receiving):
    run, _, _ = runtime
    base = (RECIPIENT_PROMPT if receiving else PROMPT).replace(
        'May not: edit files; run tests\n', '')
    prompt = base + '\n' + restriction
    result = run('UserPromptSubmit', prompt=prompt)
    context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    shell = ('Shell tools and code interpreters (for example node_repl or a Python REPL) '
             'must not be called in this turn')
    files = 'Write/Edit/apply_patch and file-writing tools must not be called in this turn'
    assert context.count(files if 'file' in restriction else shell) == 1
    assert 'attempts are compliance failures even if denied.' in context
    if 'file' in restriction:
        # Round j: a file-only ban must not tell the agent that commands are forbidden.
        assert shell not in context and 'Shell,' not in context


@pytest.mark.parametrize('tool', ['Write', 'Edit', 'MultiEdit', 'NotebookEdit',
                                 'apply_patch', 'functions.apply_patch'])
@pytest.mark.parametrize('receiving', [False, True])
def test_should_deny_file_write_tools_in_file_forbidden_handoff(runtime, tool, receiving):
    run, _, _ = runtime
    base = (RECIPIENT_PROMPT if receiving else PROMPT).replace(
        'May not: edit files; run tests\n', '')
    prompt = base + '\nNo file changes.'
    run('UserPromptSubmit', prompt=prompt)
    denied = run('PreToolUse', tool_name=tool, tool_input={})
    assert denied.returncode == 2
    output = json.loads(denied.stdout)['hookSpecificOutput']
    assert output['hookEventName'] == 'PreToolUse' and output['permissionDecision'] == 'deny'
    assert 'file changes' in output['permissionDecisionReason']
    # Only the handoff's owner restriction activates this guard.
    for allowed_prompt in ('Fix this bug. No file changes.',
                           'Write a handoff for another agent.\nMay: edit files'):
        run('UserPromptSubmit', prompt=allowed_prompt)
        allowed = run('PreToolUse', tool_name=tool, tool_input={})
        assert allowed.returncode == 0 and allowed.stdout == ''


@pytest.mark.parametrize('label', [
    '\ub300\uc0c1(Qualified target):', 'Qualified target (\ub300\uc0c1):',
    '**\ub300\uc0c1 (Qualified target):**', '**Qualified target(\ub300\uc0c1)**:',
    '## \ub300\uc0c1 (Qualified target):',
])
def test_should_require_base_pins_for_parenthetical_recipient_target(runtime, label):
    run, _, _ = runtime
    prompt = RECIPIENT_PROMPT.replace('Qualified target:', label)
    assert module().recipient(prompt)
    assert 'Received handoff:' in run('UserPromptSubmit', prompt=prompt).stdout
    output = json.loads(run('Stop', last_assistant_message='Done.').stdout)
    for name in PIN_NAMES[:8]:
        assert 'missing recipient pin label: ' + name in output['reason']


@pytest.mark.parametrize('label', [
    '\ub300\uc0c1(Qualified target):', 'Qualified target (\ub300\uc0c1):',
    '**\ub300\uc0c1 (Qualified target):**',
])
def test_should_check_parenthetical_author_target_and_namespace(tmp_path, label):
    hook = module()
    (tmp_path / '.mir').mkdir()
    mapping = tmp_path / '.mir/ontology-map.json'
    mapping.write_text(json.dumps({'namespace': 'example'}))
    body = packet().replace('Qualified target:', label)
    state = {'pins': PINS, 'owner': hook.owner_sections(PROMPT), 'root': tmp_path}
    assert hook.check_packet(body, state) == []
    mapping.write_text(json.dumps({'namespace': 'local-project'}))
    assert hook.namespace_defects(body, tmp_path) == [
        'qualified target namespace example differs from map namespace local-project']


@pytest.mark.parametrize('shape', ['claude', 'codex'])
@pytest.mark.parametrize('mode', ['author', 'no-command', 'recipient'])
def test_should_block_namespace_first_exposed_after_repair_only_twice(runtime, shape, mode):
    run, _, repo = runtime
    (repo / '.mir').mkdir()
    mapping = repo / '.mir/ontology-map.json'
    original = json.dumps({'namespace': 'local-project'})
    mapping.write_text(original)
    prompt = RECIPIENT_PROMPT if mode == 'recipient' else PROMPT
    if mode == 'no-command':
        prompt += 'No commands.'
    run('UserPromptSubmit', prompt=prompt)
    first_body = ('Done.' if mode == 'recipient' else
                  packet().replace('Qualified target:', 'Target identity:') + '\nHEAD: abcdef123')
    first = json.loads(run('Stop', last_assistant_message=first_body).stdout)
    assert first['decision'] == 'block'
    assert 'differs from map namespace' not in first['reason']
    append_block(repo, shape, first['reason'])
    body = (packet() if mode != 'recipient' else
            'Qualified target: example:review\n' + RECIPIENT_LABELS)
    second = json.loads(run('Stop', last_assistant_message=body, stop_hook_active=True).stdout
                        or '{}')
    assert second.get('decision') == 'block', second
    assert ('qualified target namespace example differs from map namespace local-project'
            in second['reason'])
    append_block(repo, shape, second['reason'])
    third = run('Stop', last_assistant_message=body, stop_hook_active=True)
    assert 'decision' not in json.loads(third.stdout or '{}')
    assert mapping.read_text() == original


def test_should_parse_pin_labels_in_separate_markdown_cells():
    body = ('| Pin | Value | Label | Reason |\n| --- | --- | --- | --- |\n'
            '| `head` | ' + 'a' * 40 + ' | **verified-in-repo** | git |\n'
            '| mapping.digest | ' + 'b' * 64 + ' | parent-supplied | inherited |\n'
            '| unavailable | sources[3].revision | no history | |\n')
    assert module().pin_claims(body) == [
        ('head', 'verified-in-repo'), ('mapping.digest', 'parent-supplied'),
        ('sources[3].revision', 'unavailable')]


@pytest.mark.parametrize('no_commands', [False, True])
def test_should_accept_recipient_pin_table_with_computation_or_reader(runtime, no_commands):
    run, _, repo = runtime
    prompt = RECIPIENT_PROMPT + ('\nNo commands.' if no_commands else '')
    run('UserPromptSubmit', prompt=prompt)
    body = '| Pin | Value | Label |\n| --- | --- | --- |\n'
    for name in PIN_NAMES:
        label = 'verified-in-repo' if name in {'head', 'mapping.version'} else 'parent-supplied'
        value = ('1.1.0' if name == 'mapping.version' else
                 'a' * 40 if name == 'head' else 'inherited')
        body += f'| {name} | {value} | {label} |\n'
    rejected = json.loads(run('Stop', last_assistant_message=body).stdout)
    assert 'lacks this-turn' in rejected['reason']
    assert 'missing recipient pin label' not in rejected['reason']
    if no_commands:
        append_tool(repo, 'claude', 'Read', {'file_path': '.git/HEAD'})
        append_tool(repo, 'claude', 'Read', {'file_path': '.mir/ontology-map.json'})
    else:
        append_code_mode(repo, 'await tools.exec_command({cmd:"git rev-parse HEAD; '
                         'python3 scripts/mir_ontology.py mapping --handoff src/example.py"});')
    assert run('Stop', last_assistant_message=body).stdout == ''


@pytest.mark.parametrize('text', [
    'Reason: parent-supplied\nreasons=unavailable\n\uc774\uc720: parent-supplied',
    'sha256: parent-supplied ' + 'a' * 64 + '\nrevision=unavailable',
    '| sha256 | revision |\n| ' + 'b' * 64 + ' | parent-supplied |',
])
def test_should_never_require_non_pin_prose_or_summary_headers(runtime, text):
    run, _, _ = runtime
    assert module().pin_claims(text) == []
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT + '\n' + text)
    assert run('Stop', last_assistant_message=RECIPIENT_LABELS).stdout == ''


@pytest.mark.parametrize('token', [
    '1.1.0', 'mir.common-semantics:review/item.v1', 'mapping.digest',
    'contract.version', 'sources[3].revision',
])
def test_should_ignore_non_path_tokens_but_require_real_verified_path(runtime, token):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    append_tool(repo, 'claude', 'Read', {'file_path': 'src/example.py'})
    body = RECIPIENT_LABELS + '\nSummary verified-in-repo: ' + token
    assert run('Stop', last_assistant_message=body).stdout == ''
    result = run('Stop', last_assistant_message=body + ' docs/unchecked.md')
    assert ('verified-in-repo path lacks this-turn tool reference: docs/unchecked.md'
            in json.loads(result.stdout)['reason'])


@pytest.mark.parametrize('may_not', [
    'May not: edit files; run tests; run commands other than `echo attest-probe`',
    'May not: run any commands except `echo attest-probe`.',
    'May not: execute shell besides `echo attest-probe`',
])
def test_should_read_a_command_ban_with_a_stated_exception_as_scoped(may_not):
    prompt = ('Write a handoff for another agent.\nSources: README.md\n'
              'May: read README.md; run `echo attest-probe` once\n' + may_not)
    assert not module().restricted(prompt)


def test_should_keep_a_blanket_command_ban_beside_a_scoped_clause():
    prompt = ('Write a handoff for another agent.\nSources: README.md\n'
              'May: read README.md\nMay not: run commands; edit files other than notes.md')
    assert module().restricted(prompt)
