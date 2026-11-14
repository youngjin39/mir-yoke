"""Freeze Y-E6 from the pinned console; run with python -I."""
import argparse
import gzip
import http.server
import importlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

import sqlite_vec

assert sys.flags.isolated
PIN = "5f8f69f94e09b64c5e4d07d329ed17797c35e6cb"
p = argparse.ArgumentParser()
p.add_argument('--scratch', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--proxy-output', type=Path, required=True)
a = p.parse_args()
repo = Path(__file__).resolve().parents[4]
root = a.scratch.resolve() / 'oracle'
root.mkdir(parents=True, exist_ok=True)
archive = subprocess.check_output(['git', 'archive', PIN, 'src/mir'], cwd=repo)
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
    tar.extractall(root, filter='data')
packages = (
    'pydantic pydantic_core typing_extensions typing_inspection annotated_types '
    'httpx httpcore h11 anyio idna certifi yaml sqlite_vec jsonschema attrs attr '
    'referencing rpds jsonschema_specifications'
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
import ipaddress, socket
lookup, connect = socket.getaddrinfo, socket.socket.connect
connect_ex = socket.socket.connect_ex
def local(host):
    assert ipaddress.ip_address(host).is_loopback, host
def resolve(host, *args, **kwargs):
    local(host)
    return lookup(host, *args, **kwargs)
def dial(sock, address):
    local(address[0])
    return connect(sock, address)
def dial_ex(sock, address):
    local(address[0])
    return connect_ex(sock, address)
socket.getaddrinfo, socket.socket.connect = resolve, dial
socket.socket.connect_ex = dial_ex
addr = ('192.0.2.1', 80)
for probe in (lambda: resolve(*addr), lambda: dial(None, addr), lambda: dial_ex(None, addr)):
    try:
        probe()
    except AssertionError:
        continue
    raise RuntimeError('oracle network guard failed')
from mir.cli.__main__ import main
from mir.cli import context
from mir.core.engine.memory import store
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
if sys.argv[1] == 'proxy':
    import httpx, json
    with httpx.Client() as client:
        selected = client._transport_for_url(httpx.URL(sys.argv[2]))
        print(json.dumps(selected is not client._transport))
    raise SystemExit(0)
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

proxy_records = []
for pattern in ['localhost', 'LOCALHOST', '.localhost', 'example.com', '.example.com',
                '127.0.0.1', '*', '', ' localhost , example.com ', 'unrelated.test']:
    for host in ['localhost', 'child.localhost', 'example.com', 'child.example.com',
                 'badexample.com', '127.0.0.1', 'child.127.0.0.1']:
        env = {'HOME': str(root), 'PATH': os.defpath,
               'HTTP_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': pattern}
        result = subprocess.run([sys.executable, '-I', str(wrapper), 'proxy',
                                 f'http://{host}:12345/'], cwd=root, env=env,
                                capture_output=True, check=True)
        proxy_records.append(dict(pattern=pattern, host=host,
                                  applies=json.loads(result.stdout)))
# IDNA is deliberately OPEN natively; freeze httpx's selection without dialing.
for host, pattern in [
    ('xn--bcher-kva.test', 'xn--bcher-kva.test'),
    ('XN--BCHER-KVA.test', 'XN--BCHER-KVA.test'),
    ('child.xn--bcher-kva.test', '.xn--bcher-kva.test'),
    ('bücher.test', 'example.com'),
    ('example.com', 'bücher.test'),
    ('example.com', 'example.com,xn--bcher-kva.test'),
    ('example.com', '*,xn--bcher-kva.test'),
    ('xn--bcher-kva.test', '*'),
    ('example.com', '*,bücher.test'),
    ('bücher.test', '*'),
    ('example.com', '\u00a0example.com'),
]:
    env = {'HOME': str(root), 'PATH': os.defpath,
           'HTTP_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': pattern}
    result = subprocess.run([sys.executable, '-I', str(wrapper), 'proxy',
                             f'http://{host}:12345/'], cwd=root, env=env,
                            capture_output=True)
    record = dict(pattern=pattern, host=host, native_open=True)
    if result.returncode:
        error = result.stderr.decode().splitlines()[-1]
        assert error.startswith('httpx.InvalidURL:'), error
        record['error'] = error
    else:
        record['applies'] = json.loads(result.stdout)
    proxy_records.append(record)
a.proxy_output.write_text(json.dumps(proxy_records, separators=(',', ':')) + '\n')
records = []
for mode in ["valid", "no-key", "shape", "norm", "missing-data", "bad-json", "status",
             "required-shape", "required-norm", "required-missing-data",
             "required-bad-json", "required-status", "reindex", "reindex-shape",
             "required-disconnect", "required-timeout", "fragment", "query", "chunked", "close",
             "required-refused", "required-garbage", "required-short", "required-gzip", "unicode",
             "required-204", "required-304"]:
    work = root / mode
    work.mkdir(exist_ok=True)
    (work / "notes").mkdir(exist_ok=True)
    (work / "notes/a.md").write_text("Synthetic archive document.\n")
    requests = []
    vector = [1.0] + [0.0] * (1022 if "shape" in mode else 1023)
    if mode.endswith("norm"):
        vector[0] = 2.0
    body = json.dumps({"data": [{"embedding": vector}]}).encode()
    if mode.endswith("missing-data"):
        body = b"{}"
    if mode.endswith("bad-json"):
        body = b"{"
    status = 503 if mode.endswith("status") else 200
    if mode in {'required-204', 'required-304'}:
        status = int(mode.split('-')[1])

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self, requests=requests, status=status, body=body, mode=mode):
            data = self.rfile.read(int(self.headers['Content-Length']))
            requests.append(dict(path=self.path, auth=self.headers.get('Authorization'),
                                 body=json.loads(data), raw_body=data.decode(),
                                 headers={k.lower(): self.headers[k].replace(
                                     str(self.server.server_port), "@PORT@")
                                     for k in ["Host", "Content-Type", "Content-Length"]}))
            if mode == 'required-timeout':
                time.sleep(3)
            if mode in {'required-timeout', 'required-disconnect'}:
                self.close_connection = True
                return
            if mode in {'required-204', 'required-304'}:
                reason = 'No Content' if status == 204 else 'Not Modified'
                self.wfile.write(
                    f'HTTP/1.1 {status} {reason}\r\nConnection: keep-alive\r\n\r\n'.encode())
                self.wfile.flush()
                time.sleep(3)
                return
            if mode == 'required-garbage':
                self.wfile.write(b"garbage\r\n\r\n")
                return
            if mode == 'chunked':
                self.wfile.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n")
                self.wfile.write(f"{len(body):x};fake=yes\r\n".encode() + body
                                 + b"\r\n0\r\nX-Fake: yes\r\n\r\n")
                return
            self.send_response(status)
            payload = gzip.compress(body) if mode == 'required-gzip' else body
            if mode == 'required-gzip':
                self.send_header('Content-Encoding', 'gzip')
            if mode != 'close':
                self.send_header('Content-Length', str(len(payload)
                                 + (1 if mode == 'required-short' else 0)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/v1/'
    url += '#part' if mode == 'fragment' else '?x=1#part' if mode == 'query' else ''
    if mode == 'required-refused':
        server.server_close()
    config = f"""[memory]
vector_mode="{'required' if mode.startswith('required-') else 'optional'}"
[memory.embedding]
enabled=true
required={'true' if mode.startswith('required-') else 'false'}
fingerprint="synthetic-v1"
base_url="{url}"
model="{'synthetic-모델' if mode == 'unicode' else 'synthetic-model'}"
api_key_env="SYNTHETIC_KEY"
auth_scheme="Token"
timeout_sec=2
[[memory.external_archives]]
slug="notes"
root="notes"
"""
    (work / 'harness_a.toml').write_text(config)
    env = {'HOME': str(work), 'PATH': os.defpath, 'PYTHONIOENCODING': 'utf-8', 'NO_PROXY': '*'}
    if mode != 'no-key':
        env['SYNTHETIC_KEY'] = 'fake-only'

    def run(args, work=work, env=env):
        return subprocess.run([sys.executable, '-I', str(wrapper), *args], cwd=work,
                              env=env, capture_output=True)

    # Re-create only this synthetic database on regeneration.
    for suffix in ['', '-wal', '-shm']:
        (work / ('memory.db' + suffix)).unlink(missing_ok=True)
    assert run(['seed', 'memory.db']).returncode == 0
    argv = ['context', 'sync', '--db', 'memory.db']
    if mode.startswith('reindex'):
        disabled = config.replace('enabled=true', 'enabled=false').replace(
            'fingerprint="synthetic-v1"', 'fingerprint=""')
        (work / 'harness_a.toml').write_text(disabled)
        assert run(argv).returncode == 0
        (work / 'harness_a.toml').write_text(config)
        argv.append('--reindex-missing-vectors')
    try:
        result = run(argv)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    assert requests or mode == 'required-refused', (mode, result.stderr)
    with sqlite3.connect(work / 'memory.db') as db:
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        counts = [db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                  for table in ['external_documents', 'external_chunks', 'external_chunks_vec']]
    records.append(dict(mode=mode, argv=argv,
                        config=config.replace(url.split('#')[0].split('?')[0], '@URL@'),
                        body=body.decode(), status=status, requests=requests,
                        exit=result.returncode, stdout=result.stdout.decode().replace(
                            url.rstrip('/'), '@URLBASE@'),
                        stderr=result.stderr.decode(), counts=counts))
assert records[0]['exit'] == 0 and records[0]['requests'][0]['path'] == '/v1/embeddings'
a.output.write_text(json.dumps(records, separators=(',', ':')) + '\n')
