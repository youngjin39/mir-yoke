"""Capture the unchanged Python client using only a portable fake child."""
import json
import pathlib
import re
import subprocess
import sys
import threading
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor.codex_mcp_client import CodexMcpClient  # noqa: E402

HERE = pathlib.Path(__file__).parent
MODES = '''normal streaming server_error malformed unknown_ids stderr_flood stall deadline cancel
exit_before_response nested_limits early_completion invalid_id invalid_envelope missing_thread
missing_turn invalid_item invalid_item_type empty_item_id invalid_item_text unknown_item_type
commentary failed interrupted wrong_turn invalid_turn invalid_items duplicate_items heartbeat
reader_eof approval thread_timeout blocked_send deadline_activity completion_model_usage
invalid_completion_params invalid_thread_id callback_error'''.split()
POPEN = subprocess.Popen


def capture(mode):
    def spawn(*args, **kwargs):
        return POPEN([sys.executable, str(HERE / 'executor_transport_server.py'), mode], **kwargs)

    client = CodexMcpClient(kill_timeout=0.1)
    timer = None
    with patch('subprocess.Popen', side_effect=spawn):
        try:
            client.start()
            if mode == 'cancel':
                # Cancel at a protocol boundary, independent of child startup speed.
                client._progress_callback = None
                original = client._handle_stdout_line

                def handle(line):
                    nonlocal timer
                    original(line)
                    if '"id": 3' in line:
                        timer = threading.Timer(0.05, client.close)
                        timer.start()
                client._handle_stdout_line = handle
            def progress(method, _params):
                if mode == 'callback_error' and method == 'test/callback':
                    raise ValueError('fixture callback')

            short = mode in ('deadline', 'thread_timeout', 'blocked_send', 'deadline_activity')
            result = client.call_codex(
                prompt='x' * (2 * 1024 * 1024) if mode == 'blocked_send' else 'hello',
                cwd='.', sandbox='workspace-write', model='fixture', base_instructions='base',
                config={'effort': 'medium'}, timeout=0.3 if short else 3,
                progress_callback=progress,
                stall_timeout={'stall': 0.15, 'heartbeat': 0.5}.get(mode))
            outcome = {'text': result.content_text, 'thread_id': result.thread_id,
                       'model_id': result.model_id, 'usage': result.token_usage,
                       'tool_version': result.tool_version, 'raw_result': result.raw_result}
        except Exception as exc:
            message = str(exc)
            # Preserve all static message bytes; elapsed seconds are runtime observations.
            message = re.sub(r'after [0-9.e+-]+s', 'after <seconds>s', message)
            outcome = {'error': type(exc).__name__, 'message': message}
        finally:
            if timer:
                timer.join()
            client.close()
    return {'mode': mode, 'expected': outcome, 'malformed': len(client.malformed_messages),
            'stderr': len(client.stderr_lines)}


if __name__ == '__main__':
    (HERE / 'executor_transport.json').write_text(
        json.dumps([capture(mode) for mode in MODES], indent=2, ensure_ascii=True) + '\n',
        encoding='utf-8')
