"""Offline contracts for stateless common mechanical handoff hooks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'plugins/mir-lifecycle-hooks/skills/runtime-continuity'
HANDLER = SKILL / 'scripts/handoff_packet.py'
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
        result = subprocess.run([sys.executable, str(HANDLER)], input=json.dumps(payload),
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
        result = subprocess.run([sys.executable, str(HANDLER)], input=payload,
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
        'role': 'user', 'content': 'Prepare a brief for another agent. No commands.',
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
    result = subprocess.run([sys.executable, str(HANDLER)], input=json.dumps(payload),
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
    result = subprocess.run([sys.executable, str(HANDLER)], input=json.dumps(payload),
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
RECIPIENT_LABELS = '\n'.join('pin ' + name + '=parent-supplied' for name in PIN_NAMES)


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
    body = RECIPIENT_LABELS.replace('pin sources[0].digest=parent-supplied',
                                    'pin sources[0].digest=verified-in-repo src/example.py')
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
        result = subprocess.run([sys.executable, '-c', guard], input=json.dumps(payload),
                                text=True, capture_output=True, check=False)
        assert 'Traceback' not in result.stderr, result.stderr
        assert result.returncode in {0, 2}
    supplied = subprocess.run(
        [sys.executable, '-c', guard], text=True, capture_output=True, check=False,
        input=json.dumps({'hook_event_name': 'UserPromptSubmit', 'prompt': PROMPT, 'cwd': str(repo),
                          'session_id': 'session-1', 'transcript_path': str(transcript)}))
    assert 'Mechanical handoff packet' in supplied.stdout
