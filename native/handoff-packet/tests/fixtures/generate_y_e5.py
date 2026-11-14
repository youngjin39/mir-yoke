"""Freeze Y-E5 from the pinned console; run with python -I."""
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
PIN = "5f8f69f94e09b64c5e4d07d329ed17797c35e6cb"
p = argparse.ArgumentParser()
p.add_argument('--scratch', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
repo = Path(__file__).resolve().parents[4]
root = a.scratch.resolve() / 'oracle'
root.mkdir(parents=True, exist_ok=True)
archive = subprocess.check_output(['git', 'archive', PIN, 'src/mir'], cwd=repo)
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    tar.extractall(root, filter='data')
packages = (
    'pydantic pydantic_core typing_extensions typing_inspection annotated_types '
    'yaml sqlite_vec jsonschema attrs attr referencing rpds jsonschema_specifications'
).split()
for name in packages:
    module = importlib.import_module(name)
    path = Path(module.__file__)
    if path.name == '__init__.py':
        shutil.copytree(path.parent, root / name, dirs_exist_ok=True)
    else:
        shutil.copy2(path, root / path.name)
wrapper = root / 'console.py'
wrapper.write_text('''import sys, pathlib, sysconfig
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload')]
from mir.cli.__main__ import main
from mir.cli import context
from mir.core.engine.memory import store
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
if sys.argv[1] == 'seed':
    c = store.connect(pathlib.Path(sys.argv[2]))
    store.apply_migrations(c.conn)
    c.conn.close()
    raise SystemExit(0)
try:
    raise SystemExit(main())
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    raise SystemExit(1)
'''.replace('SET', repr(set(['mir', *packages]))))
archive_cfg = '\n[[memory.external_archives]]\nslug="notes"\nroot="notes"\n'
cases = [(['sync'], ''), (['--help'], ''), (['sync', '--help'], ''),
         (['sync', '--bad'], ''), (['sync', '--db'], ''),
         (['sync', '--project'], ''), (['sync', '--reindex=oops'], ''),
         (['sync', '--db', '-inf'], ''), (['sync', '--db', '-1', '--help'], ''),
         (['sync', '--db', '-inf x', '--help'], ''),
         (['sync', '--db=memory.db', '--project-root=.'], ''),
         (['sync', '--reindex-missing-vectors'], ''),
         (['sync'], 'bad = [\n'), (['sync'], '[memory]\nwrong=true\n'),
         (['sync'], archive_cfg), (['sync', '--reindex'], archive_cfg),
         (['sync', '--pro', '.'], archive_cfg), (['sync', '--', 'tail'], ''),
         (['bogus'], ''), (['-h=oops'], ''), (['sync', '-hgarbage'], ''),
         (['sync'], ''), (['sync'], ''), (['sync'], ''),
         (['sync', '--project-root', '~'], archive_cfg)]
records = []
for i, (args, config) in enumerate(cases):
    work = root / f'case-{i}'
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    (work / 'notes').mkdir()
    (work / 'notes/a.md').write_text('Synthetic archive document.\n')
    (work / 'harness_a.toml').write_text(config)
    env = {'HOME': str(work), 'PATH': os.defpath, 'PYTHONIOENCODING': 'utf-8'}
    def run(args, work=work, env=env):
        return subprocess.run([sys.executable, '-I', str(wrapper), *args], cwd=work,
                              env=env, capture_output=True)
    seed = i not in {4, 5, 7, 21, 22, 23}  # all DB operations remain synthetic
    if seed:
        result = run(['seed', 'memory.db'])
        assert result.returncode == 0, result.stderr
    if i == 22:
        (work / 'memory.db').write_text('not a database')
    if i == 23:
        (work / 'memory.db').touch()
    argv = ['context', *args, '--db', 'memory.db']
    result = run(argv)
    assert result.returncode in {0, 1, 2}, result.stderr
    records.append(dict(argv=argv, config=config, seed=seed, exit=result.returncode,
                        stdout=result.stdout.decode().replace(str(work), '@ROOT@'),
                        stderr=result.stderr.decode().replace(str(work), '@ROOT@')))
assert records[10]['stdout'] == 'no archives configured\n', records[10]
a.output.write_text(json.dumps(records, separators=(',', ':')) + '\n')
