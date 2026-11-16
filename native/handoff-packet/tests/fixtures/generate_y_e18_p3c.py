"""Freeze p3c with the isolated PyYAML 6.0.3 oracle acquired by p3b."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--scratch', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
assert sys.flags.isolated
root = a.scratch.resolve()
root.mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('generate_y_e18_p3b.py')),
                '--scratch', str(root), '--output', str(root/'p3b.json')], check=True)
rows = [dict(r, implemented=True) for r in json.loads((root/'p3b.json').read_text())
        if not r['implemented']]
for row in rows:
    row['route'] = 'value' if row['case'].startswith('constructor') else 'compose'
for name, data in {
    'utf8-start': b'\xff', 'utf8-tail': b'\xc3', 'utf8-continuation': b'\xc3x',
    'utf8-bom': b'\xef\xbb\xbf\xff', 'utf16-le-odd': b'\xff\xfea',
    'utf16-be-odd': b'\xfe\xffa', 'utf16-high': b'\xff\xfe\x00\xd8',
    'utf16-pair': b'\xfe\xff\xd8\x00\x00a', 'utf16-low': b'\xff\xfe\x00\xdc',
    'byte-control': b'\xef\xbb\xbf\x01', 'utf16-control': b'\xff\xfe\x01\x00',
}.items():
    rows.append(dict(case=name, bytes=list(data), route='compose', implemented=True))
for name, text, route in [
    ('scanner-key-eof', 'a: b\nc', 'compose'),
    ('scanner-explicit-key', 'a: ? b', 'compose'),
    ('scanner-alias', '* a', 'compose'),
    ('scanner-block-comment', '|  bad\n a', 'compose'),
    ('scanner-hex-second', '"\\x0G"', 'compose'),
    ('scanner-uri-second', '!<tag:%0G> x', 'compose'),
    ('constructor-bom', '\ufeff!unknown 한글', 'value'),
    ('constructor-standard', '!!unknown x', 'value'),
    ('constructor-sequence', '!unknown []', 'value'),
    ('constructor-key-map', '{{a: b}: c}', 'value'),
    ('precedence-parser', '[a}\n@', 'compose'),
    ('precedence-composer', '*missing\n@', 'compose'),
    ('precedence-directive', '%YAML 2.0\n---\n@', 'compose'),
    *[(f'recursion-{n}', '['*n+'0'+']'*n, 'compose') for n in (450, 451, 490, 600)],
    ('value-int', '!!int nope', 'value'), ('value-float', '!!float nope', 'value'),
    ('value-recursive', '&a [*a]', 'value'),
]:
    rows.append(dict(case=name, text=text, route=route,
                     implemented=name.startswith(('constructor', 'scanner'))))
wrapper = root/'oracle/capture-p3c.py'
wrapper.write_text('''import sys, sysconfig, pathlib, json
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
import yaml
assert yaml.__version__ == '6.0.3'
assert all(pathlib.Path(m.__file__).resolve().is_relative_to(root)
           for n,m in sys.modules.items() if n == 'yaml' or n.startswith('yaml.'))
rows = json.loads(sys.stdin.read())
assert yaml.safe_load('[]') == []
for r in rows:
    try: yaml.safe_load(bytes(r['bytes']) if 'bytes' in r else r['text'])
    except Exception as exc: r.update(error=type(exc).__name__, message=str(exc))
    else: r.update(error=None, message=None)
print(json.dumps(rows, ensure_ascii=True, separators=(',', ':')))
''')
run = subprocess.run([sys.executable, '-I', str(wrapper)], cwd=wrapper.parent,
    env=dict(HOME=str(root), PATH='/usr/bin:/bin'), input=json.dumps(rows).encode(),
    capture_output=True, check=True)
a.output.write_bytes(run.stdout)
print(f'{len(rows)} p3c records frozen; HOME={os.environ.get("HOME", "")}')
