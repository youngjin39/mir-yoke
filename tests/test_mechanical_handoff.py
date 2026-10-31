"""Offline contracts for stateless common mechanical handoff hooks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import locale
import os
import shlex
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
                       for key in ['identity', 'version'])
    output = json.loads(run('Stop', last_assistant_message=body + '\n' + claims).stdout)
    for key in ['identity', 'version']:
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
     'verified-in-repo digest needs a this-turn computation'),
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
            'pin mapping.identity=verified-in-repo .mir/ontology-map.json\n')
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


@pytest.mark.parametrize('receiving', [False, True])
@pytest.mark.parametrize('pin', ['contract.digest', 'mapping.digest', 'sources[0].sha256'])
def test_should_reject_read_only_verified_digest_under_command_ban(runtime, receiving, pin):
    run, _, repo = runtime
    prompt = (RECIPIENT_PROMPT if receiving else PROMPT) + '\nNo commands.'
    run('UserPromptSubmit', prompt=prompt)
    for path in ['schema/contract.json', '.mir/ontology-map.json', 'src/example.py']:
        append_tool(repo, 'claude', 'Read', {'file_path': path})
    body = (RECIPIENT_LABELS if receiving else NO_PIN_PACKET)
    body += '\ncontract_path: schema/contract.json\npin ' + pin + '=verified-in-repo'
    result = json.loads(run('Stop', last_assistant_message=body).stdout)
    assert 'verified-in-repo digest needs a this-turn computation' in result['reason']
    assert pin in result['reason']


@pytest.mark.parametrize('receiving', [False, True])
@pytest.mark.parametrize('search', [None, ('Grep', {'path': 'tests', 'pattern': 'item'}),
    ('Glob', {'glob': '{scripts,spec,tests,tools}/**', 'pattern': '*item*'})])
@pytest.mark.parametrize('claim', ['The item does not exist in the repository.',
                                 '\uc774 \ud56d\ubaa9\uc740 '
                                 '\uc800\uc7a5\uc18c\uc5d0\ub294 \uc5c6\uc74c.',
                                 'There is no dedicated reader in the repository.'])
def test_should_block_repository_absence_after_limited_or_no_search(
    runtime, receiving, search, claim,
):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT if receiving else PROMPT)
    if search:
        name, args = search
        if 'path' in args:
            args = {**args, 'path': str(repo / args['path'])}
        append_tool(repo, 'claude', name, args)
    body = (RECIPIENT_LABELS if receiving else packet()) + '\n' + claim
    result = json.loads(run('Stop', last_assistant_message=body).stdout)
    assert 'repository-wide absence claimed after searches limited to:' in result['reason']
    assert (('tests' if search[0] == 'Grep' else '{scripts,spec,tests,tools}/**')
            if search else 'no searches') in result['reason']


@pytest.mark.parametrize('claim', ['Item absent in repository tests/ only.',
    '\uc800\uc7a5\uc18c tests/ \ubc94\uc704 \uc548\uc5d0\uc11c '
    '\ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.',
    'A hook pass is not approval.',
    '\uc800\uc7a5\uc18c \ubcc0\uacbd \uc5c6\uc74c.',
    '\uc804\uccb4 \ud14c\uc2a4\ud2b8 \uc2e4\ud328 \uc5c6\uc74c.',
    'No files changed in the repository status.',
    'There is no reader in the repository tests/ tree.'])
def test_should_allow_scoped_absence_and_non_absence_negation(runtime, claim):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    append_tool(repo, 'claude', 'Grep', {'path': 'tests', 'pattern': 'item'})
    assert run('Stop', last_assistant_message=RECIPIENT_LABELS + '\n' + claim).stdout == ''


@pytest.mark.parametrize('tool,args', [
    ('Grep', {'pattern': 'item'}), ('Glob', {'pattern': '**/*'}),
    ('Grep', {'path': '.', 'pattern': 'item'}),
    ('Bash', {'command': 'rg item .'}), ('Bash', {'command': 'grep -r item .'}),
    ('Bash', {'command': 'rg item ROOT'}),
])
def test_should_allow_repository_absence_after_root_search(runtime, tool, args):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    args = {key: value.replace('ROOT', shlex.quote(str(repo))) for key, value in args.items()}
    append_tool(repo, 'claude', tool, args)
    body = RECIPIENT_LABELS + '\nItem not found anywhere in the repository.'
    assert run('Stop', last_assistant_message=body).stdout == ''


@pytest.mark.parametrize('receiving', [False, True])
def test_should_supply_owner_permission_and_search_scope_rule(runtime, receiving):
    run, _, _ = runtime
    result = run('UserPromptSubmit', prompt=RECIPIENT_PROMPT if receiving else PROMPT)
    context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    rule = ('A hook or gate pass means only that the call was not blocked; read and act '
            'permission comes only from the owner May line. '
            'Claim absence only for the scope you searched.')
    assert context.count(rule) == 1


# Round p C1 text excerpts; P3 evidence is embedded in the owner prompt.
ROUND_P_LABELS = (
    '| `repository_root` | **parent-supplied**: `/srv/my-life` |\n| `h'
    'ead` | **unavailable**: \uc804\uccb4 SHA\uac00 \uc804\ub2ec\ub418\uc9c0 \uc54a\uc558\uace0'
    ', \uc774\ubc88 \ud134\uc5d0\ub3c4 \ud655\uc778\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.'
    ' |\n| `mapping.identity` | **parent-supplied**: schema `mir-semantic-mapping/v1`, namespac'
    'e `my-life` |\n| `mapping.version` | **unavailable**: \ub3c5\ub9bd version \ud544\ub4dc'
    '\uac00 \uc5c6\ub2e4\ub294 \uc124\uba85\ub3c4 \uc9c1\uc811 \ud655\uc778\ud558\uc9c0 \ubabb'
    '\ud588\uc2b5\ub2c8\ub2e4. |\n| `mapping.digest` | **unavailable** |\n| `contract.identity`'
    ' | **parent-supplied**: \uc120\uc5b8\uac12 `mir.common-semantics` |\n| `contract.version` '
    '| **parent-supplied**: \uc120\uc5b8\uac12 `1.1.0` |\n| `contract.digest` | **parent-suppli'
    'ed**: \uc120\uc5b8\uac12 `b2f1ecd01aaa88d41caac2bc2481e7f4c5a429cff3983aaa85ddfb0fc2f1b93f'
    '`. \uc2e4\uc81c \uacc4\uc57d\uacfc\uc758 \uc77c\uce58\ub294 \ubbf8\ud655\uc778\uc785\ub2c8'
    '\ub2e4. |'
)

ROUND_P_ATTRIBUTION = (
    '\uc6d0\ubb38\uc758 \xa711\uc5d0\uc11c `verified-in-repo`\ub85c \ud45c\uc2dc\ud55c \ud56d'
    '\ubaa9\uc740 \ubd80\ubaa8\uac00 \uc77d\uc5c8\ub2e4\uace0 \uc804\ub2ec\ud55c \uae30\ub85d'
    '\uc785\ub2c8\ub2e4. **\uc774\ubc88 \uc218\uc2e0\uc790 \uac80\ud1a0\uc5d0\uc11c\ub294 `pare'
    'nt-supplied`\ub85c \ud45c\uc2dc\ud569\ub2c8\ub2e4.** \ub610\ud55c `contract.digest`\ub294 '
    '\ud30c\uc77c\uc5d0 \uc801\ud78c \uc120\uc5b8\uac12\uc744 \uc77d\ub294 \uac83\uacfc \uc2e4'
    '\uc81c digest\ub97c \uac80\uc99d\ud558\ub294 \uac83\uc744 \uad6c\ubd84\ud574\uc57c \ud569'
    '\ub2c8\ub2e4.'
)

ROUND_P_NEGATION = (
    '\ud604\uc7ac \ucf54\ub4dc\xb7\uc904 \ubc88\ud638\uc758 \uc77c\uce58, \uc2e4\uc81c ref allo'
    'wlist\uc640 verifier \ubaa9\ub85d, canary \uad00\ub828 \ud14c\uc2a4\ud2b8\uc758 \uc874'
    '\uc7ac, \uc124\uce58\ub41c \uacc4\uc57d\uacfc \uc120\uc5b8 digest\uc758 \uc77c\uce58, '
    '\ubaa8\ub4e0 \uc2e4\ud589 \uacb0\uacfc\uac00 \ubbf8\ud655\uc778\uc785\ub2c8\ub2e4. \ud2b9'
    '\uc815 \ud1a0\ud070\uc774\ub098 ID\uac00 \uc800\uc7a5\uc18c\uc5d0 \uc5c6\ub2e4\ub294 '
    '\uacb0\ub860\ub3c4 \ub0b4\ub9ac\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4. \uc804\ub2ec\ub41c \uacfc'
    '\uac70 \uac80\uc0c9 \uacb0\uacfc\ub294 \uba85\uc2dc\ub41c \ub124 \uc18c\uc2a4 \ub8e8\ud2b8'
    '\uc640 \ub2f9\uc2dc \uac80\uc0c9 \uc2dc\uc810\uc5d0 \ud55c\uc815\ub41c \uc8fc\uc7a5\uc785'
    '\ub2c8\ub2e4.'
)

ROUND_P_LIMITATION = (
    '\uc774\ubc88 \ucc28\ub840\uc5d0\ub294 \ub3c4\uad6c \ubaa9\ub85d\uc5d0\uc11c \uba85\ub839 '
    '\uc2e4\ud589 \uc5c6\uc774 \ud30c\uc77c\uc744 \uc77d\uc744 \uc218 \uc788\ub294 \uc804\uc6a9'
    ' \ub3c4\uad6c\ub97c \ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4. \uc178\xb7\ucf54\ub4dc '
    '\uc778\ud130\ud504\ub9ac\ud130\ub294 \ud638\ucd9c\ud558\uc9c0 \uc54a\uc558\uc73c\uba70, '
    '\ub85c\uceec \uc18c\uc2a4\ub3c4 \uc9c1\uc811 \uc77d\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4. '
    '\ub530\ub77c\uc11c \uc544\ub798 \uc800\uc7a5\uc18c \uad00\ub828 \uadfc\uac70\ub294 \ubaa8'
    '\ub450 **parent-supplied**\uc785\ub2c8\ub2e4. \uc9c1\uc811 \ud655\uc778\ud55c \uc18c\uc2a4'
    ', \ud604\uc7ac HEAD, \ud30c\uc77c \ud574\uc2dc \ub610\ub294 \ud14c\uc2a4\ud2b8 \uacb0'
    '\uacfc\ub294 \uc5c6\uc2b5\ub2c8\ub2e4.'
)

ROUND_P_TARGET = (
    '| \uc815\uaddc\ud654 \ub300\uc0c1 | `my-life:scripts/verify_memory_freshness.py`, \ud569'
    '\uc131 \uccb4\uc778 `my-life:s4a-life-chain` (\ubd80\ubaa8\uac00 \uc81c\uacf5, \uc800'
    '\uc7a5\uc18c\uc5d0 \uc5c6\uc74c) |'
)

ROUND_P_ABSENCE = (
    '- **Qualified target**: `my-life:s4a-life-chain`. \ud569\uc131 \uc5f0\uc1c4 ID\uc785\ub2c8'
    '\ub2e4. \uc774 ID\ub294 \uc800\uc7a5\uc18c\uc5d0 \uc5c6\uace0, \uc774 \uc9c0\uc2dc\ubb38'
    '\uc5d0\uc11c\ub9cc \uc815\uc758\ud569\ub2c8\ub2e4.'
)


ROUND_P_CONTRACT_ID = (
    '| contract.identity | verified-in-repo | \uc774\ubc88 \ud134 Read `.mir/ontology-map.json:'
    '3`: `"id":"mir.common-semantics"` (\uc120\uc5b8\ub41c \uac12) |'
)

ROUND_P_CONTRACT_VERSION = (
    '| contract.version | verified-in-repo | \uc774\ubc88 \ud134 Read `.mir/ontology-map.json:3'
    '`: `"version":"1.1.0"` (\uc120\uc5b8\ub41c \uac12) |'
)

ROUND_P_DIGEST = (
    '| contract.digest | verified-in-repo | \uc774\ubc88 \ud134 Read `.mir/ontology-map.json:3`'
    ': `b2f1ecd01aaa88d41caac2bc2481e7f4c5a429cff3983aaa85ddfb0fc2f1b93f` (\uc120\uc5b8\ub41c '
    '\uac12\uc774\uba70, \uc124\uce58\ub41c \uacc4\uc57d\uacfc\ub294 \ub300\uc870\ud558\uc9c0 '
    '\uc54a\uc558\uc2b5\ub2c8\ub2e4) |'
)


@pytest.mark.parametrize('claim', [
    ROUND_P_ABSENCE, ROUND_P_TARGET,
])
def test_round_p_d05_unrelated_scope_does_not_bound_absence(claim):
    assert module().absence_defects(claim, [], ROOT)


def test_round_p_d05_scoped_absence_in_the_same_item_stays_allowed():
    """Round p P03 F13 (judged MET): the search-scope sentence bounds its absence claim."""
    calls = [('grep', {'path': 'scripts', 'pattern': 's4a-life-chain'})]
    claim = ('- `my-life:s4a-life-chain` \u2014 \ubd80\ubaa8\uac00 \uc815\uc758\ud55c '
             '**\ud569\uc131** \uccb4\uc778\uc785\ub2c8\ub2e4. \uc800\uc7a5\uc18c'
             '\uc5d0\ub294 \uc544\uc9c1 \uc5c6\uc2b5\ub2c8\ub2e4. \uc704 \ub124 \uc18c'
             '\uc2a4 \ub8e8\ud2b8\uc5d0\uc11c `s4a-life-chain|S4A_LIFE|s4a_life`\ub97c '
             '\uac80\uc0c9\ud588\uc744 \ub54c 0\uac74\uc774\uc5c8\uc73c\uba70, \uc774 '
             '\ubd80\uc7ac \ud310\ub2e8\uc740 \ud574\ub2f9 \ubc94\uc704\uc5d0\ub9cc \uc801'
             '\uc6a9\ub429\ub2c8\ub2e4.')
    assert module().absence_defects(claim, calls, ROOT) == []


@pytest.mark.parametrize('names', [
    ['contract.identity'], ['contract.version'], ['contract.identity', 'contract.version'],
])
def test_round_p_d01_map_declarations_accept_shared_reference(monkeypatch, names):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: (
        [('read', {'file_path': '.mir/ontology-map.json'})], ['.mir/ontology-map.json'], []))
    rows = {'contract.identity': ROUND_P_CONTRACT_ID,
            'contract.version': ROUND_P_CONTRACT_VERSION}
    body = '\n'.join(rows[name] for name in names)
    if len(names) > 1:
        # Share the real map citation between the two declaration labels.
        body = ' | '.join(name + ': verified-in-repo' for name in names)
        body += ' | ' + ROUND_P_CONTRACT_ID.split('|')[3]
    assert hook.verification_defects('', body, {'cwd': str(ROOT)}, no_commands=True) == []


def test_round_p_d02_labels_allow_explanation_in_cell():
    assert dict(module().pin_claims(ROUND_P_LABELS)) == {
        'repository_root': 'parent-supplied', 'head': 'unavailable',
        'mapping.identity': 'parent-supplied', 'mapping.version': 'unavailable',
        'mapping.digest': 'unavailable', 'contract.identity': 'parent-supplied',
        'contract.version': 'parent-supplied', 'contract.digest': 'parent-supplied'}


@pytest.mark.parametrize('body', [ROUND_P_NEGATION, ROUND_P_ATTRIBUTION,
    'I do not conclude it is absent from the repository.',
    '> The item is absent from the repository.',
    '> contract.digest: verified-in-repo',
])
def test_round_p_d03_negated_and_attributed_claims_are_not_assertions(monkeypatch, body):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: ([], [], []))
    assert hook.verification_defects('', body, {'cwd': str(ROOT)}) == []


def test_round_p_d04_access_limit_disclosure_is_sufficient(runtime):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT + '\nNo commands.')
    body = RECIPIENT_LABELS + '\n' + ROUND_P_LIMITATION
    assert run('Stop', last_assistant_message=body).stdout == ''


@pytest.mark.parametrize('pin', ['contract.digest', 'mapping.digest', 'sources[0].sha256'])
def test_round_p_d06_read_digest_requires_computation_without_ban(runtime, pin):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    append_tool(repo, 'claude', 'Read', {'file_path': '.mir/ontology-map.json'})
    body = packet() + '\n' + ROUND_P_DIGEST.replace('contract.digest', pin)
    result = json.loads(run('Stop', last_assistant_message=body).stdout or '{}')
    assert result.get('decision') == 'block'
    assert 'this-turn computation' in result['reason']


@pytest.mark.parametrize('claim', [ROUND_P_ABSENCE, 'pin contract.digest=verified-in-repo'])
@pytest.mark.parametrize('receiving', [False, True])
def test_round_p_d06_replacement_final_rechecks_absence_and_digest(runtime, claim, receiving):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=(RECIPIENT_PROMPT if receiving else PROMPT)
        + '\nNo commands.')
    first_body = RECIPIENT_LABELS if receiving else NO_PIN_PACKET
    first = json.loads(run('Stop', last_assistant_message=first_body + '\nHEAD: abcdef123').stdout)
    append_block(repo, 'claude', first['reason'])
    result = json.loads(run('Stop', last_assistant_message=first_body + '\n' + claim,
                           stop_hook_active=True).stdout or '{}')
    assert result.get('decision') == 'block'
    assert ('repository-wide absence' if claim == ROUND_P_ABSENCE else 'this-turn computation'
            ) in result['reason']


def test_round_p_d07_table_only_target_requires_every_pin(runtime):
    run, _, _ = runtime
    prompt = (ROUND_P_TARGET + '\n| Lifecycle | proposed |\n| Verification | unchecked |'
              '\n| Unknowns | hashes unchecked |')
    assert module().recipient(prompt)
    supplied = run('UserPromptSubmit', prompt=prompt)
    assert 'Received handoff' in supplied.stdout
    result = json.loads(run('Stop', last_assistant_message='No local check was performed.').stdout)
    assert result['reason'].count('missing recipient pin label:') == 8


# Round q excerpts: Q01P L134/F65, Q02P L138 source/self-check sections,
# and Q01C/Q02C/Q03C T28. Host-specific roots are replaced with neutral paths.
ROUND_Q_ABSENCE = (
    '\uc774 \uccb4\uc778\uc740 \uc800\uc7a5\uc18c\uc5d0 \uc5c6\uace0 parent\uac00 \uc81c'
    '\uc548\ud55c \uac83\uc785\ub2c8\ub2e4.'
)
ROUND_Q_DECLARATIONS = (
    '- `.mir/ontology-map.json`\n'
    '  - `:3`: contract `mir.common-semantics` 1.1.0, sha256 '
    '`b2f1ecd01aaa88d41caac2bc2481e7f4c5a429cff3983aaa85ddfb0fc2f1b93f`(\uc120\uc5b8\uac12)\n'
    '  - contract.identity=verified-in-repo: `mir.common-semantics`\n'
    '  - contract.version=verified-in-repo: 1.1.0\n'
    '  - contract.digest=verified-in-repo: \uc120\uc5b8\uac12\uc774\uba70 \uacc4\uc57d '
    '\ud30c\uc77c\uacfc \ub300\uc870\ud558\uc9c0 \uc54a\uc74c'
)
ROUND_Q_LIMITATIONS = [
    '\uc774\ubc88 \ud134\uc5d0\ub294 \ub3c4\uad6c \ubaa9\ub85d\ub9cc \ud655\uc778\ud588'
    '\uc2b5\ub2c8\ub2e4. \uba85\ub839 \uc2e4\ud589 \uc5c6\uc774 \ub85c\uceec \uc18c\uc2a4'
    '\ub97c \uc77d\ub294 \uc804\uc6a9 \ub3c4\uad6c\ub97c '
    '\ucc3e\uc9c0 \ubabb\ud588\uc73c\ubbc0\ub85c **\ud30c\uc77c\uc744 \uc9c1\uc811 \uc77d'
    '\uac70\ub098 \uac80\uc0c9\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.** \uc544\ub798 '
    '\ud30c\uc77c\ubcc4 \uc124\uba85\uacfc \uc904 '
    '\ubc88\ud638\ub294 \ubaa8\ub450 `parent-supplied`\uc774\uba70, \ud604\uc7ac \uc800'
    '\uc7a5\uc18c\uc5d0\uc11c \ud655\uc778\ud55c \uadfc\uac70\ub85c \ucde8\uae09\ud558'
    '\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4. '
    '\uba85\ub839\xb7\ud14c\uc2a4\ud2b8\xb7\uc218\uc815\xb7\uc2e4\uc81c \uc704\uc784\ub3c4 '
    '\uc218\ud589\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.',
    '\uac80\ud1a0 \ub300\uc0c1\uacfc \uad8c\ud55c \ubc94\uc704\ub294 \uba85\ud655\ud569'
    '\ub2c8\ub2e4. \ub2e4\ub9cc \uc774\ubc88 \ud134\uc5d0\ub294 \ub85c\uceec \ud14d\uc2a4'
    '\ud2b8\ub97c \uc77d\ub294 \ub3c4\uad6c\ub97c '
    '\ucc3e\uc9c0 \ubabb\ud574 \uc18c\uc2a4\ub97c \uc9c1\uc811 \ud655\uc778\ud558\uc9c0 '
    '\ubabb\ud588\uc2b5\ub2c8\ub2e4. \uc544\ub798 \ub0b4\uc6a9\uc740 \uc804\ub2ec\ubc1b'
    '\uc740 \uc9c0\uc2dc\ubb38\uacfc \uc18c\uc2a4 '
    '\uc124\uba85\uc5d0 \ub300\ud55c \uac80\ud1a0\uc785\ub2c8\ub2e4. \uba85\ub839\xb7\ud14c'
    '\uc2a4\ud2b8 \uc2e4\ud589, \uc2e4\uc81c \uc704\uc784\xb7dispatch, DB \uc811\uadfc, '
    '\ud30c\uc77c \uc218\uc815\uc740 '
    '\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.',
    '\uc774\ubc88 \ud134\uc5d0\ub294 \ub3c4\uad6c \ubaa9\ub85d\uc5d0\uc11c \ud30c\uc77c '
    '\uc77d\uae30 \uae30\ub2a5\uc744 \ucc3e\uc544\ubd24\uc9c0\ub9cc, \uc0ac\uc6a9\ud560 '
    '\uc218 \uc788\ub294 \ub85c\uceec \ud14d\uc2a4\ud2b8 '
    'reader\ub97c \ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4. \uae08\uc9c0\ub41c shell'
    '\uc774\ub098 \ucf54\ub4dc \uc778\ud130\ud504\ub9ac\ud130\ub294 \ud638\ucd9c\ud558'
    '\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4. '
    '\ub530\ub77c\uc11c **\uc800\uc7a5\uc18c\uc5d0\uc11c \uc774\ubc88 \ud134\uc5d0 \uc9c1'
    '\uc811 \ud655\uc778\ud55c \uadfc\uac70\ub294 \uc5c6\uc73c\uba70**, \uc544\ub798 \uc18c'
    '\uc2a4 \uc124\uba85\uc740 \ubaa8\ub450 '
    '\uc804\ub2ec\ubc1b\uc740 \uc9c0\uc2dc\ubb38\uc744 \uae30\uc900\uc73c\ub85c \uac80'
    '\ud1a0\ud55c \uacb0\uacfc\uc785\ub2c8\ub2e4.',
]
ROUND_Q_READ_GRANT = (
    '\uba85\ub839\uc744 \uc2e4\ud589\ud558\uc9c0 \uc54a\ub294 \uc77d\uae30 \ub3c4\uad6c'
    '\uac00 \uc788\uc744 \ub54c, \ud5c8\uc6a9\ub41c \ucf54\ub4dc\xb7\uc2a4\ud0a4\ub9c8\xb7'
    '\uad6c\uc870 \uc815\uc758\xb7\ud15c\ud50c\ub9bf\xb7'
    '\ud569\uc131 \ud14c\uc2a4\ud2b8\ub97c \uc77d\uace0 \uc124\uba85\ud560 \uc218 \uc788'
    '\uc2b5\ub2c8\ub2e4.'
)


@pytest.mark.parametrize('scope', [{'path': '/srv/my-life'}, {}])
def test_round_q_d01_glob_pattern_bounds_root_search(scope):
    calls = [('glob', {'pattern': '.mir/*.json', **scope})]
    calls += [('grep', {'path': path, 'pattern': 's4a-life-chain'})
              for path in ('tests', 'scripts', 'spec', 'tools')]
    defects = module().absence_defects(ROUND_Q_ABSENCE, calls, Path('/srv/my-life'))
    assert defects and '.mir/*.json' in defects[0]


def test_round_q_d02_source_section_supports_contract_declarations(monkeypatch):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: (
        [('read', {'file_path': '.mir/ontology-map.json'})], ['.mir/ontology-map.json'], []))
    defects = hook.verification_defects('', ROUND_Q_DECLARATIONS,
                                       {'cwd': str(ROOT)}, no_commands=True)
    assert len(defects) == 1
    assert 'digest needs a this-turn computation' in defects[0]


@pytest.mark.parametrize('body', ROUND_Q_LIMITATIONS, ids=['Q01C', 'Q02C', 'Q03C'])
def test_round_q_d03_real_access_limit_disclosures(runtime, body):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT + '\nNo commands.')
    assert run('Stop', last_assistant_message=RECIPIENT_LABELS + '\n' + body).stdout == ''


def test_round_q_d04_conditional_read_narrows_owner_grant():
    hook = module()
    boundary = hook.owner_sections('May: read/inspect only\nMay not: run commands; edit files')
    assert hook.authority_defects(ROUND_Q_READ_GRANT, boundary) == []


@pytest.mark.parametrize('tool,args,complete', [
    ('glob', {'pattern': '**/*'}, True),
    ('glob', {'pattern': '**'}, True),
    ('glob', {'pattern': '**/*', 'path': 'tests'}, False),
    ('glob', {}, False),
    ('grep', {'pattern': 's4a-life-chain'}, True),
    ('grep', {'pattern': 's4a-life-chain', 'glob': 'tests/**'}, False),
])
def test_round_q_search_scope_boundaries(tool, args, complete):
    defects = module().absence_defects(ROUND_Q_ABSENCE, [(tool, args)], ROOT)
    assert bool(defects) is not complete


@pytest.mark.parametrize('body,reads', [
    (ROUND_Q_DECLARATIONS, []),
    (ROUND_Q_DECLARATIONS.replace('.mir/ontology-map.json', 'other/map.json'),
     ['.mir/ontology-map.json']),
])
def test_round_q_contract_declarations_still_need_map_reference(monkeypatch, body, reads):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: ([], reads, []))
    defects = hook.verification_defects('', body, {'cwd': str(ROOT)}, no_commands=True)
    assert any('tool reference: contract.identity' in defect for defect in defects)
    assert any('tool reference: contract.version' in defect for defect in defects)


@pytest.mark.parametrize('body', [
    'No commands were run.',
    'No non-command reader was available.',
    'A local text reader was available. Commands were not run.',
    'No non-command reader was available. Commands were run.',
    'No non-command reader was available. Commands were allowed.',
])
def test_round_q_missing_access_limit_disclosure_stays_blocked(monkeypatch, body):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: ([], [], []))
    defects = hook.recipient_check('No commands.', body, {'cwd': str(ROOT)})
    assert 'state commands forbidden and no non-command reader was used/available' in defects


@pytest.mark.parametrize('extra', [
    ' \ud569\uc131 \ud14c\uc2a4\ud2b8\ub97c \uc2e4\ud589\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.',
    ' \ud30c\uc77c\uc744 \uc218\uc815\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.',
    ' You may run commands.',
])
def test_round_q_enlarged_authority_stays_blocked(extra):
    hook = module()
    boundary = hook.owner_sections('May: read/inspect only\nMay not: run commands; edit files')
    assert hook.authority_defects(ROUND_Q_READ_GRANT + extra, boundary)


# Round r regressions retain the observed wording with neutral repository paths.
ROUND_R_SCOPE = (
    '\ubc94\uc704: scripts/, spec/, tests/, tools/ \uc548\uc758 \ucf54\ub4dc\xb7\uc2a4'
    '\ud0a4\ub9c8\xb7\uad6c\uc870 \uc815\uc758\xb7\ud569\uc131 \ud14c\uc2a4\ud2b8'
)
ROUND_R_PROPOSAL = (
    '\uc6d0\ucc9c \ubcc0\uacbd \uc9c1\ud6c4\uc640 \uccb4\ucee4 \ud638\ucd9c \uc9c1\uc804'
    '\uc744 \uae30\uc900\uc73c\ub85c \uc2a4\ub0c5\uc0f7\uc744 \uc7a1\uace0, \ud638\ucd9c'
    ' \ud6c4 future\ub97c \ud3ec\ud568\ud55c \ubaa8\ub4e0 fixture \ud30c\uc77c\uacfc DB'
    '\uac00 \uc720\uc9c0\ub418\ub294\uc9c0 \ube44\uad50\ud558\uba74 \ubcf4\uc874 \uc758'
    '\ubb34\ub97c \ub354 \uba85\ud655\ud788 \uac80\uc99d\ud560 \uc218 \uc788\uc2b5\ub2c8'
    '\ub2e4.'
)
ROUND_R_SOURCE_CLAIMS = [
    (
        '| `\u2026:61-83` | \ud574\uc2dc \ubd88\uc77c\uce58, \ud574\uc2dc \ub204\ub77d, '
        '\ud30c\uc77c \ub204\ub77d\uc740 \ubaa8\ub450 "owner judgement required"\ub85c '
        '\ubcf4\uace0\ud569\ub2c8\ub2e4. |'
    ),
    (
        '- **\ucf54\ub4dc \ub3d9\uc791:** \uc18c\uc2a4 \uc0c1\ud0dc(proposed\uc778\uc9c0 acc'
        'epted\uc778\uc9c0)\uc640 \uad00\uacc4\uc5c6\uc774 \ubaa8\ub4e0 \uc548\ub0b4\uac00 '
        '\ub611\uac19\uc774 "owner judgement required"\ub85c \ub05d\ub0a9\ub2c8\ub2e4(`verif'
        'y_memory_freshness.py:82, 149-151`).'
    ),
    (
        '| `scripts/verify_memory_freshness.py:61-83` | \uc6d0\ubcf8\uc5d0 \ubb38\uc81c'
        '\uac00 \uc0dd\uae30\uba74 \ub124 \uac00\uc9c0 \ubb38\uad6c \uc911 \ud558\ub098'
        '\ub97c \ub0c5\ub2c8\ub2e4: `source missing`, `source hash missing`, `source unreada'
        'ble`, `source changed`. \ubaa8\ub450 "owner judgement required"\ub85c \ub05d\ub098'
        '\uace0, \ud574\ub2f9 \uacbd\ub85c\ub294 `affected`\uac00 \ub429\ub2c8\ub2e4. |'
    )
]


def test_round_r_d01_unique_basename_reference(monkeypatch):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: (
        [('read', {'file_path': '.mir/ontology-map.json'})], ['.mir/ontology-map.json'], []))
    body = '| mapping.identity | verified-in-repo | `ontology-map.json` |'
    assert hook.verification_defects('', body, {'cwd': str(ROOT)}, no_commands=True) == []


@pytest.mark.parametrize('reads,expected', [
    ([], False), (['other.json'], False),
    (['.mir/ontology-map.json', 'other/ontology-map.json'], False),
    (['.mir/ontology-map.json', '/srv/my-life/.mir/ontology-map.json'], True),
])
def test_round_r_basename_reference_boundaries(reads, expected):
    result = module().path_referenced('ontology-map.json', reads, [], Path('/srv/my-life'))
    assert result is expected


def test_round_r_d02_scope_under_read_only_may():
    hook = module()
    owner = hook.owner_sections('May: read/inspect only\nMay not: run commands; edit files')
    body = 'May: read/inspect only\n  - ' + ROUND_R_SCOPE
    assert hook.authority_defects(body, owner) == []


def test_round_r_d03_conditional_proposal():
    hook = module()
    owner = hook.owner_sections('May: read/inspect only\nMay not: run commands; edit files')
    assert hook.authority_defects(ROUND_R_PROPOSAL, owner) == []


@pytest.mark.parametrize('extra', [
    'May: read/inspect only\n - Scope: scripts/; run tests',
    'You may run commands if that would make the comparison clearer.',
    'You may modify files. This could make the review clearer.',
    'You may commit changes.',
    '\ud30c\uc77c\uc744 \uc218\uc815\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.',
])
def test_round_r_enlarged_authority_stays_blocked(extra):
    hook = module()
    owner = hook.owner_sections('May: read/inspect only\nMay not: run commands; edit files')
    assert hook.authority_defects(extra, owner)


def test_round_r_d04_provenance_is_a_label(monkeypatch):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: ([], [], []))
    prompt = RECIPIENT_PROMPT + '\nprovenance: parent-supplied'
    assert hook.recipient_check(prompt, RECIPIENT_LABELS, {'cwd': str(ROOT)}) == []


@pytest.mark.parametrize('markup', ['mapping.version=unavailable\uc785\ub2c8\ub2e4',
                                  '| `mapping.digest` | **unavailable**\uc785\ub2c8\ub2e4. |'])
def test_round_r_d05_hangul_label_suffix(markup):
    name = 'mapping.digest' if 'digest' in markup else 'mapping.version'
    assert module().pin_claims(markup) == [(name, 'unavailable')]


@pytest.mark.parametrize('label', [
    'unavailableExtra', 'parent-suppliedValue', 'verified-in-repository',
])
def test_round_r_ascii_label_suffix_is_not_a_label(label):
    assert module().pin_claims('mapping.version=' + label) == []


@pytest.mark.parametrize('claim', ROUND_R_SOURCE_CLAIMS,
                         ids=['R01-table', 'R01-prose', 'R03-table'])
@pytest.mark.parametrize('no_commands', [False, True])
def test_round_r_s01_author_source_claim_first_block_only(runtime, claim, no_commands):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=PROMPT + ('\nNo commands.' if no_commands else ''))
    body = (NO_PIN_PACKET if no_commands else packet()) + '\n' + claim + '\n' + claim
    first = json.loads(run('Stop', last_assistant_message=body).stdout)
    prefix = 'universal claim about cited source output:'
    assert first['decision'] == 'block'
    assert first['reason'].count(prefix) == 1
    append_block(repo, 'claude', first['reason'])
    second = run('Stop', last_assistant_message=body, stop_hook_active=True)
    assert prefix not in second.stdout


@pytest.mark.parametrize('claim', [
    'All branches report "owner judgement required".',
    '`scripts/check.py:61-83` reports "owner judgement required".',
    'Eight pins are all verified-in-repo (`map:3`).',
    'All checks passed (`map:3`); "output" is a field name.',
    'All runs report "ok" at 10:30 (2026-10-31T01:40:41Z).',
])
def test_round_r_s01_non_output_claims_stay_allowed(runtime, claim):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=PROMPT)
    result = run('Stop', last_assistant_message=packet() + '\n' + claim)
    assert 'universal claim about cited source output:' not in result.stdout


def test_round_r_s01_recipient_not_checked(runtime):
    run, _, _ = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    result = run('Stop', last_assistant_message=RECIPIENT_LABELS + '\n' + ROUND_R_SOURCE_CLAIMS[0])
    assert 'universal claim about cited source output:' not in result.stdout


# S03C T44/52/60/68: distinct native messages reuse the same Stop run ID.
ROUND_S_REPAIRS = [{'type': 'response_item',
  'payload': {'type': 'message',
              'id': 'msg_01a18ecc-a3c1-7ad0-96ea-15c1b51176ad',
              'role': 'user',
              'content': [{'type': 'input_text',
                           'text': '<hook_prompt '
                                   'hook_run_id="stop:21:/synthetic/hooks/hooks.json">Repair '
                                   'recipient accounting once: missing recipient pin label: '
                                   'abbreviated. Re-send the complete corrected artifact as '
                                   'your final message; it replaces the previous one, so do '
                                   'not send only the changed sections.</hook_prompt>'}]}},
 {'type': 'response_item',
  'payload': {'type': 'message',
              'id': 'msg_01a18ecd-0bdf-7e50-995a-a7566046c148',
              'role': 'user',
              'content': [{'type': 'input_text',
                           'text': '<hook_prompt '
                                   'hook_run_id="stop:21:/synthetic/hooks/hooks.json">Repair '
                                   'handoff deterministic defects (second/final block): '
                                   'missing recipient pin label: abbreviated. Re-send the '
                                   'complete corrected artifact as your final message; it '
                                   'replaces the previous one, so do not send only the changed '
                                   'sections.</hook_prompt>'}]}},
 {'type': 'response_item',
  'payload': {'type': 'message',
              'id': 'msg_01a18ecd-790d-7552-a367-5cfc560f1e0f',
              'role': 'user',
              'content': [{'type': 'input_text',
                           'text': '<hook_prompt '
                                   'hook_run_id="stop:21:/synthetic/hooks/hooks.json">Repair '
                                   'handoff deterministic defects (second/final block): '
                                   'missing recipient pin label: head. Re-send the complete '
                                   'corrected artifact as your final message; it replaces the '
                                   'previous one, so do not send only the changed '
                                   'sections.</hook_prompt>'}]}},
 {'type': 'response_item',
  'payload': {'type': 'message',
              'id': 'msg_01a18ece-025a-7a43-ad14-8c4e5fdae0a3',
              'role': 'user',
              'content': [{'type': 'input_text',
                           'text': '<hook_prompt '
                                   'hook_run_id="stop:21:/synthetic/hooks/hooks.json">Repair '
                                   'handoff deterministic defects (second/final block): '
                                   'missing recipient pin label: repository_root; missing '
                                   'recipient pin label: head; missing recipient pin label: '
                                   'mapping.identity; missing recipient pin label: '
                                   'mapping.version; missing recipient pin label: '
                                   'mapping.digest; missing recipient pin label: '
                                   'contract.identity; missing recipient pin label: '
                                   'contract.version; missing recipient pin label: '
                                   'contract.digest; missing recipient pin label: abbreviated. '
                                   'Re-send the complete corrected artifact as your final '
                                   'message; it replaces the previous one, so do not send only '
                                   'the changed sections.</hook_prompt>'}]}}]


def test_round_s_d04_reused_stop_id_counts_occurrences(runtime):
    run, _, repo = runtime
    run('UserPromptSubmit', prompt=RECIPIENT_PROMPT)
    hook = module()
    event = {'cwd': str(repo), 'transcript_path': str(repo / 'native-session.jsonl')}
    for count, row in enumerate(ROUND_S_REPAIRS, 1):
        with (repo / 'native-session.jsonl').open('a') as stream:
            stream.write(json.dumps(row) + '\n')
        if count == 2:
            third = run('Stop', last_assistant_message='Done.', stop_hook_active=True)
            assert 'decision' not in json.loads(third.stdout or '{}')
        assert hook.prior_blocks(event) == count


# S01P T383:134/153, S02P T387:90, S01C T28:124.
ROUND_S_AUTHORITY = [
    (
        '      test_l'
        'ocal_hooks.p'
        'y:79-81\uc774 \ud1b5\uacfc\ud55c'
        '\ub2e4\uba74 scripts/\xb7'
        'tests/ \uacc4\uc5f4 pr'
        'efix\uac00 \ud5c8\uc6a9\ub41c\ub2e4\uace0 '
        '\ucd94\uc815\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.'
    ),
    (
        'May: \uc704 1\uc808\uc5d0 \ub098'
        '\uc5f4\ud55c scripts/,'
        ' spec/, test'
        's/, tools/ \ud30c'
        '\uc77c\uacfc \uc774 \uc9c0\uc2dc\ubb38\uc744 \uc77d\uace0'
        ' \uac80\ud1a0 \uc758\uacac\ub9cc \ub0c5\ub2c8\ub2e4.'
    ),
    (
        '- **(a) \uc0c1\ud0dc\uac00 '
        '\ub4dc\ub7ec\ub098\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.**'
        ' \ucd9c\ub825\uc5d0 \ucd9c\ucc98\uc758 lif'
        'ecycle(propo'
        'sed/accepted'
        ')\uacfc \ubcc0\uacbd \uc804\ud6c4 \ud574\uc2dc\uac00'
        ' \uc5c6\uc2b5\ub2c8\ub2e4. \uadf8\ub798\uc11c "'
        '\uc7ac\uac80\ud1a0 \ud544\uc694"\ub97c "\ubcc0\uacbd'
        ' \ud655\uc815"\uc73c\ub85c \uc624\ub3c5\ud560 \uc218'
        ' \uc788\uc2b5\ub2c8\ub2e4.'
    ),
    (
        '- \uba85\ub839 \uc2e4\ud589\uc774 \ud544\uc694 '
        '\uc5c6\ub294 \uc77d\uae30 \ub3c4\uad6c\uac00 \uc788\ub2e4'
        '\uba74, \ud5c8\uc6a9\ub41c \uc18c\uc2a4\uc758 \ud544'
        '\uc694\ud55c \ubd80\ubd84\uc744 \uc77d\uace0 \ub300\uc870'
        '\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.'
    ),
]

# S03C T57:93-100 and T65:71-99; neutral repository root.
ROUND_S_INVENTORIES = [
 'repository_root=parent-supplied: /srv/my-life; repository-root identity not '
 'independently verified\n'
 'head=abbreviated: parent-supplied 974eebf; full SHA and current HEAD unavailable\n'
 'mapping.identity=unavailable\n'
 'mapping.version=unavailable\n'
 'mapping.digest=unavailable\n'
 'contract.identity=unavailable\n'
 'contract.version=parent-supplied: test expectation 1.1.0 only; runtime version '
 'unavailable\n'
 'contract.digest=unavailable',
 'recipient_pins:\n'
 '  repository_root:\n'
 '    label: parent-supplied\n'
 '    value: "/srv/my-life"\n'
 '    verification: unavailable\n'
 '  head:\n'
 '    label: parent-supplied\n'
 '    completeness: abbreviated\n'
 '    value: "974eebf"\n'
 '    full_sha: unavailable\n'
 '    current_head: unavailable\n'
 '  abbreviated:\n'
 '    label: parent-supplied\n'
 '    applies_to: head\n'
 '    value: "974eebf"\n'
 '  mapping.identity:\n'
 '    label: unavailable\n'
 '  mapping.version:\n'
 '    label: unavailable\n'
 '  mapping.digest:\n'
 '    label: unavailable\n'
 '  contract.identity:\n'
 '    label: unavailable\n'
 '  contract.version:\n'
 '    label: parent-supplied\n'
 '    value: "1.1.0"\n'
 '    limitation: "Reported test expectation only; runtime version unavailable."\n'
 '  contract.digest:\n'
 '    label: unavailable']


@pytest.mark.parametrize('body', ROUND_S_AUTHORITY,
                         ids=['fixture-inference', 'review-scope', 'risk', 'reader'])
def test_round_s_d01_read_scope_and_inference(body, monkeypatch):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: ([], [], []))
    owner = hook.owner_sections('May: read/inspect only\nMay not: run commands; edit files')
    assert hook.authority_defects(body, owner) == []
    for enlarged in ('You may run commands.', 'You may modify files.',
                     'You may commit changes.', 'You may write files.',
                     'You may use the network.'):
        assert hook.authority_defects(body + '\n' + enlarged, owner)
    # The same drafts also contained valid absence and digest interventions.
    assert hook.absence_defects(ROUND_S_ABSENCE, [], ROOT)
    assert any('verified-in-repo digest needs' in defect for defect in
               hook.verification_defects('', ROUND_S_DIGEST, {'cwd': str(ROOT)},
                                         no_commands=True))


def test_round_s_d02_value_is_not_a_pin(monkeypatch):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: ([], [], []))
    claim = 'head=abbreviated: parent-supplied'
    assert hook.pin_claims(claim) == [('head', 'parent-supplied')]
    assert hook.recipient_check(RECIPIENT_PROMPT + '\n' + claim,
                                RECIPIENT_LABELS, {'cwd': str(ROOT)}) == []


@pytest.mark.parametrize('inventory', ROUND_S_INVENTORIES, ids=['combined', 'nested'])
def test_round_s_d03_recipient_inventory(monkeypatch, inventory):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: ([], [], []))
    prompt = 'Review this received handoff.'
    body = inventory + '\nNo local check was performed.'
    assert hook.recipient_check(prompt, body, {'cwd': str(ROOT)}) == []
    assert hook.recipient_check(prompt, body.replace('label:', 'provenance:'),
                                {'cwd': str(ROOT)}) == []
    # An adjacent sibling label cannot supply the missing pin's provenance.
    body = body.replace('head=abbreviated: parent-supplied', 'head=abbreviated: unknown')
    body = body.replace('  head:\n    label: parent-supplied',
                        '  head:\n    completeness: abbreviated')
    assert 'missing recipient pin label: head' in hook.recipient_check(
        prompt, body, {'cwd': str(ROOT)})


ROUND_S_ABSENCE = (
    '2. \ud569\uc131 s4a-li'
    'fe-chain (pa'
    'rent-supplie'
    'd \uc815\uc758. \uc800\uc7a5\uc18c\uc5d0 \uc774'
    ' fixture\ub294 \uc5c6\uc2b5'
    '\ub2c8\ub2e4)'
)


ROUND_S_DIGEST = (
    '- contract.d'
    'igest=verifi'
    'ed-in-repo: '
    'map\uc5d0 \uc120\uc5b8\ub41c `b2'
    'f1ecd0\u2026`(`:3'
    '`)\uc785\ub2c8\ub2e4. \uc2e4\uc81c co'
    'ntract \ud30c\uc77c\uacfc \ub300'
    '\uc870\ud558\uc9c0\ub294 \uc54a\uc558\uc2b5\ub2c8\ub2e4.'
)


def test_round_t_d01_owner_only_authority():
    hook = module()
    owner = hook.owner_sections('May: read/inspect only\nMay not: run commands; edit files')
    for sentence in (
        'owner(\uc0ac\uc6a9\uc790)\ub9cc \ubb38\uad6c \ubcc0\uacbd\uc744 '
        '\uc2b9\uc778\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.',
        'Only the owner may approve edits.', 'Only the owner can run commands.',
    ):
        assert hook.authority_defects('May: read/inspect only\n  - ' + sentence, owner) == []
        for grant in ('You may run commands.',
                      '\uc218\uc2e0\uc790\ub294 \ud30c\uc77c\uc744 '
                      '\uc218\uc815\ud574\ub3c4 \ub429\ub2c8\ub2e4.'):
            assert hook.authority_defects(sentence + '\n' + grant, owner)


def test_round_t_d02_pin_headings(monkeypatch):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: ([], [], []))
    for heading in ('pin', 'pins'):
        prompt = ('Review this received handoff.\n- **' + heading + ':**\n'
                  '  - repository_root: parent-supplied(example)\n'
                  '  - head: parent-supplied(example)')
        claims = hook.pin_claims(prompt)
        assert claims == [('repository_root', 'parent-supplied'), ('head', 'parent-supplied')]
        assert hook.recipient_check(prompt, RECIPIENT_LABELS, {'cwd': str(ROOT)}) == []
        assert 'missing recipient pin label: head' in hook.recipient_check(
            prompt, RECIPIENT_LABELS.replace('pin head=parent-supplied', ''), {'cwd': str(ROOT)})


def test_round_t_d03_reader_disclosure(monkeypatch):
    hook = module()
    monkeypatch.setattr(hook, 'turn_tools', lambda event: ([], [], []))
    prompt = RECIPIENT_PROMPT + '\nNo commands.'
    disclosure = (
        '\uc18c\uc2a4 \ub9ac\ub354\ub97c \ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4. '
        '\uc15c\u00b7\ucf54\ub4dc \uc778\ud130\ud504\ub9ac\ud130\ub294 '
        '\uc2e4\ud589\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.'
    )
    defect = 'state commands forbidden and no non-command reader was used/available'
    assert hook.recipient_check(prompt, RECIPIENT_LABELS + '\n' + disclosure,
                                {'cwd': str(ROOT)}) == []
    assert defect in hook.recipient_check(prompt, RECIPIENT_LABELS, {'cwd': str(ROOT)})


def test_round_t_d04_evidential_precondition():
    hook = module()
    owner = hook.owner_sections('May: read/inspect only\nMay not: run commands; edit files')
    for sentence in (
        '\ub300\uc870\uad70\uc774 \uc2e4\ud589\ub418\uc5b4\uc57c \uc8fc\uc7a5\uc744 '
        '\ud655\uc778\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.',
        'Controls would need to be executed to verify the claim.',
        'Controls would need to be run to verify the claim.',
    ):
        assert hook.authority_defects(sentence, owner) == []
        for grant in ('You may run commands.',
                      '\uba85\ub839\uc744 \uc2e4\ud589\ud574\ub3c4 \ub429\ub2c8\ub2e4.'):
            assert hook.authority_defects(sentence + '\n' + grant, owner)


def test_round_t_d05_nested_source_citation():
    hook = module()
    claim = '  - All reports end with "review required".'
    for numbers in ('12-14', '12\u201314', '12, 20\u201322', '12'):
        cited = '- **`scripts/check.py`**\n  - ' + numbers + ': inspect branches.\n'
        assert hook.source_claim_defects(cited + claim)
        assert hook.source_claim_defects('- All reports end with "review required".') == []
        assert hook.source_claim_defects(cited + '  - One branch reports "review required".') == []
        assert hook.source_claim_defects(cited + '  - All branches have "status" fields.') == []
        assert hook.source_claim_defects('- Source\n  - ' + numbers + ': inspect.\n' + claim) == []
        assert hook.source_claim_defects('- `scripts/check.py`\n  - 10:30 meeting.\n' + claim) == []
        assert hook.source_claim_defects(cited + '- Separate item\n' + claim) == []
        assert hook.source_claim_defects(cited + '- `scripts/other.py`\n' + claim) == []
