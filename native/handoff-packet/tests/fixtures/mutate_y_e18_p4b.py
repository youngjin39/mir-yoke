"""Behavioral RED witnesses: compile actual commit-path implementation edits."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

repo, out = (Path(p).resolve() for p in sys.argv[1:3])
base = repo/'native/handoff-packet'
mutants = [
    ('mismatch', 'bootstrap_core_adoption.rs',
     'slim commit cannot match the durable transaction journal',
     'slim commit missing journal', 'mismatch'),
    ('unverified', 'bootstrap_core_adoption.rs', 'if journal["status"] != "verified" {',
     'if journal["status"] == "invalid" {', 'unverified'),
    ('journal-cleanup', 'bootstrap_core_adoption.rs',
     'for path in [root.join(JOURNAL), root.join(LOCK)] {',
     'for path in [root.join(LOCK)] {', 'journal-directory'),
    ('lock-cleanup', 'bootstrap_core_adoption.rs',
     'for path in [root.join(JOURNAL), root.join(LOCK)] {',
     'for path in [root.join(JOURNAL)] {', 'lock-directory'),
    ('cleanup-message', 'bootstrap_main.rs', 'slim commit cleanup failed:',
     'slim commit failed:', 'missing'),
    ('cleanup-kind', 'bootstrap_main.rs',
     'if error.class != "SlimError" {\n            return Err(error);\n        }\n'
     '        unique_errors.push(format!("slim commit cleanup failed:',
     'if error.class != "PermissionError" {\n            return Err(error);\n        }\n'
     '        unique_errors.push(format!("slim commit cleanup failed:', 'lock-directory'),
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
            cwd=base, env=env, capture_output=True, timeout=180)
        (out/f'mutant-{name}-build.log').write_bytes(build.stdout+build.stderr)
        assert build.returncode == 0, (name, build.stderr)
        run = subprocess.run([str(repo/'.venv/bin/python'), '-I', '-X', 'utf8',
            str(base/'tests/fixtures/generate_y_e18_p4b.py'), '--scratch', str(out/'mutation'),
            '--output', str(out/'mutation.json'), '--binary', str(base/'target/debug/mir'),
            '--case', case], cwd=out, env=env, capture_output=True, timeout=120)
        (out/f'mutant-{name}.log').write_bytes(run.stdout+run.stderr)
        assert run.returncode != 0 and b'AssertionError:' in run.stderr, (name, run)
        results.append(dict(mutant=name, killed=True, case=case, file=file, old=old, new=new))
        (out/'mutants.json').write_text(json.dumps(results, indent=2)+'\n')
        print(name, 'behavioral kill', flush=True)
    finally:
        path.write_text(original)
