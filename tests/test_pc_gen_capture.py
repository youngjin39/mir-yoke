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


def test_e17_round_comparison_preserves_other_paths():
    scope = helpers('e17')
    roots = [r'C:\scratch\r1', r'C:\scratch\r2']
    records = [[{'project_root': root + r'\oracle\case-0', 'platform': 'win32',
                 'reference_pin': '5f8f69f94e09b64c5e4d07d329ed17797c35e6cb',
                 'calls': [['sync', '--project-root', root + r'\oracle\case-0']],
                 'stderr': 'unchanged'}] for root in roots]
    observed = [scope['observe_capture_round'](r, root)
                for r, root in zip(records, roots, strict=True)]
    assert observed[0] == observed[1]
    assert records[0][0]['project_root'] != records[1][0]['project_root']
    records[1][0]['stderr'] = roots[1]
    assert scope['observe_capture_round'](records[1], roots[1]) != observed[0]
    records[1][0]['calls'][0][2] = roots[1].replace('\\', '/') + '/oracle/case-0'
    with pytest.raises(AssertionError, match='--project-root spelling'):
        scope['observe_capture_round'](records[1], roots[1])
    records[1][0]['project_root'] = roots[1] + r'\other'
    with pytest.raises(AssertionError, match='project_root'):
        scope['observe_capture_round'](records[1], roots[1])
