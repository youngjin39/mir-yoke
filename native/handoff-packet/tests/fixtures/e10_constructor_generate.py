import json
import os
import subprocess
import sys
from pathlib import Path

source = Path(__file__).with_name('generate_y_e9.py').read_text()
setup = {}
exec(source.split("wrapper = root / 'capture.py'")[0], setup)
root, packages, a = (setup[k] for k in ('root', 'packages', 'a'))
wrapper = root / 'constructor.py'
wrapper.write_text('''import sys, pathlib, sysconfig, json
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root/'src'),str(root),stdlib,str(pathlib.Path(stdlib)/'lib-dynload')]
from mir.cli.__main__ import main
from mir.cli import context
from mir.core.engine.memory import store
from mir.core.engine.memory.backends import omlx_http
for name,module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in
                   ([module.__file__] if module.__file__ else module.__path__)), name
import socket
socket.socket.connect = lambda *a: (_ for _ in ()).throw(AssertionError('network forbidden'))
c=store.connect(pathlib.Path('memory.db')); store.apply_migrations(c.conn); c.conn.close()
try: code=main(json.loads(sys.argv[1]))
except Exception as exc:
    print(type(exc).__name__+': '+str(exc),file=sys.stderr); code=1
raise SystemExit(code)
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
records = []
for action, archives, enabled, required, reindex in [
        ('sync', True, True, False, False), ('sync', True, True, True, False),
        ('sync', True, True, False, True), ('sync', False, True, False, False),
        ('sync', True, False, False, False), ('pull', False, True, False, False)]:
    for url, key, env in [('http://127.0.0.1:bad', '', {}),
                          ('http://[bad]/', '', {}), ('http://127.0.0.1/\n', '', {}),
                          ('http://127.0.0.1', 'ü', {}),
                          ('http://127.0.0.1', '', {'SSL_CERT_FILE':'absent.pem'}),
                          ('http://127.0.0.1', '', {'SSL_CERT_FILE':'notes'}),
                          ('http://[fe80::1%25lo0]/', '', {})]:
        work = root / ('constructor-' + str(len(records)))
        work.mkdir(exist_ok=True)
        (work/'notes').mkdir(exist_ok=True)
        config = ('[memory]\nvector_mode="optional"\n[memory.embedding]\n'
                  f'enabled={str(enabled).lower()}\nrequired={str(required).lower()}\n'
                  f'fingerprint="synthetic"\nbase_url={json.dumps(url)}\napi_key_env="FAKE_KEY"\n')
        if archives:
            config += '[[memory.external_archives]]\nslug="notes"\nroot="notes"\nmode="indexed"\n'
        (work/'harness_a.toml').write_text(config)
        argv = ['context',action,*(['query'] if action == 'pull' else []),'--db','memory.db']
        if reindex:
            argv += ['--reindex-missing-vectors']
        for suffix in ['', '-wal', '-shm']:
            (work/('memory.db'+suffix)).unlink(missing_ok=True)
        result = subprocess.run([sys.executable,'-I',str(wrapper),json.dumps(argv)],cwd=work,
                                env=dict(HOME=str(work),PATH=os.defpath,FAKE_KEY=key,**env),capture_output=True)
        records.append(dict(argv=argv,config=config,key=key,env=env,exit=result.returncode,
                            stdout=result.stdout.decode(),stderr=result.stderr.decode()))
assert records[0]['stdout'].startswith('[degraded] embedding unavailable'), records[0]
a.output.write_text(json.dumps(records,separators=(',',':'))+'\n')
