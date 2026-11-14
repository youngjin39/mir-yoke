"""Capture additional h11 framing cases from the isolated pinned E10 oracle."""
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

http_source = Path(__file__).with_name('generate_y_e10_http.py').read_text()
scope = {'__file__': __file__}
exec(http_source.split('responses =')[0], scope)
root, wrapper, a = (scope[k] for k in ('root', 'wrapper', 'a'))
responses = [
    *[b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nX: a' + bytes([c]) + b'b\r\n\r\n{}'
      for c in (1, 11, 31, 127)],
    b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nX: ' + b'x' * 110000 + b'\r\n\r\n{}',
    b'HTTP/1.1 200 OK\r\nX: ' + b'x' * 110000,
    b'HTTP/1.1 200 OK\r\nContent-Length: 18446744073709551616\r\n\r\nx',
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n10000000000000000\r\nx',
]
scope['responses'] = responses
exec(http_source[http_source.index('records = []'):], scope)
records = scope['records']
assert records[0]['body'] == '{}'
assert records[4]['body'] == '{}'
assert records[5]['message'] == 'Receive buffer too long'
http_prelude = wrapper.read_text().split('backend =')[0]
probe = http_prelude + '''
import h11, httpx
records = []
for value in ['Bearer x ', 'Bearer x\\t', 'Bearer x\\x0b', 'Bearer x\\x01y', 'Bearer x\\x7fy']:
    try:
        h11.Request(method='POST', target='/',
                    headers=[('Host', 'localhost'), ('Authorization', value)])
        result = dict(ok=True)
    except Exception as exc:
        result = dict(error=type(exc).__name__, message=str(exc))
    records.append(dict(value=value, **result))
print(json.dumps(records))
'''
wrapper.write_text(probe)
output = subprocess.check_output([sys.executable, '-I', str(wrapper)], cwd=root,
                                env={'HOME': str(root), 'PATH': os.defpath})
a.output.with_name('y-e12b-auth.json').write_bytes(output)
wrapper.write_text(http_prelude + '''
backend = OmlxHttpBackend(_BackendCfg(sys.argv[1], 'fake', 1,
                                    18446744073709551615, .001, 'NO_KEY', 'Bearer'))
assert backend._client.timeout.read == 18446744073709551615
backend.close()
backend = OmlxHttpBackend(_BackendCfg(sys.argv[1], 'fake', 1, 1, .001, 'NO_KEY', 'Bearer'))
print(json.dumps(dict(statuses=[backend._client.post('/embeddings', json={}).status_code
                                for _ in range(2)], timeout=18446744073709551615)))
backend.close()
''')
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(3)
    def serve_reuse():
        with listener.accept()[0] as stream:
            stream.settimeout(2)
            for _ in range(2):
                data = b''
                while b'\r\n\r\n' not in data:
                    part = stream.recv(1)
                    assert part, 'reference did not reuse connection'
                    data += part
                size = int(next(line.split(b':')[1] for line in data.split(b'\r\n')
                                if line.lower().startswith(b'content-length:')))
                while size:
                    part = stream.recv(size)
                    assert part
                    size -= len(part)
                stream.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}')
    thread = threading.Thread(target=serve_reuse)
    thread.start()
    child_env = {'HOME': str(root), 'PATH': os.defpath, 'NO_PROXY': '*',
                 'SSL_CERT_FILE': str(root / 'certifi/cacert.pem')}
    output = subprocess.check_output([sys.executable, '-I', str(wrapper),
                                      f'http://127.0.0.1:{listener.getsockname()[1]}/'],
                                     cwd=root, env=child_env)
    thread.join()
a.output.with_name('y-e12b-lifecycle.json').write_bytes(output)
