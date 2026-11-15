"""Real rendering mutations: every promoted p3c row must fail behaviorally."""
import json
import os
import subprocess
import sys
from pathlib import Path

repo, out = (Path(s).resolve() for s in sys.argv[1:3])
base = repo/'native/handoff-packet'
out.mkdir(parents=True, exist_ok=True)
assert os.environ.get('RUSTUP_HOME') and os.environ.get('CARGO_HOME')
env = dict(os.environ, CARGO_TARGET_DIR=str(base/'target'), CARGO_BUILD_JOBS='4')
path = base/'src/mir_core/yaml.rs'
original = path.read_text()
mutants = [
    ('marked', 'message: lines.join("\\n")', 'message: format!("invalid YAML ({class})")',
     '--test', 'mir_core_yaml', 'frozen_deferred_diagnostics'),
    ('reader', 'unacceptable character #x{code:04x}', 'unacceptable character #x{code:02x}',
     '--test', 'mir_core_yaml', 'frozen_deferred_diagnostics'),
    ('constructor', 'message: lines.join("\\n")', 'message: format!("invalid YAML ({class})")',
     '--lib', '', 'frozen_constructor_diagnostics'),
]
results = []
covered = set()
for name, old, new, kind, target, test in mutants:
    assert original.count(old) == 1
    try:
        path.write_text(original.replace(old, new))
        cmd = ['cargo', 'test', '--offline', '--locked', kind, *([target] if target else []),
               test, '--', '--nocapture']
        run = subprocess.run(cmd, cwd=base, env=env, capture_output=True, check=False)
        log = run.stdout + run.stderr
        (out/f'mutant-{name}.log').write_bytes(log)
        assert run.returncode != 0 and b'test result: FAILED' in log, name
        rows = json.loads((base/'tests/fixtures/y_e18_p3c.json').read_text())
        killed = [r['case'] for r in rows if r['implemented'] and
                  f'"{r["case"]}":'.encode() in log]
        covered.update(killed)
        results.append(dict(mutant=name, cases=killed))
    finally:
        path.write_text(original)
assert covered == {r['case'] for r in rows if r['implemented']}, covered
(out/'mutants.json').write_text(json.dumps(results, indent=2)+'\n')
print(f'{len(mutants)} implementation mutants killed; {len(covered)} records covered')
