"""ADR-59 L1 chokepoint — codex-shim regression tests.

PRIMARY-PATH test: drive MirExecutor.run_codex with CODEX_BIN=shim +
a stub codex that exits with a known code + known stderr, then assert:
  - exactly ONE event row appended to tasks/codex-exec-events.jsonl
  - row has the matching exit_code
  - row has a non-empty error_sig (12 hex chars)
  - no shim recursion guard works (missing CODEX_REAL_BIN exits non-zero)
  - events file is created if it did not exist beforehand

Design ref: docs/decisions/adr-59-agent-execution-monitoring-2026-06-22.md
            section 5.1, section 13 row adr59-l1-chokepoint#unit
"""

from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import textwrap

import pytest

from tools.mir_executor.executor import MirExecutor

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SHIM = _REPO_ROOT / 'scripts' / 'codex-shim.sh'


def _make_stub_codex(tmp_path, exit_code, stderr_text):
    stub = tmp_path / 'stub_codex.sh'
    stub.write_text(
        textwrap.dedent(
            '#!/usr/bin/env sh\n'
            'if [ -n "${STUB_ARGS_FILE:-}" ]; then\n'
            '    printf \'%s\\n\' "$@" > "$STUB_ARGS_FILE"\n'
            'fi\n'
            "printf '%s\\n' '" + stderr_text + "' >&2\n"
            'exit ' + str(exit_code) + '\n'
        ),
        encoding='utf-8',
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _make_minimal_ledger(tmp_path):
    tasks_dir = tmp_path / 'tasks'
    tasks_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = tasks_dir / 'tdd.json'
    ledger = {
        'adr59-l1-chokepoint': {
            'description': 'stub entry for shim test',
            'categories': {
                'unit': {'status': 'planned', 'command': 'uv run pytest ...'}
            },
        }
    }
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding='utf-8')
    return ledger_path


def _read_events(events_file):
    return [
        json.loads(line)
        for line in events_file.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]


def _run_shim(tmp_path, args, *, include_real_binary=True):
    stub = _make_stub_codex(tmp_path, exit_code=0, stderr_text='')
    args_file = tmp_path / 'stub-args.txt'
    events_file = tmp_path / 'events.jsonl'
    env = {
        **os.environ,
        'CODEX_EVENTS_FILE': str(events_file),
        'STUB_ARGS_FILE': str(args_file),
    }
    if include_real_binary:
        env['CODEX_REAL_BIN'] = str(stub)
    result = subprocess.run(
        [str(_SHIM), *args],
        env=env,
        capture_output=True,
        text=True,
    )
    return result, args_file, events_file


class TestCodexShimPrimaryPath:
    def test_event_row_appended_with_exit_code_and_error_sig(self, tmp_path, monkeypatch):
        stub = _make_stub_codex(tmp_path, exit_code=7, stderr_text='stub-error-output')
        events_file = tmp_path / 'tasks' / 'codex-exec-events.jsonl'
        assert not events_file.exists()

        monkeypatch.setenv('CODEX_BIN', str(_SHIM))
        monkeypatch.setenv('CODEX_REAL_BIN', str(stub))
        monkeypatch.setenv('CODEX_EVENTS_FILE', str(events_file))

        ledger_path = _make_minimal_ledger(tmp_path)
        executor = MirExecutor(tmp_path, ledger_path=ledger_path)
        result = executor.run_codex(['mcp-server'])

        assert result.exit_code == 1
        assert 'Codex MCP server exited with code 7' in result.stderr
        assert events_file.exists()
        events = _read_events(events_file)
        assert len(events) == 1
        event = events[0]
        assert event['exit_code'] == 7
        assert event.get('error_sig')
        assert len(event['error_sig']) == 12

    def test_events_file_created_if_absent(self, tmp_path, monkeypatch):
        stub = _make_stub_codex(tmp_path, exit_code=0, stderr_text='')
        events_file = tmp_path / 'no_dir' / 'codex-exec-events.jsonl'
        assert not events_file.exists()

        monkeypatch.setenv('CODEX_BIN', str(_SHIM))
        monkeypatch.setenv('CODEX_REAL_BIN', str(stub))
        monkeypatch.setenv('CODEX_EVENTS_FILE', str(events_file))

        ledger_path = _make_minimal_ledger(tmp_path)
        executor = MirExecutor(tmp_path, ledger_path=ledger_path)
        executor.run_codex(['mcp-server'])
        assert events_file.exists()

    def test_no_shim_recursion(self, tmp_path, monkeypatch):
        events_file = tmp_path / 'tasks' / 'events.jsonl'
        result = subprocess.run(
            [str(_SHIM), 'mcp-server'],
            capture_output=True,
            text=True,
            env={
                'PATH': os.environ.get('PATH', ''),
                'HOME': os.environ.get('HOME', ''),
                'CODEX_EVENTS_FILE': str(events_file),
            },
        )
        assert result.returncode == 1
        assert 'CODEX_REAL_BIN is not set' in result.stderr
        events = _read_events(events_file)
        assert len(events) == 1
        assert events[0]['exit_code'] == 1
        assert len(events[0]['error_sig']) == 12

    def test_second_run_appends_second_row(self, tmp_path, monkeypatch):
        stub = _make_stub_codex(tmp_path, exit_code=0, stderr_text='run2')
        events_file = tmp_path / 'tasks' / 'events.jsonl'

        monkeypatch.setenv('CODEX_BIN', str(_SHIM))
        monkeypatch.setenv('CODEX_REAL_BIN', str(stub))
        monkeypatch.setenv('CODEX_EVENTS_FILE', str(events_file))

        ledger_path = _make_minimal_ledger(tmp_path)
        executor = MirExecutor(tmp_path, ledger_path=ledger_path)
        executor.run_codex(['mcp-server'])
        executor.run_codex(['mcp-server'])

        assert len(_read_events(events_file)) == 2


@pytest.mark.parametrize(
    'args',
    [
        pytest.param(['exec'], id='exec'),
        pytest.param(['e'], id='e'),
        pytest.param(['--model', 'gpt-5', 'exec'], id='global-option-before-exec'),
        pytest.param(['--model=gpt-5', 'e'], id='equals-option-before-e'),
    ],
)
@pytest.mark.parametrize('include_real_binary', [True, False])
def test_rejects_raw_exec_without_invoking_real_binary(
    tmp_path,
    args,
    include_real_binary,
):
    result, args_file, events_file = _run_shim(
        tmp_path,
        args,
        include_real_binary=include_real_binary,
    )

    assert result.returncode == 2
    assert result.stderr == (
        "[codex-shim] raw 'codex exec' and 'codex e' are prohibited; "
        'use MCP-backed dispatch.\n'
    )
    assert not args_file.exists()
    events = _read_events(events_file)
    assert len(events) == 1
    assert events[0]['exit_code'] == 2
    assert len(events[0]['error_sig']) == 12


@pytest.mark.parametrize('value', ['exec', 'e'])
def test_rejects_exact_token_used_as_separate_option_value(tmp_path, value):
    result, args_file, events_file = _run_shim(
        tmp_path,
        ['--profile', value, 'mcp-server'],
    )

    assert result.returncode == 2
    assert not args_file.exists()
    assert [event['exit_code'] for event in _read_events(events_file)] == [2]


@pytest.mark.parametrize('value', ['exec', 'e'])
def test_allows_equals_form_option_value_for_mcp_server(tmp_path, value):
    args = [f'--profile={value}', 'mcp-server']
    result, args_file, events_file = _run_shim(tmp_path, args)

    assert result.returncode == 0
    assert args_file.read_text(encoding='utf-8').splitlines() == args
    assert [event['exit_code'] for event in _read_events(events_file)] == [0]


def test_shim_is_executable_in_filesystem_and_git_index():
    assert os.access(_SHIM, os.X_OK)
    index_row = subprocess.run(
        ['git', 'ls-files', '-s', '--', 'scripts/codex-shim.sh'],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert index_row.split()[0] == '100755'
