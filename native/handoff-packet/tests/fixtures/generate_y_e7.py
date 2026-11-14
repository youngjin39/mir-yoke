"""Freeze vector retrieval at 5f8f69f; isolated acquisition, synthetic inputs only."""
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
archive = subprocess.check_output(['git', 'archive', pin, 'src/mir'])
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    tar.extractall(root, filter='data')
packages = ('pydantic pydantic_core typing_extensions typing_inspection annotated_types '
            'yaml sqlite_vec jsonschema attrs attr referencing rpds '
            'jsonschema_specifications').split()
for name in packages:
    path = Path(importlib.import_module(name).__file__)
    if path.name == '__init__.py':
        shutil.copytree(path.parent, root / name, dirs_exist_ok=True)
    else:
        shutil.copy2(path, root / path.name)
wrapper = root / 'capture.py'
wrapper.write_text('''import sys, pathlib, sysconfig, json
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload')]
from mir.core.engine.memory import store
from mir.core.engine.memory.external_store import ExternalStore
import sqlite_vec
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
work = pathlib.Path.cwd()
c = store.connect(work / 'memory.db')
store.apply_migrations(c.conn)
if sys.argv[1] == 'unavailable':
    c = store.Connection(c.conn, False, None)
es = ExternalStore(c)
archive = es.register(slug='notes', root_path=str(work / 'notes'),
                      mode='indexed', owner='synthetic')
es.scan(archive)
mode = sys.argv[1]
for i in range(len(list((work / 'notes').glob('*.md')))):
    v = [0.0] * 1024
    v[0 if mode in {'ties', 'recent', 'expansion'} else (2-i) % 1024] = 1.0
    if mode not in {'no-vectors', 'unavailable', 'no-scores'}:
        c.conn.execute('INSERT INTO external_chunks_vec(rowid,embedding) VALUES (?,?)',
                       (i+1, sqlite_vec.serialize_float32(v)))
c.conn.execute('INSERT OR REPLACE INTO external_store_meta(key,value) VALUES (?,?)',
               ('external_embedding_fingerprint',
                'wrong' if mode == 'mismatch' else 'synthetic-v1'))
c.conn.commit()
if mode == 'vec-error':
    c.conn.execute('DROP TABLE external_chunks_vec')
if mode == 'fts-error':
    c.conn.execute('DROP TABLE external_chunks_fts')
if mode == 'expansion':
    c.conn.execute("UPDATE external_documents SET status='archived' WHERE relative_path!='7.md'")
if mode == 'recent':
    c.conn.execute('UPDATE external_documents SET frontmatter_json=? WHERE relative_path=?',
                   ('{"created":"2026-11-15"}', '2.md'))
if mode in {'filtered', 'history'}:
    c.conn.execute("UPDATE external_documents SET status='archived' WHERE relative_path='2.md'")
scopes = ('1.md',) if mode == 'scoped' else ('absent',) if mode == 'empty' else ()
def embed(texts):
    assert texts == ['absentword' if mode == 'no-scores' else 'apple']
    if mode == 'failed':
        raise ValueError('synthetic provider failure')
    if mode == 'bad-dim':
        return [[1.0]]
    if mode == 'empty-embedding':
        return []
    if mode == 'multiple':
        return [[], []]
    return [[1.0] + [0.0] * 1023]
try:
    hits = es.search('absentword' if mode == 'no-scores' else 'apple',
                     k=int(sys.argv[2]), embed_fn=None if mode == 'disabled' else embed,
                     encoder_fingerprint='synthetic-v1', path_scopes=scopes,
                     include_history=mode in {'history', 'empty-index'})
    print(json.dumps([dict(path=h.relative_path, score=h.score) for h in hits]))
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    raise SystemExit(1)
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
records = []
for mode in ['hybrid', 'ties', 'limit', 'zero', 'disabled', 'failed', 'mismatch', 'no-vectors',
             'recent', 'filtered', 'history', 'scoped', 'empty', 'bad-dim', 'empty-embedding',
             'unavailable', 'vec-error', 'fts-error', 'expansion', 'no-scores', 'multiple',
             'empty-index']:
    work = root / mode
    work.mkdir(exist_ok=True)
    (work / 'notes').mkdir(exist_ok=True)
    docs = ['alpha apple orchard.\n', 'beta ocean harbor.\n', 'gamma desert dunes.\n']
    if mode == 'empty-index':
        docs = []
    if mode == 'expansion':
        docs += [f'Extra synthetic document {i}.\n' for i in range(3, 8)]
    for i, text in enumerate(docs):
        (work / f'notes/{i}.md').write_text(text)
    for suffix in ['', '-wal', '-shm']:
        (work / ('memory.db' + suffix)).unlink(missing_ok=True)
    k = 1 if mode in {'limit', 'expansion'} else 0 if mode == 'zero' else 3
    result = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(wrapper), mode, str(k)],
                            cwd=work, env=dict(HOME=str(work), PATH=os.defpath),
                            capture_output=True)
    records.append(dict(mode=mode, docs=docs, k=k, exit=result.returncode,
                        stdout=result.stdout.decode(), stderr=result.stderr.decode()))
assert len(json.loads(records[0]['stdout'])) == 3, records
assert records[5]['stderr'] == 'ValueError: synthetic provider failure\n'
a.output.write_text(json.dumps(records, separators=(',', ':')) + '\n')
