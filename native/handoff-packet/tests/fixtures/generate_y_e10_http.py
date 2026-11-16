import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

os_env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR')
          if os.name == 'nt' and k in os.environ}
setup = {}
source = Path(__file__).with_name('generate_y_e9.py').read_text()
exec(source.split("wrapper = root / 'capture.py'")[0], setup)
root, packages, a = (setup[k] for k in ('root', 'packages', 'a'))
wrapper = root / 'http_probe.py'
wrapper.write_text('''import pathlib, socket, sys, sysconfig, json
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload')]
if sys.platform == 'win32':
    sys.path.append(str(pathlib.Path(sys.base_prefix) / 'DLLs'))
lookup, connect, connect_ex = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex
def resolve(host, *args, **kwargs):
    assert host == '127.0.0.1', host
    return lookup(host, *args, **kwargs)
def dial(sock, address):
    assert address[0] == '127.0.0.1', address
    return connect(sock, address)
def dial_ex(sock, address):
    assert address[0] == '127.0.0.1', address
    return connect_ex(sock, address)
socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex = resolve, dial, dial_ex
from mir.core.engine.memory.backends.omlx_http import OmlxHttpBackend, _BackendCfg
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGES and getattr(module, '__file__', None):
        assert pathlib.Path(module.__file__).resolve().is_relative_to(root), name
backend = OmlxHttpBackend(_BackendCfg(sys.argv[1], 'fake', 1, 1, .001, 'NO_KEY', 'Bearer'))
try:
    r = backend._client.post('/embeddings', json={'model': 'fake', 'input': ['fake']})
    result = dict(status=r.status_code, reason=r.reason_phrase, body=r.text)
except Exception as e:
    result = dict(error=type(e).__name__, message=str(e))
finally:
    backend.close()
print(json.dumps(result))
'''.replace('PACKAGES', repr(set(['mir', *packages]))))
responses = [b'garbage\r\n\r\n', b'\r\n', b'HTTP/1.1 20 OK\r\n\r\n', b'HTTP/1.1 099 X\r\n\r\n',
             b'HTTP/1.1 101 Switch\r\n\r\n', b'HTTP/1.2 200 OK\r\nContent-Length: 0\r\n\r\n',
             b'HTTP/1.1 200 O\x00K\r\n\r\n',
             b'HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 103 Early\r\n\r\n'
             b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}']
responses += [
    b'garbage\r\n', b'HTTP/1.1 200 OK\r\nX: ' + b'x' * 102400,
    *[b'HTTP/1.1 200 OK\r\n' + h + b'\r\n\r\n' for h in (
        b'Bad Name: a', b'X: a\x00b', b' continuation',
        b'X: a\r\n b\r\nContent-Length: 0',
        b'Content-Length: 0, 0', b'Content-Length: 0, 1',
        b'Content-Length: 0\r\nContent-Length: 1', b'Content-Length: +0',
        b'Transfer-Encoding: gzip', b'Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked')],
    *[b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n' + c for c in (
        b'wat\r\n', b'1\r\nx!!', b'1\r\nx', b'2\r\nx', b'0\r\nBad Name: x\r\n\r\n',
        b'0\r\nX: y\r\n z\r\n\r\n', b'1;foo=bar\r\nx\r\n0\r\n\r\n')],
]
responses += [b'HTTP/1.1 200 OK\r\nContent-Length: \xe2\x80\x830\r\n\r\n']
records = []
for response in responses:
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        def serve(response=response):
            with listener.accept()[0] as stream:
                stream.settimeout(2)
                request = b''
                while b'\r\n\r\n' not in request:
                    request += stream.recv(65536)
                head, body = request.split(b'\r\n\r\n', 1)
                size = int(next(line.split(b':')[1] for line in head.split(b'\r\n')
                                if line.lower().startswith(b'content-length:')))
                while len(body) < size:
                    body += stream.recv(65536)
                stream.sendall(response)
        thread = threading.Thread(target=serve)
        thread.start()
        url = f'http://127.0.0.1:{listener.getsockname()[1]}/'
        output = subprocess.check_output(
            [sys.executable, '-I', str(wrapper), url], cwd=root,
            env={**os_env, 'HOME': str(root), 'USERPROFILE': str(root),
                 'PYTHONIOENCODING': 'utf-8', 'PATH': os.defpath, 'NO_PROXY': '*',
                 'SSL_CERT_FILE': str(root / 'certifi/cacert.pem')})
        thread.join()
        records.append(dict(wire=list(response), **json.loads(output)))
a.output.write_text(json.dumps(records, separators=(',', ':')) + '\n')
