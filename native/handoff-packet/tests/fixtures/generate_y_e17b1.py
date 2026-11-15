import json
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e13.py").read_text().split("resources =")[0], scope)
a, root, packages = (scope[k] for k in ("a", "root", "packages"))
wrapper = root / "capture.py"
wrapper.write_text('''import sys, sysconfig, pathlib, json, os, socket, subprocess
root, stdlib = pathlib.Path(__file__).resolve().parent, sysconfig.get_path('stdlib')
sys.path[:] = [str(root/'src'), str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
from mir.core.capabilities.manager import CapabilityManager
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        assert pathlib.Path(module.__file__).resolve().is_relative_to(root), name
def forbidden(*args, **kwargs):
    raise AssertionError('external action forbidden')
socket.socket = subprocess.Popen = forbidden
work, r = pathlib.Path.cwd(), json.loads(sys.argv[1])
case, call = r['case'], r['call']
try:
    m = CapabilityManager(work/'project', config_path=work/'config.json',
                          capability_home=work/'cap')
    if case == 'identity':
        (work/'project').rename(work/'old')
        (work/'project').symlink_to(work/'outside', target_is_directory=True)
    value = getattr(m, call['method'])(*call['args'], **call['kwargs'])
    result = dict(value=value, error=None, events=[])
except BaseException as exc:
    result = dict(value=None, error={'class': type(exc).__name__, 'message': str(exc)}, events=[])
print(json.dumps(result))
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
records = []
config = subprocess.check_output(
    ['/usr/bin/git', 'show', scope['pin'] + ':config/capability-sources.json']).decode()
for case in ('status check sync update finalize attest constructor uncaught identity').split():
    work = root / case
    for name in ['project', 'outside']:
        (work / name).mkdir(parents=True, exist_ok=True)
    (work / 'config.json').write_text('{}' if case == 'constructor' else config)
    method = 'finalize' if case == 'identity' else 'status' if case == 'uncaught' else case
    args = ['bad-profile'] if method not in ('finalize', 'constructor') else []
    call = dict(op='call', method=method, args=['bad-runtime', []] if method == 'attest' else args,
                kwargs={'apply': True} if case == 'identity' else
                {'unexpected': True} if case == 'uncaught' else {})
    argv = [scope['sys'].executable, '-I', str(wrapper), json.dumps(dict(case=case, call=call))]
    result = subprocess.run(argv, cwd=work, env={'HOME': str(work), 'PATH': '/usr/bin:/bin'},
                            capture_output=True, check=True)
    assert not result.stderr, result.stderr
    reply = json.loads(result.stdout.replace(str(work).encode(), b'{ROOT}'))
    assert reply['error'], (case, reply)
    records.append(dict(case=case, call=call, reply=reply))
assert records[-1]['reply']['error']['message'] == 'project root identity changed'
a.output.write_text(json.dumps(dict(config=config, records=records), sort_keys=True) + '\n')
