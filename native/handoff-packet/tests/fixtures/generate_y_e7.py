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
p.add_argument('--e12a', action='store_true')
p.add_argument('--output', type=Path, required=True)
p.add_argument('--admission-output', type=Path, required=True)
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
sys.path[:] = [str(root / 'src'), str(root), stdlib,
               str(pathlib.Path(stdlib) / 'lib-dynload'),
               str(pathlib.Path(sys.base_prefix) / 'DLLs')]
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
if mode.startswith('metadata-'):
    kind = mode.removeprefix('metadata-')
    value = (b'{"created":"2026-11-15"}' if kind in {'unrelated', 'archived'}
             else bytes.fromhex(sys.argv[3]) if kind.startswith('blob')
             else int(sys.argv[3]) if kind == 'integer' else sys.argv[3])
    c.conn.execute('UPDATE external_documents SET frontmatter_json=? WHERE relative_path=?',
                   (value, '1.md'))
    if kind == 'archived':
        c.conn.execute("UPDATE external_documents SET status='archived' WHERE relative_path='1.md'")
scopes = ('1.md',) if mode == 'scoped' else ('absent',) if mode == 'empty' else ()
# Trace a separate diagnostic run; frozen results always come from an untraced run.
events = []
def trace(frame, event, arg):
    if frame.f_code.co_name == '_doc_created_ordinal':
        if event == 'exception':
            events.append(dict(exception=arg[0].__name__, message=str(arg[1])))
        elif event == 'return':
            events.append(dict(ordinal=arg))
        return trace
if len(sys.argv) > 4:
    sys.settrace(trace)
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
                     k=int(sys.argv[2]),
                     embed_fn=None if mode == 'disabled' or mode.startswith('metadata-') else embed,
                     encoder_fingerprint='synthetic-v1', path_scopes=scopes,
                     include_history=mode in {'history', 'empty-index'})
    print(json.dumps([dict(path=h.relative_path, score=h.score) for h in hits]))
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    raise SystemExit(1)
finally:
    sys.settrace(None)
    if len(sys.argv) > 4:
        pathlib.Path(sys.argv[4]).write_text(json.dumps(dict(
            python=sys.version, platform=sys.platform, events=events)), encoding='utf-8')
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
records = []
admission = []
modes = ['hybrid', 'ties', 'limit', 'zero', 'disabled', 'failed', 'mismatch', 'no-vectors',
             'recent', 'filtered', 'history', 'scoped', 'empty', 'bad-dim', 'empty-embedding',
             'unavailable', 'vec-error', 'fts-error', 'expansion', 'no-scores', 'multiple',
             'empty-index']
metadata = {}
if a.e12a:
    metadata = {'unrelated': '', 'archived': '', 'integer': '7', 'malformed': '{',
                'surrogate': '{"created":"2026-11-15","x":"\\ud800"}',
                'deep': '{"created":"2026-11-15","x":' + '['*5000 + '0' + ']'*5000 + '}'}
    for enc in ['utf-8-sig', 'utf-16-le', 'utf-16-be', 'utf-32-le', 'utf-32-be']:
        metadata['blob-' + enc] = '{"created":"2026-11-15T12:00:00"}'.encode(enc).hex()
    metadata['blob-invalid'] = 'ff'
    if sys.platform == 'win32':
        # Measure both neighbours of the existing native limit in this exact wrapper.
        for depth in range(2994, 3002):
            metadata[f'deep-{depth}'] = (
                '{"created":"2026-11-15","x":' + '['*depth + '0' + ']'*depth + '}')
    modes = ['metadata-' + kind for kind in metadata]
for mode in modes:
    work = root / mode
    work.mkdir(exist_ok=True)
    (work / 'notes').mkdir(exist_ok=True)
    docs = ['alpha apple orchard.\n', 'beta ocean harbor.\n', 'gamma desert dunes.\n']
    if mode.startswith('metadata-') and mode not in {'metadata-unrelated', 'metadata-archived'}:
        docs = ['apple.\n', 'apple.\n']
    if mode == 'empty-index':
        docs = []
    if mode == 'expansion':
        docs += [f'Extra synthetic document {i}.\n' for i in range(3, 8)]
    for i, text in enumerate(docs):
        (work / f'notes/{i}.md').write_text(text)
    for suffix in ['', '-wal', '-shm']:
        (work / ('memory.db' + suffix)).unlink(missing_ok=True)
    k = 1 if mode in {'limit', 'expansion'} else 0 if mode == 'zero' else 3
    argv = [sys.executable, '-I', '-X', 'utf8', str(wrapper), mode, str(k),
            metadata.get(mode.removeprefix('metadata-'), '')]
    env = dict(HOME=str(work), USERPROFILE=str(work), PATH=os.defpath)
    for key in ('SystemRoot', 'WINDIR'):
        if key in os.environ:
            env[key] = os.environ[key]
    result = subprocess.run(argv, cwd=work, env=env, capture_output=True)
    if mode == 'metadata-deep':
        diagnostic = work / 'admission.json'
        for suffix in ['', '-wal', '-shm']:
            (work / ('memory.db' + suffix)).unlink(missing_ok=True)
        probe = subprocess.run([*argv, str(diagnostic)], cwd=work, env=env, capture_output=True)
        assert (probe.returncode, probe.stdout, probe.stderr) == (
            result.returncode, result.stdout, result.stderr), mode
        admission.append(dict(mode=mode, **json.loads(diagnostic.read_text(encoding='utf-8'))))
    # These helper records compare logical print output, not console-entry CRLF bytes.
    records.append(dict(metadata=metadata.get(mode.removeprefix('metadata-')), mode=mode, docs=docs,
                        k=k, exit=result.returncode,
                        stdout=result.stdout.decode('utf-8').replace('\r\n', '\n'),
                        stderr=result.stderr.decode('utf-8').replace('\r\n', '\n')))
if not a.e12a:
    for r in records:
        r.pop('metadata')
    assert len(json.loads(records[0]['stdout'])) == 3, records
    assert records[5]['stderr'] == 'ValueError: synthetic provider failure\n'
else:
    assert len(json.loads(records[0]['stdout'])) == 1, records[0]
    assert json.loads(records[2]['stdout'])[0]['path'] == '0.md', records[2]
    assert json.loads(records[4]['stdout'])[0]['path'] == '1.md', records[4]
a.output.write_text(json.dumps(records, separators=(',', ':')) + '\n',
                    encoding='utf-8', newline='\n')
a.admission_output.write_text(json.dumps(dict(pin=pin, captures=admission), indent=2) + '\n',
                              encoding='utf-8')
