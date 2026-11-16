"""Capture helpers are loaded without executing either oracle generator."""
import ast
import json
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / 'native/handoff-packet/tests/fixtures'


def helpers(name):
    tree = ast.parse((FIXTURES / f'generate_y_{name}.py').read_text(encoding='utf-8'))
    scope = {'subprocess': subprocess}
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)],
                            type_ignores=[]), str(FIXTURES), 'exec'), scope)
    return scope


def spellings(path):
    native = path.removeprefix('\\\\?\\')
    for base in (path, path.replace('\\', '/'), '\\\\?\\' + native):
        for _ in range(3):
            yield base
            base = base.replace('\\', '\\\\')


@pytest.mark.parametrize('root', [r'C:\Users\Synthetic\scratch\case',
                                 r'\\?\C:\Users\Synthetic\scratch\case',
                                 r'\\?\UNC\server\share\case'])
def test_e14_nested_record_scrub(root):
    scope = helpers('e14')
    nested = json.dumps({'nested': json.dumps({'path': root})})
    assert root not in scope['observe_root'](nested, root)
    assert '{ROOT}' in scope['observe_root'](nested, root)
    for path in spellings(root):
        record = '{"nested": "' + path + '/suffix"}'
        assert scope['observe_root'](record, root) == '{"nested": "{ROOT}/suffix"}'


def test_e14_guard_rejects_remaining_paths():
    scope = helpers('e14')
    root = r'C:\Users\Synthetic\scratch'
    for path in spellings(root):
        with pytest.raises(AssertionError, match='absolute scratch path'):
            scope['assert_scrubbed']('{"nested": "' + path + '"}', [root])
    scope['assert_scrubbed']('{"nested": "{ROOT}/suffix"}', [root])


def test_e17_failed_child_diagnostics(tmp_path):
    # A real OS child exits 1 and emits invalid UTF-8 on both streams.
    import sys

    scope = helpers('e17')
    argv = [sys.executable, '-I', '-c',
            "import os; os.write(1, b'out\\xff'); os.write(2, b'err\\xfe'); raise SystemExit(1)"]
    with pytest.raises(RuntimeError) as failure:
        scope['run_oracle'](argv, cwd=tmp_path)
    message = str(failure.value)
    for expected in (repr(argv), 'exit=1', 'stdout=out\\xff', 'stderr=err\\xfe'):
        assert expected in message
    assert scope['run_oracle']([sys.executable, '-I', '-c', 'print("ok")'],
                               cwd=tmp_path).stdout == b'ok\n'
