"""Execution-layer v3 contracts; providers are isolated test doubles."""
from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from tools.mir_executor import cli, dispatch, local_hooks
from tools.mir_executor.codex_mcp_client import CodexMcpError, CodexMcpResult
from tools.mir_executor.tests.test_dispatch import _cleanup, _make_repo
from tools.mir_executor.tests.test_resume_v2 import prepare_resume


def hooks(root, code):
    path = root / 'tools/mir_executor/local.py'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code)
    return local_hooks._module(root)


def config(root, **values):
    path = root / 'config/mir-executor.local.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(values))


LEASE = '''from contextlib import contextmanager
active = False
entries = 0
@contextmanager
def writer_scope(repo_root):
    global active, entries
    assert not active, 'writer lease is not reentrant'
    active = True
    entries += 1
    try:
        yield
    finally:
        active = False
'''


@pytest.mark.parametrize('exit_code', [0, 2])
def test_item2_should_preserve_stderr_in_dispatch_outcome(tmp_path, exit_code):
    repo = _make_repo(tmp_path)
    outcome = dispatch.run_dispatch(repo, 'stderr-v3', codex_runner=lambda *_:
                                    dispatch.CodexAttempt(exit_code, stderr='provider detail'))
    try:
        assert outcome.stderr == 'provider detail'
    finally:
        _cleanup(outcome)


def test_item3_should_hold_writer_lease_in_direct_dispatch(tmp_path):
    repo = _make_repo(tmp_path)
    local = hooks(repo, LEASE)
    def runner(*_):
        assert local.active
        return dispatch.CodexAttempt(0)
    outcome = dispatch.run_dispatch(repo, 'lease-v3', codex_runner=runner)
    try:
        assert local.entries == 1
        assert not local.active
    finally:
        _cleanup(outcome)


def test_item3_should_reenter_lease_across_async_worker(tmp_path):
    local = hooks(tmp_path, LEASE)
    async def nested():
        def worker():
            with local_hooks.writer_scope(tmp_path):
                assert local.active
        await asyncio.to_thread(worker)
    with local_hooks.writer_scope(tmp_path):
        with local_hooks.writer_scope(tmp_path):
            asyncio.run(nested())
    assert local.entries == 1
    assert not local.active


@pytest.mark.parametrize('failure', [False, True])
def test_item5_should_replace_provider_result_and_keep_metadata(tmp_path, failure):
    repo = _make_repo(tmp_path)
    local = hooks(repo, '''from dataclasses import replace
calls = []
def after_provider_call(result, metadata):
    calls.append((result, metadata))
    return replace(result, exit_code=2, stdout=result.stdout, stderr='budget exceeded')
''')
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def call_codex(self, **kwargs):
            if failure:
                raise CodexMcpError('provider error')
            return CodexMcpResult('preserved output', 'thread', {
                'model': 'actual', 'usage': {'inputTokens': 12}, 'tool_version': 'v1',
            })
    runner = dispatch.build_codex_mcp_runner(
        repo, 'task', model='requested', reasoning_effort='high', client_factory=Client,
    )
    outcome = dispatch.run_dispatch(repo, 'provider-v3', brief_text='task', codex_runner=runner)
    try:
        assert outcome.exit_code == 2
        assert outcome.stdout == ('' if failure else 'preserved output')
        assert len(local.calls) == 1
        _, meta = local.calls[0]
        assert meta['prompt_sha256'] == hashlib.sha256(b'task').hexdigest()
        assert meta['model'] == ('requested' if failure else 'actual')
        assert meta['reasoning_effort'] == 'high'
        assert meta['attempt'] == 1
        assert meta['elapsed_seconds'] >= 0
        if not failure:
            assert meta['token_usage'] == {'input_tokens': 12}
            assert meta['tool_version'] == 'v1'
    finally:
        _cleanup(outcome)


def test_item5_should_call_hook_once_per_custom_dispatch_attempt(tmp_path):
    repo = _make_repo(tmp_path)
    local = hooks(repo, '''calls = []
def after_provider_call(result, metadata):
    calls.append(metadata)
''')
    outcome = dispatch.run_dispatch(
        repo, 'retry-hook-v3', brief_text='task', max_codex_attempts=2,
        codex_runner=lambda wt, attempt: dispatch.CodexAttempt(1 if attempt == 1 else 0),
    )
    try:
        assert [m['attempt'] for m in local.calls] == [1, 2]
    finally:
        _cleanup(outcome)


@pytest.mark.parametrize('builder', ['build_codex_mcp_runner', 'build_claude_runner',
                                      'build_codex_review_runner'])
@pytest.mark.parametrize('value', [9, 21])
def test_item6_should_bound_dispatch_timeout(tmp_path, builder, value):
    config(tmp_path, timeout_seconds_range=[10, 20])
    args = (tmp_path, 'task') if builder == 'build_codex_mcp_runner' else (tmp_path,)
    with pytest.raises(ValueError, match='timeout'):
        getattr(dispatch, builder)(*args, timeout_seconds=value)


@pytest.mark.parametrize('value', [None, 10, 20])
def test_item6_should_allow_optional_and_inclusive_timeout(tmp_path, value):
    config(tmp_path, timeout_seconds_range=[10, 20])
    local_hooks.validate_timeout(tmp_path, value)


@pytest.mark.parametrize('bounds', [[20, 10], [0, 20], [True, 20], [10], '10..20'])
def test_item6_should_reject_malformed_bounds(tmp_path, bounds):
    config(tmp_path, timeout_seconds_range=bounds)
    with pytest.raises(ValueError, match='timeout_seconds_range'):
        local_hooks.validate_timeout(tmp_path, 15)


@pytest.mark.parametrize('override', [False, True])
def test_item6_should_refuse_out_of_bounds_resume_before_dispatch(tmp_path, monkeypatch, override):
    _, _, args = prepare_resume(tmp_path)
    config(tmp_path, timeout_seconds_range=[10, 20])
    if override:
        args.timeout = 21
    calls = []
    monkeypatch.setattr(cli, '_handle_dispatch', lambda *a: calls.append(a) or 0)
    assert cli._handle_resume(args) == 1
    assert calls == []


def test_item5_should_keep_notification_usage_in_dispatch_metadata(tmp_path):
    repo = _make_repo(tmp_path)
    local = hooks(repo, '''calls = []
def after_provider_call(result, metadata):
    calls.append(metadata)
''')
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def call_codex(self, **kwargs):
            return CodexMcpResult('output', 'thread', {}, model_id='confirmed',
                                  token_usage={'last': {'inputTokens': 4, 'outputTokens': 6,
                                                        'totalTokens': 10}},
                                  tool_version='provider/v3')
    runner = dispatch.build_codex_mcp_runner(repo, 'task', client_factory=Client)
    outcome = dispatch.run_dispatch(repo, 'usage-v3', codex_runner=runner)
    try:
        assert dict(outcome.tokens_used) == {
            'input_tokens': 4, 'output_tokens': 6, 'total_tokens': 10,
        }
        assert local.calls[0]['token_usage'] == dict(outcome.tokens_used)
        assert local.calls[0]['model'] == 'confirmed'
        assert local.calls[0]['tool_version'] == 'provider/v3'
    finally:
        _cleanup(outcome)


@pytest.mark.parametrize('entry', ['run_codex', 'run_codex_async'])
def test_item6_should_bound_executor_stall_timeout(tmp_path, monkeypatch, entry):
    from tools.mir_executor import executor
    config(tmp_path, timeout_seconds_range=[10, 20])
    calls = []
    monkeypatch.setattr(executor, '_guard_codex_main_worktree', lambda *a: None)
    monkeypatch.setattr(executor.MirExecutor, '_run_codex_mcp_for_async',
                        lambda *a: calls.append(a))
    api = executor.MirExecutor(tmp_path)
    with pytest.raises(ValueError, match='timeout'):
        if entry == 'run_codex_async':
            asyncio.run(api.run_codex_async(['task'], stall_timeout=21))
        else:
            api.run_codex(['task'], stall_timeout=21)
    assert calls == []


def test_item5_should_apply_budget_hook_to_readonly_reviewer(tmp_path):
    repo = _make_repo(tmp_path)
    local = hooks(repo, '''from dataclasses import replace
calls = []
def after_provider_call(result, metadata):
    calls.append(metadata)
    return replace(result, exit_code=2, stderr='budget exceeded')
''')
    text = '{"verdict":"pass","reason":"approved","findings":[]}'
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def call_codex(self, **kwargs):
            return CodexMcpResult(text, 'thread', {})
    wt = dispatch.create_dispatch_worktree(repo, 'review-budget-v3')
    try:
        review = dispatch.build_codex_review_runner(repo, client_factory=Client)(wt, [])
        assert not review.passed
        assert review.content == text
        assert len(local.calls) == 1
    finally:
        dispatch.cleanup_worktree(wt)


@pytest.mark.parametrize('backend', ['codex', 'claude'])
def test_item3_should_hold_inherited_lease_through_repeated_cancellation(
    tmp_path, monkeypatch, backend,
):
    import threading

    from tools.mir_executor import executor
    local = hooks(tmp_path, LEASE)
    started, release = threading.Event(), threading.Event()
    monkeypatch.setattr(executor, '_guard_codex_main_worktree', lambda *a: None)
    selected = dispatch.AgentRoute('worker', backend, 'model', 'high', 'agent.md',
                                    'digest', 'instructions', 'workspace-write')
    api = executor.MirExecutor(tmp_path, agent_route=selected)
    def codex(*args):
        started.set()
        release.wait(3)
        return executor.SubprocessResult(0, '', '', 0, [])
    monkeypatch.setattr(api, '_run_codex_mcp_for_async', codex)
    class Process:
        returncode = None
        async def communicate(self, prompt):
            started.set()
            await asyncio.Future()
        def terminate(self):
            self.returncode = -15
        async def wait(self):
            await asyncio.to_thread(release.wait, 3)
            return self.returncode
    async def spawn(*args, **kwargs):
        return Process()
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    async def exercise():
        async def outer():
            with local_hooks.writer_scope(tmp_path):
                await api.run_agent_async(['task'])
        task = asyncio.create_task(outer())
        try:
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel()
            await asyncio.sleep(0.02)
            task.cancel()
            await asyncio.sleep(0.02)
            assert local.active, 'lease released before provider cleanup'
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(exercise())
    assert not local.active
