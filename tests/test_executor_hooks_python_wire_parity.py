"""Record real Rust/Python hook stdin frames and compare every byte in order."""
from __future__ import annotations

import hashlib
import json
import os
import runpy
from pathlib import Path

import pytest

from tools.mir_executor.native_hooks import HookSession, require_success

ROOT = Path(__file__).resolve().parents[1]
PARITY = runpy.run_path(str(ROOT / 'tests/test_executor_hooks_native_parity.py'))
SUPPORT = PARITY['SUPPORT']
binary = PARITY['binary']
HOST = '''#!/usr/bin/env python3
import json
import sys
from pathlib import Path
log = Path(sys.argv[1])
print(json.dumps({'version': 'mir-executor.hooks@1',
                  'hooks': ['writer_scope', 'on_job_event']}), flush=True)
for frame in sys.stdin.buffer:
    with log.open('ab') as stream:
        stream.write(frame)
    request = json.loads(frame)
    result = {'token': 'opaque'} if request['hook'] == 'writer_enter' else None
    print(json.dumps({'version': 'mir-executor.hooks@1', 'id': request['id'],
                     'ok': True, 'result': result}), flush=True)
'''


@pytest.mark.skipif(os.name == 'nt', reason='fixture host uses a POSIX executable shebang')
def test_rust_and_python_emit_identical_hook_frames(binary, tmp_path):
    root = tmp_path / 'wire home \ud55c\uae00'
    launcher = SUPPORT['seed'](root, 'success')
    (root / 'tools/mir_executor/local.py').unlink(missing_ok=True)
    environment = SUPPORT['environment'](root, 'success', launcher)
    host = root / 'recording-host'
    host.write_text(HOST, encoding='utf-8')
    host.chmod(0o755)
    rust_log, python_log = root / 'rust-wire', root / 'python-wire'
    config = {
        'executable': host.name, 'argv': [str(rust_log)],
        'sha256': hashlib.sha256(host.read_bytes()).hexdigest(),
        'hooks': ['writer_scope', 'on_job_event'],
    }
    (root / 'config').mkdir()
    (root / 'config/mir-executor.local.json').write_text(
        json.dumps({'native_policy': {'version': 1, 'hooks': config}}), encoding='utf-8',
    )
    result = PARITY['PARITY']['invoke'](
        binary, root, environment, SUPPORT['argv']('background_success'),
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    rust_frames = rust_log.read_bytes().splitlines(keepends=True)
    requests = [json.loads(frame) for frame in rust_frames]
    assert requests[0]['hook'] == 'writer_enter'
    assert requests[-1]['hook'] == 'writer_exit'
    assert any(request['hook'] == 'on_job_event' for request in requests)
    assert all(frame.endswith(b'\n') for frame in rust_frames)

    # Replay captured runtime values verbatim, including IDs, timestamps and argv.
    # Both real clients write to a fresh host; the assertion reads raw pipe bytes.
    session = HookSession(root, dict(config, argv=[str(python_log)]))
    try:
        for request in requests:
            require_success(session.call(request['hook'], request['params']))
    finally:
        session.close()
    python_frames = python_log.read_bytes().splitlines(keepends=True)
    assert python_frames == rust_frames
