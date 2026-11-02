"""Capture review evidence from the unchanged Python runner, without providers."""
import dataclasses
import json
import pathlib
import re
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.mir_executor.codex_mcp_client import CodexMcpClient  # noqa: E402
from tools.mir_executor.dispatch import build_codex_review_runner  # noqa: E402

HERE = pathlib.Path(__file__).parent
CONTENTS = [
    '{"verdict":"pass","reason":"ok","findings":[]}',
    '{"verdict":"fail","reason":"unsafe","findings":["bug"]}',
    '{"verdict":"pass","reason":"","findings":["bug"]}',
    '{"verdict":"pass","reason":"","findings":[]}',
    '{"verdict":"fail","reason":"","findings":[]}',
    '', '{bad', 'null', '[]', '{}',
    '{"verdict":"pass","reason":"ok","findings":[],"extra":true}',
    '{"verdict":"pass","reason":1,"findings":[]}',
    '{"verdict":"pass","reason":"ok","findings":[1]}',
    '{"verdict":"PASS","reason":"ok","findings":[]}',
    '{"verdict":"pass","reason":"ok","findings":null}',
]


def capture(content):
    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call_codex(self, **kwargs):
            assert kwargs['sandbox'] == 'read-only'
            assert kwargs['approval_policy'] == 'never'
            return SimpleNamespace(content_text=content)

    with patch('tools.mir_executor.dispatch.validate_timeout'), patch(
        'tools.mir_executor.dispatch.dispatch_env', return_value={}
    ), patch(
        'tools.mir_executor.dispatch.after_provider_call', side_effect=lambda _, value, **kw: value
    ):
        evidence = build_codex_review_runner(ROOT, client_factory=Client)(
            SimpleNamespace(path=pathlib.Path('.'), dispatch_id='fixture'), ['pkg/mod.py']
        )
    return {'content': content, 'expected': dataclasses.asdict(evidence)}


def protocol_capture(mode):
    popen = subprocess.Popen
    metadata = {}

    def spawn(*args, **kwargs):
        return popen([sys.executable, str(HERE / 'executor_review_server.py'), mode], **kwargs)

    def observe(_root, _name, _result, value):
        metadata.update(value)

    with patch('subprocess.Popen', side_effect=spawn), patch(
        'tools.mir_executor.dispatch.validate_timeout'
    ), patch('tools.mir_executor.dispatch.dispatch_env', return_value={}), patch(
        'tools.mir_executor.local_hooks.invoke_hook', side_effect=observe
    ):
        result = build_codex_review_runner(
            ROOT, timeout_seconds=3 if mode == 'timeout' else 15,
            client_factory=CodexMcpClient,
        )(SimpleNamespace(path=pathlib.Path('.'), dispatch_id='fixture'),
          ['pkg/\uac00\U0001f600\x7f.py', 'quote"\\.py'] if mode == 'unicode' else ['pkg/mod.py'])
    # Elapsed time is an observation, not a deterministic fixture field.
    metadata.pop('elapsed_seconds')
    expected = dataclasses.asdict(result)
    if mode == 'timeout':
        expected['content'] = re.sub(r'after [0-9.e+-]+s', 'after <seconds>s', expected['content'])
    return {'mode': mode, 'expected': expected, 'metadata': metadata}


if __name__ == '__main__':
    (HERE / 'executor_review.json').write_text(
        json.dumps([capture(content) for content in CONTENTS], indent=2, ensure_ascii=True) + '\n',
        encoding='utf-8',
    )
    (HERE / 'executor_review_protocol.json').write_text(
        json.dumps([protocol_capture(mode) for mode in (
            'approve', 'reject', 'malformed', 'empty', 'missing', 'timeout', 'unicode'
        )], indent=2, ensure_ascii=True) + '\n', encoding='utf-8',
    )
