"""Offline, portable app-server scenarios shared by Python and Rust."""
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
        assert request == {'id': 1, 'method': 'initialize', 'params': {
            'capabilities': {}, 'clientInfo': {'name': 'mir_executor', 'version': '0.1.0'}}}
        send({'id': 1, 'result': {'userAgent': ' fake/1 '}})
    elif method == 'initialized':
        assert 'id' not in request
    elif method == 'thread/start':
        assert request['id'] == 2
        assert request['params'] == {'cwd': '.', 'sandbox': 'workspace-write',
                                     'approvalPolicy': 'never', 'model': 'fixture',
                                     'baseInstructions': 'base', 'config': {'effort': 'medium'}}
        if mode == 'server_error':
            send({'id': 2, 'error': {'message': 'bad model'}})
        elif mode == 'missing_thread':
            send({'id': 2, 'result': {}})
        else:
            if mode == 'thread_timeout':
                time.sleep(30)
            send({'id': 2, 'result': {'thread': {'id': 'thread-1'}, 'model': 'fixture'}})
            if mode == 'blocked_send':
                time.sleep(30)
    elif method == 'turn/start':
        assert request == {'id': 3, 'method': 'turn/start', 'params': {
            'threadId': 'thread-1', 'input': [{'type': 'text', 'text': 'hello'}]}}
        if mode == 'exit_before_response':
            sys.exit(7)
        if mode == 'reader_eof':
            sys.stdout.close()
            import os
            os.close(1)
            time.sleep(30)
        if mode == 'blocked_send':
            time.sleep(30)
        if mode == 'unknown_ids':
            for key in (999999, 'turn:thread-1', '3'):
                send({'id': key, 'result': 'spoof', 'error': {'message': 'spoof'}})
        if mode == 'invalid_id':
            send({'id': [], 'result': {}})
        if mode == 'invalid_envelope':
            send({'id': 3, 'result': {}, 'error': {}})
        if mode == 'malformed':
            for raw in ('{bad', '[]', '', '{}'):
                print(raw, flush=True)
        if mode == 'nested_limits':
            print('[' * 10000 + '0' + ']' * 10000, flush=True)
            print('{"method":"ignored","params":' + '[' * 200 + '0' + ']' * 200 + '}', flush=True)
        if mode == 'stderr_flood':
            for _ in range(2048):
                print('diagnostic' * 100, file=sys.stderr, flush=True)
        turn = {'id': 'turn-1', 'status': 'completed', 'items': []}
        item = {'id': 'item-1', 'type': 'agentMessage', 'text': 'completed \u2713'}
        if mode == 'invalid_item':
            item = None
        if mode == 'invalid_item_type':
            item['type'] = None
        if mode == 'empty_item_id':
            item['id'] = ''
        if mode == 'invalid_item_text':
            item['text'] = None
        if mode == 'unknown_item_type':
            item['type'] = 'futureItem'
        if mode == 'commentary':
            item['phase'] = 'commentary'
        if mode == 'failed':
            turn.update(status='failed', error={'message': 'model unavailable'})
        if mode == 'interrupted':
            turn['status'] = 'interrupted'
        if mode == 'wrong_turn':
            turn['id'] = 'other'
        if mode == 'invalid_turn':
            turn['status'] = None
        if mode == 'completion_model_usage':
            turn.update(modelId='resolved', usage={'inputTokens': 20})
        if mode == 'invalid_items':
            turn['items'] = None
        completion = {'method': 'turn/completed', 'params': {'threadId': 'thread-1', 'turn': turn}}
        send({'method': 'thread/tokenUsage/updated', 'params': {
            'threadId': 'thread-1',
            'tokenUsage': {'total': {'inputTokens': 12, 'outputTokens': 3}}}})
        if mode == 'early_completion':
            turn['items'] = [item]
            send(completion)
        send({'id': 3, 'result': {'turn': {'id': '' if mode == 'missing_turn' else 'turn-1'}}})
        if mode == 'cancel':
            send({'method': 'test/cancel', 'params': {}})
        if mode == 'deadline_activity':
            for _ in range(100):
                send({'method': 'heartbeat', 'params': {}})
                time.sleep(0.05)
        if mode in ('stall', 'deadline', 'cancel'):
            time.sleep(30)
        if mode in ('streaming', 'heartbeat'):
            for _ in range(16):
                send({'method': 'item/agentMessage/delta', 'params': {'delta': 'partial'}})
                time.sleep(0.05)
        if mode == 'approval':
            send({'id': 'approval-1', 'method': 'requestApproval', 'params': {}})
            continue
        if mode != 'early_completion':
            if mode == 'invalid_completion_params':
                send({'method': 'turn/completed', 'params': []})
            if mode == 'invalid_thread_id':
                send({'method': 'item/completed', 'params': {'threadId': []}})
            if mode == 'callback_error':
                send({'method': 'test/callback', 'params': {}})
            send({'method': 'item/completed', 'params': {'threadId': 'thread-1', 'item': item}})
            if mode == 'duplicate_items':
                turn['items'] = [item]
            send(completion)
