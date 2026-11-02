"""Portable stdlib-only reviewer app-server; fails on any writable request."""
import json
import sys
import time

mode = sys.argv[1]


def send(value):
    print(json.dumps(value), flush=True)


for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    if method == 'initialize':
        send({'id': request['id'], 'result': {'userAgent': 'review-fixture/1'}})
    elif method == 'thread/start':
        params = request['params']
        assert params['sandbox'] == 'read-only', params
        assert params['approvalPolicy'] == 'never'
        assert 'codex-final-reviewer' in params['baseInstructions']
        send({'id': request['id'], 'result': {
            'thread': {'id': 'review'}, 'model': 'fixture-model'}})
    elif method == 'turn/start':
        prompt = request['params']['input'][0]['text']
        paths = (
            ['pkg/\uac00\U0001f600\x7f.py', 'quote"\\.py'] if mode == 'unicode' else ['pkg/mod.py']
        )
        assert f'Changed files: {json.dumps(paths)}' in prompt
        send({'id': request['id'], 'result': {'turn': {'id': 'turn'}}})
        if mode == 'timeout':
            time.sleep(60)
        if mode == 'missing':
            sys.exit(0)
        content = {
            'approve': '{"verdict":"pass","reason":"ok","findings":[]}',
            'reject': '{"verdict":"fail","reason":"unsafe","findings":["bug"]}',
            'malformed': '{}',
            'empty': '',
            'unicode': '{"verdict":"pass","reason":"ok","findings":[]}',
        }[mode]
        send({'method': 'thread/tokenUsage/updated', 'params': {
            'threadId': 'review', 'tokenUsage': {'last': {
                'inputTokens': 12, 'outputTokens': 3, 'totalTokens': 15}}}})
        send({'method': 'turn/completed', 'params': {'threadId': 'review', 'turn': {
            'id': 'turn', 'status': 'completed', 'items': [
                {'id': 'answer', 'type': 'agentMessage', 'text': content}]}}})
