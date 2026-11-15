"""Compile real diagnostic mutations and require behavioral replay failures."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

repo, out = (Path(p).resolve() for p in sys.argv[1:3])
base = repo/'native/handoff-packet'
env = dict(os.environ, CARGO_BUILD_JOBS='4', CARGO_TARGET_DIR=str(base/'target'))
assert env.get('RUSTUP_HOME') and env.get('CARGO_HOME')
cargo = shutil.which('cargo')
assert cargo
mutants = [
    ('class-only', 'mir_core/yaml.rs', 'message: lines.join("\\n")',
     'message: format!("invalid YAML ({class})")'),
    ('snippet', 'mir_core/yaml.rs', 'self.index - start > 36', 'self.index - start > 20'),
    ('context', 'mir_core/yaml.rs',
     '(start.line, start.column) != (mark.line, mark.column)',
     '(start.line, start.column) == (mark.line, mark.column)'),
    ('line', 'mir_core/yaml.rs', 'self.line + 1,', 'self.line + 2,'),
    ('token', 'mir_core/yaml.rs', 'Self::End => "<stream end>"', 'Self::End => "<end>"'),
    ('pointer', 'mir_core/yaml.rs', 'self.mark.index = self.pos;',
     'self.mark.index = self.pos.saturating_sub(1);'),
    ('public-route', 'mir_cli/bootstrap_adoption_phase2.rs', 'map_err(|e| e.message)?',
     'map_err(|e| e.message.replace("while", "during"))?'),
]
results = []
for name, file, old, new in mutants:
    path = base/'src'/file
    original = path.read_text()
    assert original.count(old) == 1, name
    try:
        path.write_text(original.replace(old, new))
        cmd = [cargo, 'test', '--offline', '--locked', '--test',
               'mir_core_yaml', 'frozen_marked_diagnostics']
        if name == 'public-route':
            build = subprocess.run([cargo, 'build', '--offline', '--locked', '--bin', 'mir'],
                cwd=base, env=env, capture_output=True, check=True)
            (out/'mutant-public-build.log').write_bytes(build.stdout+build.stderr)
            cmd = [str(repo/'.venv/bin/python'), '-I',
                str(base/'tests/fixtures/generate_y_e18_p3.py'), '--yaml-diagnostics',
                '--case', 'flow-sequence', '--scratch', str(out/'mutation'),
                '--output', str(out/'mutation.json'), '--binary', str(base/'target/debug/mir')]
        run = subprocess.run(cmd, cwd=base, env=env, capture_output=True, check=False)
        (out/f'mutant-{name}.log').write_bytes(run.stdout+run.stderr)
        assert run.returncode != 0 and (b'test result: FAILED' in run.stdout or
                                       b'AssertionError:' in run.stderr), (name, run)
        results.append(dict(mutant=name, killed=True))
        (out/'mutants.json').write_text(json.dumps(results)+'\n')
        print(name, 'behavioral kill', flush=True)
    finally:
        path.write_text(original)
