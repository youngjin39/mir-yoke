"""Capture pprint diagnostics through the pinned shipped payload schema."""
import json
import subprocess
import sys
from pathlib import Path

scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e16.py").read_text(), scope)
a, root, wrapper = (scope[k] for k in ("a", "root", "wrapper"))
schema = (root / 'config/adopter-payload.schema.json').read_text()
records = []
for case, classification in [
    ('long-string', 'word ' * 30),
    ('long-list', ['word ' * 20] * 8),
    ('nested-dict', {'outer': {'inner': ['word ' * 20, {'label': 'value ' * 20}]}}),
    ('unicode-long-string', '\ud55c\uae00 café 🙂 ' * 30),
]:
    work = root / case
    (work / 'config').mkdir(parents=True, exist_ok=True)
    document = json.dumps(dict(schema_version=1, **{'$schema': 's'},
                               generated_from='config/template-assets.json',
                               files=[dict(path='a', sha256='a' * 64,
                                           classification=classification, disposition='remove')]))
    (work / 'config/p.json').write_text(document)
    (work / 'config/s').write_text(schema)
    out = subprocess.run([sys.executable, '-I', str(wrapper), 'payload'],
                         cwd=work, env={'HOME': str(work), 'PATH': '/usr/bin:/bin'},
                         capture_output=True, check=True)
    assert not out.stderr, out.stderr
    result = json.loads(out.stdout.replace(str(work).encode(), b'{ROOT}'))
    assert result['class'] == 'SlimError', result
    assert "On instance['files'][0]['classification']:\n" in result['message'], result
    records.append(dict(mode='payload', case=case, document=document, schema=schema,
                        result=result))
a.output.with_name('y-e16c.json').write_text(
    '[\n' + ',\n'.join(json.dumps(r, sort_keys=True) for r in records) + '\n]\n')
