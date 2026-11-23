"""Freeze Y-E13 public routes from the pinned, isolated Python console."""
import argparse
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

assert sys.flags.isolated
p = argparse.ArgumentParser()
p.add_argument('--scratch', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
root = a.scratch.resolve() / 'oracle'
root.mkdir(parents=True, exist_ok=True)
# Keep Windows' loader locations while isolating HOME and all writable state.
host_env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR') if k in os.environ}
env = dict(host_env, HOME=str(root), USERPROFILE=str(root), PATH=os.defpath,
           GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
git = shutil.which('git')
assert git, 'git must be available on PATH'
pin = '5f8f69f94e09b64c5e4d07d329ed17797c35e6cb'
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(
        [git, '-C', str(Path(__file__).resolve().parents[4]),
         'archive', pin, 'src/mir', 'config/project-hooks-provider.json',
         'config/adopter-boundary.schema.json', 'config/adopter-payload.schema.json'],
        env=env))) as tar:
    tar.extractall(root, filter='data')
packages = ('pydantic pydantic_core typing_extensions typing_inspection annotated_types '
            'yaml sqlite_vec jsonschema attrs attr referencing rpds jsonschema_specifications '
            'httpx httpcore h11 anyio idna certifi').split()
for name in packages:
    path = Path(importlib.import_module(name).__file__)
    if path.name == '__init__.py':
        shutil.copytree(path.parent, root / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    else:
        shutil.copy2(path, root / path.name)
resources = root / 'src/mir/resources'
resources.mkdir(exist_ok=True)
shutil.copy2(root / 'config/project-hooks-provider.json', resources)
wrapper = root / 'capture.py'
wrapper.write_text("""import sys, pathlib, sysconfig, json, hashlib
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib,
               str(pathlib.Path(stdlib) / 'lib-dynload'),
               str(pathlib.Path(sys.base_prefix) / 'DLLs')]
from mir.cli.__main__ import main
from mir.cli import relations, project_hooks
from mir.core.engine.memory import store
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
if sys.argv[1] in ('local', 'probe', 'receipt'):
    artifact = pathlib.Path('artifact').resolve()
    data = b"#!/bin/sh\\nprintf 'mir-project-hooks-v1\\\\nmir-project-hooks-compact-v1\\\\n'\\n"
    if sys.argv[1] == 'probe':
        data = b"#!/bin/sh\\nexit 1\\n"
    artifact.write_bytes(data)
    metadata = dict(schema_version=1, provider_revision='a'*40,
        plugins={'mir-lifecycle-hooks': {}}, native_artifacts={'project-hooks': dict(
        plugin='mir-lifecycle-hooks', install_path='bin/project-hooks', targets={
        project_hooks.native.host_target(): dict(url=artifact.as_uri(), size=len(data),
        sha256=hashlib.sha256(data).hexdigest())})})
    (root / 'src/mir/resources/project-hooks-provider.json').write_text(json.dumps(metadata))
else:
    (root / 'src/mir/resources/project-hooks-provider.json').write_bytes(
        (root / 'config/project-hooks-provider.json').read_bytes())
if sys.argv[1] == 'valid':
    c = store.connect(pathlib.Path('.mir/memory.db'))
    store.apply_migrations(c.conn)
    c.conn.close()
try:
    code = main(sys.argv[2:])
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    code = 1
raise SystemExit(code)
""".replace('PACKAGE_SET', repr(set(['mir', *packages]))))
cases = [('empty', ['relations', *v]) for v in [
    [], ['--help'], ['query', '--help'], ['bundle', '--help'], ['bad'],
    ['query', 'x'], ['query', 'x', '--purpose', 'bad'],
    ['query', 'x', '--purpose', 'impact'],
    ['query', 'x', '--purpose', 'impact', '--memory'],
    ['bundle', 'x', '--purpose', 'impact', '--purpose', 'verification', '--memory', '--json'],
    ['bundle', 'x', 'y', '--purpose', 'impact', '--memory'],
    ['query', 'x', '--purpose', 'impact', '--graph', 'missing', '--memory'],
    ['query', 'x', '--purpose', 'impact', '--max-edges', '0'],
]]
for action in ['query', 'bundle']:
    for mode in ['valid', 'bad']:
        cases.append((mode, ['relations', action, 'x', '--purpose', 'impact',
                             *(['--purpose', 'verification'] if action == 'bundle' else []),
                             '--memory', '--json']))
cases += [('empty', ['project-hooks', *v]) for v in [
    [], ['--help'], ['bad'], ['check'], ['check', '--project-root', 'missing'],
    ['install', '--project-root', '.'], ['check', '--project-root', '.']]]
cases += [(mode, ['project-hooks', action, '--project-root', '.']) for mode, action in
          [('local', 'install'), ('probe', 'install'), ('receipt', 'check')]]
cases += [('graph', ['relations', action, 'x', '--purpose', 'implementation', '--json'])
          for action in ['query', 'bundle']]
cases.append(('valid', ['relations', 'query', 'x', '--purpose', 'impact',
                         '--root', '{ROOT}', '--memory', '--json']))
# Exercise every option with argparse's inline and prefix spellings.
for action in ['query', 'bundle']:
    base = ['relations', action, 'x', '--purpose', 'impact']
    for option, prefix, value in [('--purpose', '--p', 'impact'),
                                ('--root', '--r', '.'), ('--graph', '--g', 'spec/graph.yaml'),
                                ('--depth', '--d', '1'), ('--max-edges', '--max-e', '2'),
                                ('--max-bytes', '--max-b', '6000')]:
        cases += [('graph', [*base, option + '=' + value]),
                  ('graph', [*base, prefix, value]),
                  ('graph', [*base, prefix + '=' + value])]
    for option, prefix in [('--help', '--he'), ('--memory', '--me'), ('--json', '--j')]:
        cases += [('empty', [*base, prefix]), ('empty', [*base, option + '=yes']),
                  ('empty', [*base, prefix + '=yes'])]
    for tail in [['--m'], ['--max=1'], ['--m=1'], ['--depth'],
                 ['--depth', '--json'], ['--depth=-1']]:
        cases.append(('graph', [*base, *tail]))
for action in ['install', 'check']:
    for tail in [['--project-root=.'], ['--project-r', '.'], ['--p=.'],
                 ['--he'], ['--help=yes'], ['--he=yes'], ['--project-r'],
                 ['--project-r', '--unknown'], ['--project-r='],
                 ['--project-r', '-1'], ['--project-root', '.', '--unknown'],
                 ['--unknown'], ['--', '--project-root', '.']]:
        cases.append(('empty', ['project-hooks', action, *tail]))
cases += [('empty', ['relations', '--he']), ('empty', ['relations', '--help=yes'])]
records = []
for mode, argv in cases:
    # These routes execute Unix shell artifacts and are excluded by the Rust test too.
    if os.name == 'nt' and mode in ('local', 'probe', 'receipt'):
        continue
    work = root / ('case-' + str(len(records)))
    work.mkdir(exist_ok=True)
    (work / 'spec').mkdir(exist_ok=True)
    (work / 'spec/graph.yaml').write_text('edges: [[x, implemented_in, src/a.rs]]\n')
    if mode == 'bad':
        (work / '.mir').mkdir(exist_ok=True)
        (work / '.mir/memory.db').write_bytes(b'not a database')
    result = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(wrapper), mode,
                             *[v.replace('{ROOT}', str(work)) for v in argv]],
                            cwd=work, env=dict(host_env, HOME=str(work), USERPROFILE=str(work),
                                               PATH=os.defpath, TMP=str(work), TEMP=str(work)),
                            capture_output=True, timeout=20)
    records.append(dict(mode=mode, argv=argv, exit=result.returncode,
                        stdout=result.stdout.decode().replace(str(work), '{ROOT}'),
                        stderr=result.stderr.decode().replace(str(work), '{ROOT}')))
assert len(records) == (121 if os.name == 'nt' else 124)
by_case = {(r['mode'], tuple(r['argv'])): r for r in records}
install = by_case['empty', ('project-hooks', 'install', '--project-root', '.')]
assert install['exit'] == 1 and 'no published host pin' in install['stdout']
check = by_case['empty', ('project-hooks', 'check', '--project-root', '.')]
assert check['exit'] == 1 and 'no published host pin' in check['stdout']
if os.name != 'nt':
    assert by_case['local', ('project-hooks', 'install', '--project-root', '.')]['exit'] == 0
assert records[8]['exit'] == 2 and 'unavailable' in records[8]['stderr']
if os.name == 'nt':
    # Decode raw UTF-8 bytes above, never universal-newline translate console output.
    for record in records:
        for field in ('stdout', 'stderr'):
            assert '\n' not in record[field].replace('\r\n', ''), record
a.output.write_bytes((json.dumps(records, separators=(',', ':')) + '\n').encode('utf-8'))
