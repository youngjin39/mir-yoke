"""Capture the pinned ontology parser's repr diagnostics in explicit scratch."""
import argparse
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--scratch', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
output = args.output.resolve()
root = args.scratch.resolve()
(root / 'home').mkdir(parents=True, exist_ok=False)
pin = '33feb31a64082b472ee908b2c7f72d74c946cecc'
source = root / 'ontology_check.py'
source.write_bytes(subprocess.check_output([
    'git', 'show', f'{pin}:plugins/mir-core/skills/ontology/scripts/ontology_check.py',
]))
os.chdir(root)
os.environ.update(HOME=str(root / 'home'), PATH='', PYTHONDONTWRITEBYTECODE='1')
sys.path[:] = [str(root)] + [p for p in sys.path if p and 'site-packages' not in p]
spec = importlib.util.spec_from_file_location('pinned_ontology', source)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
assert Path(module.__file__).resolve().is_relative_to(root)
for name, loaded in tuple(sys.modules.items()):
    if name == '__main__':
        continue  # This isolated capture driver; never imported by the reference.
    if getattr(loaded, '__file__', None):
        path = Path(loaded.__file__).resolve()
        assert path.is_relative_to(root) or path.is_relative_to(Path(sys.base_prefix))
spec.loader.exec_module(module)
sys.argv[0] = 'ontology_check.py'
records = []
for value in [r'C:\scratch\contract.json', "can't", 'both\'"quotes', '/scratch/contract.json']:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
            mock.patch('subprocess.run', side_effect=AssertionError('unexpected process')), \
            mock.patch('subprocess.Popen', side_effect=AssertionError('unexpected child')):
        try:
            module.main([value])
        except SystemExit as exc:
            code = exc.code
        else:
            raise AssertionError('expected parser refusal')
    assert code == 2 and stdout.getvalue() == ''
    assert f'invalid choice: {value!r} ' in stderr.getvalue()
    records.append(dict(value=value, repr=repr(value), exit=code,
                        stdout=stdout.getvalue(), stderr=stderr.getvalue()))
output.write_text(json.dumps(dict(pin=pin, records=records), indent=2) + '\n')
