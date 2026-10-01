"""Common-base v2 extension contracts; no provider processes are launched."""
from __future__ import annotations

import json
import pathlib
import subprocess
from types import SimpleNamespace

import pytest

from tools.mir_executor import cli, dispatch, local_hooks, policy
from tools.mir_executor.jobs import JobRegistry


@pytest.fixture
def target(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    hooks = tmp_path / 'tools/mir_executor/local.py'
    hooks.parent.mkdir(parents=True)
    hooks.write_text('''events = []
identity_calls = []
validated = []
fail_event = None
def on_job_event(event, payload):
    events.append((event, payload))
    if event == fail_event:
        raise RuntimeError('event storage unavailable')
def job_identity(args, repo_root, prompt, model):
    identity_calls.append((args, repo_root, prompt, model))
    return '{"instruction_sha256":"digest","model_alias":"m"}'
def validate_brief(brief, repo_root):
    result = {'scope': 'src', 'capabilities': ['read', 'edit']}
    validated.append(result)
    return result
def render_brief(validated, repo_root):
    assert validated is globals()['validated'][-1]
    return 'Scope: src; capabilities: read, edit'
''')
    monkeypatch.setattr(policy, 'load_sub_agent_policy', lambda _: SimpleNamespace(
        mode='force_codex', resolve_category=lambda _: {'model': 'm', 'reasoning_effort': 'high'}
    ))
    monkeypatch.setattr(dispatch, 'build_codex_mcp_runner', lambda *a, **kw: object())
    return tmp_path, local_hooks._module(tmp_path)


def arguments(root, *options):
    return cli._build_parser(root).parse_args([
        'execute', '--repo-root', str(root), '--codex-args', 'task', *options,
    ])


def record(root):
    registry = JobRegistry(root / 'tasks/jobs.db')
    try:
        return registry.list_jobs()[0]
    finally:
        registry.close()


def blocked(monkeypatch):
    monkeypatch.setattr(dispatch, 'run_dispatch', lambda *a, **kw:
                        dispatch.DispatchOutcome('blocked', 0, False, 'test', None))


@pytest.mark.parametrize('background', [False, True])
def test_should_emit_job_inserted_on_both_paths(target, monkeypatch, background):
    root, hooks = target
    blocked(monkeypatch)

    class Executor:
        def __init__(self, **kw):
            pass

        def _validate_ledger_entry(self, *a):
            pass

    monkeypatch.setattr(cli, 'MirExecutor', Executor)

    async def finish(**kw):
        registry = JobRegistry(kw['jobs_db_path'])
        registry.update_status(kw['job_id'], 'completed', exit_code=0)
        registry.close()

    monkeypatch.setattr(cli, '_run_background', finish)
    args = arguments(root, *(['--background', '--change-id', 'X', '--category', 'unit']
                             if background else ['--dispatch']))
    cli._handle_execute(args)
    inserted = next(payload for event, payload in hooks.events if event == 'job_inserted')
    assert inserted['job_id'] == record(root).job_id
    assert inserted['path'] == ('background' if background else 'dispatch')
    assert inserted['args'] is args
    assert inserted['repo_root'] == root
    assert pathlib.Path(inserted['jobs_db']) == root / 'tasks/jobs.db'


@pytest.mark.parametrize('background', [False, True])
def test_should_persist_identity_on_both_paths(target, monkeypatch, background):
    root, hooks = target
    blocked(monkeypatch)

    class Executor:
        def __init__(self, **kw):
            pass

        def _validate_ledger_entry(self, *a):
            pass

    monkeypatch.setattr(cli, 'MirExecutor', Executor)

    async def finish(**kw):
        registry = JobRegistry(kw['jobs_db_path'])
        registry.update_status(kw['job_id'], 'completed', exit_code=0)
        registry.close()

    monkeypatch.setattr(cli, '_run_background', finish)
    args = arguments(root, *(['--background', '--change-id', 'X', '--category', 'unit']
                             if background else ['--dispatch']))
    cli._handle_execute(args)
    assert json.loads(record(root).identity_json)['model_alias'] == 'm'
    assert hooks.identity_calls == [(args, root, 'task', 'm')]


@pytest.mark.parametrize('file_brief', [False, True])
def test_should_pass_rendered_validated_brief(target, monkeypatch, file_brief):
    root, _ = target
    calls = []

    def run(*a, **kw):
        calls.append(kw)
        return dispatch.DispatchOutcome('blocked', 0, False, 'test', None)

    monkeypatch.setattr(dispatch, 'run_dispatch', run)
    options = ['--dispatch']
    if file_brief:
        path = root / 'brief.json'
        path.write_text('{"expanded_goal":"task"}')
        options += ['--dispatch-brief', str(path)]
    cli._handle_execute(arguments(root, *options))
    assert calls[0]['brief_text'] == 'Scope: src; capabilities: read, edit'


@pytest.mark.parametrize('event', ['job_inserted', 'dispatch_state', 'dispatch_finalized'])
def test_should_apply_lifecycle_error_policy(target, monkeypatch, capsys, event):
    root, hooks = target
    hooks.fail_event = event
    worktree = SimpleNamespace(main_repo_root=root, dispatch_id='will-be-set')
    calls = []
    monkeypatch.setattr(dispatch, 'write_status', lambda *a, **kw: None)

    def run(*a, **kw):
        calls.append('run')
        worktree.dispatch_id = kw['dispatch_id']
        dispatch._write_dispatch_status(worktree, 'codex_completed', attempt=1)
        return dispatch.DispatchOutcome('completed', 1, False, None, worktree)

    monkeypatch.setattr(dispatch, 'run_dispatch', run)
    monkeypatch.setattr(dispatch, 'finalize_dispatch', lambda *a, **kw:
                        dispatch.FinalizeResult('merged', 'ok', ['src/main.py']))
    rc = cli._handle_execute(arguments(root, '--dispatch'))
    job = record(root)
    if event == 'job_inserted':
        assert rc == 1 and job.status == 'failed' and calls == []
        assert any(e == 'dispatch_failed' for e, _ in hooks.events)
    else:
        assert rc == 0 and job.status == 'completed'
    assert 'event storage unavailable' in job.stderr
    assert 'event storage unavailable' in capsys.readouterr().err


def test_should_emit_finalized_and_failed_evidence(target, monkeypatch):
    root, hooks = target
    wt = SimpleNamespace(main_repo_root=root, dispatch_id='unused')
    monkeypatch.setattr(dispatch, 'run_dispatch', lambda *a, **kw:
                        dispatch.DispatchOutcome('completed', 1, False, None, wt))
    monkeypatch.setattr(dispatch, 'finalize_dispatch', lambda *a, **kw:
                        dispatch.FinalizeResult('merged', 'ok', ['src/main.py']))
    assert cli._handle_execute(arguments(root, '--dispatch')) == 0
    event = next(p for e, p in hooks.events if e == 'dispatch_finalized')
    assert event['job_id'] == record(root).job_id
    assert event['dispatch_id'] == event['job_id']
    assert event['status'] == 'completed'
    assert event['finalize_action'] == 'merged'
    assert event['merged_files'] == ['src/main.py'] and event['reason'] == 'ok'

    def fail(*a, **kw):
        raise OSError('worktree creation failed')

    monkeypatch.setattr(dispatch, 'run_dispatch', fail)
    assert cli._handle_execute(arguments(root, '--dispatch')) == 1
    event = next(p for e, p in hooks.events if e == 'dispatch_failed')
    assert event['error_type'] == 'OSError'
    assert event['message'] == 'worktree creation failed'
    assert event['dispatch_id'] is not None


def test_should_preserve_old_callback_and_emit_state(target, monkeypatch):
    root, hooks = target
    hooks.state_callback = lambda state, evidence: hooks.events.append(('old', (state, evidence)))
    monkeypatch.setattr(dispatch, 'write_status', lambda *a, **kw: None)
    wt = SimpleNamespace(main_repo_root=root, dispatch_id='direct')
    dispatch._write_dispatch_status(wt, 'blocked', reason='test')
    assert hooks.events[0] == ('old', ('blocked', {'reason': 'test'}))
    payload = hooks.events[1][1]
    assert payload == {'job_id': None, 'dispatch_id': 'direct', 'state': 'blocked',
                       'evidence': {'reason': 'test'}}


def test_should_resolve_repo_root_after_pre_execute(target, tmp_path, monkeypatch):
    root, hooks = target
    selected = root / 'family-repo'
    subprocess.run(['git', 'init', '-q', str(selected)], check=True)
    hooks.pre_execute = lambda args, initial: setattr(args, 'repo_root', selected)
    calls = []
    monkeypatch.setattr(cli, '_handle_dispatch', lambda args, repo, codex_args:
                        calls.append((repo, args.repo_root)) or 0)
    assert cli._handle_execute(arguments(root, '--dispatch', '--family', 'family')) == 0
    assert calls == [(selected, selected)]


def test_should_refuse_non_git_selected_root(target, monkeypatch, capsys):
    root, hooks = target
    selected = root / 'not-git'
    selected.mkdir()
    # Outside the initial repository, so Git cannot discover its parent.
    selected = root.parent / 'not-git'
    selected.mkdir()
    hooks.pre_execute = lambda args, initial: setattr(args, 'repo_root', selected)
    monkeypatch.setattr(cli, '_handle_dispatch', lambda *a: 0)
    assert cli._handle_execute(arguments(root, '--dispatch')) == 1
    assert 'git repository' in capsys.readouterr().err


def test_should_persist_effective_dispatch_options(target, monkeypatch):
    import hashlib

    root, _ = target
    brief = root / 'brief.json'
    brief.write_text('{"expanded_goal":"task"}')
    blocked(monkeypatch)
    monkeypatch.setattr(policy, 'load_sub_agent_policy', lambda _: SimpleNamespace(
        mode='force_codex', resolve_category=lambda _: {'model': 'm', 'reasoning_effort': 'high'},
        monitoring={'stall_timeout_seconds': 47},
    ))
    args = arguments(root, '--dispatch', '--dispatch-brief', str(brief),
                     '--allow-path', 'src/', '--verify', 'unit', '--no-expect-changes',
                     '--stall-timeout', '47')
    cli._handle_execute(args)
    options = json.loads(record(root).dispatch_options_json)
    assert options['dispatch_brief'] == str(brief)
    assert options['brief_sha256'] == hashlib.sha256(brief.read_bytes()).hexdigest()
    assert options['allow_paths'] == ['src/'] and options['verify_cmds'] == ['unit']
    assert options['expect_changes'] is False and options['change_id'] is None
    assert options['model'] == 'm' and options['reasoning_effort'] == 'high'
    assert options['execution_backend'] == record(root).execution_backend == 'codex'
    assert options['stall_timeout'] == 47


def test_should_include_durable_review_evidence(target, monkeypatch):
    root, hooks = target
    (root / 'config').mkdir()
    (root / 'config/mir-executor.local.json').write_text('{"require_review":true}')
    monkeypatch.setattr(dispatch, 'build_codex_review_runner', lambda *a, **kw: object())
    monkeypatch.setattr(dispatch, 'run_dispatch', lambda *a, **kw:
                        dispatch.DispatchOutcome('completed', 1, False, None, object()))
    evidence = {'passed': True, 'reason': 'approved', 'content': 'review content'}

    def finalize(*a, **kw):
        job_id = record(root).job_id
        directory = root / 'tasks/dispatch' / job_id
        directory.mkdir(parents=True)
        (directory / 'reviewer.json').write_text(json.dumps(evidence))
        return dispatch.FinalizeResult('reviewed', 'approved', [])

    monkeypatch.setattr(dispatch, 'finalize_dispatch', finalize)
    assert cli._handle_execute(arguments(root, '--dispatch')) == 0
    finalized = next(p for e, p in hooks.events if e == 'dispatch_finalized')
    assert finalized['review_evidence'] == evidence


def test_should_keep_single_plain_validation_without_render_hook(target, monkeypatch):
    root, hooks = target
    del hooks.render_brief
    seen = []
    hooks.validate_brief = lambda brief, repo: seen.append(brief)

    def run(repo, **kw):
        local_hooks.invoke_hook(repo, 'validate_brief', kw['brief_text'], repo)
        return dispatch.DispatchOutcome('blocked', 0, False, 'test', None)

    monkeypatch.setattr(dispatch, 'run_dispatch', run)
    cli._handle_execute(arguments(root, '--dispatch'))
    assert seen == ['task']


def test_should_emit_started_running_with_original_resume_job_id(target, monkeypatch):
    root, hooks = target
    wt = SimpleNamespace(main_repo_root=root, path=root / 'worktree', dispatch_id='new-attempt')
    monkeypatch.setattr(dispatch, 'create_dispatch_worktree', lambda *a, **kw: wt)
    monkeypatch.setattr(dispatch, 'write_status', lambda *a, **kw: None)
    old_states = []
    hooks.state_callback = lambda state, evidence: old_states.append(state)

    def run(*a):
        assert [p['state'] for e, p in hooks.events if e == 'dispatch_state'] == [
            'started', 'running',
        ]
        return dispatch.CodexAttempt(0)

    errors = []
    with local_hooks.job_event_scope(root, 'original-job', errors):
        outcome = dispatch.run_dispatch(root, 'new-attempt', codex_runner=run)
    assert outcome.status == 'completed' and errors == []
    states = [p for e, p in hooks.events if e == 'dispatch_state']
    assert all(p['job_id'] == 'original-job' and p['dispatch_id'] == 'new-attempt' for p in states)
    assert [p['state'] for p in states] == ['started', 'running', 'codex_completed']
    assert old_states == ['codex_completed']


@pytest.mark.parametrize('fail_dispatch', [False, True])
def test_should_emit_job_resumed_with_original_id_and_options(target, monkeypatch, fail_dispatch):
    root, hooks = target
    brief = root / 'brief.json'
    brief.write_text('{"expanded_goal":"task"}')
    blocked(monkeypatch)
    assert cli._handle_execute(arguments(root, '--dispatch', '--dispatch-brief', str(brief))) == 1
    original = record(root)
    hooks.events.clear()
    wt = SimpleNamespace(main_repo_root=root, dispatch_id='unused')
    monkeypatch.setattr(dispatch, 'write_status', lambda *a, **kw: None)

    def run(*a, **kw):
        assert hooks.events[0][0] == 'job_resumed'
        wt.dispatch_id = kw['dispatch_id']
        dispatch._write_dispatch_status(wt, 'running')
        if fail_dispatch:
            raise OSError('resume dispatch failed')
        return dispatch.DispatchOutcome('completed', 1, False, None, wt)

    monkeypatch.setattr(dispatch, 'run_dispatch', run)
    monkeypatch.setattr(dispatch, 'finalize_dispatch', lambda *a, **kw:
                        dispatch.FinalizeResult('merged', 'ok', ['src/main.py']))
    args = cli._build_parser(root).parse_args([
        'resume', '--repo-root', str(root), '--job-id', original.job_id,
    ])
    assert cli._handle_resume(args) == int(fail_dispatch)
    resumed = hooks.events[0][1]
    assert hooks.events[0][0] == 'job_resumed'
    assert resumed['job_id'] == original.job_id and resumed['path'] == 'resume'
    assert resumed['args'].resume_job_id == original.job_id
    assert resumed['repo_root'] == root and resumed['jobs_db'] == root / 'tasks/jobs.db'
    assert resumed['dispatch_options'] == json.loads(original.dispatch_options_json)
    later = hooks.events[1:]
    assert [event for event, _ in later] == [
        'dispatch_state', 'dispatch_failed' if fail_dispatch else 'dispatch_finalized',
    ]
    assert all(payload['job_id'] == original.job_id for _, payload in later)
    assert all(payload['dispatch_id'] != original.job_id for _, payload in later)


def test_should_abort_resume_when_job_resumed_hook_fails(target, monkeypatch, capsys):
    root, hooks = target
    brief = root / 'brief.json'
    brief.write_text('{"expanded_goal":"task"}')
    blocked(monkeypatch)
    cli._handle_execute(arguments(root, '--dispatch', '--dispatch-brief', str(brief)))
    original = record(root)
    hooks.events.clear()
    hooks.fail_event = 'job_resumed'
    calls = []
    monkeypatch.setattr(dispatch, 'run_dispatch', lambda *a, **kw: calls.append(kw))
    args = cli._build_parser(root).parse_args([
        'resume', '--repo-root', str(root), '--job-id', original.job_id,
    ])
    assert cli._handle_resume(args) == 1
    assert calls == []
    job = record(root)
    assert job.job_id == original.job_id and job.status == 'failed'
    assert 'event storage unavailable' in job.stderr
    assert 'event storage unavailable' in capsys.readouterr().err
    assert [event for event, _ in hooks.events] == ['job_resumed', 'dispatch_failed']
