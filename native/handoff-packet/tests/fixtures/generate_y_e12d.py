"""Freeze Y-E12d reviewer counterexamples, pinned console and loopback only."""
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

scope = {'__file__': __file__}
exec(Path(__file__).with_name('generate_y_e12c.py').read_text().split('records = []')[0], scope)
root, wrapper, a = (scope[k] for k in ('root', 'wrapper', 'a'))
records = []
for mode in ('close-first', 'close-last', 'trailer-eof', 'plus-port'):
    requests = []
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(2)
        port = listener.getsockname()[1]

        def serve(mode=mode, listener=listener, requests=requests, port=port):
            for _ in range(2):
                with listener.accept()[0] as stream:
                    stream.settimeout(2)
                    data = b''
                    while not data.endswith(b'\r\n\r\n'):
                        part = stream.recv(1)
                        assert part
                        data += part
                    size = int(next(v.split(b':')[1] for v in data.split(b'\r\n')
                                    if v.lower().startswith(b'content-length:')))
                    while size:
                        part = stream.recv(size)
                        assert part
                        size -= len(part)
                    requests.append(data.decode().replace(str(port), '{PORT}'))
                    wire = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n'
                    if mode.startswith('close-'):
                        values = ['close', 'keep-alive']
                        if mode == 'close-last':
                            values.reverse()
                        wire += ''.join(f'Connection: {v}\r\n' for v in values).encode()
                    if mode == 'trailer-eof':
                        wire = b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\nX: abc'
                    else:
                        wire += b'\r\n{}'
                    stream.sendall(wire)
                    # Keep connection open until client closes, exposing erroneous reuse.
                    if mode.startswith('close-'):
                        assert stream.recv(1) == b''
        thread = threading.Thread(target=serve)
        thread.start()
        output = subprocess.check_output(
            [sys.executable, '-I', str(wrapper),
             f'http://127.0.0.1:{"+" if mode == "plus-port" else ""}{port}/', mode, '1'],
            cwd=root, env={'HOME': str(root), 'PATH': os.defpath, 'NO_PROXY': '*',
                           'SSL_CERT_FILE': str(root / 'certifi/cacert.pem')})
        thread.join()
    records.append(dict(mode=mode, connections=len(requests), requests=requests,
                        results=json.loads(output)))
a.output.write_text(json.dumps(records, separators=(',', ':')) + '\n')
# Reuse the isolated console/migration wrapper, with all sockets forbidden.
setup = {'__file__': __file__}
source = Path(__file__).with_name('generate_y_e10_constructor.py').read_text()
exec(source.split('records = []')[0], setup)
root, wrapper = (setup[k] for k in ('root', 'wrapper'))
records = []
for action, required in [('pull', False), ('sync', False), ('sync', True)]:
    for env in [{'SSL_CERT_FILE': 'invalid.pem'},
                {'HTTP_PROXY': 'http://127.0.0.1:bad'},
                {'HTTPS_PROXY': 'http://127.0.0.1:bad'},
                {'ALL_PROXY': 'ftp://127.0.0.1:1'}]:
        work = root / f'e12d-{len(records)}'
        work.mkdir(exist_ok=True)
        (work / 'invalid.pem').write_text('not a certificate\n')
        config = ('[memory]\nvector_mode="optional"\n[memory.embedding]\n'
                  'enabled=true\nfingerprint="synthetic"\nbase_url="http://127.0.0.1/"\n'
                  f'required={str(required).lower()}\n')
        (work / 'harness_a.toml').write_text(config)
        argv = ['context', action, *(['q', '--json'] if action == 'pull' else []),
                '--db', 'memory.db']
        result = subprocess.run([sys.executable, '-I', str(wrapper), json.dumps(argv)],
                                cwd=work, capture_output=True,
                                env={'HOME': str(work), 'PATH': os.defpath,
                                     'NO_PROXY': '127.0.0.1', **env})
        records.append(dict(argv=argv, config=config, env=env, exit=result.returncode,
                            stdout=result.stdout.decode(), stderr=result.stderr.decode()))
assert json.loads(records[0]['stdout'])['degraded'] is True
a.output.with_name('y-e12d-cli.json').write_text(json.dumps(records, separators=(',', ':')) + '\n')
wrapper.write_text(wrapper.read_text().split('c=store.connect')[0] + '''
try:
    omlx_http.OmlxHttpBackend(omlx_http._BackendCfg(
        'http://127.0.0.1/', 'fake', 1, 1, .001, 'NO_KEY', 'Bearer'))
except Exception as e:
    print(json.dumps(dict(error=type(e).__name__, message=str(e))))
else:
    raise AssertionError('constructor accepted invalid input')
''')
errors = []
for r in records[:4]:
    result = subprocess.check_output([sys.executable, '-I', str(wrapper)], cwd=work,
                                     env={'HOME': str(work), 'PATH': os.defpath,
                                          'NO_PROXY': '127.0.0.1', **r['env']})
    errors.append(dict(env=r['env'], **json.loads(result)))
a.output.with_name('y-e12d-errors.json').write_text(
    json.dumps(errors, separators=(',', ':')) + '\n')
