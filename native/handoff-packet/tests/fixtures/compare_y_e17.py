"""Compare raw PC rounds, observing only validated project roots."""
import argparse
import ast
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--left', type=Path, required=True)
p.add_argument('--right', type=Path, required=True)
p.add_argument('--left-scratch', required=True)
p.add_argument('--right-scratch', required=True)
a = p.parse_args()
source = Path(__file__).with_name('generate_y_e17.py')
tree = ast.parse(source.read_text(encoding='utf-8'))
scope = {}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)],
                        type_ignores=[]), str(source), 'exec'), scope)
observe = scope['observe_capture_round']
left = observe(json.loads(a.left.read_bytes()), a.left_scratch)
right = observe(json.loads(a.right.read_bytes()), a.right_scratch)
assert left == right, 'independent captures differ outside validated project roots'
print('independent captures equal after validated structured root observation')
