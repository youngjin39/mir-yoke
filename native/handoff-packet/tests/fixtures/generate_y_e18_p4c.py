"""Interrupted recovery: isolated pinned capture before literal public replay."""
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def receipt_flags_guard(project):
    try:
        yield
    finally:
        receipt = project/'.mir/bootstrap-receipt.json'
        if receipt.is_file() and not receipt.is_symlink():
            os.chflags(receipt, 0)  # Drop guard: always clear scratch uchg, including RED.


fixture = Path(__file__).with_name('generate_y_e18_p4.py').read_text()
scope = {'__file__': __file__}
exec(fixture.split('records = []')[0], scope)
a, binary, clock, selected = (scope[k] for k in ('a', 'binary', 'clock', 'selected'))
wrapper = a.scratch.resolve()/'oracle/capture_p2.py'
# C input forces the native receipt tempfile's third-collision reseed to zero.
wrapper.write_text(wrapper.read_text().replace('try: code = bootstrap.main',
    "import tempfile, itertools\ntempfile._get_candidate_names = "
    "lambda: itertools.repeat('lAFSES')\ntry: code = bootstrap.main"))
setup = fixture.split("    name = 'verify-' + case\n", 1)[1].split('    prepare()\n', 1)[0]
manager = a.scratch.resolve()/'oracle/src/mir/core/capabilities/manager.py'
manager.write_text(manager.read_text() + '''
_finalize = CapabilityManager.finalize
def recovery_finalize(self, **kw):
    result = _finalize(self, **kw)
    import runpy
    runpy.run_path(str(Path.cwd().parent/'inject.py'))
    return result
CapabilityManager.finalize = recovery_finalize
''')
seam = a.scratch.resolve()/'recovery.dylib'
subprocess.run(['/usr/bin/clang', '-dynamiclib', '-Wall', '-Wextra', '-Werror',
    str(Path(__file__).with_name('e18_recovery.c')), '-o', str(seam)], check=True)
cases = ['clean', 'stale-lock', 'invalid-lock', 'unicode-lock', 'live-lock', 'live-journal',
         'committed', 'rollback', 'receipt-missing', 'receipt-json', 'receipt-unreadable',
         'receipt-array',
         'receipt-directory', 'receipt-immutable', 'receipt-link', 'receipt-mismatch',
         'receipt-slim-array',
         'partial', 'quarantine-link', 'restore-link', 'restore-file', 'move-failure',
         'source-swap', 'parent-swap', 'cleanup-journal', 'cleanup-lock', 'lock-link',
         'journal-link', 'journal-directory', 'journal-json', 'journal-shape',
         'publish-rollback', 'publish-partial', 'publish-source-swap', 'publish-parent-swap']
records = []
for case in cases:
    if selected and selected != case:
        continue
    publication = case.startswith('publish-')
    state = dict(scope, name='recovery-' + case,
                 route='applied' if publication else 'already', response='ready',
                 code=0, stdout=b'{"ready":true,"changed_paths":[]}', stderr=b'')
    exec('if True:\n' + setup, state)
    work, project, install, env, argv, prepare, snapshot, reference = (state[k] for k in
        ('work', 'project', 'install', 'env', 'argv', 'prepare', 'snapshot', 'reference'))
    outside = work/'outside'
    outside.mkdir()
    for name in ('a.txt', 'b.txt', 'retire.txt', 'slim.lock', 'slim-transaction.json', 'sentinel'):
        (outside/name).write_bytes(b'Outside must remain unchanged\n')
    sentinels = {p.name: list(p.read_bytes()) for p in outside.iterdir()}
    moves = work/'moves.jsonl'
    env.update(DYLD_INSERT_LIBRARIES=f'{clock}:{seam}', E18_RECOVERY_ROOT=str(project),
               E18_RECOVERY_MODE=case, E18_RECOVERY_MOVES=str(moves),
               E18_TRANSACTION=scope['transaction'])
    # Fake provider only: executes identically in the pinned call and native RPC.
    (work/'inject.py').write_text('''import json, os
from pathlib import Path
root = Path.cwd()
assert root == Path(__ROOT__)
case = __CASE__
mir = root/'.mir'
outside = root.parent/'outside'
journal = mir/'slim-transaction.json'
lock = mir/'slim.lock'
receipt = mir/'bootstrap-receipt.json'
transaction = 'c'*32
quarantine = mir/'slim-quarantine'/transaction
paths = ['restored/already.txt', 'restore/a.txt', 'restore/b.txt']
if case not in ('clean', 'stale-lock', 'invalid-lock', 'unicode-lock', 'live-lock'):
    quarantine.mkdir(parents=True)
    journal.write_text(json.dumps(dict(transaction_id=transaction, paths=paths,
                                     pid=424243 if case == 'live-journal' else 2147483647)))
    lock.write_text('2147483647')
    for relative in paths:
        path = (root if relative.startswith('restored/') else quarantine)/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('Recovery ' + relative + '\\n').encode())
    receipt.write_text(json.dumps(dict(status='incomplete')))
elif case != 'clean':
    lock.write_bytes(b'424243' if case == 'live-lock' else b'bad' if case == 'invalid-lock'
                     else b'\\xff' if case == 'unicode-lock' else b'2147483647')
if case == 'committed':
    receipt.write_text(json.dumps(dict(status='ready', slim=dict(transaction_id=transaction))))
elif case == 'receipt-mismatch':
    receipt.write_text(json.dumps(dict(status='ready', slim=dict(transaction_id='d'*32))))
elif case == 'receipt-slim-array':
    receipt.write_text('{"status":"ready","slim":[]}')
elif case == 'receipt-missing': receipt.unlink()
elif case == 'receipt-json': receipt.write_text('{')
elif case == 'receipt-array': receipt.write_text('[]')
elif case in ('receipt-link', 'receipt-directory'):
    receipt.unlink()
    if case == 'receipt-link': receipt.symlink_to(outside/'sentinel')
    else: receipt.mkdir()
elif case == 'partial':
    # Reverse order restores b, then records two distinct ambiguities, retaining state.
    path = root/'restore/a.txt'
    path.parent.mkdir()
    path.write_bytes(b'Both present\\n')
    (root/paths[0]).unlink()
elif case == 'quarantine-link':
    path = quarantine/'restore/a.txt'
    path.unlink()
    path.symlink_to(outside/'a.txt')
elif case in ('restore-link', 'restore-file'):
    path = root/'restore'
    if case == 'restore-link': path.symlink_to(outside)
    else: path.write_bytes(b'Blocked restore parent\\n')
elif case == 'lock-link':
    lock.unlink()
    lock.symlink_to(outside/'slim.lock')
elif case in ('journal-link', 'journal-directory'):
    journal.unlink()
    if case == 'journal-link': journal.symlink_to(outside/'slim-transaction.json')
    else: journal.mkdir()
elif case == 'journal-json': journal.write_text('{')
elif case == 'journal-shape': journal.write_text('{"paths":[]}')
if case == 'receipt-immutable':
    import stat
    os.chflags(receipt, stat.UF_IMMUTABLE)  # Real chflags uchg, scratch only.
    assert receipt.stat().st_flags & stat.UF_IMMUTABLE
'''.replace('__ROOT__', repr(str(project))).replace('__CASE__', repr(case)))
    if publication:
        (work/'inject.py').write_text('pass\n')
    def snapshot_all(snapshot=snapshot, project=project, outside=outside, moves=moves,
                     case=case):
        receipt = project/'.mir/bootstrap-receipt.json'
        mode = receipt.stat().st_mode & 0o777 if case == 'receipt-unreadable' else None
        if mode is not None:
            receipt.chmod(0o600)  # Observe bytes, then restore the exact unreadable mode.
        try:
            contents = snapshot()
        finally:
            if mode is not None:
                receipt.chmod(mode)
        return dict(**contents, directories=sorted(str(p.relative_to(project))
                    for p in project.rglob('*') if p.is_dir() and not p.is_symlink()),
                    outside={p.name: list(p.read_bytes()) for p in outside.iterdir()},
                    moves=moves.read_text().splitlines() if moves.exists() else [])
    prepare()
    state['observe'].touch()
    with receipt_flags_guard(project):
        out = reference(argv)
    record = dict(case=case, exit=out.returncode, stdout=list(out.stdout),
                  stderr=list(out.stderr), **snapshot_all())
    (work/'reference-output.json').write_text(json.dumps(dict(exit=out.returncode,
        stdout=out.stdout.decode(), stderr=out.stderr.decode())))
    assert record['outside'] == sentinels, case
    assert not (project/'.mir/memory.db').exists()
    # Reference assertions establish the input's intended reachability before freezing.
    success = case in ('clean', 'stale-lock', 'invalid-lock', 'unicode-lock', 'committed',
                      'rollback', 'receipt-missing', 'receipt-json',
                      'receipt-mismatch', 'receipt-slim-array')
    uncaught = case in ('receipt-array', 'receipt-unreadable', 'cleanup-journal', 'cleanup-lock')
    assert out.returncode == (0 if success else 1), (case, out)
    if uncaught:
        assert not out.stdout and out.stderr, (case, out)
    else:
        assert not out.stderr, (case, out)
        receipt = json.loads(out.stdout)
        assert receipt['status'] == ('ready' if success else 'incomplete'), receipt
        if publication:
            assert receipt['slim']['status'] == 'applied', receipt
            assert receipt['errors'][0].startswith('bootstrap receipt publish failed: '), receipt
            assert len(receipt['errors']) == (2 if case == 'publish-partial' else 1), receipt
            assert (project/'.mir/slim.lock').exists() == (case == 'publish-partial')
            assert 'provider-marker/retire.txt' in record['files'] or case == 'publish-parent-swap'
        elif case == 'receipt-immutable':
            assert receipt['errors'][0].startswith(
                'bootstrap receipt publish failed: [Errno 1] Operation not permitted:'), receipt
        elif not success:
            assert receipt['errors'][0].startswith('adopter slim failed: '), receipt
    if case == 'partial':
        assert record['files']['restore/b.txt']
        assert '.mir/slim-transaction.json' in record['files']
        assert 'restore/a.txt: ambiguous rollback state; restored/already.txt: ambiguous' in (
            receipt['errors'][0]), receipt
    if case in ('rollback', 'receipt-unreadable', 'receipt-immutable'):
        assert record['moves'] == ['b.txt', 'a.txt'], record['moves']
        assert record['files']['restore/a.txt'] and record['files']['restore/b.txt']
    records.append(record)
    a.output.write_text(json.dumps(records)+'\n')  # Frozen BEFORE native execution.
    if binary:
        prepare()
        state['observe'].touch()
        moves.unlink(missing_ok=True)
        shutil.copy2(binary, install/'bin/mir')
        with receipt_flags_guard(project):
            actual = subprocess.run([str(install/'bin/mir'), 'bootstrap', *argv], cwd=project,
                env=env, capture_output=True, check=False, timeout=30)
        replay = dict(case=case, exit=actual.returncode, stdout=list(actual.stdout),
                      stderr=list(actual.stderr), **snapshot_all())
        (work/'actual.json').write_text(json.dumps(replay)+'\n')
        assert replay == record, (case, [k for k in record if replay[k] != record[k]])
assert records
print(f'{len(records)} literal recovery records' + (' replayed' if binary else ' frozen'))
