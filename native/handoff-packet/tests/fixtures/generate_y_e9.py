"""Freeze the pinned pull console in an isolated synthetic repository."""
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
pin = '5f8f69f94e09b64c5e4d07d329ed17797c35e6cb'
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(
        ['git', 'archive', pin, 'src/mir']))) as tar:
    tar.extractall(root, filter='data')
packages = ('pydantic pydantic_core typing_extensions typing_inspection annotated_types '
            'yaml sqlite_vec jsonschema attrs attr referencing rpds '
            'jsonschema_specifications httpx httpcore h11 anyio idna certifi').split()
for name in packages:
    path = Path(importlib.import_module(name).__file__)
    if path.name == '__init__.py':
        shutil.copytree(path.parent, root / name, dirs_exist_ok=True)
    else:
        shutil.copy2(path, root / path.name)
wrapper = root / 'capture.py'
wrapper.write_text("""import sys, pathlib, sysconfig, os
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload')]
from mir.cli.__main__ import main
from mir.core.engine.memory import store
from mir.cli import context  # preload lazy modules before the provenance check
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
if 'valid.db' in sys.argv:
    c = store.connect(pathlib.Path('valid.db'))
    store.apply_migrations(c.conn)
    c.conn.close()
if sys.argv[1] == 'removed':
    os.rmdir(os.getcwd())
try:
    code = main(sys.argv[2:])
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    code = 1
raise SystemExit(code)
""".replace('PACKAGE_SET', repr(set(['mir', *packages]))))
cases = [[], ['--help'], ['pull', '--help'], ['pull'], ['pull', '--wat'],
         ['pull', 'q', '--wat'], ['pull', 'q', 'extra'], ['pull', '--k'],
         ['pull', 'q', '--k', 'abc'], ['pull', 'q', '--k', '-inf'],
         ['pull', 'q', '--risk', 'bad'], ['pull', 'q', '--risk', '--help'],
         ['pull', 'q', '--p', 'x'], ['pull', 'q', '--history=yes'],
         ['pull', 'q', '--json=x'], ['pull', '-hgarbage'], ['pull', '-h=bad'],
         ['pull', 'q', '--db', 'missing//./'], ['pull', 'q', '--db='],
         ['pull', 'q', '--d', 'absent', '--proj', 'absent'],
         ['pull', 'q', '--k', '١_٢'], ['pull', 'q', '--k', '  +2 '],
         ['pull', '--', '-query'], ['pull', '--', 'q', '--json'],
         ['pull', 'q', '--k', '2', '--k', '3'], ['pull', 'q', '--his', '--j'],
         ['pull', 'q', '--db', '-inf x'], ['pull', 'q', '--db', '--help'],
         ['sync', '--help'], ['sync', '--db', 'absent//./'],
         ['sync', '--reindex-missing-vectors=x'], ['--wat', 'pull', 'q'],
         ['pull', 'q', '--', 'extra'], ['pull', 'q', '--k', '1.0'],
         ['pull', 'q', '--db', 'bad.db'], ['sync', '--db', 'bad.db'],
         ['pull', 'q', '--db', 'valid.db', '--k', '999999999999999999999'],
         ['pull', 'q', '--db', 'valid.db', '--k', '-999999999999999999999']]
records = []
for removed, argv in [(False, c) for c in cases] + [(True, c) for c in
        [['pull', '--help'], ['sync', '--help'], ['pull', 'q'], ['sync'],
         ['pull', 'q', '--db', 'absent'], ['sync', '--db', 'absent']]]:
    work = root / ('case-' + str(len(records)))
    work.mkdir(exist_ok=True)
    if not removed:
        (work / 'bad.db').write_bytes(b'not a database')
    # Every invocation has synthetic HOME/cwd and --db, including error/help routes.
    args = ['context', *argv]
    if not any(v.split('=')[0] in {'--db', '--d'} for v in argv):
        at = args.index('--') if '--' in args else len(args)
        args[at:at] = ['--db', 'absent']
    result = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(wrapper),
                             'removed' if removed else 'normal', *args], cwd=work,
                            env=dict(HOME=str(work), PATH=os.defpath), capture_output=True)
    records.append(dict(argv=args, removed=removed, exit=result.returncode,
                        stdout=result.stdout.decode(), stderr=result.stderr.decode()))
assert 'usage: mir context pull' in records[2]['stdout'], records[2]
a.output.write_text(json.dumps(records, separators=(',', ':')) + '\n')
