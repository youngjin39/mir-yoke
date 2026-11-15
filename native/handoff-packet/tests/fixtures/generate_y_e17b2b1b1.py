"""Additive codec observations in the isolated pinned bootstrap environment."""
import json
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e13.py").read_text().split("resources =")[0], scope)
a, root, packages = (scope[k] for k in ("a", "root", "packages"))
wrapper = root / "codec.py"
wrapper.write_text(r'''import sys, pathlib, sysconfig, json
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root/'src'), str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
from mir.cli import bootstrap_adoption
for name, module in list(sys.modules.items()):
 if name.split('.')[0] in PACKAGE_SET:
  paths = [module.__file__] if module.__file__ else module.__path__
  assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
s = '\x1c \udcff literal \\udcff \ud800 é 😀\x1f'
v = {'z': [s, None, True, False, 1.5, float('inf'), float('-inf'), float('nan')],
     '\udcff': {}, '\\udcff': [], 'a': {'é': '\x7f\n"\\'}, '😀': 0}
r = dict(text=json.dumps(s), wtf8=list(s.encode('utf-8', 'surrogatepass')),
         points=list(map(ord, s)), strip=list(map(ord, s.strip())),
         concat=list(map(ord, s + '\ud800' + r'\ud800')), value=json.dumps(v),
         compact=json.dumps(v, sort_keys=True, separators=(',', ':')),
         pretty=json.dumps(v, sort_keys=True, indent=2), errors=[])
for b in [b'\xff', b'\xc2', b'a\xe2(\xa1']:
 try: b.decode('utf-8', 'surrogatepass')
 except UnicodeError as e: r['errors'].append(dict(bytes=list(b), message=str(e)))
print(json.dumps(r, sort_keys=True))
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
out = subprocess.check_output([scope['sys'].executable, '-I', str(wrapper)], cwd=root,
                              env={'HOME': str(root), 'PATH': '/usr/bin:/bin'})
assert json.loads(out)['points'][:3] == [28, 32, 56575]
a.output.write_bytes(out)
