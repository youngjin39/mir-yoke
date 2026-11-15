"""Additive Text print/OS boundary captures from isolated pinned Python."""
import json
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
base = Path(__file__).with_name('generate_y_e17b2b1b1.py').read_text()
exec(base.split("out = subprocess")[0], scope)
a, root, wrapper = (scope[k] for k in ('a', 'root', 'wrapper'))
env = {'HOME': str(root), 'PATH': str(root)}
python = scope['scope']['sys'].executable
prefix = wrapper.read_text().split("s = '\\x1c")[0].replace(
    'from mir.cli import bootstrap_adoption', 'from mir.cli import bootstrap, capability')
receipt = dict(status='restart_required', errors=['first é', '\ud800 literal \\ud800 é\nnext'])
wrapper.write_text(prefix + "import types\n"
                   "sys.stdout.reconfigure(encoding='utf-8', errors=sys.argv[2])\n"
                   "bootstrap._emit(types.SimpleNamespace("
                   "json=sys.argv[1]=='true'), json.loads(" + repr(json.dumps(receipt)) + "))\n")
records = []
for as_json in (False, True):
    for handler in ('strict', 'surrogatepass', 'backslashreplace'):
        out = subprocess.run([python, '-I', str(wrapper), str(as_json).lower(), handler],
                             cwd=root, env=env, capture_output=True)
        stderr = out.stderr.decode().splitlines()[-1] + '\n' if out.stderr else ''
        records.append(dict(json=as_json, handler=handler, code=out.returncode,
                            stdout=list(out.stdout), stderr=stderr, receipt=json.dumps(receipt)))
expected = 'mir bootstrap: restart_required\n  [not-ready] first é\n'.encode()
assert records[0]['stdout'] == list(expected)
assert 'position 14' in records[0]['stderr']
assert [r['code'] for r in records] == [1, 0, 0, 0, 0, 0]
wrapper.write_text(prefix + "class Provider:\n def __init__(self,*a,**kw): pass\n"
                   " def status(self,*a,**kw): raise capability.CapabilityError(" +
                   repr('\ud800 literal \\ud800 é') + ")\n"
                   "capability.CapabilityManager=Provider\n"
                   "raise SystemExit(capability.main(['status','--project-root','.','--json']))\n")
out = subprocess.run([python, '-I', str(wrapper)], cwd=root, env=env, capture_output=True)
assert out.returncode == 1 and not out.stdout
records[0]['public_stderr'] = list(out.stderr)
wrapper.write_text(prefix + "print('small')\n")
(root / 'readonly').touch()
with (root / 'readonly').open('rb') as fd:
    out = subprocess.run([python, '-I', str(wrapper)], cwd=root, env=env,
                         stdout=fd, stderr=subprocess.PIPE)
records[0]['stdout_os'] = dict(code=out.returncode, stderr=out.stderr.decode())
assert out.returncode == 120 and 'Bad file descriptor' in out.stderr.decode()
a.output.write_text(json.dumps(records, sort_keys=True) + '\n')
