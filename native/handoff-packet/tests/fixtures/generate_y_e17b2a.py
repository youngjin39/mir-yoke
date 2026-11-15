"""Freeze text redirection and inherited fd output at the pinned Python boundary."""
import json
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e13.py").read_text().split("resources =")[0], scope)
a, root, packages = (scope[k] for k in ("a", "root", "packages"))
wrapper = root / "capture.py"
wrapper.write_text('''import sys, pathlib, sysconfig, json, socket, subprocess
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root/'src'), str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
from mir.cli import bootstrap, capability
for name, module in list(sys.modules.items()):
 if name.split('.')[0] in PACKAGE_SET:
  paths = [module.__file__] if module.__file__ else module.__path__
  assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
def forbidden(*a, **kw): raise AssertionError('external action forbidden')
socket.socket = subprocess.Popen = forbidden
r = json.loads(sys.argv[1])
namespace = {}
exec(r['source'], namespace)
capability.CapabilityManager = namespace['CapabilityManager']
work = pathlib.Path.cwd()
if r['mode'] == 'activate': value = bootstrap._activate_capabilities(work, 'code_app')
elif r['mode'] == 'finalize':
 value = bootstrap._finalize_capabilities(work, {'status':'restart_required'})
elif r['mode'] == 'import': value = None
else: value = capability.main(['sync','--profile','code_app','--project-root','.',
                               '--apply','--json'])
(work/'result.json').write_text(json.dumps(value))
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
records = []
text = "print('A',end=''); print('B',end='',file=sys.stderr); "
for mode, case, body in [
        ('activate', 'interleaved', text + "print('C',end='')"),
        ('activate', 'grouped', "print('AC',end=''); print('B',end='',file=sys.stderr)"),
        ('activate', 'raw', "os.write(1,b'A')"),
        ('activate', 'text', "print('A',end='')"),
        ('console', 'constructor-buffering', "os.write(1,b'B')"),
        ('console', 'streams', "print('A',end='',flush=True); os.write(2,b'B'); os.write(1,b'C')"),
        ('import', 'streams', ''), ('import', 'activate', ''), ('import', 'finalize', ''),
        ('finalize', 'streams', text + "os.write(1,b'C')")]:
    prefix = "import sys,os\nfrom mir.core.capabilities.manager import CapabilityError\n"
    source = prefix + ("print('I',end=''); os.write(2,b'J')\n" if mode == 'import' else '')
    init = "print('A',end='')" if case == 'constructor-buffering' else 'pass'
    source += f"class CapabilityManager:\n def __init__(self,*a,**kw): {init}\n"
    source += " def sync(self,*a,**kw):\n  " + body + "\n"
    source += "  raise CapabilityError('refused')\n finalize = sync\n"
    work = root / f'{mode}-{case}'
    work.mkdir(exist_ok=True)
    r = dict(mode=mode, case=case, source=source)
    out = subprocess.run([scope['sys'].executable, '-I', str(wrapper), json.dumps(r)],
                         cwd=work, env={'HOME': str(work), 'PATH': '/usr/bin:/bin'},
                         capture_output=True, check=True)
    merged = subprocess.run([scope['sys'].executable, '-I', str(wrapper), json.dumps(r)],
                            cwd=work, env={'HOME': str(work), 'PATH': '/usr/bin:/bin'},
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    records.append(r | dict(stdout=list(out.stdout), stderr=list(out.stderr),
                            merged=list(merged.stdout),
                            value=json.loads((work / 'result.json').read_text())))
assert records[0]['value'][1]['reason'] == 'ABCERROR: refused'
assert records[1]['value'][1]['reason'] == 'ACBERROR: refused'
assert records[2]['stdout'] == [65] and records[2]['value'][1]['reason'] == 'ERROR: refused'
assert records[3]['stdout'] == [] and records[3]['value'][1]['reason'] == 'AERROR: refused'
assert records[4]['merged'] == list(b'BERROR: refused\nA')
a.output.write_text('[\n' + ',\n'.join(json.dumps(r, sort_keys=True) for r in records) + '\n]\n')
