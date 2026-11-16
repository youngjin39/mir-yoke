"""Check the actual oracle child invocation without executing the reference."""
import ast
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('name', ['generate_y_e9.py', 'generate_y_e10_constructor.py'])
def test_windows_capture_invocation(name, tmp_path):
    tree = ast.parse(Path(__file__).with_name(name).read_text())
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and ast.unparse(n.func) == 'subprocess.run')
    scope = dict(os=SimpleNamespace(name='nt', defpath=os.defpath,
                                   environ={'SystemRoot': 'synthetic-system',
                                            'WINDIR': 'synthetic-windir'}),
                 work=tmp_path, root=tmp_path, wrapper=tmp_path / 'capture.py',
                 sys=sys, json=__import__('json'), removed=False, args=['context'],
                 argv=['context'], key='', env={})
    base = ast.parse(Path(__file__).with_name('generate_y_e9.py').read_text())
    helper = next(n for n in base.body if isinstance(n, ast.FunctionDef))
    exec(compile(ast.Module(body=[helper], type_ignores=[]), name, 'exec'), scope)
    scope['setup'] = {'console_env': scope['console_env']}
    # Load only helper definitions, never the top-level archive or capture loop.
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            exec(compile(ast.Module(body=[node], type_ignores=[]), name, 'exec'), scope)
    child_env = eval(compile(ast.Expression(next(k.value for k in call.keywords
                                               if k.arg == 'env')), name, 'eval'), scope)
    assert child_env['HOME'] == str(tmp_path)
    assert child_env.get('SystemRoot') == 'synthetic-system'
    assert child_env.get('WINDIR') == 'synthetic-windir'
    argv = eval(compile(ast.Expression(call.args[0]), name, 'eval'), scope)
    assert argv[argv.index('-X') + 1] == 'utf8'
