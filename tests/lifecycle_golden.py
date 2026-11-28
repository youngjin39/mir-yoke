"""Decode immutable lifecycle reference captures without executing an oracle."""
import ast
import base64
import json
import os
import re
import subprocess
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / 'native/handoff-packet/tests/fixtures/g6/lifecycle.json').read_text())


def unpack(blob):
    if 'blob' in blob:
        blob = GOLDEN['blobs'][blob['blob']]
    if 'text' in blob:
        return blob['text'].encode()
    data = base64.b64decode(blob.get('zlib_base64', blob.get('base64')))
    return zlib.decompress(data) if 'zlib_base64' in blob else data


def _replacement(text, token, value, context):
    """Escape only inserted bytes, retaining every original capture byte."""
    pattern = r'"(?:\\.|[^"\\])*"'
    if context == 'python':
        pattern = r"'(?:\\.|[^'\\])*'|" + pattern
    position = text.find(token)
    for match in re.finditer(pattern, text):
        if not match.start() <= position < match.end():
            continue
        try:
            inner = (ast.literal_eval(match.group()) if context == 'python'
                     else json.loads(match.group()))
        except (ValueError, SyntaxError):
            break
        inserted = _replacement(inner, token, value, context)
        if context == 'python':
            # Both quote styles may occur in synthetic helper source.
            return inserted.replace('\\', '\\\\').replace(match.group()[0],
                                                        '\\' + match.group()[0])
        return json.dumps(inserted, ensure_ascii=False)[1:-1]
    return value


def expand(blob, tmp_path, *, stream=False, context='json'):
    import sys
    data = unpack(blob).decode('utf-8', errors='surrogateescape')
    if stream:
        context = 'json'
    for token, value in [('@TMP@', str(tmp_path)), ('@REPO@', str(ROOT)),
                         ('@PYTHON@', sys.executable)]:
        if context == 'plain':
            data = data.replace(token, value)
        else:
            # Each occurrence may have a different serialization depth.
            offset = 0
            while (position := data.find(token, offset)) >= 0:
                inserted = _replacement(data, token, value, context)
                data = data[:position] + inserted + data[position + len(token):]
                offset = position + len(inserted)
    data = data.encode('utf-8', errors='surrogateescape')
    if stream and os.name == 'nt':
        data = data.replace(b'\n', b'\r\n')
    return data


def snapshot_context(name):
    if name.endswith('.py'):
        return 'python'
    if name.endswith(('.json', '.jsonl')):
        return 'json'
    return 'plain'


def expected_result(record, tmp_path):
    return subprocess.CompletedProcess([], record['returncode'],
        expand(record['stdout'], tmp_path, stream=True),
        expand(record['stderr'], tmp_path, stream=True))


def install_snapshot(snapshot, tmp_path):
    for name, value in snapshot.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if 'directory' in value:
            path.mkdir(exist_ok=True)
        elif 'symlink' in value:
            target = value['symlink'].replace('@TMP@', str(tmp_path))
            try:
                path.symlink_to(target)
            except OSError:
                pytest.skip('symlink privilege unavailable')
        else:
            path.write_bytes(expand(value, tmp_path, context=snapshot_context(name)))


FROZEN_CASES = [
    (name, index, record)
    for name, records in GOLDEN['records'].items()
    for index, record in enumerate(records)
    # Python interpreter startup diagnostics retire with the Python entrypoint.
    if 'native_applicability' not in record
]
