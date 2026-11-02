"""Portable offline app-server used only by direct-execute parity fixtures."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def send(value):
    print(json.dumps(value), flush=True)


root = Path(os.environ['EXECUTE_FIXTURE_ROOT'])
mode = os.environ['EXECUTE_FIXTURE_MODE']
(root / 'provider-started').write_text('started', encoding='utf-8')
for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    with (root / 'provider-methods').open('a', encoding='utf-8') as stream:
        stream.write(method + '\n')
    if method == 'initialize':
        if os.environ.get('EXECUTE_FIXTURE_GATE') == '1':
            deadline = time.monotonic() + 40
            while not (root / 'provider-release').exists():
                if time.monotonic() > deadline:
                    raise RuntimeError('fixture gate was not released')
                time.sleep(0.01)
        send({'id': request['id'], 'result': {'userAgent': 'offline-execute/1'}})
    elif method == 'thread/start':
        assert request['params']['approvalPolicy'] == 'never'
        assert request['params']['cwd'] == str(root)
        assert request['params']['config']['project_doc_max_bytes'] == 0
        send({'id': request['id'], 'result': {'thread': {'id': 'fixture-thread'},
                                           'model': 'offline-fixture'}})
    elif method == 'turn/start':
        assert request['params']['input'] == [{'type': 'text', 'text': 'offline fixture'}]
        send({'id': request['id'], 'result': {'turn': {'id': 'fixture-turn'}}})
        if mode == 'timeout':
            time.sleep(30)
        turn = {'id': 'fixture-turn', 'status': 'completed', 'items': [
            {'id': 'fixture-item', 'type': 'agentMessage', 'text': "done 'quoted' \\ \u2713\n"}]}
        if mode == 'error':
            turn.update(status='failed', error={'message': 'offline provider failure'})
        send({'method': 'turn/completed', 'params': {'threadId': 'fixture-thread',
                                                    'turn': turn}})
