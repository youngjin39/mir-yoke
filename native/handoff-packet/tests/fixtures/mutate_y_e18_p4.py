"""Compiled implementation mutants, restored even when an assertion fails."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

repo, out = (Path(p).resolve() for p in sys.argv[1:3])
base = repo/'native/handoff-packet'
mutants = [
    ('ready', 'bootstrap_core_adoption.rs',
     'matches!(report["ready"], crate::python_json::Value::Bool(true))',
     '!matches!(report["ready"], crate::python_json::Value::Bool(false))', 'applied-truthy'),
    ('readonly', 'bootstrap_core_adoption.rs', 'evidence.len() == 2',
     'evidence.len() >= 2', 'applied-extra-evidence'),
    ('changes', 'bootstrap_core_adoption.rs', '.is_some_and(Vec::is_empty)',
     '.is_some()', 'applied-changed'),
    ('json', 'bootstrap_core_adoption.rs', 'capability status did not return JSON',
     'invalid JSON', 'applied-json'),
    ('object', 'bootstrap_core_adoption.rs', 'capability status did not return a JSON object',
     'invalid object', 'applied-array'),
    ('exit', 'bootstrap_core_adoption.rs', 'format!("exit {}", output.returncode)',
     'format!("status {}", output.returncode)', 'applied-exit'),
    ('strip', 'bootstrap_core_adoption.rs', 'crate::python_json::python_strip(&stderr).into()',
     'stderr.into()', 'applied-stderr'),
    ('already', 'bootstrap_core_adoption.rs', 'external CLI already-slim verification failed:',
     'external CLI verification failed:', 'already-missing'),
    ('rollback', 'bootstrap_core_adoption.rs',
     'confined_move(root, &destination, &source, host)',
     'Ok::<(), Error>(())', 'applied-false'),
    ('clean-env', 'bootstrap_process_host.rs', 'execute(request, true)',
     'execute(request, false)', 'applied-ready'),
]
env = dict(os.environ, CARGO_BUILD_JOBS='4', CARGO_TARGET_DIR=str(base/'target'))
assert env.get('RUSTUP_HOME') and env.get('CARGO_HOME')
cargo = shutil.which('cargo')
assert cargo
results = []
for name, file, old, new, case in mutants:
    path = base/'src/mir_cli'/file
    original = path.read_text()
    assert original.count(old) == 1, (name, original.count(old))
    try:
        path.write_text(original.replace(old, new))
        build = subprocess.run([cargo, 'build', '--offline', '--locked', '--bin', 'mir'],
            cwd=base, env=env, capture_output=True, timeout=120)
        (out/f'mutant-{name}-build.log').write_bytes(build.stdout+build.stderr)
        assert build.returncode == 0, (name, build.stderr)
        run = subprocess.run([str(repo/'.venv/bin/python'), '-I', '-X', 'utf8',
            str(base/'tests/fixtures/generate_y_e18_p4.py'), '--scratch', str(out/'mutation'),
            '--output', str(out/'mutation.json'), '--binary', str(base/'target/debug/mir'),
            '--case', case], cwd=out, env=env, capture_output=True, timeout=120)
        (out/f'mutant-{name}.log').write_bytes(run.stdout+run.stderr)
        assert run.returncode != 0 and b'AssertionError:' in run.stderr, (name, run)
        results.append(dict(mutant=name, killed=True, case=case, file=file, old=old, new=new))
        (out/'mutants.json').write_text(json.dumps(results, indent=2)+'\n')
        print(name, 'behavioral kill', flush=True)
    finally:
        path.write_text(original)
