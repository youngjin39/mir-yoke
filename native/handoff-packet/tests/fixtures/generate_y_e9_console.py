"""Capture the complete E9 console family; Windows records require a PC run."""
import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

assert sys.flags.isolated
assert sys.version_info[:2] == (3, 12), 'Use the pinned Python 3.12 venv'
p = argparse.ArgumentParser()
p.add_argument('--scratch', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.scratch.mkdir(parents=True, exist_ok=True)
records = []
for name, generator, flags in [
        ('y-e9', 'generate_y_e9.py', []),
        ('y-e10', 'generate_y_e9.py', ['--e10']),
        ('e10_constructor', 'generate_y_e10_constructor.py', []),
        ('y-e11', 'generate_y_e9.py', ['--e11']),
        ('y-e12a-parser', 'generate_y_e9.py', ['--e12a']),
        ('y-e12d-cli', 'generate_y_e10_constructor.py', ['--e12d-cli'])]:
    output = a.scratch / (name + '.json')
    subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).with_name(generator)),
                    '--scratch', str(a.scratch / name), '--output', str(output), *flags],
                   check=True)
    rows = json.loads(output.read_bytes())
    for row in rows:
        row['family'] = name
        # UTF-8 decoding in the child generator preserves CRLF. Keep a byte carrier
        # as well so transport/log sanitization cannot destroy non-ASCII evidence.
        for field in ('stdout', 'stderr'):
            row[field + '_b64'] = base64.b64encode(row[field].encode('utf-8')).decode('ascii')
    records.extend(rows)
expected = 213 if sys.platform == 'win32' else 239
assert len(records) == expected, (len(records), expected)
assert sum(r.get('env', {}).get('SSL_CERT_FILE') == 'notes'
           and ('FTS-only sync:' in r['stdout'] or r['exit'] == 1) for r in records) == 3
assert any('\u1c50' in r['argv'] for r in records)
a.output.write_text(json.dumps(dict(platform=sys.platform,
    reference_pin='5f8f69f94e09b64c5e4d07d329ed17797c35e6cb', records=records),
    separators=(',', ':')) + '\n', encoding='utf-8')
