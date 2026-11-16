"""Freeze numeric constructor diagnostics with pin 5f8f69f's PyYAML 6.0.3."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

p = argparse.ArgumentParser()
p.add_argument('--scratch', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
assert sys.flags.isolated
repo = Path(__file__).resolve().parents[4]
root = a.scratch.resolve()/'oracle'
root.mkdir(parents=True, exist_ok=True)
pin = '5f8f69f94e09b64c5e4d07d329ed17797c35e6cb'
lock = subprocess.check_output(['/usr/bin/git', '-C', str(repo), 'show', f'{pin}:uv.lock'])
assert f'name = "pyyaml"\nversion = "{yaml.__version__}"'.encode() in lock
shutil.copytree(Path(yaml.__file__).parent, root/'yaml', dirs_exist_ok=True)
rows = []
for tag, values in {
    'int': ['nope', '+N_oPe', '-nope', '0b102', '-0bNOPE', '0xNOPE', '+0x', '09',
            '0bad', '-', '', '___', '1:bad:wrong', '1::2', 'a\'b"c', '한글\t\n',
            'x'*240, '  nope  ', '\u00a0nope', '123', '-0x10', '077', '1:02:03'],
    'float': ['nope', '-N_OPE', '+BAD', '1eNOPE', '-', '', '___', '1:BAD:WRONG',
              '1::2', 'A\'B"C', '한글\t\n', 'X'*240, '  NoPe  ', '\u00a0NoPe',
              '1.5', '-1_2.5', '1:02.5'],
}.items():
    for index, value in enumerate(values):
        rows.append(dict(case=f'{tag}-{index}', text=f'!!{tag} {json.dumps(value)}'))
rows.extend([dict(case='int-index', text='requirements: [!!int nope]', path='spec/index.yaml'),
             dict(case='float-graph', text='nodes: [!!float NOPE]', path='spec/graph.yaml'),
             dict(case='int-digit-limit', text='!!int "'+'9'*4301+'"')])
for tag, values in {
    'int': ['1:١٢:BAD', '1:\u00a0१२\u3000:BAD', '\u00a0１２\u2007',
            '0x١٢', '0٧', '0b١٠', '\x1c١٢', '²'],
    'float': ['1:١٢:BAD', '1:\u00a0१२.٥\u2007:BAD', '\u202f१२.٥\u3000',
              '-١٢.٥', '\x1f١٢', '²',
              *[':'.join(['0']*n) for n in (173, 174, 175, 176)],
              ':'.join(['1']+['0']*173), ':'.join(['0']*175+['BAD'])],
}.items():
    for index, value in enumerate(values):
        rows.append(dict(case=f'closing-{tag}-{index}', text=f'!!{tag} {json.dumps(value)}'))
for name, value in [('unicode-int', '!!int "1:١٢:BAD"'),
                    ('unicode-float', '!!float "1:١٢:BAD"'),
                    ('overflow', '!!float "'+':'.join(['0']*175)+'"')]:
    for path in ['spec/index.yaml', 'spec/graph.yaml']:
        rows.append(dict(case=f'closing-{name}-{Path(path).stem}', text=value, path=path))
wrapper = root/'capture.py'
wrapper.write_text('''import sys, sysconfig, pathlib, json
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
import yaml
assert yaml.__version__ == '6.0.3'
assert all(pathlib.Path(m.__file__).resolve().is_relative_to(root)
           for n,m in sys.modules.items() if n == 'yaml' or n.startswith('yaml.'))
assert yaml.safe_load('[]') == []
rows = json.loads(sys.stdin.read())
for r in rows:
    try: value = yaml.safe_load(r['text'])
    except Exception as exc: r.update(error=type(exc).__name__, message=str(exc))
    else: r.update(error=None, message=None, value=value)
print(json.dumps(rows, ensure_ascii=True, separators=(',', ':')))
''')
run = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(wrapper)], cwd=root,
    env=dict(HOME=str(root), PATH='/usr/bin:/bin'), input=json.dumps(rows).encode(),
    capture_output=True, check=True)
a.output.write_bytes(run.stdout)
print(f'{len(rows)} pinned numeric constructor records frozen')
