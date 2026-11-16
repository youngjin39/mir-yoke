"""Compile recovery implementation mutants; every RED is a literal-byte failure."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

repo, out = (Path(p).resolve() for p in sys.argv[1:3])
base = repo/'native/handoff-packet'
core = 'bootstrap_core_adoption.rs'
mutants = [
    ('snapshot-filename', 'bootstrap_main.rs',
     'crate::mir_cli::changes::snapshot_project_with_error(root, authored::io_error)',
     'crate::mir_cli::changes::snapshot_project(root).map_err(|e| authored::io_error(root, e))',
     'receipt-unreadable'),
    ('publish-no-rollback', 'bootstrap_main.rs',
     'let rollback_error = match host.rollback_adopter_slim(&root, &slim_report) {',
     'let rollback_error = match Ok::<(), Error>(()) {', 'publish-rollback'),
    ('publish-lost-error', 'bootstrap_main.rs', 'if let Some(error) = rollback_error {',
     'if let Some(error) = None::<String> {', 'publish-partial'),
    ('skip-recovery', core, '    recover(&root, host)?;', '', 'rollback'),
    ('live-journal', core, 'if process_alive(&journal["pid"], host)? {',
     'if false {', 'live-journal'),
    ('ready-receipt', core, 'if receipt["status"] == "ready"',
     'if receipt["status"] == "invalid"', 'committed'),
    ('receipt-json', core, 'Err(error) if caught_json(&error) => json!({}),',
     'Err(error) if caught_json(&error) => json!([]),', 'receipt-json'),
    ('reverse-order', core, '        .iter()\n        .rev()\n',
     '        .iter()\n', 'partial'),
    ('already-restored', core, 'if source_present && !destination_present {',
     'if false {', 'rollback'),
    ('ambiguous', core, 'if source_present || !destination_present {',
     'if source_present && !destination_present {', 'partial'),
    ('unsafe-quarantine', core, 'else if !safe_file(root, &destination) {',
     'else if false {', 'quarantine-link'),
    ('move-error', core, '.err()\n                .map(|e| e.message)',
     '.err()\n                .and_then(|_e| None)', 'move-failure'),
    ('recovery-cleanup', core,
     '        unlink(root, &root.join(JOURNAL))?;\n        unlink(root, &root.join(LOCK))?;',
     '        unlink(root, &root.join(JOURNAL))?;', 'rollback'),
    ('replace-filenames', 'bootstrap.rs',
     '''            .map_err(|e| {
                let mut error = authored::io_error(source, e);
                error.message.push_str(&format!(
                    " -> {}",
                    crate::executor_execute::repr(&destination.to_string_lossy())
                ));
                error
            })''',
     '            .map_err(|e| authored::io_error(destination, e))', 'receipt-directory'),
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
            str(base/'tests/fixtures/generate_y_e18_p4c.py'), '--scratch', str(out/'mutation'),
            '--output', str(out/'mutation.json'), '--binary', str(base/'target/debug/mir'),
            '--case', case], cwd=out, env=env, capture_output=True, timeout=120)
        (out/f'mutant-{name}.log').write_bytes(run.stdout+run.stderr)
        assert run.returncode != 0 and b'AssertionError:' in run.stderr, (name, run)
        results.append(dict(mutant=name, killed=True, case=case, file=file, old=old, new=new))
        (out/'mutants.json').write_text(json.dumps(results, indent=2)+'\n')
        print(name, 'behavioral kill', flush=True)
    finally:
        path.write_text(original)
