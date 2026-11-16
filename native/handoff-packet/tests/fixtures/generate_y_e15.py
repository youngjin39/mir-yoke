"""Freeze Y-E15 from the isolated 5f8f69f console; no network or real DB."""
import json
import os
import shutil
import subprocess
from pathlib import Path

# The shared prefix archives every package __init__ and copies installed dependencies.
scope = {"__file__": __file__}
prefix = Path(__file__).with_name("generate_y_e13.py").read_text().split("resources =")[0]
prefix = prefix.replace("'/usr/bin/git'", "shutil.which('git')")
prefix = prefix.replace("'/dev/null'", "os.devnull")
prefix = prefix.replace("env={'HOME':", "env={**{k: os.environ[k] for k in "
                        "('SystemRoot', 'WINDIR') if k in os.environ}, 'HOME':")
exec(prefix, scope)
if os.name == 'nt':
    assert scope['sys'].version_info[:2] == (3, 12), 'PC oracle requires Python 3.12'
    assert 'windows' in scope['a'].output.name, 'do not overwrite the Mac record'

a, root, packages = (scope[k] for k in ("a", "root", "packages"))
wrapper = root / "capture.py"
wrapper.write_text('''import sys, pathlib, sysconfig, socket, json, subprocess, os
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib,
               str(pathlib.Path(stdlib) / 'lib-dynload'),
               str(pathlib.Path(sys.base_prefix) / 'DLLs')]
from mir.cli import bootstrap
from mir.core.adoption import slim
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
def forbidden(*args, **kwargs):
    raise AssertionError('network forbidden')
socket.socket = forbidden
assert set(os.environ) <= {'HOME', 'PATH', 'PYTHONPATH', 'VIRTUAL_ENV',
                           'UV_PROJECT_ENVIRONMENT', 'GIT_CONFIG_NOSYSTEM',
                           'GIT_CONFIG_GLOBAL', 'USERPROFILE', 'SystemRoot', 'SYSTEMROOT',
                           'WINDIR', 'LC_CTYPE', '__CF_USER_TEXT_ENCODING'}
try:
    if sys.argv[1] == 'clean':
        result = slim._default_verify(pathlib.Path('./fake').resolve(), pathlib.Path.cwd())
        print(json.dumps(result))
        code = 0
    elif sys.argv[1] == 'inaccessible':
        denied = pathlib.Path.cwd() / 'denied'
        denied.mkdir()
        try:
            denied.chmod(0)
            slim._default_verify(pathlib.Path('./fake').resolve(), denied)
        finally:
            denied.chmod(0o700)
        code = 0
    elif sys.argv[1] == 'alive':
        child = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(30)'])
        try:
            live = slim._process_alive(child.pid)
        finally:
            child.terminate()
            child.wait()
        print(json.dumps([live, slim._process_alive(child.pid)]))
        code = 0
    else:
        code = bootstrap.main(sys.argv[3:])
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    code = 1
raise SystemExit(code)
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
records = []
cases = [('public', v) for v in [ ['--help'], ['--profile', 'code_app'],
    ['--project-root', 'absent', '--profile', 'code_app'],
    ['--profile', 'bad'], ['--profile', 'code_app', '--slug', '!'] ]]
if os.name != 'nt':
    cases += [('clean', []), ('alive', []), ('inaccessible', [])]
for mode, tail in cases:
    work = root / ('case-' + str(len(records)))
    if work.exists():
        shutil.rmtree(work)
    (work / '.mir').mkdir(parents=True, exist_ok=True)
    files = {'.mir/repo-profile.toml': '[repo]\nslug="sample"\n',
             'config/capability-sources.json': '{"source":{"url":"https://example.invalid/provider"}}'}
    if tail == ["--profile", "code_app"]:
        del files["config/capability-sources.json"]
    for name, body in files.items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    fake = work / 'fake'
    fake.write_text('''#!/bin/sh
[ -z "$PYTHONPATH$VIRTUAL_ENV$UV_PROJECT_ENVIRONMENT" ] || exit 9
[ "$HOME" = "$PWD" ] || exit 8
printf '%s' '{"ready":true,"changed_paths":[]}'
''')
    fake.chmod(0o755)
    env = dict(HOME=str(work), PATH='/usr/bin:/bin',
               PYTHONPATH='poison', VIRTUAL_ENV='poison', UV_PROJECT_ENVIRONMENT='poison',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    env.update({k: os.environ[k] for k in ('SystemRoot', 'WINDIR') if k in os.environ})
    env['USERPROFILE'] = str(work)
    out = subprocess.run([str(scope['sys'].executable), '-I', str(wrapper), mode,
                          'bootstrap', *tail], cwd=work, env=env, capture_output=True, check=False)
    assert not (work / '.mir/memory.db').exists()
    assert not (work / '.mir/bootstrap-receipt.json').exists()
    records.append(dict(mode=mode, argv=tail, files=files, exit=out.returncode,
                        stdout=out.stdout.decode().replace(str(work), '{ROOT}'),
                        stderr=out.stderr.decode().replace(str(work), '{ROOT}')))
assert records[0]['exit'] == 0 and 'usage: mir bootstrap' in records[0]['stdout']
if os.name == 'nt':
    assert len(records) == 5 and '\r\n' in records[0]['stdout']
    assert all(r['exit'] == 2 and not r['stdout'] and 'Windows' in r['stderr']
               and r['stderr'].endswith('\r\n') for r in records[1:])
else:
    assert json.loads(records[6]['stdout']) == [True, False]
    assert json.loads(records[5]['stdout']) == [True, 'ready']
    assert records[7]['exit'] == 1 and records[7]['stderr'].startswith('PermissionError: ')
a.output.write_text(json.dumps(records, indent=2) + '\n')
