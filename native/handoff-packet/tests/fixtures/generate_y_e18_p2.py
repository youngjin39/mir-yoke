"""Y-E18 p2: identical realtime input, pinned Python capture, literal public replay."""
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

binary = None
if '--binary' in sys.argv:
    index = sys.argv.index('--binary')
    binary = Path(sys.argv.pop(index + 1)).resolve()
    sys.argv.pop(index)
scope = {'__file__': __file__}
exec(Path(__file__).with_name('generate_y_e13.py').read_text().split('resources =')[0], scope)
a, oracle, packages = (scope[k] for k in ('a', 'root', 'packages'))
assert sys.platform == 'darwin'
repo = Path(__file__).resolve().parents[4]
clock = a.scratch.resolve() / 'clock.dylib'
env = dict(os.environ)
rustc = shutil.which('rustc')
assert rustc and env.get('RUSTUP_HOME')  # COMMON's preinstalled, offline toolchain.
subprocess.run([rustc, '+1.99.1', '--edition', '2024',
                '--crate-type', 'cdylib', str(Path(__file__).with_name('e18_clock.rs')),
                '-o', str(clock)], env=env, check=True)
fractional = clock.with_name('fractional.dylib')
subprocess.run([rustc, '+1.99.1', '--edition', '2024',
                '--crate-type', 'cdylib', '--cfg', 'fractional',
                str(Path(__file__).with_name('e18_clock.rs')), '-o', str(fractional)],
               env=env, check=True)
# Native transport only; the reference never imports this newer RPC adapter.
shutil.copy2(repo/'src/mir/cli/capability_manager_bridge.py', oracle/'src/mir/cli')
provider = '''
from pathlib import Path
class CapabilityManager:
    def __init__(self, project_root, **kw):
        assert project_root == Path.cwd() and not any(v is not None for v in kw.values())
    def sync(self, profile, **kw):
        assert profile == 'code_app' and kw == {'apply': True}
        Path('.mir/capability-lock.json').write_text(LOCK)
        return {'ready': True}
    def finalize(self, **kw):
        assert kw == {'apply': True, 'after_restart': True}
        return {}
'''.replace('LOCK', repr(json.dumps(dict(schema_version=1, source={'commit': 'a'*40},
                                       plugins={'mir-core': {}}, agents={}, profile='code_app',
                                       registration={'status': 'active'}))))
manager = oracle/'src/mir/core/capabilities/manager.py'
manager.write_text(manager.read_text() + provider)
wrapper = oracle/'capture_p2.py'
wrapper.write_text('''import sys, pathlib, sysconfig, socket, runpy, time
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root/'src'), str(root), stdlib, str(pathlib.Path(stdlib)/'lib-dynload')]
if sys.argv[1] != 'bridge': assert time.time() in (1700000000, 1700000000.123456)
def forbidden(*a, **kw): raise AssertionError('network forbidden')
from mir.cli import bootstrap
from mir.core.engine.memory import store
from mir.cli import context
socket.socket = forbidden
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
if sys.argv[1] == 'bridge':
    sys.argv = ['bridge', sys.argv[-1]]
    runpy.run_module('mir.cli.capability_manager_bridge', run_name='__main__')
    raise SystemExit
if sys.argv[1] == 'seed':
    db = pathlib.Path.cwd()/'.mir/synthetic.sqlite'
    c = store.connect(db)
    store.apply_migrations(c.conn)
    c.conn.execute('CREATE TABLE sentinel(value TEXT)')
    c.conn.execute("INSERT INTO sentinel VALUES ('copied original pages')")
    c.conn.commit()
    c.conn.close()
    raise SystemExit(context.main(['sync', '--db', str(db), '--project-root',
                                  str(db.parent.parent)]))
try: code = bootstrap.main(sys.argv[1:])
except Exception as exc:
    print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
    code = 1
raise SystemExit(code)
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
source = json.dumps(dict(schema_version=1, source=dict(url='https://example.invalid/provider',
                                                     ref='refs/heads/main'),
                         plugins={'mir-core': dict(path='plugins/mir-core')},
                         profiles=dict(packs={'code_app': ['mir-core']})))
config = '''[memory]
enabled = true
required = true
backend = "sqlite_fts5"
db_path = ".mir/synthetic.sqlite"
vector_mode = "off"
[[memory.external_archives]]
slug = "sample-docs"
root = "archive"
mode = "indexed"
glob_include = ["**/*.md"]
'''
records = []
cases = ['allow-new', 'allow-existing', 'restart-new', 'restart-existing', 'skip-refused',
         'doctor-refused', 'stage-refused', 'allow-fractional', 'stage-swap', 'ready-receipt']
for name in cases:
    work = a.scratch.resolve()/name
    if work.exists():
        shutil.rmtree(work)
    project, install, tools = (work/p for p in ['project', 'install', 'tools'])
    project.mkdir(parents=True)
    tools.mkdir()
    venv.EnvBuilder(with_pip=False, symlinks=True).create(install/'venv')
    (install/'bin').mkdir()
    python = install/'venv/bin/python'
    shim = install/'bin/python'
    shim.write_text(f'#!/bin/sh\nif [ "$1" = -I ]; then exec "{python}" "$@"; fi\n'
                    f'exec "{python}" -I -X utf8 "{wrapper}" bridge "$@"\n')
    shim.chmod(0o755)
    for tool in ['git', 'jq', 'bash']:
        path = tools/tool
        path.write_text('#!/bin/sh\nexit 1\n')
        path.chmod(0o755)
    env = dict(HOME=str(work), PATH=str(tools), PYTHONUTF8='1',
               DYLD_INSERT_LIBRARIES=str(fractional if name == 'allow-fractional' else clock))
    initial = {p: b'' for p in ['CLAUDE.md', 'AGENTS.md', '.codex/config.toml',
               '.ai-harness/deny-list.yaml', '.claude/agents/main-orchestrator.md',
               '.codex/agents/main-orchestrator.toml', '.claude/hooks/test.sh']}
    initial.update({p: b'{}' for p in ['.codex/hooks.json', 'config/sub-agent-policy.json',
                   'config/adopter-boundary.json', 'config/adopter-payload.json']})
    initial.update({'config/capability-sources.json': source.encode(),
                    '.claude/settings.json': b'{"hooks":{"Test":[]}}',
                    'harness_a.toml': config.encode(),
                    'archive/source.md': b'# Synthetic archive\nSearchable parity evidence.\n'})
    def reset(project=project, initial=initial, name=name):
        shutil.rmtree(project)
        project.mkdir()
        for relative, body in initial.items():
            path = project/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        if name == 'stage-swap':
            (project/'.mir/db-parent').mkdir(parents=True)
        if name == 'stage-refused':
            (project/'.mir').mkdir(exist_ok=True)
            (project/'.mir/block').write_bytes(b'blocked parent')
    def files(project=project):
        result = {}
        for path in sorted(project.rglob('*')):
            if path.is_file():
                data = bytearray(path.read_bytes())
                # COMMON: SQLite version stamp alone is excluded from physical comparison.
                if data.startswith(b'SQLite format 3\0'):
                    data[96:100] = b'\0'*4
                result[str(path.relative_to(project))] = list(data)
        return result
    def reference(argv, python=python, project=project, env=env):
        return subprocess.run([str(python), '-I', '-X', 'utf8', str(wrapper), *argv],
                              cwd=project, env=env, capture_output=True, timeout=30, check=False)
    reset()
    if name.endswith('existing'):
        out = reference(['seed'])
        assert out.returncode == 0 and not out.stderr, out
        initial['.mir/synthetic.sqlite'] = (project/'.mir/synthetic.sqlite').read_bytes()
    elif name == 'stage-refused':
        initial['harness_a.toml'] = config.replace(
            '.mir/synthetic.sqlite', '.mir/block/db').encode()
    elif name == 'stage-swap':
        initial['harness_a.toml'] = config.replace('.mir/synthetic.sqlite',
                                                   '.mir/db-parent/db').encode()
        outside = work/'outside'
        outside.mkdir()
        (outside/'sentinel').write_bytes(b'outside must stay unchanged')
        git = tools/'git'
        git.write_text('#!/bin/sh\nif [ \"$1 $2\" = \"rev-parse HEAD\" ]; then\n'
                       '/bin/mv .mir/db-parent .mir/db-parent-saved\n'
                       f'/bin/ln -s \"{outside}\" .mir/db-parent\nfi\nexit 1\n')
    elif name == 'doctor-refused':
        initial['archive/source.md'] = b''
    elif name == 'ready-receipt':
        # Narrow full-success receipt proof. Provider-owner slim is naturally not_applicable;
        # adopter transactions and the phase2/error matrix remain in split parts 3 and 4.
        initial['.mir/repo-profile.toml'] = b'''[repo]
slug = "mir-yoke"
repository_type = "public_harness_template"
purpose = "Synthetic portable project"
technology_stack = ["Rust"]
[execution]
non_code_profile = "code_app"
[gates]
requires_memory_store = true
requires_global_capabilities = true
'''
        initial['config/adopter-boundary.json'] = json.dumps(dict(
            schema_version=1, provider_markers=['provider-marker'], provider_text_markers=[],
            provider_owners=[])).encode()
        initial['.mir/bootstrap-receipt.json'] = b'{"status":"restart_required"}'
        initial['.mir/capability-lock.json'] = json.dumps(dict(
            schema_version=1, source={'commit': 'a'*40}, plugins={'mir-core': {}},
            profile='code_app', agents={}, registration={'status': 'active'})).encode()
        outputs = ['spec/STATE.md', 'spec/index.yaml', 'spec/graph.yaml', 'spec/gaps.yaml']
        for path, body in zip(outputs, ['Complete synthetic architecture.\n',
                'requirements: [{id: r1, status: ready}]\n',
                'nodes: [{id: r1}]\nedges: []\n', 'gaps: []\n'], strict=True):
            initial[path] = body.encode()
        coverage = {layer: dict(total=n, filled=n, derived=0, na=0, tbd=0)
                    for layer, n in [('l1', 1), ('l2', 1), ('l3', 9), ('l4', 10)]}
        coverage['ai_ready'] = dict(ready=1, incomplete=0, blocked=0)
        initial['spec/bootstrap-evidence.json'] = json.dumps(dict(
            schema_version=2, sequence=['mir-core:design', 'mir-core:spec-architect'],
            capability_commit='a'*40, outputs=outputs, coverage=coverage, open_gaps=0,
            full_review={k: 'pass' for k in ['project_structure', 'memory', 'discoverability',
                                           'requirements', 'organization']})).encode()
    reset()
    argv = ['--project-root', str(project), '--profile', 'code_app', '--slug', 'sample',
            '--purpose', 'Synthetic portable project', '--stack', 'Rust', '--json']
    if name == 'ready-receipt':
        argv.extend(['--finalize', '--architecture-initialized'])
    elif not name.startswith('restart'):
        argv.append('--skip-capability-activation')
    if name != 'skip-refused':
        argv.append('--allow-incomplete')
    out = reference(argv)
    def links(project=project):
        return {str(p.relative_to(project)): os.readlink(p) for p in project.rglob('*')
                if p.is_symlink()}
    record = dict(links=links(), case=name, exit=out.returncode, stdout=list(out.stdout),
                  stderr=list(out.stderr), files=files())
    records.append(record)
    a.output.write_text(json.dumps(records) + '\n')
    if name.startswith(('allow', 'restart', 'ready')):
        assert out.returncode == 0 and not out.stderr, (name, out)
        receipt = json.loads(out.stdout)
        assert receipt['status'] == ('ready' if name == 'ready-receipt' else
            'restart_required' if name.startswith('restart') else 'incomplete')
        if name == 'ready-receipt':
            assert receipt['slim']['status'] == 'not_applicable'
            assert receipt['architecture_initialization']['attested'] is True
        assert receipt['platform']['python'] == '.'.join(map(str, sys.version_info[:3]))
        assert receipt['errors'] == [] and receipt['memory']['round_trip'] == 'ok'
        assert receipt['memory']['documents_indexed'] == 1
        assert '.mir/synthetic.sqlite' in record['files']
        assert not list(project.glob('.mir/.memory.bootstrap.*'))
        assert 'docs/memory-map.md' in record['files'] and 'tasks/lessons.md' in record['files']
    else:
        assert out.returncode != 0 and not out.stderr, (name, out)
    if name == 'stage-swap':
        assert (project/'.mir/db-parent').is_symlink()
        assert {p.name: p.read_bytes() for p in outside.iterdir()} == {
            'sentinel': b'outside must stay unchanged'}
    assert not (project/'.mir/memory.db').exists()
    if binary:
        reset()
        shutil.copy2(binary, install/'bin/mir')
        actual = subprocess.run([str(install/'bin/mir'), 'bootstrap', *argv], cwd=project,
                                env=env, capture_output=True, check=False, timeout=30)
        (work/'actual.json').write_text(json.dumps(dict(exit=actual.returncode,
            stdout=list(actual.stdout), stderr=list(actual.stderr), files=files())))
        assert links() == record['links']
        if name == 'stage-swap':
            assert {p.name: p.read_bytes() for p in outside.iterdir()} == {
                'sentinel': b'outside must stay unchanged'}
        assert actual.returncode == record['exit'], (name, actual)
        assert actual.stderr == bytes(record['stderr']), (name, actual.stderr)
        assert actual.stdout == bytes(record['stdout']), (name, 'stdout', actual.stdout)
        assert files() == record['files'], (name, 'files', [p for p in files()
                                                         if files()[p] != record['files'].get(p)])
print(f'{len(records)} literal phase1 memory records' + (' replayed' if binary else ' frozen'))
