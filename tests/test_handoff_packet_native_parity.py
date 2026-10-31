"""Byte parity with the unchanged Python reference; Rust remains optional."""
from __future__ import annotations

import hashlib
import inspect
import io
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests import test_mechanical_handoff as mechanical
from tests.test_mechanical_handoff import HANDLER, HANDLER_PYTHON, PROMPT, RECIPIENT_PROMPT

# Korean fixtures are escaped: the public template carries no Hangul literals.
KO_HANDOFF = ('\ub2e4\ub978 \uc5d0\uc774\uc804\ud2b8 '
              '\ud578\ub4dc\uc624\ud504\ub97c \uc791\uc131\ud574 \uc8fc\uc138\uc694.')
KO_NO_COMMANDS = ('\uba85\ub839 \uc2e4\ud589 \uc5c6\uc774 '
                  '\ub2f5\ubcc0\ud574 \uc8fc\uc138\uc694.')
KO_NO_FILES = '\ud30c\uc77c \uc218\uc815 \uae08\uc9c0.'
KO_TARGET_TABLE = ('| \uc815\uaddc\ud654\t\ub300\uc0c1 | yoke:item |\n'
                   '\ud540: x\n\ud5c8\uc6a9: read')

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / 'native/handoff-packet'
pytestmark = pytest.mark.skipif(shutil.which('cargo') is None, reason='cargo unavailable')


@pytest.fixture(scope='module')
def binary():
    env = dict(os.environ)
    command = ['cargo', 'build', '--release', '--locked']
    if env.get('MIR_HANDOFF_CARGO_OFFLINE') == '1':
        command.append('--offline')
    subprocess.run(command, cwd=CRATE, env=env, check=True)
    target = Path(env.get('CARGO_TARGET_DIR', 'target'))
    if not target.is_absolute():
        target = CRATE / target
    executable = 'handoff-packet.exe' if os.name == 'nt' else 'handoff-packet'
    return target / 'release' / executable


def cases():
    result = []
    def add(name, **fields):
        result.append((name, json.dumps(dict(hook_event_name='PreToolUse', **fields),
                                         ensure_ascii=False).encode()))
    for base_name, base in [('author', PROMPT), ('recipient', RECIPIENT_PROMPT),
                            ('korean', KO_HANDOFF + '\n' + KO_NO_COMMANDS)]:
        for tool in ['Read', 'Bash', 'functions.exec_command', 'mcp__python_repl__exec']:
            add(f'{base_name}-{tool}', prompt=base + '\nNo commands.', tool_name=tool)
        for tool in ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'apply_patch']:
            add(f'{base_name}-{tool}', prompt=base + '\nNo file changes.', tool_name=tool)
    for prompt in ['Fix this bug. No commands.', PROMPT, 'Ordinary request.',
                   'Write a handoff for another agent.\nMay: edit files',
                   PROMPT + '\nMay not: run commands except `echo x`',
                   PROMPT + '\n> No commands.', PROMPT + '\n```\nNo commands.\n```',
                   PROMPT + '\nMay not: edit files outside src/',
                   PROMPT + '\nMay not: run commands except echo x; no commands.',
                   'Wrİte a handoff for another agent.\nNo commands.',
                   'Write\x1c a handoff for another agent.\nNo commands.']:
        for tool in ['Bash', 'Write']:
            add(f'prompt-{len(result)}-{tool}', prompt=prompt, tool_name=tool)
    for code in ['await tools.exec_command({cmd: "pwd"});',
                 'await tools.exec_command(options);',
                 'await tools.mcp__python_repl__exec({code:"1"});',
                 'text(ALL_TOOLS);', 'text(await tools.read_file({path:"a"}));',
                 'text("tools.exec_command({cmd:1})"); // tools.js()\n/* tools.js() */']:
        for shape in ['raw', 'input', 'code']:
            add(f'exec-{len(result)}-{shape}', prompt=PROMPT + '\nNo commands.',
                tool_name='functions.exec', tool_input=code if shape == 'raw' else {shape: code})
    add('surrogate-command', prompt=PROMPT + '\nNo commands.', tool_name='exec',
        tool_input={'input': r"tools.exec_command({cmd:'\uD800'})"})
    add('crlf-bullet-ban', prompt='Write a handoff for another agent.\r\n'
        'May not:\r\n- run commands', tool_name='Bash')
    for value in [None, [], 12, {'input': None}]:
        add(f'internal-{len(result)}', tool_name='exec', tool_input=value, prompt=PROMPT)
    for prompt in [
        KO_HANDOFF + '\n' + KO_NO_COMMANDS,
        KO_HANDOFF + '\n' + KO_NO_FILES,
        'Write a handoff for another agent.\nMay not: commands are forbİdden',
        'Write a handoff for another agent.\nMay not: no commands\u0301',
        'Write a handoff for another agent.\nNo commands.\n' + '\ud55c' * 360000,
        'Write a handoff for another agent.\nNo commands.\n' + 'x' * (1024 * 1024),
    ]:
        for tool in ['Bash', 'Write']:
            add(f'unicode-boundary-{len(result)}-{tool}', prompt=prompt, tool_name=tool)
    result.extend([('malformed', b'{'), ('non-dict', b'[]'),
                   ('oversized', b' ' * (1024 * 1024 + 1)),
                   ('unknown', b'{"hook_event_name":"unknown"}'),
                   ('undetermined', b'{}'),
                   ('submit', b'{"hook_event_name":"UserPromptSubmit","prompt":"hello"}')])
    return result


CASES = cases()

# Every candidate still goes through the reference regex; literals are necessary,
# never sufficient. The output assertion makes negative fixtures non-vacuous.
BOUNDARIES = [
    ('ascii', 'Write a handoff for another agent.', 2),
    # One fixture per detect literal, so dropping any literal from the prefilter fails.
    ('literal-codex', 'Write a handoff for Codex.', 2),
    ('literal-claude', 'Write a brief for Claude.', 2),
    ('literal-delegate-codex', 'Delegate this to Codex.', 2),
    ('lower-kelvin', 'Write a handoff for another codeKx. Delegate to codeKx.\n'
     'Delegate to codeKx agent.', 2),
    ('lower-i-dot', 'Wrİte a handoff for another agent.', 0),
    ('lower-dotless', 'Wrıte a handoff for another agent.', 0),
    ('lower-long-s', 'ſend a handoff for another agent.', 0),
    ('korean', KO_HANDOFF, 2),
    ('fence-join', 'Write a handoff for another ag```ignored```ent.', 2),
    ('line-split', 'Write a handoff for another ag\nent.', 0),
    ('near-word', 'Write a handoff for another agentish.', 0),
    ('unicode-word', 'Write a handoff for another agent\ud55c.', 0),
    ('combining-boundary', 'Write a handoff for another agent\u0301.', 2),
    ('target-dot-i', 'Qualİfied target: yoke:item\nPins: x\nMay: read', 2),
    ('target-dotless-i', 'Qualıfied target: yoke:item\nPins: x\nMay: read', 2),
    ('target-markup', 'Quali**fied target: yoke:item\nPins: x\nMay: read', 2),
    ('target-korean', '\ub300\uc0c1: yoke:item\n\ud540: x\n\ud5c8\uc6a9: read', 2),
    ('target-table', KO_TARGET_TABLE, 2),
    ('target-long-s', 'Qualified target: yoke:item\nſtatus axes: x\nMay: read', 2),
    ('target-kelvin', 'Qualified target: yoke:item\nunKnowns: x\nMay: read', 2),
    ('target-line-split', 'Qualified\ntarget: yoke:item\nPins: x\nMay: read', 0),
    ('target-near-word', 'Qualified targets: yoke:item\nPins: x\nMay: read', 0),
]


def run_pair(binary, raw):
    env = dict(os.environ, MIR_HANDOFF_PYTHON=HANDLER_PYTHON, PYTHONUTF8='1')
    outputs = [subprocess.run(command, input=raw, capture_output=True, timeout=10, env=env)
               for command in ([HANDLER_PYTHON, str(HANDLER)], [str(binary)])]
    return [(p.stdout, p.stderr, p.returncode) for p in outputs]


@pytest.mark.parametrize(('name', 'raw'), CASES, ids=[c[0] for c in CASES])
def test_byte_parity(binary, name, raw):
    reference, native = run_pair(binary, raw)
    assert native == reference, name


@pytest.mark.parametrize('control', ['\x1c', '\x1d', '\x1e', '\x1f'])
def test_native_stop_control_only_final_keeps_transcript(binary, stop_repository, control):
    repo, pins = stop_repository
    event = json.loads(stop_payload(repo, PROMPT, mechanical.packet(pins).replace(pins, '')))
    event['last_assistant_message'] = control
    reference, native = run_pair(binary, json.dumps(event).encode())
    assert json.loads(reference[0])['decision'] == 'block'
    assert native == reference


@pytest.mark.parametrize(('name', 'prompt', 'code'), BOUNDARIES,
                         ids=[c[0] for c in BOUNDARIES])
def test_optimization_boundaries(binary, name, prompt, code):
    raw = json.dumps(dict(hook_event_name='PreToolUse', tool_name='Bash',
                          prompt=prompt + '\nNo commands.'), ensure_ascii=False).encode()
    reference, native = run_pair(binary, raw)
    assert reference[2] == code, name
    assert native == reference, name


@pytest.mark.parametrize('shape', ['claude', 'codex', 'event', 'hook-feedback', 'tail', 'broken'])
def test_transcript_and_stop(binary, tmp_path, shape):
    prompt = PROMPT + '\nNo commands.'
    if shape == 'claude':
        rows = [{'type': 'user', 'message': {'content': [{'type': 'text', 'text': prompt}]}}]
    elif shape == 'event':
        rows = [{'type': 'event_msg', 'payload': {'type': 'user_message', 'message': prompt}}]
    else:
        rows = [{'type': 'response_item', 'payload': {'role': 'user', 'content': prompt}}]
    if shape == 'hook-feedback':
        rows.append({'type': 'response_item', 'payload': {'role': 'user', 'content':
                     '<hook_prompt hook_run_id="Stop:1">feedback</hook_prompt>'}})
    rows.append({'type': 'assistant', 'message': {'content': 'Done.'}})
    path = tmp_path / 'session.jsonl'
    path.write_bytes((b'x' * (1024 * 1024) + b'\n' if shape == 'tail' else b'') +
                     ('\n'.join(json.dumps(row) for row in rows) + '\n').encode())
    if shape == 'broken':
        path.write_bytes(b'not json\n')
    for event in ['PreToolUse', 'Stop']:
        raw = json.dumps(dict(hook_event_name=event, tool_name='Bash',
                              transcript_path=str(path), stop_hook_active=False)).encode()
        reference, native = run_pair(binary, raw)
        assert native == reference


def test_without_reference(binary):
    p = subprocess.run([str(binary)], input=b'{"hook_event_name":"PreToolUse"}',
                       capture_output=True, check=False)
    assert (p.stdout, p.stderr, p.returncode) == (b'', b'', 0)
    p = subprocess.run([str(binary)], input=b'{"hook_event_name":"Stop"}',
                       capture_output=True, check=False)
    assert p.returncode == 0
    newline = b'\r\n' if os.name == 'nt' else b'\n'
    assert json.loads(p.stdout)['systemMessage'].encode() + newline == p.stderr
    assert b'hook unavailable; allowing turn to continue.' in p.stderr


def test_build_environment(monkeypatch, tmp_path):
    target = tmp_path / 'custom target'
    home = tmp_path / 'cargo home'
    monkeypatch.setenv('CARGO_HOME', str(home))
    monkeypatch.setenv('CARGO_TARGET_DIR', str(target))
    monkeypatch.delenv('MIR_HANDOFF_CARGO_OFFLINE', raising=False)
    calls = []
    monkeypatch.setattr(subprocess, 'run',
                        lambda command, **kwargs: calls.append((command, kwargs)))
    path = binary.__wrapped__()
    command, options = calls.pop()
    assert options['env']['CARGO_HOME'] == str(home)
    assert options['env']['CARGO_TARGET_DIR'] == str(target)
    assert '--locked' in command
    assert '--offline' not in command
    assert path == target / 'release' / ('handoff-packet.exe' if os.name == 'nt'
                                        else 'handoff-packet')
    monkeypatch.setenv('MIR_HANDOFF_CARGO_OFFLINE', '1')
    binary.__wrapped__()
    assert '--offline' in calls.pop()[0]
    monkeypatch.setenv('CARGO_TARGET_DIR', 'relative target')
    assert binary.__wrapped__() == CRATE / 'relative target/release' / path.name
    monkeypatch.delenv('CARGO_TARGET_DIR')
    monkeypatch.delenv('CARGO_HOME')
    assert binary.__wrapped__() == CRATE / 'target/release' / path.name
    assert 'CARGO_HOME' not in calls.pop()[1]['env']


@pytest.mark.parametrize('event', ['Stop', 'PreToolUse', 'UserPromptSubmit', 'unknown'])
def test_no_reference_forwarding(binary, tmp_path, event):
    reference = tmp_path / 'reference with spaces.py'
    marker = tmp_path / 'forwarded'
    reference.write_text(
        f'from pathlib import Path\nPath({str(marker)!r}).touch()\n'
        'raise SystemExit(7)\n', encoding='utf-8')
    raw = json.dumps({'hook_event_name': event}).encode()
    env = dict(os.environ, MIR_HANDOFF_PYTHON=HANDLER_PYTHON, PATH=str(tmp_path))
    direct = subprocess.run([str(binary)], input=raw, capture_output=True, env=env, timeout=10)
    supplied = subprocess.run([str(binary), str(reference)], input=raw,
                              capture_output=True, env=env, timeout=10)
    assert not marker.exists(), 'native dispatch executed the reference argument'
    assert (supplied.stdout, supplied.stderr, supplied.returncode) == (
        direct.stdout, direct.stderr, direct.returncode)


@pytest.mark.parametrize('mode', ['ordinary', 'recipient', 'forbidden', 'valid', 'invalid',
    'oversized', 'excluded', 'nonzero', 'timeout', 'missing-cwd', 'bad-prompt',
    'source-escape', 'source-secret', 'source-many', 'utf8', 'crlf', 'array', 'file-only',
    'unicode-owner', 'marker-owner', 'symlink-runner', 'source-excluded', 'runner-env'])
def test_native_supply(binary, tmp_path, mode):
    # No reference argument: forwarding cannot make a native fixture pass.
    (tmp_path / '.git').mkdir()
    (tmp_path / 'scripts').mkdir()
    prompt = PROMPT
    output = b'handoff pins:\n{"ok": true}\n'
    script = ''
    if mode == 'ordinary':
        prompt = 'Inspect the repository.'
    elif mode == 'recipient':
        prompt = RECIPIENT_PROMPT + '\nNo commands.\nNo file changes.'
    elif mode == 'forbidden':
        prompt += '\nNo commands.'
    elif mode == 'invalid':
        output = b'handoff pins:\ninvalid'
    elif mode == 'array':
        output = b'handoff pins:\n[]'
    elif mode == 'oversized':
        output = b'handoff pins:\n{"x":"' + b'x' * (1024 * 1024) + b'"}'
    elif mode == 'excluded':
        output = b'handoff pins:\n{"value":"PRIVATE-CANARY-42"}'
    elif mode == 'timeout':
        script = 'import time\ntime.sleep(6)\n'
    elif mode == 'source-escape':
        prompt = PROMPT.replace('Sources: src/example.py', 'Sources: ../escape.py')
    elif mode == 'source-secret':
        prompt = PROMPT.replace('Sources: src/example.py', 'Sources: secrets/key.txt')
    elif mode == 'source-many':
        prompt = PROMPT.replace('src/example.py', ';'.join(f'{i}.py' for i in range(17)), 1)
    elif mode == 'utf8':
        output = b'handoff pins:\n{"x":"\xff"}'
    elif mode == 'crlf':
        output = b'noise\r\nhandoff pins:\r\n{"ok":true}\r\n'
    elif mode == 'unicode-owner':
        prompt += '\nMay: inspect \u00e9\U0001f600\x7f'
    elif mode == 'marker-owner':
        prompt += '\nMay: @@MAY_NOT@@ @@EXCLUDED@@'
    elif mode == 'source-excluded':
        prompt = PROMPT.replace('Sources: src/example.py', 'Sources: PRIVATE-CANARY-42.txt')
    elif mode == 'file-only':
        prompt += '\nNo file changes.'
    script += ('import os, sys\n'
               'assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1"\n'
               'assert os.environ["GIT_OPTIONAL_LOCKS"] == "0"\n'
               'assert sys.argv[1:3] == ["mapping", "--handoff"]\n'
               f'sys.stdout.buffer.write({output!r})\n')
    if mode == 'runner-env':
        script = ('import json, os, sys\n'
                  'print("handoff pins:")\n'
                  'print(json.dumps(dict(cwd=os.getcwd(), executable=sys.executable, '
                  'arguments=sys.argv[1:])))\n')
    if mode == 'nonzero':
        script += 'sys.exit(4)\n'
    (tmp_path / 'scripts/mir_ontology.py').write_text(script, encoding='utf-8')
    if mode == 'symlink-runner':
        runner = tmp_path / 'scripts/mir_ontology.py'
        target = tmp_path / 'real.py'
        runner.rename(target)
        try:
            runner.symlink_to(target)
        except OSError:
            pytest.skip('symlink privilege unavailable')
    event = dict(hook_event_name='UserPromptSubmit', prompt=prompt, cwd=str(tmp_path))
    if mode == 'missing-cwd':
        event.pop('cwd')
    elif mode == 'bad-prompt':
        event['prompt'] = []
    env = dict(os.environ, MIR_HANDOFF_PYTHON=HANDLER_PYTHON, PYTHONUTF8='1')
    outputs = [subprocess.run(cmd, input=json.dumps(event).encode(), capture_output=True,
                              env=env, timeout=12)
               for cmd in ([HANDLER_PYTHON, str(HANDLER)], [str(binary)])]
    assert (outputs[0].stdout, outputs[0].stderr, outputs[0].returncode) == (
        outputs[1].stdout, outputs[1].stderr, outputs[1].returncode)


def test_session_start(binary):
    reference = ROOT / 'plugins/mir-lifecycle-hooks/hooks/runtime_continuity.py'
    native = binary.with_name('runtime-continuity' + binary.suffix)
    outputs = [subprocess.run(cmd, capture_output=True, check=False)
               for cmd in ([HANDLER_PYTHON, str(reference)], [str(native)])]
    assert (outputs[0].stdout, outputs[0].stderr, outputs[0].returncode) == (
        outputs[1].stdout, outputs[1].stderr, outputs[1].returncode)


def test_supply_timeout_tree(binary, tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'scripts').mkdir()
    marker = tmp_path / 'descendant-survived'
    descendant = ('import time; from pathlib import Path; time.sleep(5.7); '
                  f'Path({str(marker)!r}).touch()')
    (tmp_path / 'scripts/mir_ontology.py').write_text(
        'import subprocess, sys, time\n'
        f'subprocess.Popen([sys.executable, "-c", {descendant!r}])\n'
        'time.sleep(6)\n', encoding='utf-8')
    raw = json.dumps(dict(hook_event_name='UserPromptSubmit', prompt=PROMPT,
                          cwd=str(tmp_path))).encode()
    env = dict(os.environ, MIR_HANDOFF_PYTHON=HANDLER_PYTHON, PYTHONUTF8='1')
    outputs = []
    for cmd in ([HANDLER_PYTHON, str(HANDLER)], [str(binary)]):
        start = time.monotonic()
        p = subprocess.run(cmd, input=raw, capture_output=True, env=env, timeout=10)
        assert time.monotonic() - start < 5.6
        outputs.append((p.stdout, p.stderr, p.returncode))
        time.sleep(1)
        assert not marker.exists(), 'runner descendant survived timeout'
    assert outputs[0] == outputs[1]


# Reuse the original pytest functions and marks, including every parameter value.
# Interception at the actual process boundary captures payloads after each test has
# finished updating its transcript, runner, map, and repair history.
runtime = mechanical.runtime
for _name, _test in vars(mechanical).items():
    if _name.startswith('test_') and callable(_test):
        _source = inspect.getsource(_test)
        if 'runtime' in inspect.signature(_test).parameters or "'Stop'" in _source:
            globals()['test_stop_reuse__' + _name.removeprefix('test_')] = _test


@pytest.fixture(autouse=True)
def compare_reused_stop(request, monkeypatch):
    if not request.node.name.startswith('test_stop_reuse__'):
        return
    native_binary = request.getfixturevalue('binary')
    original_run = subprocess.run

    def compare(command, *args, **kwargs):
        direct = list(command) == [HANDLER_PYTHON, str(HANDLER)]
        # The compatibility test also invokes the handler via runpy. Compare its
        # unmodified baseline; its simulated unsupported Python 3.9 invocation
        # intentionally adds an interpreter diagnostic absent from native Rust.
        runpy_baseline = (len(command) == 3 and command[1] == '-c'
                          and str(HANDLER) in command[2]
                          and "run_name='__main__'" in command[2]
                          and 'sys.version_info = (3, 9, 6);' not in command[2])
        if not direct and not runpy_baseline:
            return original_run(command, *args, **kwargs)
        try:
            event = json.loads(kwargs.get('input', ''))
        except (ValueError, TypeError):
            return original_run(command, *args, **kwargs)
        if not isinstance(event, dict) or event.get('hook_event_name') != 'Stop':
            return original_run(command, *args, **kwargs)
        # Compare pipe bytes before providing the original text-mode API to the
        # reused test. In particular Windows newline conversion cannot hide drift.
        options = dict(kwargs)
        text_mode = any([options.pop(key, None) for key in ('text', 'universal_newlines')])
        encoding = options.pop('encoding', None)
        errors = options.pop('errors', None)
        if isinstance(options.get('input'), str):
            options['input'] = options['input'].encode(encoding or 'utf-8', errors or 'strict')
        reference = original_run(command, *args, **options)
        native = original_run([str(native_binary)], *args, **options)
        assert (native.stdout, native.stderr, native.returncode) == (
            reference.stdout, reference.stderr, reference.returncode), event
        if text_mode or encoding or errors:
            reference.stdout = io.TextIOWrapper(io.BytesIO(reference.stdout),
                                                encoding=encoding, errors=errors).read()
            reference.stderr = io.TextIOWrapper(io.BytesIO(reference.stderr),
                                                encoding=encoding, errors=errors).read()
        return reference

    monkeypatch.setattr(subprocess, 'run', compare)


@pytest.fixture
def stop_repository(tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'scripts').mkdir()
    # JSON-escape the path: Windows backslashes are not valid JSON escapes.
    pins = mechanical.PINS.replace('/example', json.dumps(str(tmp_path))[1:-1])
    (tmp_path / 'scripts/mir_ontology.py').write_text(
        f'print({pins!r})\n', encoding='utf-8')
    return tmp_path, pins


def stop_payload(repo, prompt, body, rows=(), shape='claude'):
    if shape == 'claude':
        user = {'type': 'user', 'message': {'content': prompt}}
        assistant = {'type': 'assistant', 'message': {'content': body}}
    else:
        user = {'type': 'response_item', 'payload': {'role': 'user', 'content': prompt}}
        assistant = {'type': 'response_item', 'payload': {'role': 'assistant', 'content': body}}
    transcript = repo / 'stop.jsonl'
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in [user, *rows, assistant]),
                          encoding='utf-8')
    return json.dumps({'hook_event_name': 'Stop', 'cwd': str(repo),
                       'session_id': 'native-stop', 'transcript_path': str(transcript),
                       'stop_hook_active': False, 'last_assistant_message': body}).encode()


@pytest.mark.parametrize('matches', [True, False], ids=['matching-pins', 'changed-head'])
def test_native_stop_fake_repository_pins(binary, stop_repository, matches):
    repo, pins = stop_repository
    body = mechanical.packet(pins)
    if not matches:
        body = body.replace('a' * 40, 'f' * 40)
    reference, native = run_pair(binary, stop_payload(repo, PROMPT, body))
    assert ('decision' in json.loads(reference[0] or b'{}')) is not matches
    assert native == reference


def test_native_stop_preserves_warning_before_exception(binary, stop_repository):
    repo, _ = stop_repository
    payload = json.loads(stop_payload(repo, PROMPT + '\nNo commands.', mechanical.packet()))
    del payload['cwd']
    reference, native = run_pair(binary, json.dumps(payload).encode())
    warnings = reference[1].splitlines()
    assert len(warnings) == 2
    assert b'owner forbids commands; no runner performed.' in warnings[0]
    assert b'hook unavailable; allowing turn to continue.' in warnings[1]
    assert native == reference


@pytest.mark.parametrize('shape', ['claude', 'codex'])
@pytest.mark.parametrize('count', [0, 1, 2, 3])
def test_native_stop_repair_limit_reused_ids(binary, stop_repository, shape, count):
    repo, _ = stop_repository
    rows = mechanical.ROUND_S_REPAIRS[:count]
    if shape == 'claude':
        rows = [{'type': 'system', 'subtype': 'hook_response', 'hookName': 'Stop',
                 'hookRunId': 'stop:21:/synthetic/hooks/hooks.json',
                 'stdout': row['payload']['content'][0]['text']}
                for row in rows]
    raw = stop_payload(repo, RECIPIENT_PROMPT, 'Done.', rows, shape)
    reference, native = run_pair(binary, raw)
    assert ('decision' in json.loads(reference[0] or b'{}')) is (count < 2)
    assert native == reference


STOP_REGRESSIONS = [
    ('round-r-source-' + str(i), PROMPT, claim)
    for i, claim in enumerate(mechanical.ROUND_R_SOURCE_CLAIMS)
] + [
    ('round-s-authority-' + str(i), PROMPT, claim)
    for i, claim in enumerate(mechanical.ROUND_S_AUTHORITY)
] + [
    ('round-s-inventory-' + str(i), RECIPIENT_PROMPT, inventory)
    for i, inventory in enumerate(mechanical.ROUND_S_INVENTORIES)
] + [
    ('round-s-digest', RECIPIENT_PROMPT, mechanical.ROUND_S_DIGEST),
    ('round-t-owner', PROMPT, 'Only the owner may approve edits.'),
    ('round-t-pin-heading', 'Review this received handoff.\n- **pins:**\n'
     '  - repository_root: parent-supplied(example)\n  - head: parent-supplied(example)',
     mechanical.RECIPIENT_LABELS),
    ('round-t-reader', RECIPIENT_PROMPT + '\nNo commands.', mechanical.RECIPIENT_LABELS +
     '\n\uc18c\uc2a4 \ub9ac\ub354\ub97c \ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4. '
     '\uc15c\u00b7\ucf54\ub4dc \uc778\ud130\ud504\ub9ac\ud130\ub294 '
     '\uc2e4\ud589\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.'),
    ('round-t-evidence', PROMPT, 'Controls would need to be run to verify the claim.'),
    ('round-t-source', PROMPT, '- **`scripts/check.py`**\n  - 12\u201314: inspect branches.\n'
     '  - All reports end with "review required".'),
    ('korean-owner-ban', KO_HANDOFF + '\n' + KO_NO_COMMANDS,
     '### \uad8c\ud55c\n- \ud5c8\uc6a9: \ud30c\uc77c \uc218\uc815'),
]


@pytest.mark.parametrize('name,prompt,claim', STOP_REGRESSIONS,
                         ids=[case[0] for case in STOP_REGRESSIONS])
def test_native_stop_regressions(binary, stop_repository, name, prompt, claim):
    repo, pins = stop_repository
    if prompt.startswith('Review this received handoff.'):
        body = claim
    else:
        body = mechanical.packet(pins).replace(
            hashlib.sha256(PROMPT.encode()).hexdigest(),
            hashlib.sha256(prompt.encode()).hexdigest()) + '\n' + claim
    reference, native = run_pair(binary, stop_payload(repo, prompt, body))
    assert native == reference, name
