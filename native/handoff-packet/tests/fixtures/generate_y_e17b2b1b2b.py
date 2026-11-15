"""Additive main carrier captures, using the pinned isolated B30 harness."""
import json
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e13.py").read_text().split("resources =")[0], scope)
a, root, packages = (scope[k] for k in ("a", "root", "packages"))
source = subprocess.check_output([
    '/usr/bin/git', 'show', scope['pin'] + ':tests/test_w2_b30_bootstrap_main_frozen.py'
]).decode().split('\nMODES =')[0].replace('import pytest', '')
# These are the pinned harness seams, with only capability evidence replaced.
source = source.replace("if mode != 'synthetic_e2e':\n            for name, value",
                        "scripts['_activate_capabilities'] = scripts['_finalize_capabilities'] = "
                        "(r['status'], r['evidence'])\n        if mode != 'synthetic_e2e':\n"
                        "            for name, value")
wrapper = root / 'capture.py'
wrapper.write_text('''import sys, pathlib, sysconfig, socket, json, os
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root/'src'), str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
r = json.loads(sys.argv[1])
'''+source+'''
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
def forbidden(*a, **kw):
    raise AssertionError('external action forbidden')
socket.socket = __import__('subprocess').Popen = forbidden
compact = lambda value, tmp: value
result = main(pathlib.Path.cwd(), r['mode'], r['json'])
print(json.dumps(result))
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
mix = '\ud800 literal \\ud800 é\x1c\r\n'
evidence = {'reason': mix, mix: ['\udcff', '\U00010000'], 'n': 10**80,
            'overflow': float('inf'), 'nan': float('nan')}
records = []
for mode in ('activation', 'receipt', 'commit'):
    for as_json in (False, True):
        for status in ('failed', 'ready'):
            case = dict(mode=mode, json=as_json, status=status, evidence=
                        evidence | ({'status': 'ready'} if status == 'ready' and
                                    mode == 'activation' else {}))
            work = root / f'main-{len(records)}'
            work.mkdir(exist_ok=True)
            out = subprocess.run([scope['sys'].executable, '-I', str(wrapper), json.dumps(case)],
                                 cwd=work, env={'HOME': str(work), 'PATH': '/usr/bin:/bin'},
                                 capture_output=True, check=True)
            assert not out.stderr, out.stderr
            result = json.loads(out.stdout.replace(str(work).encode(), b'{ROOT}'))
            receipt = result['files'].get('.mir/bootstrap-receipt.json')
            assert (receipt is None) == (mode == 'receipt')
            assert result['exit'] == (0 if status == 'ready' and mode == 'activation' else 1)
            records.append(case | dict(result=result, receipt=receipt))
a.output.write_text(json.dumps(records, sort_keys=True) + '\n')
