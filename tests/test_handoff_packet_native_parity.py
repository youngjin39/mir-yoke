"""Byte parity with the unchanged Python reference; Rust remains optional."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_mechanical_handoff import HANDLER, PROMPT, RECIPIENT_PROMPT

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
    env = dict(os.environ, CARGO_HOME=str(CRATE / 'target/cargo-home'),
               CARGO_TARGET_DIR=str(CRATE / 'target'))
    subprocess.run(['cargo', 'build', '--release', '--offline', '--locked'],
                   cwd=CRATE, env=env, check=True, capture_output=True)
    return CRATE / 'target/release/handoff-packet'


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
    outputs = [subprocess.run(command, input=raw, capture_output=True, timeout=10)
               for command in (["python3", str(HANDLER)], [str(binary), str(HANDLER)])]
    return [(p.stdout, p.stderr, p.returncode) for p in outputs]


@pytest.mark.parametrize(('name', 'raw'), CASES, ids=[c[0] for c in CASES])
def test_byte_parity(binary, name, raw):
    reference, native = run_pair(binary, raw)
    assert native == reference, name


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
        path.write_text('not json\n')
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
    assert json.loads(p.stdout)['systemMessage'].encode() + b'\n' == p.stderr
    assert b'hook unavailable; allowing turn to continue.' in p.stderr
