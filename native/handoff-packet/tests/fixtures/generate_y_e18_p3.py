"""Pinned phase2 and content routes; reuse p2's isolated acquisition/clock inputs."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

yaml_diagnostics = '--yaml-diagnostics' in sys.argv
if yaml_diagnostics:
    sys.argv.remove('--yaml-diagnostics')
yaml_cases = {r['case']: r['text'].encode() for r in json.loads(
    Path(__file__).with_name('y_e18_p3b.json').read_text()) if r['implemented']}
yaml_probe = '--yaml-probe' in sys.argv
if yaml_probe:
    sys.argv.remove('--yaml-probe')
selected = None
if '--case' in sys.argv:
    index = sys.argv.index('--case')
    selected = sys.argv.pop(index + 1)
    sys.argv.pop(index)
scope = {'__file__': __file__}
exec(Path(__file__).with_name('generate_y_e18_p2.py').read_text().split('records = []')[0], scope)
a, oracle, wrapper, binary, clock = (scope[k] for k in
                                     ('a', 'oracle', 'wrapper', 'binary', 'clock'))
provider = scope['provider'].replace(
    "profile == 'code_app'", "profile in ('code_app', 'content_workspace')")
provider = provider.replace("return {'ready': True}", """import json
        path = Path('.mir/capability-lock.json')
        lock = json.loads(path.read_text())
        lock['profile'] = profile
        path.write_text(json.dumps(lock))
        return {'ready': True}""")
provider = provider.replace("return {}", """path = Path('provider-mode')
        mode = path.read_text() if path.exists() else ''
        if mode == 'error': raise CapabilityError('synthetic finalize refusal')
        if mode == 'inactive':
            import json
            path = Path('.mir/capability-lock.json')
            lock = json.loads(path.read_text())
            lock['registration']['status'] = 'pending'
            path.write_text(json.dumps(lock))
        return {}""")
scope['manager'].write_text(scope['manager'].read_text() + provider)
source = json.loads(scope['source'])
source['profiles']['packs']['content_workspace'] = ['mir-core']
cases = ['ready', 'flag', 'prior', 'prior-status', 'inactive', 'error', 'missing', 'linked',
         'json', 'schema', 'sequence', 'commit', 'outputs', 'coverage', 'row', 'counts',
         'total', 'sum', 'tbd', 'ai', 'review', 'output-missing', 'output-empty',
         'placeholder', 'gaps', 'gap-shape', 'index', 'graph',
         'content-allow', 'content-restart', 'content-ready', 'content-stale', 'content-miss',
         'content-generated']
if yaml_probe:  # Original p3 gap; also covered by --yaml-diagnostics after p3b.
    cases = ['gap-json']
if yaml_diagnostics:
    cases = list(yaml_cases)
if selected:
    assert selected in cases, selected
    cases = [selected]
records = []
reasons = {
    'flag': '--finalize requires --architecture-initialized',
    'prior': 'requires a prior restart_required',
    'prior-status': 'requires a prior restart_required',
    'inactive': 'capability activation lock is not active', 'error': 'capability status exited 1',
    'missing': 'architecture evidence is missing', 'linked': 'architecture evidence is missing',
    'json': 'architecture evidence or capability lock is invalid',
    'schema': 'schema_version must be 2', 'sequence': 'must record design then spec-architect',
    'commit': 'capability_commit does not match', 'outputs': 'must list the required spec outputs',
    'coverage': 'must contain four-layer spec coverage', 'row': 'coverage is missing l2',
    'counts': 'counts must be non-negative integers', 'total': 'l3.total must be exactly 9',
    'sum': 'counts do not sum to total', 'tbd': 'still contains TBD requirements',
    'ai': 'all requirements must be AI-ready', 'review': 'passing full project review',
    'output-missing': 'architecture output is missing or linked',
    'output-empty': 'architecture output is empty', 'placeholder': 'output contains placeholder',
    'gaps': 'contains 1 open gap(s)', 'gap-shape': 'must contain a gaps list',
    'gap-json': 'while parsing a flow sequence',
    'index': 'requirements must match L1 total', 'graph': 'must contain non-empty nodes',
    'content-stale': 'content onboarding manifest is stale',
    'content-miss': 'project-specific memory query returned no matching path',
}
reasons.update(dict.fromkeys(yaml_cases, 'is invalid:'))
for name in cases:
    work = a.scratch.resolve()/name
    if work.exists():
        shutil.rmtree(work)
    project, install, tools = (work/p for p in ['project', 'install', 'tools'])
    project.mkdir(parents=True)
    tools.mkdir()
    scope['venv'].EnvBuilder(with_pip=False, symlinks=True).create(install/'venv')
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
    env = dict(HOME=str(work), PATH=str(tools), PYTHONUTF8='1', DYLD_INSERT_LIBRARIES=str(clock))
    content = name.startswith('content')
    profile = 'content_workspace' if content else 'code_app'
    initial = {p: b'' for p in ['CLAUDE.md', 'AGENTS.md', '.codex/config.toml',
               '.ai-harness/deny-list.yaml', '.claude/agents/main-orchestrator.md',
               '.codex/agents/main-orchestrator.toml', '.claude/hooks/test.sh']}
    initial.update({p: b'{}' for p in ['.codex/hooks.json', 'config/sub-agent-policy.json',
                   'config/adopter-payload.json']})
    initial.update({'config/capability-sources.json': json.dumps(source).encode(),
        'config/adopter-boundary.json': json.dumps(dict(schema_version=1,
            provider_markers=['provider-marker'],
            provider_text_markers=[], provider_owners=[])).encode(),
        '.claude/settings.json': b'{"hooks":{"Test":[]}}',
        'harness_a.toml': scope['config'].encode(),
        'archive/source.md': b'# Searchable archive\nDistinctive parity evidence.\n'})
    if content:
        initial['archive/source.pdf'] = b'%PDF synthetic non-indexable record'
        initial['harness_a.toml'] = scope['config'].replace(
            'sample-docs', 'sample-content').replace(
            'root = "archive"', 'root = "."').replace(
            '["**/*.md"]', '["docs/**/*.md", "tasks/**/*.md", "archive/**/*.md"]').encode()
    if name == 'content-generated':
        del initial['harness_a.toml']  # Exercise generated archive globs, not authored config.
    def reset(initial, project=project, name=name):
        shutil.rmtree(project)
        project.mkdir()
        for relative, body in initial.items():
            path = project/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        if name == 'linked':
            (project/'spec/bootstrap-evidence.json').symlink_to('evidence.json')
    def files(mask=True, project=project):
        result = {}
        for path in sorted(project.rglob('*')):
            if path.is_file():
                data = bytearray(path.read_bytes())
                if mask and data.startswith(b'SQLite format 3\0'):
                    data[96:100] = b'\0'*4  # COMMON's only physical DB exclusion.
                result[str(path.relative_to(project))] = list(data)
        return result
    def reference(argv, python=python, project=project, env=env):
        return subprocess.run([str(python), '-I', '-X', 'utf8', str(wrapper), *argv],
                              cwd=project, env=env, capture_output=True, timeout=30, check=False)
    argv = ['--project-root', str(project), '--profile', profile, '--slug', 'sample',
            '--purpose', 'Synthetic portable project', '--stack', 'Rust', '--json']
    phase1 = name in ('content-allow', 'content-restart', 'content-miss', 'content-generated')
    if content and not phase1:
        reset(initial)
        seed = reference([*argv, '--archive', 'records=archive'])
        assert seed.returncode == 0, seed
        assert json.loads(seed.stdout)['status'] == 'restart_required', seed
        initial = {p: bytes(b) for p, b in files(mask=False).items()}
    if not phase1:
        initial['.mir/repo-profile.toml'] = f'''[repo]
slug = "mir-yoke"
repository_type = "public_harness_template"
purpose = "Synthetic portable project"
technology_stack = ["Rust"]
[execution]
non_code_profile = "{profile}"
[gates]
requires_memory_store = true
requires_global_capabilities = true
'''.encode()
        initial['.mir/bootstrap-receipt.json'] = b'{"status":"restart_required"}'
        initial['.mir/capability-lock.json'] = json.dumps(dict(schema_version=1,
            source={'commit': 'a'*40}, plugins={'mir-core': {}}, profile=profile,
            agents={}, registration={'status': 'active'})).encode()
        outputs = ['spec/STATE.md', 'spec/index.yaml', 'spec/graph.yaml', 'spec/gaps.yaml']
        for path, body in zip(outputs, ['Complete synthetic architecture.\n',
                'requirements: [{id: r1, status: ready}]\n',
                'nodes: [{id: r1}]\nedges: []\n', 'gaps: []\n'], strict=True):
            initial[path] = body.encode()
        coverage = {layer: dict(total=n, filled=n, derived=0, na=0, tbd=0)
                    for layer, n in [('l1', 1), ('l2', 1), ('l3', 9), ('l4', 10)]}
        coverage['ai_ready'] = dict(ready=1, incomplete=0, blocked=0)
        evidence = dict(schema_version=2, sequence=['mir-core:design', 'mir-core:spec-architect'],
            capability_commit='a'*40, outputs=outputs, coverage=coverage, open_gaps=0,
            full_review={k: 'pass' for k in ['project_structure', 'memory', 'discoverability',
                                           'requirements', 'organization']})
        edits = {'schema': ('schema_version', 1), 'sequence': ('sequence', []),
                 'commit': ('capability_commit', 'b'*40), 'outputs': ('outputs', []),
                 'coverage': ('coverage', None), 'review': ('full_review', {})}
        if name in edits:
            key, value = edits[name]
            evidence[key] = value
        if name == 'row':
            del coverage['l2']
        if name == 'counts':
            coverage['l3']['total'] = -1
        if name == 'total':
            coverage['l3'].update(total=8, filled=8)
        if name == 'sum':
            coverage['l3']['filled'] = 8
        if name == 'tbd':
            coverage['l3'].update(filled=8, tbd=1)
        if name == 'ai':
            coverage['ai_ready']['blocked'] = 1
        initial['spec/bootstrap-evidence.json'] = json.dumps(evidence).encode()
        if name == 'missing':
            del initial['spec/bootstrap-evidence.json']
        if name == 'linked':
            initial['spec/evidence.json'] = initial.pop('spec/bootstrap-evidence.json')
        if name == 'json':
            initial['spec/bootstrap-evidence.json'] = b'{'
        if name == 'prior':
            del initial['.mir/bootstrap-receipt.json']
        if name == 'prior-status':
            initial['.mir/bootstrap-receipt.json'] = b'{"status":"ready"}'
        if name in ('inactive', 'error'):
            initial['provider-mode'] = name.encode()
        if name == 'output-missing':
            del initial['spec/STATE.md']
        if name == 'output-empty':
            initial['spec/STATE.md'] = b' \t\r\n'
        if name == 'placeholder':
            initial['spec/STATE.md'] = 'TODÓ\n'.encode()
        if name == 'gaps':
            initial['spec/gaps.yaml'] = b'gaps: [{status: open}]\n'
        if name == 'gap-shape':
            initial['spec/gaps.yaml'] = b'{}\n'
        if name == 'gap-json':
            initial['spec/gaps.yaml'] = b'[broken\n'
        if yaml_diagnostics:
            initial['spec/gaps.yaml'] = yaml_cases[name]
        if name == 'index':
            initial['spec/index.yaml'] = b'requirements: [{status: incomplete}]\n'
        if name == 'graph':
            initial['spec/graph.yaml'] = b'nodes: []\nedges: []\n'
        if name == 'content-stale':
            initial['archive/another.md'] = b'Searchable new record.\n'
        argv += ['--finalize', *([] if name == 'flag' else ['--architecture-initialized'])]
    else:
        argv += ['--archive', 'records=archive']
        if name != 'content-restart':
            argv += ['--skip-capability-activation', '--allow-incomplete']
    if name == 'content-miss':
        # A real filesystem change after onboarding validation, before archive indexing.
        (tools/'git').write_text('#!/bin/sh\nif [ "$1 $2" = "rev-parse HEAD" ]; then\n'
            'echo "Different lexical evidence." > archive/source.md\nfi\nexit 1\n')
    reset(initial)
    out = reference(argv)
    def links(project=project):
        return {str(p.relative_to(project)): os.readlink(p) for p in project.rglob('*')
                if p.is_symlink()}
    record = dict(case=name, exit=out.returncode, stdout=list(out.stdout), stderr=list(out.stderr),
                  files=files(), links=links())
    records.append(record)
    a.output.write_text(json.dumps(records)+'\n')
    receipt = json.loads(out.stdout)
    success = name in ('ready', 'content-ready', 'content-allow',
                       'content-restart', 'content-generated')
    assert out.returncode == (0 if success else 2 if name == 'content-stale' else 1), (name, out)
    if not success:
        assert any(reasons[name] in error for error in receipt['errors']), (name, receipt['errors'])
    if success:
        assert not out.stderr and receipt['errors'] == [], (name, out)
        if name.endswith('ready'):
            assert receipt['status'] == 'ready'
            assert receipt['architecture_initialization']['attested']
            assert receipt['slim']['status'] == 'not_applicable'
        if content:
            assert receipt['content_onboarding']['status'] == 'pass'
            assert len(receipt['content_onboarding']['queries']) == 2
            assert all(q['status'] == 'pass' for q in receipt['content_onboarding']['queries'])
    if name == 'content-miss':
        assert receipt['content_onboarding']['status'] == 'fail'
        assert receipt['content_onboarding']['queries'][1]['status'] == 'fail'
    assert project.resolve().is_relative_to(a.scratch.resolve())
    if name != 'content-generated':
        assert not (project/'.mir/memory.db').exists()
    if binary:
        reset(initial)
        shutil.copy2(binary, install/'bin/mir')
        actual = subprocess.run([str(install/'bin/mir'), 'bootstrap', *argv], cwd=project,
                                env=env, capture_output=True, check=False, timeout=30)
        (work/'actual.json').write_text(json.dumps(dict(exit=actual.returncode,
            stdout=list(actual.stdout), stderr=list(actual.stderr), files=files())))
        assert actual.returncode == record['exit'], (name, actual)
        assert actual.stderr == bytes(record['stderr']), (name, actual.stderr)
        assert actual.stdout == bytes(record['stdout']), (name, 'stdout', actual.stdout)
        assert links() == record['links'], name
        assert files() == record['files'], (name, 'files', [p for p in files()
                                                         if files()[p] != record['files'].get(p)])
print(f'{len(records)} literal phase2/content records' + (' replayed' if binary else ' frozen'))
