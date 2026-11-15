"""Additive capability carrier observations from the isolated pinned bootstrap."""
import json
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e17.py").read_text().split("# Inputs")[0], scope)
a, root, wrapper = (scope[k] for k in ("a", "root", "wrapper"))
mix = '\x1c \udcff literal \\udcff \ud800 é\x1f'
lock = dict(schema_version=1, source={'commit': 'a' * 40}, profile=mix,
            plugins={mix: {}, 'a': {}, '\U00010000': {}}, agents=[mix, 'a', '\U00010000'],
            registration={'status': 'active', 'note': mix})
cases = [dict(mode=mode, case='mixed', code=7, out=mix, err='\ud800',
              prior={'status': 'restart_required'}) for mode in ('activate', 'finalize')]
cases += [dict(mode=mode, case='lock', lock=lock, prior={'status': 'restart_required'})
          for mode in ('activate', 'finalize', 'lock')]
wrapper.write_text(wrapper.read_text().replace(
    "'provider refused'", "r.get('error', 'provider refused')"))
cases.append(dict(mode='console', case='console-error', error='provider\r\nrefused\r',
                  argv=['sync', '--profile', 'code_app', '--project-root', '.', '--json',
                        '--apply']))
records = []
for i, case in enumerate(cases):
    work = root / f'carrier-{i}'
    (work / '.mir').mkdir(parents=True, exist_ok=True)
    files = {'.mir/capability-lock.json': json.dumps(case['lock'])} if 'lock' in case else {}
    for name, body in files.items():
        (work / name).write_text(body)
    out = subprocess.run([scope['scope']['sys'].executable, '-I', str(wrapper), json.dumps(case)],
                         cwd=work, env={'HOME': str(work), 'PATH': '/usr/bin:/bin'},
                         capture_output=True, check=True)
    assert not out.stderr
    result = json.loads(out.stdout.replace(str(work).encode(), b'{ROOT}'))
    if case['mode'] != 'console':
        assert result['result']['value'][0] == ('ready' if files else 'failed')
    else:
        assert result['stderr'] == 'ERROR: provider\r\nrefused\r\n'
    records.append(case | dict(files=files, **result))
a.output.write_text(json.dumps(records, sort_keys=True) + '\n')
