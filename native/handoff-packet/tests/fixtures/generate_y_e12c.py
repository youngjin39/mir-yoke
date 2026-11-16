"""Freeze sequential requests from the isolated pinned Python backend, loopback only."""
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

os_env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR')
          if os.name == 'nt' and k in os.environ}
scope = {'__file__': __file__}
source = Path(__file__).with_name('generate_y_e10_http.py').read_text()
exec(source.split('responses =')[0], scope)
root, wrapper, a = (scope[k] for k in ('root', 'wrapper', 'a'))
prelude = wrapper.read_text().split('backend =')[0]
wrapper.write_text(prelude + '''
backend = OmlxHttpBackend(_BackendCfg(sys.argv[1], 'fake', 1,
                                    int(sys.argv[3]), .001, 'NO_KEY', 'Bearer'))
results = []
for _ in range(2):
    try:
        r = backend._client.post('/embeddings', json={'model':'fake','input':['fake']})
        results.append(dict(status=r.status_code, reason=r.reason_phrase, body=r.text))
    except Exception as e:
        results.append(dict(error=type(e).__name__, message=str(e)))
    if sys.argv[2] == 'stale':
        # Server closes before the next request: select/peek observes EOF.
        import time
        time.sleep(.1)
backend.close()
print(json.dumps(results))
''')
records = []
for mode in ('reuse', 'stale', 'mid', 'close', 'timeout'):
    count = []
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(1)

        def serve(mode=mode, count=count, listener=listener):
            try:
                for _ in range(1 if mode in ('reuse', 'mid') else 2):
                    with listener.accept()[0] as stream:
                        count.append(1)
                        stream.settimeout(1)
                        for n in range(2 if mode in ('reuse', 'mid') else 1):
                            data = b''
                            while not data.endswith(b'\r\n\r\n'):
                                part = stream.recv(1)
                                if not part:
                                    return
                                data += part
                            size = int(next(v.split(b':')[1] for v in data.split(b'\r\n')
                                            if v.lower().startswith(b'content-length:')))
                            while size:
                                part = stream.recv(size)
                                assert part
                                size -= len(part)
                            wire = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n'
                            if mode == 'close':
                                wire += b'Connection: close\r\n'
                            body = b'x' if mode == 'mid' and n else b'{}'
                            stream.sendall(wire + b'\r\n' + body)
            except TimeoutError:
                assert mode == 'timeout'
        thread = threading.Thread(target=serve)
        thread.start()
        output = subprocess.check_output(
            [sys.executable, '-I', str(wrapper),
             f'http://127.0.0.1:{listener.getsockname()[1]}/', mode,
             str(18446744073709551615 if mode == 'timeout' else 1)], cwd=root,
            env={**os_env, 'HOME': str(root), 'USERPROFILE': str(root),
                 'PYTHONIOENCODING': 'utf-8', 'PATH': os.defpath, 'NO_PROXY': '*',
                 'SSL_CERT_FILE': str(root / 'certifi/cacert.pem')})
        thread.join()
    records.append(dict(mode=mode, connections=len(count), results=json.loads(output)))
assert records[0]['connections'] == 1
assert records[1]['connections'] == 2
assert records[2]['results'][1]['error'] == 'RemoteProtocolError'
a.output.write_text(json.dumps(records, separators=(',', ':')) + '\n')
wrapper.write_text(prelude + '''
try:
    backend = OmlxHttpBackend(_BackendCfg('http://127.0.0.1/', 'fake', 1, 1,
                                        .001, 'NO_KEY', 'Bearer'))
except Exception as e:
    print(json.dumps(dict(error=type(e).__name__, message=str(e))))
else:
    raise AssertionError('invalid PEM accepted')
''')
pem = root / 'empty.pem'
pem.write_text('not a certificate\n')
output = subprocess.check_output([sys.executable, '-I', str(wrapper)], cwd=root,
                                env={**os_env, 'HOME': str(root), 'USERPROFILE': str(root),
                 'PYTHONIOENCODING': 'utf-8', 'PATH': os.defpath,
                                     'SSL_CERT_FILE': str(pem)})
a.output.with_name('y-e12c-pem.json').write_bytes(output)
