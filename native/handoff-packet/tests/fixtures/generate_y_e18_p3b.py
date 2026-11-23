"""Freeze diagnostics using the isolated PyYAML version locked by pin 5f8f69f."""
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
cases = {
    'flow-sequence': '[broken\n', 'empty-flow': '[', 'flow-mapping': '{a: 1\n',
    'flow-mismatch': '[a}', 'map-mismatch': '{a: 1]', 'comma-node': '[,]',
    'block-node': ']', 'block-sequence': '- [a]\n  b',
    'block-mapping': 'a:\n  b: c\n d: e', 'undefined-tag': '!e!x a',
    'tag-after-anchor': '&a !e!x b', 'undefined-alias': '*missing',
    'duplicate-anchor': '[&a x, &a y]', 'documents': '---\na\n---\nb',
    'document-start': 'a\n...\nb', 'directive-start': '%YAML 1.1\na',
    'duplicate-yaml': '%YAML 1.1\n%YAML 1.2\n---\na',
    'incompatible-yaml': '%YAML 2.0\n---\na',
    'duplicate-tag': '%TAG !e! tag:example:\n%TAG !e! tag:other:\n---\na',
    'unicode-marks': '---\n[\ud55c\uae00, {a: 1]\n',
    'crlf-marks': '---\r\n[one, two\r\n',
    'break-marks': '---\x85[one, two\u2028',
    'long-snippet': '[' + 'x'*90 + ', ' + 'y'*90 + '}',
    'bom-marks': '\ufeff[\ud55c\uae00}',
}
# These routes are measured, frozen, and explicitly deferred in measure.md.
deferred = {'scanner-character': '@', 'scanner-key': 'a: 1\nb\nc: 2',
    'scanner-entry': 'a: - b', 'scanner-value': 'a: b: c',
    'scanner-anchor': '& a', 'scanner-quote': '"unterminated',
    'scanner-escape': '"\\q"', 'scanner-hex': '"\\xGG"',
    'scanner-block-zero': '|0\n a', 'scanner-block-tail': '|x\n a',
    'scanner-tag': '!<tag\n', 'scanner-uri': '!<tag:%GG> x',
    'scanner-directive': '%YAML x\n---\na', 'reader-control': 'a\x01',
    'constructor-tag': '!unknown x', 'constructor-key': '{[a]: b}'}
wrapper = root/'capture.py'
wrapper.write_text('''import sys, sysconfig, pathlib, json
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
import yaml
assert all(pathlib.Path(m.__file__).resolve().is_relative_to(root)
           for n, m in sys.modules.items() if n == 'yaml' or n.startswith('yaml.'))
rows = []
for name, text, implemented in json.loads(sys.stdin.read()):
    try: yaml.safe_load(text)
    except yaml.YAMLError as exc:
        rows.append(dict(case=name, text=text, implemented=implemented,
                         error=type(exc).__name__, message=str(exc)))
    else: raise AssertionError((name, 'expected failure'))
print(json.dumps(rows, ensure_ascii=True, separators=(',', ':')))
''')
inputs = [(k, v, True) for k, v in cases.items()] + [
          (k, v, False) for k, v in deferred.items()]
out = subprocess.run([sys.executable, '-I', str(wrapper)], cwd=root,
    env=dict(HOME=str(root), PATH='/usr/bin:/bin'), input=json.dumps(inputs).encode(),
    capture_output=True, check=False)
assert out.returncode == 0, out.stderr.decode()
a.output.write_bytes(out.stdout)
print(f'{len(inputs)} pinned diagnostics frozen')
