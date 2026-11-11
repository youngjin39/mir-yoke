"""Capture JSON admission from an explicitly supplied frozen Python reference."""
import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    reference, output = map(Path, sys.argv[1:])
    prefix = (b'{"hook_event_name":"PreToolUse","tool_name":"Bash",'
              b'"prompt":"Write a handoff for agent receiver. Do not run any commands. '
              b'Owner instruction: no commands.","ignored":')
    cases = {
        'baseline': b'null', 'nan': b'NaN', 'infinity': b'Infinity',
        'negative-infinity': b'-Infinity', 'overflow': b'1e400',
        'huge-integer': b'1' + b'0' * 400,
        'high-surrogate': b'"\\ud800"', 'low-surrogate': b'"\\udcff"',
        'surrogate-pair': b'"\\ud800\\udc00"',
        'deep': b'[' * 140 + b'0' + b']' * 140,
        'depth-9995': b'[' * 9995 + b'0' + b']' * 9995,
        'depth-9996': b'[' * 9996 + b'0' + b']' * 9996,
        'depth-9997': b'[' * 9997 + b'0' + b']' * 9997,
        'integer-4300': b'1' * 4300,
        'integer-4301': b'1' * 4301,
        'invalid-utf8': b'"\xff"',
        'quoted-special': b'"NaN Infinity 1e400 \\ud800"',
        'malformed-object': b'{', 'malformed-number': b'1e',
        'malformed-nan': b'NaNgarbage', 'malformed-escape': b'"\\x00"',
        'malformed-control': b'"\x01"', 'trailing-comma': b'[0,]',
    }
    inputs = [(name, prefix + value + b'}') for name, value in cases.items()]
    base = prefix + b'null}'
    inputs.extend([
        ('bom', b'\xef\xbb\xbf' + base),
        ('trailing-data', base + b'0'),
        ('event-not-object', b'[]'),
        ('used-nan-tool', base.replace(b'"Bash"', b'NaN')),
        ('used-array-tool', base.replace(b'"Bash"', b'[]')),
        ('used-surrogate-tool', base.replace(b'"Bash"', b'"\\ud800"')),
        ('used-surrogate-prompt', base.replace(b'Write a handoff', b'\\ud800 Write a handoff')),
        ('used-overflow-prompt', base.replace(
            base.split(b'"prompt":')[1].split(b',"ignored"')[0], b'1e400')),
        ('escaped-key', base.replace(b'hook_event_name', b'\\u0068ook_event_name')),
        ('surrogate-key', base.replace(b'ignored', b'\\ud800')),
        ('literal-marker', base.replace(b'null', b'{"__python_number__":"NaN"}')),
        ('missing-tool', base.replace(b'"tool_name":"Bash",', b'')),
        ('exec-null-arguments', base.replace(b'"Bash"', b'"exec"').replace(
            b'"ignored":null', b'"tool_input":null')),
        ('oversize', base),
    ])
    records = []
    env = dict(os.environ, PATH='', PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    for name, raw in inputs:
        spaces = 1024 * 1024 if name == 'oversize' else 0
        result = subprocess.run([sys.executable, str(reference)], input=b' ' * spaces + raw,
                                capture_output=True, env=env, check=False)
        def encode(value):
            return base64.b64encode(value).decode('ascii')
        records.append(dict(name=name, input=encode(raw), input_prefix_spaces=spaces,
                            stdout=encode(result.stdout),
                            stderr=encode(result.stderr), code=result.returncode))
    output.write_text(json.dumps({'reference': '8c58654:plugins/mir-lifecycle-hooks/skills/'
                                 'runtime-continuity/scripts/handoff_packet.py',
                                 'reference_sha256': hashlib.sha256(
                                     reference.read_bytes()).hexdigest(),
                                 'records': records}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
