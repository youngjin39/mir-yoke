"""B30 main oracle from unmodified Python; synthetic_e2e keeps bootstrap helpers real."""
import contextlib
import hashlib
import io
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import pytest

from mir.cli import bootstrap as M

FIXTURE = (Path(__file__).parents[1] /
           'native/handoff-packet/tests/fixtures/w2/b30-bootstrap-main.json')
CASES = {}
def observe(case, tmp):
    try:
        return {'value': case(tmp)}
    except (Exception, SystemExit) as exc:
        return {'error': [type(exc).__name__, str(exc).replace(str(tmp), '<tmp>')]}
def put(tmp, name, body):
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')
    return path
def compact(value, tmp):
    if isinstance(value, str):
        value = value.replace(str(tmp), '<tmp>')
        return value if len(value) <= 512 else {
            'len': len(value), 'sha256': hashlib.sha256(value.encode()).hexdigest()}
    if isinstance(value, dict):
        return {k: compact(v, tmp) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [compact(v, tmp) for v in value]
    return value
def files(tmp):
    result = {}
    for p in sorted(tmp.rglob('*')):
        if not p.is_file() or p.name.endswith(('-wal', '-shm')):
            continue
        if p.suffix == '.db':
            with sqlite3.connect(p) as db:
                result[p.relative_to(tmp).as_posix()] = [
                    [db.execute('PRAGMA ' + k).fetchall() for k in
                     ('journal_mode', 'user_version', 'schema_version')],
                    db.execute('SELECT version,name FROM schema_migrations ORDER BY version')
                    .fetchall(), db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master '
                                           'ORDER BY type,name,tbl_name,sql').fetchall()]
                key = p.relative_to(tmp).as_posix()
                result[key] = compact(json.dumps(result[key], sort_keys=True), tmp)
        else:
            result[p.relative_to(tmp).as_posix()] = p.read_text(encoding='utf-8')
    return compact(result, tmp)
def main(tmp, mode, json_mode, scenario=None):
    out, err, calls, helpers = io.StringIO(), io.StringIO(), [], []
    args = ['--project-root', str(tmp), '--slug', 'sample', '--profile', 'code_app',
            '--purpose', 'Build tools', '--stack', 'Rust'] + (['--json'] if json_mode else [])
    overrides = {'help': ['--help'], 'short_help': ['-h'], 'missing_profile': [],
                 'unknown': args + ['--bad'], 'dry_run': args + ['--dry-run'],
                 'apply': args + ['--apply'], 'slug': args + ['--slug', '!'],
                 'profile': args + ['--profile', 'bad'],
                 'root': args + ['--project-root', str(tmp / 'absent')]}
    if mode.startswith('missing:'):
        args += [mode[8:]]
    else:
        args = overrides.get(mode, args)
    if mode.startswith(('finalize', 'architecture', 'slim', 'receipt', 'commit')):
        args += ['--finalize'] + ([] if mode == 'finalize_no_attestation' else
                                ['--architecture-initialized'])
        if mode != 'finalize_missing':
            put(tmp, '.mir/repo-profile.toml', 'profile')
    if mode in ('existing', 'provider'):
        put(tmp, '.mir/repo-profile.toml', 'profile')
    if mode in ('skip', 'allow', 'synthetic_e2e'):
        args += ['--skip-capability-activation']
        if mode != 'skip':
            args += ['--allow-incomplete']
    if mode == 'archive':
        args += ['--archive', 'notes=docs']
    if mode in ('content', 'acceptance', 'onboarding', 'finalize_content'):
        args += ['--profile', 'content_workspace']
    def run(argv, **kw):
        calls.append([list(map(str, argv)), str(kw.get('cwd', '')), kw.get('input'),
                      kw.get('stdin')])
        return NS(returncode=0, stdout='', stderr='')
    cfg = NS(memory=NS(enabled=mode != 'disabled', required=True, vector_mode='off'))
    profile = {'repo': {'purpose': 'Build tools', 'technology_stack': ['Rust']}}
    scripts = dict(_source_control_ownership=(['ownership refused'] if mode == 'ownership'
                   else [], {}), _storage_preflight=(['storage refused'] if mode == 'storage'
                   else [], {}), _validate_project_identity=['identity refused']
                   if mode == 'identity' else [], _validate_surfaces=(['surface refused']
                   if mode == 'surface' else [], {}), _load_capability_sources={},
                   load_profile=profile, load_boundary={}, is_provider_owner=mode == 'provider',
                   _validate_existing_profile=ValueError('existing refused')
                   if mode == 'existing' else profile, _is_raw_provider_checkout=mode == 'raw',
                   load_config=cfg, resolve_memory_db=tmp / '.mir/memory.db',
                   _activate_capabilities=('failed', {'reason': 'activation refused'})
                   if mode == 'activation' else ('ready', {}),
                   _finalize_capabilities=('failed', {'reason': 'finalize refused'})
                   if mode == 'finalize_failure' else ('ready', {}),
                   _validate_architecture_evidence=(['architecture refused']
                   if mode == 'architecture' else [], {}), apply_adopter_slim=M.SlimError('slim')
                   if mode == 'slim' else {}, commit_adopter_slim=M.SlimError('commit')
                   if mode == 'commit' else None, rollback_adopter_slim=None,
                   _validate_content_memory_acceptance=(['acceptance refused']
                   if mode == 'acceptance' else [], {}),
                   _build_content_onboarding=ValueError('onboarding refused')
                   if mode == 'onboarding' else ({'scan': {'unclassified': []}}, 'Definition'),
                   _build_projection_updates=ValueError('projection refused')
                   if mode == 'projection' else {tmp / 'docs/projection.md': 'Projection'})
    env = {'HOME': str(tmp), 'VIRTUAL_ENV': str(tmp), 'TMPDIR': str(tmp)}
    if scenario:
        if scenario == 'help_windows':
            args = ['--help']
        if scenario.startswith('content_'):
            manifest = {'schema_version': 1, 'profile': 'content_workspace',
                        'purpose': 'Build tools', 'technology_stack': ['Rust'],
                        'archives': [{'classification': 'notes', 'path': 'docs'}],
                        'scan': {'unclassified': []}}
            put(tmp, 'config/content-onboarding.json', json.dumps(manifest))
            scripts['_build_content_onboarding'] = (manifest, 'Definition')
            if scenario == 'content_purpose':
                args += ['--purpose', 'Different purpose']
            if scenario == 'content_stack':
                args += ['--stack', 'Python']
            if scenario == 'content_stale':
                scripts['_build_content_onboarding'] = ({}, 'Definition')
            if scenario == 'content_existing':
                manifest['purpose'] = 'Other purpose'
                put(tmp, 'config/content-onboarding.json', json.dumps(manifest))
            if scenario == 'content_unclassified':
                scripts['_build_content_onboarding'] = (
                    {'scan': {'unclassified': [{'path': 'notes', 'formats': ['md']}]}}, '')
        if scenario in ('profile_purpose', 'profile_stack'):
            scripts['_validate_existing_profile'] = {'repo': dict(profile['repo'])}
            scripts['_validate_existing_profile']['repo'][
                'purpose' if scenario == 'profile_purpose' else 'technology_stack'] = (
                    'Other purpose' if scenario == 'profile_purpose' else ['Python'])
        if scenario == 'prior_receipt':
            put(tmp, '.mir/bootstrap-receipt.json', '{"marker":"prior"}')
        if scenario == 'harness_invalid':
            put(tmp, 'harness_a.toml', 'invalid')
            scripts['load_config'] = M.ConfigLoadError('harness refused')
        if scenario == 'no_venv':
            env.pop('VIRTUAL_ENV')
        if scenario == 'vector_required':
            cfg.memory.vector_mode = 'required'
        if scenario in ('cli_file', 'cli_missing', 'cli_manifest'):
            env['MIR_BOOTSTRAP_CLI_PATH'] = str(tmp / 'cli')
            if scenario != 'cli_missing':
                put(tmp, 'cli', 'synthetic cli')
            if scenario == 'cli_manifest':
                env['MIR_BOOTSTRAP_RUNTIME_MANIFEST'] = str(tmp / 'manifest.json')
                scripts['install_runtime_verifier'] = {'status': 'scripted'}
        if scenario == 'slim_applied':
            scripts['apply_adopter_slim'] = {'status': 'applied'}
        if scenario == 'rollback_failure':
            scripts['rollback_adopter_slim'] = M.SlimError('rollback refused')
    def scripted(name, value):
        def call(*a, **kw):
            helpers.append(name)
            if scenario == 'prior_receipt' and name == '_finalize_capabilities':
                helpers.append({'prior_receipt': a[1]})
            if scenario == 'slim_applied' and name == 'apply_adopter_slim':
                for path in ('.mir/slim.lock', '.mir/slim-transaction.json'):
                    put(tmp, path, '{}')
            if isinstance(value, Exception):
                raise value
            return value
        return call
    with contextlib.ExitStack() as s:
        s.enter_context(mock.patch.dict(M.os.environ, env, clear=True))
        for name, value in [('system', 'Windows' if (mode == 'windows'
                                                      or scenario == 'help_windows')
                             else
                             'Other' if mode == 'platform' else 'Linux'),
                            ('release', 'test'), ('python_version', 'test')]:
            s.enter_context(mock.patch.object(M.platform, name, return_value=value))
        s.enter_context(mock.patch.object(M.Path, 'home', return_value=tmp))
        s.enter_context(mock.patch.object(M.Path, 'cwd', return_value=tmp))
        s.enter_context(mock.patch.object(M.shutil, 'which', side_effect=lambda n: str(tmp / n)))
        s.enter_context(mock.patch.object(M.subprocess, 'run', side_effect=run))
        s.enter_context(mock.patch.object(M.store, '_now_iso', return_value='fixed'))
        if scenario == 'no_venv':
            s.enter_context(mock.patch.object(M.sys, 'prefix', M.sys.base_prefix))
        if scenario == 'vector_required':
            migrate = M.store.apply_migrations
            def seed(db):
                migrate(db)
                db.execute("INSERT INTO external_store_meta VALUES "
                           "('schema_metadata_version:archive:sample', '1')")
                db.commit()
            def sync(argv):
                with contextlib.closing(sqlite3.connect(argv[2])) as db:
                    helpers.append(db.execute('SELECT key,value FROM external_store_meta '
                                              'ORDER BY key').fetchall())
                return 0
            s.enter_context(mock.patch.object(M.store, 'apply_migrations', side_effect=seed))
        if mode != 'synthetic_e2e':
            for name, value in scripts.items():
                s.enter_context(mock.patch.object(M, name, side_effect=scripted(name, value)))
            s.enter_context(mock.patch.object(M.context_cli, 'main', return_value=
                                             3 if mode == 'sync' else 0,
                                             side_effect=sync if scenario == 'vector_required'
                                             else None))
            s.enter_context(mock.patch.object(M.memory_cli, 'run_doctor', return_value=
                                             (1, {'errors': ['doctor refused']})
                                             if mode == 'doctor' else (0, {})))
        if mode == 'authored':
            s.enter_context(mock.patch.object(M, '_ensure_authored_files',
                                             side_effect=ValueError('authored refused')))
        if mode == 'stage':
            s.enter_context(mock.patch.object(M, '_stage_memory_db', side_effect=OSError('stage')))
        if mode == 'migrate':
            s.enter_context(mock.patch.object(M.store, 'apply_migrations',
                                             side_effect=ValueError('migrate')))
        if mode == 'publish':
            original = M._atomic_write_text
            s.enter_context(mock.patch.object(M, '_atomic_write_text', side_effect=lambda p, b:
                (_ for _ in ()).throw(OSError('publish')) if p.name == 'projection.md'
                else original(p, b)))
        if mode == 'receipt':
            s.enter_context(mock.patch.object(M, '_atomic_write_json',
                                             side_effect=OSError('receipt')))
        if mode == 'synthetic_e2e':
            for name in ('CLAUDE.md AGENTS.md .claude/settings.json .codex/config.toml '
                         '.codex/hooks.json .ai-harness/deny-list.yaml '
                         '.claude/agents/main-orchestrator.md .codex/agents/main-orchestrator.toml '
                         'config/sub-agent-policy.json config/adopter-boundary.json '
                         'config/adopter-payload.json .claude/hooks/a.sh').split():
                put(tmp, name, '{"hooks":{"Stop":[]}}' if name.endswith('.json') else '')
            put(tmp, 'config/capability-sources.json', json.dumps({'source': {
                'url': 'https://example.invalid/provider', 'ref': 'main'},
                'profiles': {'packs': {'code_app': []}}}))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = M.main(args)
            except SystemExit as exc:
                code = ['SystemExit', exc.code]
        return compact({'exit': code, 'stdout': out.getvalue(), 'stderr': err.getvalue(),
                        'files': files(tmp), 'subprocess': calls, 'scripts_called': helpers}, tmp)

MODES = ('help short_help missing_profile unknown dry_run apply slug profile root windows platform '
         'ownership storage identity surface existing provider raw archive disabled authored stage '
         'migrate sync doctor projection content acceptance onboarding activation skip allow '
         'finalize_no_attestation finalize_missing finalize_content architecture finalize_failure '
         'finalize_ready slim receipt commit publish synthetic_e2e').split()
LABELS = dict(zip('ownership storage identity surface existing provider raw activation '
                  'finalize_failure architecture acceptance onboarding projection'.split(),
                  '_source_control_ownership _storage_preflight _validate_project_identity '
                  '_validate_surfaces _validate_existing_profile is_provider_owner '
                  '_is_raw_provider_checkout _activate_capabilities _finalize_capabilities '
                  '_validate_architecture_evidence _validate_content_memory_acceptance '
                  '_build_content_onboarding _build_projection_updates'.split(), strict=True))
for mode in MODES:
    for output in ('text', 'json'):
        CASES[f'main.{LABELS.get(mode, mode)}.{mode}.{output}'] = (
            lambda tmp, m=mode, j=output == 'json': main(tmp, m, j))
for flag in ('--project-root', '--slug', '--profile', '--purpose', '--stack', '--archive',
             '--storage-root'):
    CASES[f'main.argument_missing.{flag}'] = lambda tmp, f=flag: main(tmp, 'missing:' + f, False)

for scenario, mode in {
    'help_windows': 'help', 'prior_receipt': 'finalize_ready',
    'content_purpose': 'finalize_content', 'content_stack': 'finalize_content',
    'content_stale': 'finalize_content', 'content_valid': 'finalize_content',
    'content_existing': 'content', 'content_reuse': 'content',
    'content_unclassified': 'content', 'no_venv': 'ready',
    'profile_purpose': 'finalize_ready', 'profile_stack': 'finalize_ready',
    'harness_invalid': 'ready', 'vector_required': 'ready', 'cli_file': 'ready',
    'cli_missing': 'ready', 'cli_manifest': 'ready', 'slim_applied': 'finalize_ready',
    'rollback_failure': 'receipt',
}.items():
    label = dict(help='platform.system', prior='_finalize_capabilities',
                 content='_build_content_onboarding', no='sys.prefix',
                 profile='_validate_existing_profile', harness='load_config',
                 vector='store.apply_migrations', cli='install_runtime_verifier',
                 slim='apply_adopter_slim', rollback='rollback_adopter_slim')[
                     scenario.split('_')[0]]
    CASES[f'main.{label}.{scenario}.json'] = (
        lambda tmp, m=mode, c=scenario: main(tmp, m, True, c))

RECORDS = json.loads(FIXTURE.read_text(encoding='utf-8')) if FIXTURE.exists() else {}
def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)

@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
