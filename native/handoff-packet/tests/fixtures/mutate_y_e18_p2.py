"""One production implementation mutation at a time, always restored."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

repo, out = (Path(p).resolve() for p in sys.argv[1:3])
base = repo/'native/handoff-packet'
mutants = [
    ('zero-fraction', 'mir_cli/bootstrap_main_host.rs',
     'now.replace(".000000+00:00", "+00:00")', 'now.to_owned()'),
    ('nonzero-fraction', 'mir_cli/bootstrap_main_host.rs',
     'now.replace(".000000+00:00", "+00:00")',
     'now.split(\'.\').next().unwrap_or(now).to_owned() + "+00:00"'),
    ('not-directory', 'mir_core/config/loader.rs',
     'io::ErrorKind::NotFound | io::ErrorKind::NotADirectory', 'io::ErrorKind::NotFound'),
    ('exists-errno', 'mir_cli/bootstrap_adoption.rs',
     '("FileExistsError", 17, "File exists")', '("FileExistsError", 20, "Not a directory")'),
    ('backup', 'mir_cli/bootstrap_memory.rs', 'if !db_path.exists() {', 'if true {'),
    ('db-publication', 'mir_cli/bootstrap_main.rs', 'if staged_db {', 'if false {'),
    ('projections', 'mir_cli/bootstrap_main.rs', 'in projection_updates {',
     'in projection_updates.into_iter().take(0) {'),
    ('allowed', 'mir_cli/bootstrap_main.rs',
     'let mut allowed = unique_errors.is_empty() && allow && skip;',
     'let mut allowed = unique_errors.is_empty() && allow && !skip;'),
    ('restart', 'mir_cli/bootstrap_main.rs',
     '"restart_required"\n            } else', '"incomplete"\n            } else'),
    ('version', 'mir_cli/bootstrap_main.rs', '"python":python_version,',
     '"python":format!("{python_version}-mutant"),'),
    ('ready-version', 'mir_cli/bootstrap_main.rs', '"python":python_version,',
     '"python":if finalize {format!("{python_version}-mutant")} else {python_version},'),
]
env = dict(os.environ, CARGO_BUILD_JOBS='4',
           CARGO_TARGET_DIR=str(base/'target'))
cargo = shutil.which('cargo')
assert cargo and env.get('RUSTUP_HOME') and env.get('CARGO_HOME')
selection = sys.argv[3:]
results = json.loads((out/'mutants.json').read_text()) if selection else []
for name, file, old, new in mutants:
    if selection and name not in selection:
        continue
    path = base/'src'/file
    original = path.read_text()
    assert original.count(old) == 1, (name, original.count(old))
    try:
        path.write_text(original.replace(old, new))
        p = subprocess.run([cargo, 'test', '--offline', '--locked',
                            '--test', 'mir_entry_e18', 'public_bootstrap_phase1_memory_receipts'],
                           cwd=base, env=env, capture_output=True, timeout=120)
        log = p.stdout + p.stderr
        (out/f'mutant-{name}.log').write_bytes(log)
        assert p.returncode == 101 and b'test result: FAILED.' in log, (name, log[-2000:])
        assert b'AssertionError:' in log, name
        results.append(dict(mutant=name, killed=True, file=file, old=old, new=new))
        (out/'mutants.json').write_text(json.dumps(results, indent=2)+'\n')
        print(name, 'behavioral kill', flush=True)
    finally:
        path.write_text(original)
