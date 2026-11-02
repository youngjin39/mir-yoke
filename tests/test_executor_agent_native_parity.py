"""Exercise repository agent routes through the pinned, offline CLI boundary."""
from __future__ import annotations

import hashlib
import json
import os
import runpy
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PARITY = runpy.run_path(str(ROOT / 'tests/test_executor_execute_native_parity.py'))
SUPPORT = PARITY['SUPPORT']
DISPATCH = PARITY['DISPATCH']
binary = PARITY['binary']
decline_trace = PARITY['decline_trace']
trace_details = PARITY['trace_details']

CASES = ('codex', 'claude', 'dynamic', 'read_only', 'missing', 'resume',
         'command_precedence', 'malformed_frontmatter', 'opaque_brief',
         'hook_read_only', 'invalid_hook', 'forced_backend',
         'generated_read_only', 'invalid_sandbox', 'hook_policy_update')


def seed_agent(root, case):
    launcher, environment, arguments = DISPATCH['seed'](root, 'success', SUPPORT)
    for flag in ('--model', '--reasoning-effort'):
        offset = arguments.index(flag)
        del arguments[offset:offset + 2]
    (root / 'offline-policy.json').write_text(json.dumps({
        'mode': 'force_codex' if case == 'forced_backend' else 'select',
        'routing': {'default': {
            'model': 'policy-model', 'reasoning_effort': 'medium'}}}), encoding='utf-8')
    agent = 'offline-agent'
    definition = root / '.claude' / 'agents' / f'{agent}.md'
    definition.parent.mkdir(parents=True)
    backend = 'claude' if case in ('claude', 'forced_backend') else 'codex'
    definition.write_text(
        '---\nexecution_backend: ' + backend + '\nmodel: agent-model\neffort: high\n' +
        ('disallowedTools: "Write,\n  Edit"\n'
         if case in ('read_only', 'hook_read_only') else '') +
        '---\nOffline agent instructions.\n', encoding='utf-8')
    (root / 'brief.json').write_text(json.dumps({
        'expanded_goal': 'offline fixture', 'target_agent': agent}), encoding='utf-8')
    if case == 'missing':
        definition.unlink()
    elif case == 'malformed_frontmatter':
        definition.write_text('Missing frontmatter.\n', encoding='utf-8')
    elif case in ('dynamic', 'hook_read_only'):
        # Validation overrides the brief; the local route overrides the definition.
        (root / 'brief.json').write_text(json.dumps({
            'expanded_goal': 'offline fixture', 'target_agent': 'unused-agent'}),
            encoding='utf-8')
        with (root / 'tools' / 'mir_executor' / 'local.py').open('a', encoding='utf-8') as stream:
            stream.write(
                '\ndef validate_brief(*args):\n'
                "    return {'target_agent': 'offline-agent'}\n"
                'def resolve_agent_route(root, name):\n'
                '    from tools.mir_executor.dispatch import AgentRoute\n'
                "    assert name == 'offline-agent'\n"
                "    return AgentRoute(name, 'codex', 'hook-model', 'low',\n"
                "                      'offline-route', 'offline-digest',\n"
                "                      'Offline hook instructions.', 'workspace-write')\n")
    elif case == 'opaque_brief':
        with (root / 'tools' / 'mir_executor' / 'local.py').open('a', encoding='utf-8') as stream:
            stream.write(
                '\nfrom types import SimpleNamespace\n'
                "VALIDATED = SimpleNamespace(target_agent='offline-agent')\n"
                'def validate_brief(*args):\n'
                '    return VALIDATED\n'
                'def render_brief(value, root):\n'
                '    assert value is VALIDATED\n'
                "    record('rendered_opaque_brief')\n"
                "    return 'Rendered offline brief.'\n")
        (root / 'brief.json').write_text(json.dumps({
            'expanded_goal': 'offline fixture', 'target_agent': 'unused-agent'}),
            encoding='utf-8')
    elif case == 'invalid_hook':
        with (root / 'tools' / 'mir_executor' / 'local.py').open('a', encoding='utf-8') as stream:
            stream.write('\ndef resolve_agent_route(root, name):\n'
                         "    return {'execution_backend': 'codex'}\n")
    elif case == 'hook_policy_update':
        with (root / 'tools' / 'mir_executor' / 'local.py').open('a', encoding='utf-8') as stream:
            stream.write(
                '\ndef resolve_agent_route(root, name):\n'
                "    policy = root / 'offline-policy.json'\n"
                "    value = json.loads(policy.read_text(encoding='utf-8'))\n"
                "    value['routing']['default']['model'] = 'policy-after-hook'\n"
                "    policy.write_text(json.dumps(value), encoding='utf-8')\n"
                '    return None\n')
    elif case in ('generated_read_only', 'invalid_sandbox'):
        generated = root / '.codex' / 'agents' / f'{agent}.toml'
        generated.parent.mkdir(parents=True)
        generated.write_text('developer_instructions = "Generated offline instructions."\n'
                             'sandbox_mode = "' + ('read-only' if case == 'generated_read_only'
                                                   else 'invalid-mode') + '"\n',
                             encoding='utf-8')
    elif case == 'command_precedence':
        arguments += ['--model', 'command-model', '--reasoning-effort', 'low']

    server = DISPATCH['SERVER'].replace(
        "method = request.get('method')",
        "method = request.get('method')\n"
        "    with (root / 'provider-requests').open('a') as stream:\n"
        "        stream.write(json.dumps(request) + '\\n')")
    (root / 'server.py').write_text(server, encoding='utf-8')
    if launcher.suffix != '.cmd':
        launcher.write_text('#!/usr/bin/env python3\n' + server, encoding='utf-8')
    if case == 'claude':
        # Reuse the portable launcher setup, then record the actual adapter argv.
        import sys

        source = DISPATCH['CLAUDE_SERVER'].replace(
            'import os', 'import os\nimport json\nimport sys').replace(
                "Path('code.txt').write_text",
                "(root / 'provider-arguments').write_text(json.dumps(sys.argv[1:]))\n"
                "Path('code.txt').write_text")
        provider = root / 'claude-server.py'
        provider.write_text(source, encoding='utf-8')
        command = root / ('fake-claude.cmd' if os.name == 'nt' else 'fake-claude')
        command.write_text(f'@"{sys.executable}" "{provider}" %*\n' if os.name == 'nt'
                           else '#!/usr/bin/env python3\n' + source, encoding='utf-8')
        command.chmod(0o755)
        environment['CLAUDE_BIN'] = str(command)
    if case == 'resume':
        arguments = DISPATCH['resume'](root, 'current')
        with closing(sqlite3.connect(root / 'tasks' / 'jobs.db')) as connection, connection:
            options = json.loads(connection.execute(
                'SELECT dispatch_options_json FROM jobs').fetchone()[0])
            options['model'] = 'saved-model'
            options['reasoning_effort'] = 'low'
            connection.execute(
                'UPDATE jobs SET dispatch_options_json=?, target_agent=?, '
                'agent_definition_path=?',
                (json.dumps(options), 'previous-agent',
                 str(Path('.claude') / 'agents' / 'previous-agent.md')))
    return environment, arguments


@pytest.mark.parametrize('case', CASES)
def test_pinned_agent_dispatch_matches_python(binary, tmp_path, case):
    snapshots = []
    for implementation in ('python', 'native'):
        root = tmp_path / implementation
        environment, arguments = seed_agent(root, case)
        destination = root / '.mir' / 'bin' / binary.name
        destination.parent.mkdir(parents=True)
        shutil.copy2(binary, destination)
        (destination.parent / 'executor-query.json').write_text(json.dumps({
            'path': destination.relative_to(root).as_posix(),
            'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
        }), encoding='utf-8')
        for selector in ('MIR_EXECUTOR_IMPL', 'MIR_EXECUTOR_EXECUTE_IMPL',
                         'MIR_EXECUTOR_DISPATCH_IMPL', 'MIR_EXECUTOR_RESUME_IMPL',
                         'MIR_NATIVE_HOOKS'):
            environment.pop(selector, None)
        if implementation == 'python':
            environment['MIR_EXECUTOR_IMPL'] = 'python'
        result = PARITY['invoke_pinned'](root, environment, arguments, capture_output=True)
        snapshot = DISPATCH['snapshot'](root, result)
        snapshots.append(snapshot)
        if case in ('malformed_frontmatter', 'invalid_hook', 'invalid_sandbox'):
            assert result.returncode == 1, (result.stderr, trace_details())
            assert {'malformed_frontmatter': b'leading frontmatter',
                    'invalid_hook': b'invalid route for target agent',
                    'invalid_sandbox': b'invalid sandbox_mode'}[case] in result.stderr, (
                trace_details()
            )
            assert not (root / 'provider-methods').exists(), trace_details()
            assert not (root / 'tasks' / 'jobs.db').exists(), trace_details()
            continue
        assert (root / 'native-owned').exists() == (implementation == 'native'), (
            (result.stderr, trace_details())
        )
        assert result.returncode == 0, ((result.stdout, result.stderr), trace_details())
        read_only = case in ('read_only', 'hook_read_only', 'generated_read_only')
        assert snapshot['code_text'] == ('initial\n' if read_only
                                         else 'delegated change\n'), trace_details()
        with closing(sqlite3.connect(root / 'tasks' / 'jobs.db')) as connection:
            metadata = connection.execute(
                'SELECT execution_backend,resolved_model,resolved_reasoning_effort,status '
                'FROM jobs').fetchone()
        model = {'claude': 'agent-model', 'dynamic': 'hook-model', 'hook_read_only': 'hook-model',
                 'command_precedence': 'command-model', 'resume': 'saved-model',
                 'hook_policy_update': 'policy-after-hook'}.get(
                     case, 'policy-model')
        effort = ('low' if case in ('dynamic', 'hook_read_only', 'command_precedence', 'resume')
                  else 'medium' if case in ('missing', 'forced_backend') else 'high')
        assert metadata[:3] == ('claude' if case == 'claude' else 'codex', model, effort), (
            trace_details()
        )
        assert metadata[3] == 'completed', trace_details()
        if case == 'missing':
            assert b'no definition for target agent' in result.stderr, trace_details()
        if case == 'opaque_brief':
            assert 'rendered_opaque_brief' in snapshot['events'], trace_details()
        if case == 'resume':
            with closing(sqlite3.connect(root / 'tasks' / 'jobs.db')) as connection:
                assert connection.execute(
                    'SELECT target_agent,agent_definition_path FROM jobs').fetchone() == (
                        'previous-agent', str(Path('.claude') / 'agents' / 'previous-agent.md')), (
                    trace_details()
                )
        if case == 'claude':
            argv = json.loads((root / 'provider-arguments').read_text())
            assert argv[:6] == ['--agent', 'offline-agent', '--model', model,
                               '--effort', effort], trace_details()
        else:
            requests = [json.loads(line) for line in
                        (root / 'provider-requests').read_text().splitlines()]
            thread = next(item['params'] for item in requests
                          if item.get('method') == 'thread/start')
            assert thread['model'] == model, trace_details()
            assert thread['sandbox'] == ('read-only' if read_only
                                         else 'workspace-write'), trace_details()
            if case != 'missing':
                assert thread['baseInstructions'] == (
                    'Offline hook instructions.' if case in ('dynamic', 'hook_read_only')
                    else 'Generated offline instructions.' if case == 'generated_read_only'
                    else 'Offline agent instructions.'), trace_details()
            assert thread['config']['model_reasoning_effort'] == effort, trace_details()
    assert snapshots[0] == snapshots[1], trace_details()
