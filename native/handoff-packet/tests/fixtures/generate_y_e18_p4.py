"""Applied adopter verification: pinned capture before literal public replay."""
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

selected = None
if '--case' in sys.argv:
    i = sys.argv.index('--case')
    selected = sys.argv.pop(i + 1)
    sys.argv.pop(i)
# Reuse the existing isolated archive, clock, provider and ready architecture inputs.
fixture = Path(__file__).with_name('generate_y_e18_p3.py').read_text()
scope = {'__file__': __file__}
exec(fixture[:fixture.index("cases = ['ready'")], scope)
a, binary, clock, wrapper = (scope[k] for k in ('a', 'binary', 'clock', 'wrapper'))
setup = fixture.split('for name in cases:\n', 1)[1].split(
    '    reset(initial)\n    out = reference(argv)', 1)[0]
setup = '\n'.join(line[4:] if line.startswith('    ') else line for line in setup.split('\n'))
transaction = hashlib.sha256(
    b'SystemTime { tv_sec: 1700000000, tv_nsec: 0 }-424242-0').hexdigest()[:32]
# Input seam, never output rewriting: the pinned uuid4 caller receives the same
# synthetic transaction identity as the native clock/pid source. RNG is unasserted.
wrapper.write_text(wrapper.read_text().replace('try: code = bootstrap.main',
    'import uuid\nuuid.uuid4 = lambda: uuid.UUID(hex=' + repr(transaction) + ')\n'
    'try: code = bootstrap.main'))
inputs = a.scratch.resolve()/'adopter.dylib'
subprocess.run(['/usr/bin/clang', '-dynamiclib', '-Wall', '-Wextra', '-Werror',
    str(Path(__file__).with_name('e18_adopter.c')), '-o', str(inputs)], check=True)
clock = f'{clock}:{inputs}'
responses = {
    'ready': (0, b'{"ready":true,"changed_paths":[]}', b''),
    'read-only': (0, b'{"ready":true,"change_evidence":'
                  b'{"status":"not-applicable","reason":"read-only-operation"}}', b''),
    'changed': (0, b'{"ready":true,"changed_paths":["x"]}', b''),
    'extra-evidence': (0, b'{"ready":true,"change_evidence":'
                       b'{"status":"not-applicable","reason":"read-only-operation","x":1}}', b''),
    'truthy': (0, b'{"ready":1,"changed_paths":[]}', b''),
    'false': (0, b'{"ready":false,"changed_paths":[]}', b''),
    'missing': (0, b'{"ready":true}', b''),
    'json': (0, b'{', b''),
    'array': (0, b'[]', b''),
    'stderr': (7, b'ignored', b'\x1c synthetic refusal \x1f'),
    'exit': (7, b'ignored', b' \t\n'),
    'bad-stdout': (0, b'\xff', b''),
    'bad-stderr': (0, b'{"ready":true,"changed_paths":[]}', b'\xff'),
    'spawn': (0, b'', b''),
}
records = []
cases = [(route, case, row) for route in ('applied', 'already')
         for case, row in responses.items()]
for route, response, (code, stdout, stderr) in cases:
    case = route + '-' + response
    if selected and selected != case:
        continue
    name = 'verify-' + case
    case_scope = dict(scope, name=name, clock=clock)
    exec(setup, case_scope)
    work, project, install, tools, python, env, initial, argv, reset, files, reference = (
        case_scope[k] for k in ('work', 'project', 'install', 'tools', 'python', 'env',
                               'initial', 'argv', 'reset', 'files', 'reference'))
    initial['.mir/repo-profile.toml'] = initial['.mir/repo-profile.toml'].replace(
        b'slug = "mir-yoke"', b'slug = "sample"\nprofile_base_commit = "' +
        b'b'*40 + b'"').replace(b'public_harness_template', b'code_app')
    initial['config/adopter-boundary.json'] = json.dumps(dict(schema_version=1,
        provider_markers=['provider-marker'], provider_text_markers=[], provider_owners=[],
        payload_manifest='config/adopter-payload.json')).encode()
    body = b'Unmodified provider payload\n'
    if route == 'applied':
        initial['provider-marker/retire.txt'] = body
    initial['config/adopter-payload.json'] = json.dumps(dict(schema_version=1, files=[dict(
        path='provider-marker/retire.txt', sha256=hashlib.sha256(body).hexdigest(),
        disposition='remove')])).encode()
    # Embed the frozen release controls in the Git shim as exact stdout bytes.
    git_script = ['#!/bin/sh', 'case "$1 $2" in']
    for control in ['config/adopter-boundary.json', 'config/adopter-payload.json']:
        command = shlex.quote(f"show {'b'*40}:{control}")
        frozen = shlex.quote(initial[control].decode('ascii'))
        git_script.append(f'{command}) printf %s {frozen};;')
    git_script.extend(['*) exit 1;;', 'esac', ''])
    (tools/'git').write_text('\n'.join(git_script))
    cli = install/'external'
    observe = work/'observations.jsonl'
    external = work/'external.py'
    external.write_text('''import sys, os, json
from pathlib import Path
project = Path.cwd()
assert project == Path(__PROJECT__)
assert sys.stdin.buffer.read() == b''
row = dict(argv=sys.argv[1:], cwd=str(project),
           environment={k: os.environ.get(k) for k in
                        ['PYTHONPATH', 'VIRTUAL_ENV', 'UV_PROJECT_ENVIRONMENT']},
           payload_present=(project/'provider-marker/retire.txt').exists(),
           journal=list((project/'.mir/slim-transaction.json').read_bytes())
                   if (project/'.mir/slim-transaction.json').exists() else None,
           lock=(project/'.mir/slim.lock').read_text()
                if (project/'.mir/slim.lock').exists() else None)
with Path(OBSERVE).open('a') as f: f.write(json.dumps(row) + '\\n')
if sys.argv[1:] == ['bootstrap', '--help']:
    if __SPAWN__: Path(__CLI__).unlink()
    raise SystemExit(0)
assert sys.argv[1:] == ['capability', 'status', '--project-root', str(project), '--json']
sys.stdout.buffer.write(STDOUT)
sys.stderr.buffer.write(STDERR)
raise SystemExit(CODE)
'''.replace('__PROJECT__', repr(str(project))).replace('OBSERVE', repr(str(observe)))
        .replace('STDOUT', repr(stdout)).replace('STDERR', repr(stderr))
        .replace('CODE', str(code)).replace('__SPAWN__', repr(response == 'spawn'))
        .replace('__CLI__', repr(str(cli))))
    cli_body = f'#!/bin/sh\nexec "{python}" -I -X utf8 "{external}" "$@"\n'
    cli.write_text(cli_body)
    cli.chmod(0o755)
    env.update(MIR_BOOTSTRAP_CLI_PATH=str(cli), PYTHONPATH='must-be-removed',
               VIRTUAL_ENV=str(install/'venv'), UV_PROJECT_ENVIRONMENT='must-be-removed')
    def snapshot(files=files, project=project, observe=observe):
        return dict(files=files(), links={str(p.relative_to(project)): os.readlink(p)
                    for p in project.rglob('*') if p.is_symlink()},
                    observations=list(observe.read_bytes()))
    def prepare(reset=reset, initial=initial, observe=observe, cli=cli, cli_body=cli_body):
        reset(initial)
        observe.unlink(missing_ok=True)
        cli.write_text(cli_body)
        cli.chmod(0o755)
    prepare()
    out = reference(argv)
    (work/'reference-output.json').write_text(json.dumps(dict(exit=out.returncode,
        stdout=out.stdout.decode(), stderr=out.stderr.decode())))
    assert observe.exists(), (case, out)
    record = dict(case=case, exit=out.returncode, stdout=list(out.stdout),
                  stderr=list(out.stderr), **snapshot())
    uncaught = route == 'already' and response in ('bad-stdout', 'bad-stderr', 'spawn')
    receipt = {} if uncaught else json.loads(out.stdout)
    success = response in ('ready', 'read-only')
    assert out.returncode == (0 if success else 1), (case, out)
    if uncaught:
        assert not out.stdout and out.stderr.startswith(
            b'FileNotFoundError:' if response == 'spawn' else b'UnicodeDecodeError:'), out
    else:
        assert not out.stderr, out
    if success:
        assert receipt['status'] == 'ready', receipt
        assert receipt['slim']['status'] == (
            'applied' if route == 'applied' else 'already_slim'), receipt
        if route == 'applied':
            assert receipt['slim']['removed'] == ['provider-marker/retire.txt']
            assert receipt['slim']['transaction_id'] == transaction
            assert record['files'][f'.mir/slim-quarantine/{transaction}/provider-marker/retire.txt']
        assert 'provider-marker/retire.txt' not in record['files']
    elif not uncaught:
        assert receipt['slim']['status'] == 'not_run', receipt
        if response not in ('bad-stdout', 'bad-stderr', 'spawn'):
            detail = 'post-slim' if route == 'applied' else 'already-slim'
            assert f'external CLI {detail} verification failed:' in receipt['errors'][0], receipt
        else:
            assert ('No such file or directory' if response == 'spawn' else
                    'invalid start byte') in receipt['errors'][0], receipt
        if route == 'applied':
            assert receipt['errors'][0].endswith('; rollback complete'), receipt
            assert record['files']['provider-marker/retire.txt'] == list(body)
    assert not (project/'.mir/slim.lock').exists()
    assert not (project/'.mir/slim-transaction.json').exists()
    assert not (project/'.mir/memory.db').exists()
    observations = [json.loads(line) for line in observe.read_text().splitlines()]
    assert len(observations) == (1 if response == 'spawn' else 2)
    assert observations[0]['payload_present'] == (route == 'applied')
    if route == 'applied' and response != 'spawn':
        journal = json.loads(bytes(observations[1]['journal']))
        assert journal['pid'] == 424242 and journal['transaction_id'] == transaction
        assert journal['status'] == 'moving' and observations[1]['lock'] == '424242'
    if response != 'spawn':
        assert not observations[1]['payload_present']
    assert all(all(v is None for v in row['environment'].values()) for row in observations)
    records.append(record)
    a.output.write_text(json.dumps(records)+'\n')  # Freeze BEFORE the native replay.
    if binary:
        prepare()
        shutil.copy2(binary, install/'bin/mir')
        actual = subprocess.run([str(install/'bin/mir'), 'bootstrap', *argv], cwd=project,
            env=env, capture_output=True, check=False, timeout=30)
        replay = dict(case=case, exit=actual.returncode, stdout=list(actual.stdout),
                      stderr=list(actual.stderr), **snapshot())
        (work/'actual.json').write_text(json.dumps(replay)+'\n')
        assert replay == record, (case, [k for k in record if replay[k] != record[k]])
assert records
print(f'{len(records)} literal adopter verification records' +
      (' replayed' if binary else ' frozen'))
