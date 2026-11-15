"""Freeze owned exception classes and import/constructor/call ordering."""
import json
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e13.py").read_text().split("resources =")[0], scope)
a, root, packages = (scope[k] for k in ("a", "root", "packages"))
manager = root / "src/mir/core/capabilities/manager.py"
original = manager.read_text()
wrapper = root / "capture.py"
wrapper.write_text('''import sys, pathlib, sysconfig, json
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root/'src'), str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
try:
 from mir.cli import capability
 for name, module in list(sys.modules.items()):
  if name.split('.')[0] in PACKAGE_SET:
   paths = [module.__file__] if module.__file__ else module.__path__
   assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
 code = capability.main(['status', '--project-root', '.', '--json'])
 result = {'code': code}
except BaseException as e:
 result = {'class': type(e).__name__, 'message': str(e)}
pathlib.Path('result.json').write_text(json.dumps(result))
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
records = []
for stage, classes in [('import', ['ImportError', 'ModuleNotFoundError', 'OSError']),
                       ('init', ['CapabilityError', 'CapabilityConfigError', 'OddProviderError']),
                       ('call', ['CapabilityError', 'CapabilityConfigError',
                                 'OddProviderError', 'success'])]:
    for cls in classes:
        source = "from pathlib import Path\nclass OddProviderError(Exception): pass\n"
        source += ("def trace(s):\n with Path('trace').open('a') as f: f.write(s+'\\n')\n"
                   "trace('import')\n")
        fail = f"raise {cls}('refused')"
        if stage == 'import':
            source += fail + '\n'
        source += "class CapabilityManager:\n def __init__(self,*a,**kw):\n  trace('init')\n"
        source += f"  {fail if stage == 'init' else 'self.token = 73'}\n"
        source += " def status(self,*a,**kw):\n  trace('call')\n"
        body = fail if stage == 'call' and cls != 'success' else 'return dict(token=self.token)'
        source += f"  {body}\n"
        manager.write_text(original + '\n' + source)
        work = root / f'{stage}-{cls}'
        work.mkdir(exist_ok=True)
        out = subprocess.run([scope['sys'].executable, '-I', str(wrapper)], cwd=work,
                             env={'HOME': str(work), 'PATH': '/usr/bin:/bin'},
                             capture_output=True, check=True)
        result = json.loads((work / 'result.json').read_text())
        assert result == ({'code': 0} if cls == 'success' else
                          {'code': 1} if cls.startswith('Capability') else
                          {'class': cls, 'message': 'refused'})
        assert (json.loads(out.stdout)['token'] == 73) if cls == 'success' else not out.stdout
        assert out.stderr == (b'ERROR: refused\n' if cls.startswith('Capability') else b'')
        records.append(dict(stage=stage, source=source, result=result,
                            stdout=list(out.stdout), stderr=list(out.stderr),
                            trace=(work / 'trace').read_text()))
source = ("from pathlib import Path\nPath('trace').write_text('import\\n')\n"
          "import os\nos._exit(23)\n")
manager.write_text(original + '\n' + source)
work = root / 'transport'
work.mkdir(exist_ok=True)
out = subprocess.run([scope['sys'].executable, '-I', str(wrapper)], cwd=work,
                     env={'HOME': str(work), 'PATH': '/usr/bin:/bin'}, capture_output=True)
assert out.returncode == 23 and not out.stdout and not out.stderr
records.append(dict(stage='transport', source=source, reference_exit=23,
                    trace=(work / 'trace').read_text()))
for case, definition, raised, expected in [
    ('subclass', 'class DerivedCapabilityError(CapabilityError): pass',
     'DerivedCapabilityError', {'code': 1}),
    ('same-name', 'Unrelated = type("CapabilityError", (Exception,), {"__module__": "unrelated"})',
     'Unrelated', {'class': 'CapabilityError', 'message': 'refused'}),
]:
    source = ("from pathlib import Path\n" + definition + "\n"
              "Path('trace').write_text('import\\n')\n"
              "class CapabilityManager:\n"
              " def __init__(self,*a,**kw):\n"
              "  with Path('trace').open('a') as f: f.write('init\\n')\n"
              " def status(self,*a,**kw):\n"
              "  with Path('trace').open('a') as f: f.write('call\\n')\n"
              f"  raise {raised}('refused')\n")
    manager.write_text(original + '\n' + source)
    work = root / case
    work.mkdir(exist_ok=True)
    out = subprocess.run([scope['sys'].executable, '-I', str(wrapper)], cwd=work,
                         env={'HOME': str(work), 'PATH': '/usr/bin:/bin'},
                         capture_output=True, check=True)
    result = json.loads((work / 'result.json').read_text())
    assert result == expected and not out.stdout
    assert out.stderr == (b'ERROR: refused\n' if case == 'subclass' else b'')
    records.append(dict(stage='call', case=case, source=source, result=result,
                        stdout=list(out.stdout), stderr=list(out.stderr),
                        trace=(work / 'trace').read_text()))
a.output.write_text('[\n' + ',\n'.join(json.dumps(r, sort_keys=True) for r in records) + '\n]\n')
