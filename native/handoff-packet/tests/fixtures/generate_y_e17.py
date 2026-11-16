"""Y-E17A acquisition: pinned local boundaries; no real provider or database."""
import json
import os
import shutil
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e13.py").read_text(encoding="utf-8")
     .split("resources =")[0], scope)
a, root, packages = (scope[k] for k in ("a", "root", "packages"))
if os.name == 'nt':
    assert scope['sys'].version_info[:2] == (3, 12), 'PC oracle requires Python 3.12'
    assert a.output.name == 'y-e17-windows.json', 'do not overwrite the Mac record'
env = scope['env'] | {'PYTHONIOENCODING': 'utf-8'}


def observe_project_roots(result, work):
    # Decode JSON first. Record exactly str(root), never wire()/as_posix().
    for argv in result['calls']:
        index = argv.index('--project-root') + 1
        assert argv[index] == str(work), ('--project-root spelling', argv[index], str(work))
        argv[index] = '{ROOT}'
    return result

def run_oracle(argv, **kwargs):
    result = subprocess.run(argv, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(
            f"oracle child argv={argv!r} exit={result.returncode}\n"
            f"stdout={result.stdout.decode('utf-8', errors='backslashreplace')}\n"
            f"stderr={result.stderr.decode('utf-8', errors='backslashreplace')}")
    return result


wrapper = root / "capture.py"
wrapper.write_text('''import sys, pathlib, sysconfig, socket, json, io, contextlib, types, os
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload'),
               str(pathlib.Path(sys.base_prefix) / 'DLLs')]
from mir.cli import bootstrap, capability
from mir.core.capabilities import manager as impl
from mir.core.capabilities.config import load_capability_config
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
assert set(os.environ) <= {'HOME', 'USERPROFILE', 'PATH', 'SystemRoot', 'WINDIR',
                           'GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_GLOBAL',
                           'PYTHONIOENCODING', 'LC_CTYPE', '__CF_USER_TEXT_ENCODING'}
def forbidden(*args, **kwargs):
    raise AssertionError('external action forbidden')
socket.socket = forbidden
subprocess = __import__('subprocess')
subprocess.Popen = forbidden
work = pathlib.Path.cwd()
r = json.loads(sys.argv[1])
out, err = io.StringIO(), io.StringIO()
calls = []
def fake_cli(argv):
    calls.append(argv)
    print(r.get('out', ''), end='')
    print(r.get('err', ''), end='', file=sys.stderr)
    return r.get('code', 0)
class Provider:
    def __init__(self, project_root, **kwargs):
        assert project_root == work
    def status(self, profile):
        return {'ready': True}
    def sync(self, profile, **kwargs):
        assert profile == 'code_app' and kwargs == {'apply': True}
        if r['case'] == 'console-error':
            raise impl.CapabilityError('provider refused')
        if r['case'] == 'console-change':
            (work / '.mir/capability-lock.json').write_text('{}')
        return {'ready': True}
try:
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        mode = r['mode']
        if mode == 'console':
            capability.CapabilityManager = Provider
            value = capability.main(r['argv'])
        elif mode == 'config':
            value = load_capability_config(work / 'config/capability-sources.json').plugins
            value = sorted(value)
        elif mode == 'provider-finalize':
            m = object.__new__(impl.CapabilityManager)
            m._assert_capability_home_safe = lambda **kw: None
            m._assert_project_lock_path_safe = lambda: None
            m._load_lock = lambda: None if r['case'] == 'missing' else r['lock']
            m._active_integrity = lambda *args: r['case'] != 'integrity'
            m._activation_evidence = lambda *args, **kw: {
                'status': 'missing' if r['case'] == 'activation' else 'verified'}
            m._discovery_evidence = lambda *args: {
                'status': 'missing' if r['case'] == 'discovery' else 'verified'}
            value = m._finalize(apply=r['case'] != 'read-only',
                                after_restart=r['case'] != 'restart')
        elif mode == 'discovery':
            m = object.__new__(impl.CapabilityManager)
            m.project_root = work
            m.active_receipt_path = work / 'receipt.json'
            m.config = types.SimpleNamespace(required_runtimes=('claude-code',),
                plugin_skills={'mir-core': ('design',)}, plugin_hooks={}, plugin_mcp={})
            m._assert_capability_home_safe = lambda **kw: None
            value = m._discovery_evidence(r['lock'], consumer_key='consumer')
        else:
            capability.main = fake_cli
            if mode == 'activate':
                value = bootstrap._activate_capabilities(work, 'code_app')
            elif mode == 'finalize':
                value = bootstrap._finalize_capabilities(work, r.get('prior'))
            else:
                value = bootstrap._capability_lock_evidence(work)
    result = {'value': value}
except Exception as exc:
    result = {'class': type(exc).__name__, 'message': str(exc)}
print(json.dumps(dict(result=result, stdout=out.getvalue(), stderr=err.getvalue(), calls=calls)))
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
# Inputs are frozen with results; assertions below guard against accidental live imports.
lock = dict(schema_version=1, source={'commit': 'a' * 40}, profile='code_app',
            plugins={'mir-core': {}}, agents={}, registration={'status': 'active'})
config = subprocess.check_output(
    [scope['git'], '-C', str(Path(__file__).resolve().parents[4]),
     'show', scope['pin'] + ':config/capability-sources.json'], env=env)
records = []
cases = [
    dict(mode='activate', case='streams', code=7, out=' out\n', err='err\n'),
    dict(mode='activate', case='empty', code=7),
    dict(mode='activate', case='missing'),
    dict(mode='activate', case='ready', lock=lock),
    dict(mode='finalize', case='prior'),
    dict(mode='finalize', case='streams', prior={'status': 'restart_required'},
         code=7, out=' out\n', err='err\n'),
    dict(mode='finalize', case='empty', prior={'status': 'restart_required'}, code=7),
    dict(mode='finalize', case='inactive', prior={'status': 'restart_required'},
         lock=lock | {'registration': {'status': 'installed'}}),
    dict(mode='finalize', case='ready', prior={'status': 'restart_required'}, lock=lock),
]
for name, value in [('not-object', []), ('bad-source', lock | {'source': {}}),
                    ('native-bad', lock | {'native_artifacts': []}),
                    ('native-empty', lock | {'native_artifacts': {}})]:
    cases.append(dict(mode='lock', case=name, lock=value))
cases += [dict(mode='config', case='projection', config=config.decode()),
          dict(mode='config', case='invalid', config='{}'),
          dict(mode='lock', case='config-invalid', config='{}',
               lock=lock | {'native_artifacts': {}})]
for case in ['console-read', 'console-nochange', 'console-change', 'console-error']:
    cases.append(dict(mode='console', case=case,
                      argv=['status' if case == 'console-read' else 'sync',
                            '--profile', 'code_app', '--project-root', '.', '--json',
                            *([] if case == 'console-read' else ['--apply'])]))
for case in ['missing', 'mismatch', 'invalid', 'stale', 'skills', 'verified']:
    receipt = dict(commit='a' * 40, plugins={'mir-core': None}, session_id='new',
                   observed_skills=['mir-core:design'], observed_hooks=[])
    receipt.update({'commit': 'b' * 40} if case == 'mismatch' else
                   {'session_id': '!'} if case == 'invalid' else
                   {'session_id': 'old'} if case == 'stale' else
                   {'observed_skills': []} if case == 'skills' else {})
    cases.append(dict(mode='discovery', case=case, lock=lock,
                      receipt=dict(installation_sessions={'consumer': {'claude-code': 'old'}},
                                   discovery={'consumer': {} if case == 'missing' else
                                              {'claude-code': receipt}})))
for case in ['missing', 'integrity', 'read-only', 'restart', 'activation', 'discovery',
             'registration']:
    cases.append(dict(mode='provider-finalize', case=case,
                      lock=lock | {'registration': None} if case == 'registration' else lock))
for i, r in enumerate(cases):
    work = root / f'case-{i}'
    if work.exists():
        shutil.rmtree(work)
    (work / '.mir').mkdir(parents=True, exist_ok=True)
    files = {}
    for key, path in [('lock', '.mir/capability-lock.json'), ('receipt', 'receipt.json'),
                      ('config', 'config/capability-sources.json')]:
        if key in r:
            files[path] = r[key] if key == 'config' else json.dumps(r[key])
    for name, body in files.items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')
    out = run_oracle([scope['sys'].executable, '-I', '-B', '-X', 'utf8', str(wrapper),
                          json.dumps(r)],
                         cwd=work, env=env | {'HOME': str(work), 'USERPROFILE': str(work)})
    assert not out.stderr, out.stderr
    result = json.loads(out.stdout)
    if os.name == 'nt':
        # Retain raw Windows argv and its input spelling; only the replay observes tokens.
        result.update(project_root=str(work), reference_pin=scope['pin'], platform='win32')
        observe_project_roots(json.loads(out.stdout), work)  # assert exact forwarding
    else:
        result = observe_project_roots(result, work)
    records.append(r | dict(files=files, **result))
assert records[0]['result']['value'] == ['failed', {'reason': 'out\nerr'}]
assert records[2]['result']['value'][0] == 'failed'
assert records[3]['result']['value'][0] == 'ready'
assert records[25]['result']['value']['status'] == 'verified'
assert records[23]['result']['value']['runtimes']['claude-code']['status'] == 'session-stale'
assert records[-1]['result']['class'] == 'CapabilityError'
a.output.write_text('[\n' + ',\n'.join(json.dumps(r, sort_keys=True) for r in records) + '\n]\n',
                    encoding='utf-8')
