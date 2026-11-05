"""Decode immutable lifecycle reference captures without executing an oracle."""
import base64
import json
import os
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


def expand(blob, tmp_path, *, stream=False):
    import sys
    data = unpack(blob)
    for token, value in [('@TMP@', str(tmp_path)), ('@REPO@', str(ROOT)),
                         ('@PYTHON@', sys.executable)]:
        data = data.replace(token.encode(), value.encode())
    if stream and os.name == 'nt':
        data = data.replace(b'\n', b'\r\n')
    return data


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
            path.write_bytes(expand(value, tmp_path))


FROZEN_CASES = [
    (name, index, record)
    for name, records in GOLDEN['records'].items()
    for index, record in enumerate(records)
    # Python interpreter startup diagnostics retire with the Python entrypoint.
    if 'native_applicability' not in record
]
