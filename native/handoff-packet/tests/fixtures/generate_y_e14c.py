"""Freeze artifact reads from isolated 5f8f69f; only loopback is permitted."""
import os
import subprocess
from pathlib import Path

os_env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR')
          if os.name == 'nt' and k in os.environ}
scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e8.py").read_text().split("wrapper =")[0]
     .replace("yaml sqlite_vec", "yaml"), scope)
root, a = scope["root"], scope["a"]
wrapper = root / "capture_c.py"
wrapper.write_text('''import sys, pathlib, sysconfig, socket, threading, json, os
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root/'src'), str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
if sys.platform == 'win32':
    sys.path.append(str(pathlib.Path(sys.base_prefix) / 'DLLs'))
from mir.core.capabilities.native import _read
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
original = socket.socket.connect
def connect(self, address):
    assert address[0] == '127.0.0.1', address
    return original(self, address)
socket.socket.connect = connect; records = []
for mode in ['200','204','300','400','500','301','302','303','307','308',
             'absolute','relative','query','scheme-relative','fragment','empty','dot','cookie',
             'slashes','loop','missing','304','404','short','https','proxy','relative-empty','absolute-query']:
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0)); listener.listen(); listener.settimeout(1)
    port = str(listener.getsockname()[1])
    base = f'http://127.0.0.1:{port}'
    requests, wires = [], []
    def serve():
        with listener:
            while True:
                try:
                    stream, _ = listener.accept()
                except TimeoutError: break
                with stream:
                    if mode == 'https' and len(requests) == 1:
                        stream.recv(65536)
                        break
                    head = b''
                    while not head.endswith(b'\\r\\n\\r\\n'):
                        head += stream.recv(1)
                    requests.append(head.split(b'\\r\\n')[0].decode("utf-8"))
                    assert head.startswith(b'GET ') and b'Content-Length:' not in head
                    status, headers, body = '200 OK', '', b'artifact'
                    if len(requests) == 1 or mode == 'loop':
                        status = (mode if mode.isdigit() else '302') + ' Test'
                        location = {'absolute':base+'/artifact', 'relative':'../artifact',
                                    'relative-empty':'a//b', 'absolute-query':base+'?next=/a/../b',
                                    'query':'?x=1', 'scheme-relative':base[5:]+'/artifact',
                                'fragment':'#x', 'empty':'', 'dot':'../dir/.', 'slashes':base+'//a',
                                    'https':base.replace('http:', 'https:')+'/artifact',
                                    'proxy':'http://localhost:'+str(listener.getsockname()[1])+'/artifact'}
                        headers = 'Location: '+location.get(mode, '/artifact')+'\\r\\n'
                        if mode == 'missing': headers = ''
                        if mode == 'cookie': headers += 'Set-Cookie: x=y\\r\\n'
                        if mode in ['200','204','300','400','500','304','404',
                                    'chunked','short']:
                            status, headers = ('200' if not mode.isdigit() else mode)+' Test', ''
                    size = 9 if mode == 'short' else len(body)
                    headers += 'Content-Length: '+str(size)+'\\r\\n'
                    wire = ('HTTP/1.1 '+status+'\\r\\n'+headers
                            +'Connection: close\\r\\n\\r\\n').encode()+body
                    wires.append(wire.decode("utf-8").replace(port, '<PORT>'))
                    stream.sendall(wire)
    thread = threading.Thread(target=serve); thread.start()
    if mode == 'proxy':
        os.environ.update(HTTP_PROXY=base, NO_PROXY='127.0.0.1')
    try:
        result = dict(body=_read(base+'/dir/start', 8).decode("utf-8"))
    except Exception as exc:
        result = dict(error=type(exc).__name__, message=str(exc).replace(base, '<BASE>'))
    thread.join()
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('NO_PROXY', None)
    records.append(dict(mode=mode, requests=[r.replace(port, "<PORT>") for r in requests],
                        wires=wires, result=result))
assert records[0]['result'] == {'body':'artifact'}
print(json.dumps(records, separators=(',', ':')))
'''.replace('PACKAGE_SET', repr(set(['mir', *scope['packages']]))))
work = a.scratch.resolve() / "work"
work.mkdir(exist_ok=True)
result = subprocess.run([scope["sys"].executable, "-I", str(wrapper)], cwd=work,
                        env={**os_env, "HOME": str(work), "USERPROFILE": str(work),
                             "PYTHONIOENCODING": "utf-8", "PATH": "/usr/bin:/bin"},
                        check=True, capture_output=True, timeout=90)
a.output.write_bytes(result.stdout)
