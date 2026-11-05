"""Test-only adapter reusing the immutable oracle, never recapturing it."""
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
from w1_golden import FIXTURES, expand, install, normalize, prepare, snapshot, stable_files

counts = {}
for record in json.loads((FIXTURES / 'records.json').read_text()):
    family = record['family']
    command = family.rsplit('/', 1)[-1].removesuffix('.sh')
    if command not in ('pre-compact', 'session-end', 'invocation_log'):
        continue
    with tempfile.TemporaryDirectory(prefix='checkpoint-') as tmp:
        root = Path(tmp)
        env = prepare(root)
        install(record['setup'], root)
        env.update({k: expand(v, root) for k, v in record['env'].items()})
        before = snapshot(root / 'project')
        args = [sys.argv[1], command]
        if command == 'invocation_log':
            args = [sys.argv[1], 'invocation-log', 'fixture', record['case']]
        result = subprocess.run(args, input=base64.b64decode(record['stdin']), env=env,
                                cwd=root / 'project', capture_output=True)
        after = snapshot(root / 'project')
        observed = dict(exit=result.returncode,
                        stdout=base64.b64encode(normalize(result.stdout, root)).decode(),
                        stderr=base64.b64encode(normalize(result.stderr, root)).decode(),
                        delta=stable_files({k: v for k, v in after.items() if before.get(k) != v}),
                        deleted=sorted(before.keys() - after.keys()))
        assert observed == record['expected'], (record['id'], observed, record['expected'])
        counts[family] = counts.get(family, 0) + 1
print(json.dumps(counts, sort_keys=True))

# Permission and bounded Git observations beyond the frozen unavailable-Git case.
with tempfile.TemporaryDirectory(prefix='checkpoint-focused-') as tmp:
    root = Path(tmp)
    env = prepare(root)
    git = root / 'tools/git'
    git.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/git-calls"\n'
                   'case "$3" in rev-parse) exit 0 ;; status) printf " M a\\n?? b\\n" ;; esac\n')
    git.chmod(0o755)
    project = root / 'project'
    target = project / 'tasks/handoffs/session-handoff-LATEST.md'
    target.parent.mkdir(parents=True)
    target.write_text('curated\n')
    target.chmod(0o640)
    result = subprocess.run([sys.argv[1], 'pre-compact'], env=env, capture_output=True)
    assert result.returncode == 0
    assert target.stat().st_mode & 0o777 == 0o600
    assert 'Working tree dirty (2 paths;' in target.read_text()
    assert (root / 'home/git-calls').read_text().splitlines() == [
        f'-C {project} rev-parse --is-inside-work-tree',
        f'-C {project} status --short --untracked-files=all']
    target.parent.chmod(0o555)
    try:
        result = subprocess.run([sys.argv[1], 'pre-compact'], env=env, capture_output=True)
        assert result.returncode == 0
        assert b'ERROR: Failed to refresh' in result.stdout
        assert target.read_text().startswith('curated\n')
    finally:
        target.parent.chmod(0o755)
