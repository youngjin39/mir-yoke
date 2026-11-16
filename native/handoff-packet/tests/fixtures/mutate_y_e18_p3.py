"""Real implementation edits; each mutant must compile and fail literal public replay."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

repo, out = (Path(p).resolve() for p in sys.argv[1:3])
base = repo/'native/handoff-packet'
mutants = [
    ('flag', 'bootstrap_main.rs', 'if ns["architecture_initialized"] != true {', 'if false {'),
    ('attestation', 'bootstrap_main.rs', 'architecture_attested = result.0 == "ready";',
     'architecture_attested = false;'),
    ('prior', 'bootstrap_capabilities.rs', 'p["status"] == "restart_required"',
     'p["status"] == "ready"'),
    ('inactive', 'bootstrap_capabilities.rs', '!= Some("active")', '!= Some("pending")'),
    ('total', 'bootstrap_surfaces.rs', 'total != exact', 'total == exact'),
    ('sum', 'bootstrap_surfaces.rs', 'sum::<i128>() != total', 'sum::<i128>() == total'),
    ('tbd', 'bootstrap_surfaces.rs', 'if counts[4] != 0 {', 'if false {'),
    ('ai', 'bootstrap_surfaces.rs', '!equals_int(&ai_ready["blocked"], 0)',
     '!equals_int(&ai_ready["blocked"], 1)'),
    ('review', 'bootstrap_surfaces.rs', 'full_review[*key] != "pass"',
     'full_review[*key] != "fail"'),
    ('placeholder', 'bootstrap_surfaces.rs', 'if placeholder.is_match(',
     'if !placeholder.is_match('),
    ('gaps', 'bootstrap_surfaces.rs', '["resolved", "dismissed", "na"]',
     '["resolved", "dismissed", "open"]'),
    ('graph', 'bootstrap_surfaces.rs', 'doc["nodes"].as_array().is_none_or(Vec::is_empty)',
     'doc["nodes"].as_array().is_none()'),
    ('content-stale', 'bootstrap_main.rs', 'if refreshed != onboarding {', 'if false {'),
    ('content-miss', 'bootstrap_memory.rs', 'if passed { "pass" } else { "fail" }',
     'if passed { "pass" } else { "pass" }'),
    ('content-query', 'bootstrap_memory.rs', 'format!("{slug}-content")',
     'format!("{slug}-other")'),
    ('content-projection', 'bootstrap_content.rs',
     'globs.insert(format!("{relative}/**/*.{suffix}"));',
     'globs.insert(format!("{relative}/excluded/*.{suffix}"));'),
]
cases = {'attestation': 'ready', 'content-query': 'content-allow',
         'content-projection': 'content-generated', 'prior': 'prior-status', 'review': 'ready'}
env = dict(os.environ, CARGO_BUILD_JOBS='4', CARGO_TARGET_DIR=str(base/'target'))
assert env.get('RUSTUP_HOME') and env.get('CARGO_HOME')
cargo = shutil.which('cargo')
assert cargo
selection = sys.argv[3:]
results = json.loads((out/'mutants.json').read_text()) if selection else []
for name, file, old, new in mutants:
    if selection and name not in selection:
        continue
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
            str(base/'tests/fixtures/generate_y_e18_p3.py'), '--scratch', str(out/'mutation'),
            '--output', str(out/'mutation.json'), '--binary', str(base/'target/debug/mir'),
            '--case', cases.get(name, name)], cwd=out, env=env, capture_output=True, timeout=120)
        (out/f'mutant-{name}.log').write_bytes(run.stdout+run.stderr)
        assert run.returncode != 0 and b'AssertionError:' in run.stderr, (name, run)
        results.append(dict(mutant=name, killed=True, file=file, old=old, new=new))
        (out/'mutants.json').write_text(json.dumps(results, indent=2)+'\n')
        print(name, 'behavioral kill', flush=True)
    finally:
        path.write_text(original)
