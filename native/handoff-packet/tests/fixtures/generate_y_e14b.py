"""Capture Y-E14b from pinned Python, with loopback-only networking."""
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
source = Path(__file__).with_name("generate_y_e13.py").read_text()
exec(source.split("resources =")[0].replace("yaml sqlite_vec", "yaml"), scope)
root, a = scope["root"], scope["a"]
wrapper = root / "capture_e14b.py"
wrapper.write_text('''import sys, pathlib, sysconfig, json, socket, threading, hashlib, os
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload')]
from mir.cli import bootstrap_adoption as adoption
from mir.cli import _adoption_native as native
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
original = socket.socket.connect
def connect(self, address):
    assert address[0] == '127.0.0.1', address
    return original(self, address)
socket.socket.connect = connect
records = []
import contextlib, io
for argv in [['-hgarbage=abc'], ['--project-root', '-1\\n', '--help']]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            adoption._parse(argv)
        except SystemExit as exc:
            code = exc.code
    records.append(dict(argv=argv, exit=code, stdout=out.getvalue(), stderr=err.getvalue()))
body = b'synthetic evaluator\\n'
for mode in ['http-ok', 'http-error', 'https-refusal', 'http-disconnect', 'http-oversize']:
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    def serve():
        with listener:
            stream, _ = listener.accept()
            with stream:
                stream.recv(65536)
                if mode == 'http-disconnect':
                    return
                payload = body + b'x' if mode == 'http-oversize' else body
                status = b'404 Not Found' if mode == 'http-error' else b'200 OK'
                head = (b'HTTP/1.1 ' + status + b'\\r\\nContent-Length: '
                        + str(len(payload)).encode() + b'\\r\\nConnection: close\\r\\n\\r\\n')
                stream.sendall(head + payload)
    thread = threading.Thread(target=serve)
    thread.start()
    scheme = 'https' if mode == 'https-refusal' else 'http'
    url = f'{scheme}://127.0.0.1:{listener.getsockname()[1]}/artifact'
    pin = dict(url=url, size=len(body), sha256=hashlib.sha256(body).hexdigest())
    work = pathlib.Path.cwd() / mode
    work.mkdir(exist_ok=True)
    result = native._install(work, source_root=None, name='bootstrap-gate', artifact_pin=pin)
    thread.join()
    dest = work / '.mir/bin/bootstrap-gate'
    records.append(dict(mode=mode, result=result,
                        installed=dest.read_text() if dest.exists() else None))
assert records[0]['exit'] == records[1]['exit'] == 0
assert records[2]['installed'] == body.decode()
assert records[3]['result'] is records[4]['result'] is None
print(json.dumps(records, separators=(',', ':')))
'''.replace('PACKAGE_SET', repr(set(['mir', *scope['packages']]))))
work = a.scratch.resolve() / "work"
work.mkdir(exist_ok=True)
result = subprocess.run([scope["sys"].executable, "-I", str(wrapper)], cwd=work,
                        env={"HOME": str(work), "PATH": "/usr/bin:/bin"},
                        check=True, capture_output=True, timeout=60)
a.output.write_bytes(result.stdout)
