"""Freeze literal public bootstrap bytes at 5f8f69f, then replay at identical roots."""
import json
import shutil
import subprocess
import sys
import venv
from pathlib import Path

# Share the pinned archive/dependency isolation, never the live mir package.
binary = None
if '--binary' in sys.argv:
    index = sys.argv.index('--binary')
    binary = Path(sys.argv.pop(index + 1)).resolve()
    sys.argv.pop(index)
scope = {'__file__': __file__}
exec(Path(__file__).with_name('generate_y_e13.py').read_text().split('resources =')[0], scope)
a, oracle, packages = (scope[k] for k in ('a', 'root', 'packages'))
wrapper = oracle / 'bootstrap_capture.py'
wrapper.write_text('''import sys, pathlib, sysconfig, socket, os
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root/'src'), str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
from mir.cli import bootstrap
def forbidden(*a, **kw): raise AssertionError('network forbidden')
socket.socket = forbidden
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
# Install after startup: the pinned bootstrap observes this already-running venv.
if pth := os.environ.get('BOOTSTRAP_TEST_PTH'):
    pathlib.Path(pth).write_text("import builtins; print('startup .pth output')\\n")
try: code = bootstrap.main(sys.argv[1:])
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    code = 1
raise SystemExit(code)
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
source = json.dumps(dict(schema_version=1, source=dict(url='https://example.invalid/provider',
                                                     ref='refs/heads/main'),
                         plugins={'mir-core': dict(path='plugins/mir-core')},
                         profiles=dict(packs={p: ['mir-core'] for p in
                                              ['code_app', 'content_workspace']})))
cases = [('site-output', 'venv', None, 'code_app', []),
         ('prefix', 'venv', None, 'code_app', []),
         ('base', 'base', None, 'code_app', []),
         ('environment', 'base', 'copied', 'code_app', []),
         ('empty-environment', 'base', '', 'code_app', []),
         ('content', 'venv', None, 'content_workspace', []),
         ('content-finalize', 'venv', None, 'content_workspace', ['--finalize']),
         ('skip', 'venv', None, 'code_app', ['--skip-capability-activation']),
         ('allowed-text', 'venv', None, 'code_app',
          ['--skip-capability-activation', '--allow-incomplete'])]
records = []
for name, interpreter, virtual, profile, extra in cases:
    work = a.scratch.resolve() / name
    if work.exists():
        shutil.rmtree(work)
    project, install, tools = (work / p for p in ['project', 'install', 'tools'])
    project.mkdir(parents=True)
    tools.mkdir()
    if interpreter == 'venv':
        venv.EnvBuilder(with_pip=False, symlinks=True).create(install)
    else:
        (install / 'bin').mkdir(parents=True)
        (install / 'bin/python').symlink_to(sys._base_executable)
    for tool in ['git', 'jq', 'bash']:
        path = tools / tool
        path.write_text('#!/bin/sh\nexit 1\n')
        path.chmod(0o755)
    initial = {'config/capability-sources.json': source}
    if name == 'content':
        initial['notes.md'] = 'Existing project notes\n'
    def reset(project=project, initial=initial):
        shutil.rmtree(project)
        project.mkdir()
        for relative, body in initial.items():
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
    def files(project=project):
        return {str(p.relative_to(project)): list(p.read_bytes())
                for p in sorted(project.rglob('*')) if p.is_file()}
    env = dict(HOME=str(work), PATH=str(tools), PYTHONUTF8='1')
    if name == 'site-output':
        site = install / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}'
        env['BOOTSTRAP_TEST_PTH'] = str(site / 'site-packages' / 'observation.pth')
    if virtual is not None:
        env['VIRTUAL_ENV'] = virtual
    argv = ['--project-root', str(project), '--profile', profile, '--slug', 'sample',
            '--purpose', 'Synthetic portable project', '--stack', 'Rust', *extra]
    if name != 'allowed-text':
        argv.append('--json')
    reset()
    out = subprocess.run([str(install/'bin/python'), '-I', '-X', 'utf8', str(wrapper), *argv],
                         cwd=project, env=env, capture_output=True, check=False, timeout=30)
    assert b'startup .pth output' not in out.stdout
    receipt = json.loads((project/'.mir/bootstrap-receipt.json').read_bytes())
    assert out.returncode == (2 if profile == 'content_workspace' else 1) and not out.stderr, (
        name, out)
    assert receipt['platform']['python'] == '.'.join(map(str, sys.version_info[:3]))
    assert ('mir bootstrap must run from the copied uv tool environment' in receipt['errors']) == (
        interpreter == 'base' and not virtual)
    assert receipt['capabilities']['status'] == ('skipped' if name in ['skip', 'allowed-text']
                                               else 'not_run')
    assert not list(project.rglob('*.db'))  # No preflight case may open memory.
    record = dict(case=name, stdout=list(out.stdout), stderr=list(out.stderr),
                  exit=out.returncode, files=files())
    records.append(record)
    # Save reference bytes BEFORE native executes; no native-derived expectations.
    a.output.write_text(json.dumps(records) + '\n')
    if binary:
        reset()
        shutil.copy2(binary, install/'bin/mir')
        actual = subprocess.run([str(install/'bin/mir'), 'bootstrap', *argv], cwd=project,
                                env=env, capture_output=True, check=False, timeout=30)
        assert actual.returncode == record['exit'], (name, actual)
        assert actual.stderr == bytes(record['stderr']), (name, actual.stderr)
        assert actual.stdout == bytes(record['stdout']), (name, 'stdout', actual.stdout)
        assert files() == record['files'], (name, 'files')
print(f'{len(records)} literal reference records' + (' replayed' if binary else ' frozen'))
# Native-only observation adapter failures: real spawn/parser failures, not injected Errors.
for failure in ['missing', 'permission', 'format', 'nonzero', 'malformed']:
    work = a.scratch.resolve() / ('error-' + failure)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    (work/'config').mkdir()
    (work/'config/capability-sources.json').write_text(source)
    python = work/'python'
    if failure != 'missing':
        python.write_text({'format': 'invalid executable', 'nonzero': '#!/bin/sh\nexit 7\n',
                           'malformed': '#!/bin/sh\nprintf broken\n'}.get(failure, '#!/bin/sh\n'))
        python.chmod(0o644 if failure == 'permission' else 0o755)
    if failure in ['missing', 'permission']:
        try:
            subprocess.run([str(python)], cwd=work, check=False)
        except OSError as exc:
            expected = f'{type(exc).__name__}: {exc}\n'.encode()
        else:
            raise AssertionError('OS seam must fail')
    else:
        # Rust's exec fallback rejects this invalid shell body with status 127.
        # This adapter has no reference route: all nonzero child exits fail closed.
        reason = ('invalid Python runtime attestation' if failure == 'malformed' else
                  'Python runtime attestation failed: exit status: ' +
                  ('127' if failure == 'format' else '7'))
        expected = f'RuntimeError: {reason}\n'.encode()
    records.append(dict(case=failure, reachability='native-only', stdout=[], exit=1,
                        stderr=list(expected)))
    a.output.write_text(json.dumps(records) + '\n')
    if binary:
        shutil.copy2(binary, work/'mir')
        actual = subprocess.run([str(work/'mir'), 'bootstrap', '--project-root', str(work),
                                 '--profile', 'code_app', '--purpose', 'Synthetic project',
                                 '--stack', 'Rust', '--json'], cwd=work,
                                env=dict(HOME=str(work), PATH=str(tools)), capture_output=True,
                                check=False, timeout=30)
        assert (actual.returncode, actual.stdout, actual.stderr) == (1, b'', expected), (
            failure, actual)
        assert not (work/'.mir/bootstrap-receipt.json').exists()
print('5 native-only real failure seams' + (' replayed' if binary else ' recorded'))
