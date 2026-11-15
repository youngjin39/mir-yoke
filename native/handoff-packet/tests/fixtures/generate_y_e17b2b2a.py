"""Lossless Manager results from isolated, pinned Python; additive records."""
import json
import shutil
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
base = Path(__file__).with_name("generate_y_e17b2b1b1.py").read_text()
exec(base.split("out = subprocess")[0], scope)
a, root, wrapper = (scope[k] for k in ("a", "root", "wrapper"))
prefix = wrapper.read_text().split("s = '\\x1c")[0].replace(
    "from mir.cli import bootstrap_adoption", "from mir.cli import capability, bootstrap")
manager = root / 'src/mir/core/capabilities/manager.py'
original = manager.read_text()
records = []
for case, expression in [
    ('rich', r"{'\ud800': '\udcff', r'\ud800': r'\udcff', 'é': '\x7f😀', "
             "'n': [float('inf'), float('-inf'), float('nan'), None, True, 1.5, 'Infinity']}"),
    ('scalar', "{'plain': [None, False, 17, 'NaN']}"),
    ('exception', r"CapabilityError('\ud800 literal \\ud800 é')"),
]:
    source = ("from pathlib import Path\nclass CapabilityManager:\n"
              " def __init__(self,*a,**kw): pass\n def status(self,*a,**kw):\n  "
              + ('raise ' if case == 'exception' else 'return ') + expression
              + "\n def sync(self,*a,**kw):\n  Path('.mir/capability-lock.json').write_text('{}')\n"
              "  return self.status()\n")
    manager.write_text(original + '\n' + source)
    for mode in ('status-compact', 'status-pretty', 'sync', 'activate'):
        work = root / (case + '-' + mode)
        if work.exists():
            shutil.rmtree(work)
        (work / '.mir').mkdir(parents=True, exist_ok=True)
        call = ("bootstrap._activate_capabilities(pathlib.Path.cwd(), 'code_app')"
                if mode == 'activate' else "capability.main(" + repr(
                    ['sync' if mode == 'sync' else 'status', '--project-root', '.']
                    + ([] if mode == 'status-pretty' else ['--json'])) + ")")
        wrapper.write_text(prefix + "import io, contextlib\nout,err=io.StringIO(),io.StringIO()\n"
                           "with contextlib.redirect_stdout(out), "
                           "contextlib.redirect_stderr(err):\n"
                           " value=" + call + "\nprint(json.dumps(dict(value=value, "
                           "stdout=list(out.getvalue().encode('utf-8','surrogatepass')), "
                           "stderr=list(err.getvalue().encode('utf-8','surrogatepass')))))\n")
        out = subprocess.check_output([scope['scope']['sys'].executable, '-I', str(wrapper)],
                                      cwd=work, env={'HOME': str(work), 'PATH': str(work)})
        result = json.loads(out)
        if mode == 'activate':
            assert result['value'][0] == 'failed'
            if case != 'exception':
                reason = 'capability lock requires source.commit and non-empty plugins'
                assert result['value'][1] == {'reason': reason}
        else:
            assert result['value'] == (1 if case == 'exception' else 0)
        if mode == 'activate':
            result['value'] = json.dumps(result['value'], sort_keys=True, separators=(',', ':'))
        records.append(dict(case=case, mode=mode, source=source, **result))
# Python JSON admission is frozen; private RPC schema refusal is derived from the native contract.
for wire in ['{}', '{"value":null,"error":null,"events":[],"extra":0}',
             '{"value":0,"value":1,"error":null,"events":[]}',
             *[json.dumps(dict(value=None, error=None, events=[e])) for e in
               [dict(stream='other', data=[]), dict(stream='stdout', data=[256]),
                dict(stream='stdout', data=[1.0]), dict(stream='stdout', data=[True]),
                dict(stream='stdout', data=[], extra=0)]],
             '{"value":null,"error":{"class":"X","message":null},"events":[]}']:
    wrapper.write_text(prefix + "print(json.dumps(json.loads(" + repr(wire) + ")))\n")
    out = subprocess.check_output([scope['scope']['sys'].executable, '-I', str(wrapper)],
                                  cwd=root, env={'HOME': str(root), 'PATH': str(root)})
    records.append(dict(mode='protocol', wire=wire, python_json=json.loads(out)))
a.output.write_text('[\n' + ',\n'.join(json.dumps(r, sort_keys=True) for r in records) + '\n]\n')
