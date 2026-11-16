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

os_env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR')
          if os.name == 'nt' and k in os.environ}
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
wrapper.write_text('''import sys, pathlib, sysconfig, json, os, http.server, threading
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload')]
if sys.platform == 'win32':
    sys.path.append(str(pathlib.Path(sys.base_prefix) / 'DLLs'))
import socket, ipaddress
lookup, connect = socket.getaddrinfo, socket.socket.connect
def resolve(host, *a, **kw):
    assert ipaddress.ip_address(host).is_loopback
    return lookup(host, *a, **kw)
def dial(sock, addr):
    assert ipaddress.ip_address(addr[0]).is_loopback
    return connect(sock, addr)
socket.getaddrinfo, socket.socket.connect = resolve, dial
from mir.cli.__main__ import main
from mir.core.engine.memory import store
from mir.core.engine.memory.backends import omlx_http
from mir.core.engine.memory.external_store import ExternalStore
import sqlite_vec
import os, json, time
if os.environ.get('MIR_E6_DIAG') == '1':
    import httpx
    send = httpx.Client.send
    def observed(self, *args, **kwargs):
        started = time.monotonic()
        data = dict(event='reference-http')
        try:
            response = send(self, *args, **kwargs)
            data.update(status=response.status_code, body_hex=response.content.hex())
            return response
        except Exception as exc:
            chain = []
            while exc is not None:
                chain.append(repr(exc))
                exc = exc.__cause__ or exc.__context__
            data['errors'] = chain
            raise
        finally:
            data['elapsed_sec'] = time.monotonic() - started
            print('[MIR_E6_DIAG] ' + json.dumps(data), file=sys.stderr)
    httpx.Client.send = observed
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
mode = sys.argv[1]
work = pathlib.Path.cwd()
c = store.connect(work / 'memory.db')
store.apply_migrations(c.conn)
es = ExternalStore(c)
if mode != 'no-archives':
    aid = es.register(slug='notes', root_path=str(work / 'notes'),
                      mode='indexed', owner='synthetic')
    es.scan(aid)
    for i in range(3):
        v = [0.0] * 1024
        v[0 if mode == 'ties' else 2-i] = 1.0
        if mode != 'no-vectors':
            c.conn.execute('INSERT INTO external_chunks_vec(rowid,embedding) VALUES (?,?)',
                           (i+1, sqlite_vec.serialize_float32(v)))
    c.conn.execute('INSERT OR REPLACE INTO external_store_meta(key,value) VALUES (?,?)',
                  ('external_embedding_fingerprint',
                   'wrong' if mode == 'mismatch' else 'synthetic-v1'))
if mode in {'fts-error', 'both-error'}:
    c.conn.execute('DROP TABLE external_chunks_fts')
if mode in {'vec-error', 'both-error'}:
    c.conn.execute('DROP TABLE external_chunks_vec')
c.conn.commit()
c.conn.close()
if mode == 'stale':
    (work / 'notes/2.md').write_text('changed', encoding='utf-8')
requests = []
class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
        body = b'{' if mode == 'bad-json' else json.dumps(
            {'data':[{'embedding':[1.0]+[0.0]*1023}]}).encode()
        self.send_response(503 if mode == 'status' else 200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_): pass
server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
thread = threading.Thread(target=server.serve_forever)
thread.start()
config = '[memory]\\nvector_mode="optional"\\n[memory.embedding]\\n'
config += 'enabled='+('false' if mode == 'disabled' else 'true')+'\\n'
config += 'fingerprint="synthetic-v1"\\n'
config += 'base_url="http://127.0.0.1:'+str(server.server_port)+'/v1/"\\n'
config += 'model="synthetic-model"\\napi_key_env="SYNTHETIC_KEY"\\n'
(work / 'harness_a.toml').write_text(config, encoding='utf-8')
try:
    code = main(sys.argv[2:])
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    code = 1
finally:
    server.shutdown()
    thread.join()
    server.server_close()
(work / 'requests.json').write_text(json.dumps(requests), encoding='utf-8')
raise SystemExit(code)
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))), encoding='utf-8')
records = []
for mode in ['hybrid', 'ties', 'limit', 'text', 'disabled', 'no-vectors', 'no-archives',
             'mismatch', 'bad-json', 'status', 'vec-error', 'fts-error', 'both-error', 'stale']:
    work = root / mode
    work.mkdir(exist_ok=True)
    (work / 'notes').mkdir(exist_ok=True)
    docs = ['alpha apple orchard.\n', 'beta ocean harbor.\n', 'gamma desert dunes.\n']
    for i, text in enumerate(docs):
        (work / f'notes/{i}.md').write_text(text, encoding='utf-8')
    for suffix in ['', '-wal', '-shm']:
        (work / ('memory.db' + suffix)).unlink(missing_ok=True)
    argv = ['context', 'pull', 'apple', '--db', 'memory.db', '--k', '1' if mode == 'limit' else '3']
    if mode != 'text':
        argv.append('--json')
    result = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-B', str(wrapper), mode, *argv],
                            cwd=work, env=dict(os_env, HOME=str(work), USERPROFILE=str(work),
                                              PYTHONIOENCODING="utf-8", PATH=os.defpath,
                                              SYNTHETIC_KEY='fake-only',
                                              MIR_E6_DIAG=os.environ.get('MIR_E6_DIAG', '')),
                            capture_output=True)
    if os.environ.get('MIR_E6_DIAG') == '1':
        print(json.dumps(dict(event='reference-console', mode=mode, exit=result.returncode,
                              stdout=result.stdout.decode('utf-8'),
                              stderr=result.stderr.decode('utf-8'))), file=sys.stderr)
        result.stderr = b''.join(line for line in result.stderr.splitlines(keepends=True)
                                 if not line.startswith(b'[MIR_E6_DIAG] '))
    records.append(dict(mode=mode, docs=docs, argv=argv, exit=result.returncode,
                        stdout=result.stdout.decode("utf-8"), stderr=result.stderr.decode("utf-8"),
                        requests=json.loads((work / 'requests.json').read_text(encoding='utf-8'))))
assert len(json.loads(records[0]['stdout'])['chunks']) == 3, records[0]
assert json.loads(records[0]['stdout'])['degraded'] is False, records[0]
assert records[0]['requests'], records[0]
assert json.loads(records[8]['stdout'])['degraded'] is True
assert not records[6]['requests']
a.output.write_text(json.dumps(records, separators=(',', ':')) + '\n', encoding='utf-8')
