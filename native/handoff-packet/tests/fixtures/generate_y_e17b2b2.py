"""Pinned bootstrap emit-to-console bytes; no live package imports."""
import json
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
base = Path(__file__).with_name("generate_y_e17b2b1b1.py").read_text()
exec(base.split("out = subprocess")[0], scope)
a, root, wrapper = (scope[k] for k in ("a", "root", "wrapper"))
source = wrapper.read_text().split("s = '\\x1c")[0]
source = source.replace("from mir.cli import bootstrap_adoption",
                        "from mir.cli import bootstrap_adoption, bootstrap, capability")
prefix = source
source += (
    "import types\nsys.stdout.reconfigure(encoding='utf-8', errors=sys.argv[2])\n"
    "bootstrap._emit(types.SimpleNamespace(json=sys.argv[1]=='1'), "
    "{'status':'incomplete','errors':['\\ud800 literal \\\\ud800 é']})\n"
)
wrapper.write_text(source)
records = []
for as_json in (False, True):
    for handler in ('strict', 'surrogatepass', 'backslashreplace'):
        out = subprocess.run(
            [scope['scope']['sys'].executable, '-I', str(wrapper), str(int(as_json)), handler],
            cwd=root, env={'HOME': str(root), 'PATH': str(root),
                           'PYTHONIOENCODING': 'utf-8:'+handler}, capture_output=True)
        stderr = out.stderr.decode().splitlines()[-1] + '\n' if out.stderr else ''
        records.append(dict(json=as_json, handler=handler, code=out.returncode,
                            stdout=list(out.stdout), stderr=stderr))
assert [r['code'] for r in records] == [1, 0, 0, 0, 0, 0]
assert records[0]['stdout'] == list(b'mir bootstrap: incomplete\n')
wrapper.write_text(prefix + """import os
class Provider:
 def __init__(self, *a, **kw): pass
 def finalize(self, *a, **kw): raise capability.CapabilityError('refused')
capability.CapabilityManager = Provider
saved, fd = os.dup(2), os.open(os.devnull, os.O_RDONLY)
os.dup2(fd, 2); os.close(fd)
try: capability.main(['finalize', '--project-root', '.', '--apply', '--after-restart', '--json'])
except Exception as e: result = dict(klass=type(e).__name__, message=str(e))
os.dup2(saved, 2); os.close(saved)
print(json.dumps(result))
""")
out = subprocess.check_output([scope['scope']['sys'].executable, '-I', str(wrapper)],
                              cwd=root, env={'HOME': str(root), 'PATH': str(root)},
                              stderr=subprocess.PIPE)
records.append(dict(mode='stderr-os', result=json.loads(out)))
manager = root / 'src/mir/core/capabilities/manager.py'
original = manager.read_text()
for r in json.loads(Path(__file__).with_name('y-e17b2b1a.json').read_text()):
    if r.get('result', {}).get('class') not in ('OddProviderError', 'CapabilityError'):
        continue
    manager.write_text(original + '\n' + r['source'])
    wrapper.write_text(prefix + "import traceback\ntry: "
                       "capability.main(['status','--project-root','.','--json'])\n"
                       "except Exception as e: print(json.dumps("
                       "traceback.format_exception_only(type(e), e)[-1]))\n")
    out = subprocess.check_output([scope['scope']['sys'].executable, '-I', str(wrapper)],
                                  cwd=root, env={'HOME': str(root), 'PATH': str(root)})
    records.append(dict(mode='console-exception', stage=r['stage'],
                        case=r.get('case'), line=json.loads(out)))
a.output.write_text(json.dumps(records, sort_keys=True) + '\n')
