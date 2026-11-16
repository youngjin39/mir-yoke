"""Pinned commit/refusal bytes, with test-only receipt/cleanup filesystem seams."""
import json
import shutil
import subprocess
from pathlib import Path

fixture = Path(__file__).with_name('generate_y_e18_p4.py').read_text()
scope = {'__file__': __file__}
exec(fixture.split('records = []')[0], scope)
a, binary, clock, transaction, selected = (scope[k] for k in
    ('a', 'binary', 'clock', 'transaction', 'selected'))
setup = fixture.split('    name = \'verify-\' + case\n', 1)[1].split('    prepare()\n', 1)[0]
seam = a.scratch.resolve()/'journal.dylib'
subprocess.run(['/usr/bin/clang', '-dynamiclib', '-Wall', '-Wextra', '-Werror',
    str(Path(__file__).with_name('e18_journal.c')), '-o', str(seam)], check=True)
cases = ['missing', 'mismatch', 'unverified', 'status-absent', 'journal-directory',
         'lock-directory', 'journal-gone', 'lock-gone', 'parent-swap', 'success']
records = []
for case in cases:
    if selected and selected != case:
        continue
    state = dict(scope, name='journal-' + case, route='applied', response='ready',
                 code=0, stdout=b'{"ready":true,"changed_paths":[]}', stderr=b'')
    exec('if True:\n' + setup, state)
    work, project, install, env, argv, prepare, snapshot, reference = (state[k] for k in
        ('work', 'project', 'install', 'env', 'argv', 'prepare', 'snapshot', 'reference'))
    env.update(DYLD_INSERT_LIBRARIES=f'{clock}:{seam}', E18_JOURNAL_ROOT=str(project),
               E18_JOURNAL_MODE=case, E18_TRANSACTION=transaction)
    outside = work/'outside'
    outside.mkdir()
    for name in ('slim-transaction.json', 'slim.lock', 'sentinel'):
        (outside/name).write_bytes(b'Outside must remain unchanged\n')
    sentinels = {p.name: list(p.read_bytes()) for p in outside.iterdir()}
    def snapshot_all(snapshot=snapshot, project=project, outside=outside):
        return dict(**snapshot(), directories=sorted(str(p.relative_to(project))
                    for p in project.rglob('*') if p.is_dir() and not p.is_symlink()),
                    outside={p.name: list(p.read_bytes()) for p in outside.iterdir()})
    prepare()
    out = reference(argv)
    (work/'reference-output.json').write_text(json.dumps(dict(exit=out.returncode,
        stdout=out.stdout.decode(), stderr=out.stderr.decode())))
    record = dict(case=case, exit=out.returncode, stdout=list(out.stdout),
                  stderr=list(out.stderr), **snapshot_all())
    receipt_path = project/('.mir-held' if case == 'parent-swap' else '.mir')
    saved = json.loads((receipt_path/'bootstrap-receipt.json').read_bytes())
    assert saved['status'] == 'ready' and not saved['errors'], (case, out)
    assert record['outside'] == sentinels, case
    if case in ('journal-directory', 'lock-directory', 'journal-gone', 'lock-gone',
                'parent-swap'):
        assert out.returncode == 1 and not out.stdout, (case, out)
        assert out.stderr.startswith((b'PermissionError:', b'FileNotFoundError:',
                                      b'NotADirectoryError:', b'OSError:')), (case, out)
    else:
        receipt = json.loads(out.stdout)
        assert not out.stderr and receipt['status'] == 'ready', (case, out)
        assert out.returncode == (0 if case == 'success' else 1), (case, out)
        reason = ('slim transaction was not verified before commit' if case in
                  ('unverified', 'status-absent') else
                  'slim commit cannot match the durable transaction journal')
        assert receipt['errors'] == ([] if case == 'success' else
                                    ['slim commit cleanup failed: ' + reason]), receipt
    assert 'provider-marker/retire.txt' not in record['files']
    assert record['files'][f'.mir{ "-held" if case == "parent-swap" else ""}'
                           f'/slim-quarantine/{transaction}/provider-marker/retire.txt']
    assert not (project/'.mir/memory.db').exists()
    records.append(record)
    a.output.write_text(json.dumps(records)+'\n')  # Frozen before native execution.
    if binary:
        if case == 'parent-swap':
            (project/'.mir').unlink()
        prepare()
        shutil.copy2(binary, install/'bin/mir')
        actual = subprocess.run([str(install/'bin/mir'), 'bootstrap', *argv], cwd=project,
            env=env, capture_output=True, check=False, timeout=30)
        replay = dict(case=case, exit=actual.returncode, stdout=list(actual.stdout),
                      stderr=list(actual.stderr), **snapshot_all())
        (work/'actual.json').write_text(json.dumps(replay)+'\n')
        assert replay == record, (case, [k for k in record if replay[k] != record[k]])
assert records
print(f'{len(records)} literal journal records' + (' replayed' if binary else ' frozen'))
