"""W2-B30-F01: unmodified Python observations; never recapture from a port."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from mir.cli import _adoption_native as adoption
from mir.cli import _changes as changes
from mir.cli import capability
from mir.cli import project_hooks as hooks

FIXTURE = Path(__file__).parent / '../native/handoff-packet/tests/fixtures/w2/b30-capability.json'
TARGET = 'x86_64-unknown-linux-gnu'
DATA = b'fixture artifact\n'
REPLY = b'mir-project-hooks-v1\nmir-project-hooks-compact-v1\n'


def files(root):
    return {p.relative_to(root).as_posix(): p.read_text() for p in sorted(root.rglob('*'))
            if p.is_file() and not p.is_symlink()}


def environment(tmp, mode):
    pin = {'url': str(tmp / 'artifact'), 'size': len(DATA),
           'sha256': hashlib.sha256(DATA).hexdigest()}
    (tmp / 'artifact').write_bytes(DATA)
    record = {'plugin': 'mir-lifecycle-hooks', 'install_path': 'bin/project-hooks',
              'targets': {'x86_64-pc-windows-msvc' if mode == 'windows' else TARGET: pin}}
    metadata = {'schema_version': True if mode == 'bad-schema' else 1,
                'provider_revision': 'main' if mode == 'bad-identity' else 'a' * 40,
                'plugins': {'mir-lifecycle-hooks': {}},
                'native_artifacts': {'project-hooks': record}}
    if mode == 'no-pin':
        record['targets'] = {}
    provider = tmp / 'provider'
    (provider / '.mir').mkdir(parents=True)
    (provider / 'resources').mkdir()
    body = json.dumps(metadata)
    (provider / '.mir/capability-lock.json').write_text(body)
    (provider / 'resources/project-hooks-provider.json').write_text(body)
    root = tmp / 'project'
    root.mkdir()
    stack = contextlib.ExitStack()
    stack.enter_context(mock.patch.dict(os.environ, {}, clear=True))
    if mode in {'disabled', 'enabled'}:
        os.environ['MIR_CAPABILITY_NATIVE_ARTIFACTS'] = '0' if mode == 'disabled' else '1'
    target = {'unsupported': None, 'windows': 'x86_64-pc-windows-msvc'}.get(mode, TARGET)
    stack.enter_context(mock.patch.object(adoption.native, 'host_target', return_value=target))
    stack.enter_context(mock.patch.object(hooks.resources, 'files', return_value=provider))
    return root, provider, pin, stack


def native_case(operation, mode='normal'):
    def run(tmp):
        root, provider, pin, stack = environment(tmp, mode)
        with stack:
            kwargs = {'source_root': provider}
            name = {'evaluator': 'bootstrap-gate', 'runtime_verifier': 'runtime-verify',
                    'executor_query': 'executor-query', 'delegation_gate': 'delegation-gate',
                    'project_hooks': 'project-hooks'}[operation]
            if operation != 'project_hooks':
                lock = provider / '.mir/capability-lock.json'
                lock.write_text(lock.read_text().replace('project-hooks', name))
            destination = root / '.mir/bin' / name
            if mode in {'replace', 'failure', 'existing', 'linked'}:
                destination.parent.mkdir(parents=True)
                destination.write_bytes(DATA if mode == 'existing' else b'old')
                destination.chmod(0o755)
            if mode == 'linked':
                destination.unlink()
                destination.symlink_to(tmp / 'artifact')
            if mode == 'linked-parent':
                (tmp / 'elsewhere').mkdir()
                (root / '.mir').mkdir(exist_ok=True)
                (root / '.mir/bin').symlink_to(tmp / 'elsewhere', target_is_directory=True)
            if mode in {'local', 'empty-local', 'missing-local'}:
                kwargs['local_source'] = tmp / 'artifact'
                if mode == 'empty-local':
                    (tmp / 'artifact').write_bytes(b'')
                if mode == 'missing-local':
                    (tmp / 'artifact').unlink()
            if mode in {'bad-lock', 'missing-lock'}:
                lock = provider / '.mir/capability-lock.json'
                lock.write_text('{')
                if mode == 'missing-lock':
                    lock.unlink()
            if mode == 'failure':
                pin['sha256'] = '0' * 64
            if mode in {'failure', 'replace', 'existing', 'linked'}:
                kwargs = {'artifact_pin': pin}
            calls, replace = [], os.replace
            def atomic(source, dest):
                calls.append([Path(source).read_text(), Path(dest).exists()])
                return replace(source, dest)
            with mock.patch.object(adoption.os, 'replace', side_effect=atomic):
                result = getattr(adoption, 'install_' + operation)(root, **kwargs)
            return {'result': result, 'files': files(root), 'atomic': calls,
                    'dirs': sorted(p.relative_to(root).as_posix() for p in root.rglob('*')
                                   if p.is_dir())}
    return run


def hook_case(operation, mode='normal'):
    def run(tmp):
        root, provider, pin, stack = environment(tmp, mode)
        calls = []
        def fake(argv, **kwargs):
            calls.append({'argv': argv, **kwargs})
            if mode == 'missing':
                raise FileNotFoundError('synthetic missing binary')
            return subprocess.CompletedProcess(argv, int(mode == 'nonzero'),
                                               b'{}' if mode == 'json' else
                                               b'{' if mode == 'malformed' else
                                               b'mir-project-hooks-v1\n' if mode == 'one-token'
                                               else REPLY)
        with stack, mock.patch.object(hooks.subprocess, 'run', side_effect=fake):
            if operation == 'provider':
                return hooks._provider_pin()
            if operation == 'check' and mode != 'uninstalled':
                installed = adoption.install_project_hooks(root, artifact_pin=pin)
                hooks._write_receipt(root / '.mir/bin/project-hooks.json', installed)
                hooks._write_receipt(root / '.mir/bin/project-hooks.json', installed)
                binary = root / '.mir/bin/project-hooks'
                if mode == 'missing-binary':
                    binary.unlink()
                if mode == 'not-executable':
                    binary.chmod(0o644)
                if mode == 'bad-receipt':
                    (root / '.mir/bin/project-hooks.json').write_text('{}')
            if operation == 'path':
                (root / 'link').symlink_to(provider, target_is_directory=True)
                return str(hooks._path(root, 'link/x'))
            args = [operation, '--project-root', str(root)]
            if operation in {'help', 'invalid', 'empty'}:
                args = {'help': ['--help'], 'invalid': ['bad'], 'empty': []}[operation]
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = hooks.main(args)
                except SystemExit as exc:
                    code = exc.code
            return [code, out.getvalue(), err.getvalue(), files(root), calls]
    return run


def capability_case(command):
    def run(tmp):
        calls = []
        class Manager:
            def __init__(self, root, **kwargs):
                calls.append(['init', str(root), kwargs])
            def __getattr__(self, name):
                def call(*args, **kwargs):
                    calls.append([name, args, kwargs])
                    if command == 'error':
                        raise capability.CapabilityError('synthetic failure')
                    (tmp / 'written').write_text(name)
                    return {'query': name}
                return call
        args = [command, '--project-root', str(tmp), '--capability-home', str(tmp / 'home'),
                '--config', str(tmp / 'config'), '--json']
        for commands, extra in [(('sync', 'update', 'finalize', 'attest'), ['--apply']),
                                (('check', 'sync', 'update'), ['--profile', 'fixture', '--no-mcp']),
                                (('finalize',), ['--after-restart'])]:
            if command in commands:
                args += extra
        if command in {'attest', 'bad-evidence'}:
            evidence = tmp / 'evidence.json'
            evidence.write_text('{' if command == 'bad-evidence' else '{"pkg":true}')
            args[0] = 'attest'
            args += ['--runtime', 'codex-cli-desktop', '--observed-skill', 'p:s',
                     '--observed-hook', 'p:h', '--mcp-evidence', str(evidence)]
        if command == 'error':
            args[0] = 'status'
        if command in {'help', 'invalid', 'empty'}:
            args = {'help': ['--help'], 'invalid': ['bad'], 'empty': []}[command]
        if command == 'pretty':
            args = ['status', '--project-root', str(tmp)]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(capability, 'CapabilityManager', Manager), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = capability.main(args)
            except SystemExit as exc:
                code = exc.code
        return [code, out.getvalue(), err.getvalue(), files(tmp), calls]
    return run


def change_case(tmp):
    (tmp / 'a').write_text('before')
    (tmp / '.git').mkdir()
    (tmp / '.git/ignored').write_text('ignored')
    (tmp / 'link').symlink_to('a')
    before = changes.snapshot_project(tmp)
    (tmp / 'a').unlink()
    (tmp / 'z').write_text('after')
    after = changes.snapshot_project(tmp)
    return [before, after, changes.changed_paths(before, after)]


CASES = {f'native.{op}.{mode}': native_case(op, mode)
         for op in ('evaluator', 'runtime_verifier', 'executor_query',
                    'delegation_gate', 'project_hooks') for mode in ('normal', 'disabled')}
CASES.update({f'native.project_hooks.{mode}': native_case('project_hooks', mode)
              for mode in ('replace', 'failure', 'existing', 'linked', 'unsupported', 'windows',
                           'bad-lock', 'missing-lock', 'enabled', 'linked-parent')})
CASES.update({f'native.evaluator.{mode}': native_case('evaluator', mode)
              for mode in ('local', 'empty-local', 'missing-local', 'windows')})
CASES.update({f'hooks.{op}.{mode}': hook_case(op, mode) for op, modes in {
    'provider': ('normal', 'disabled', 'unsupported', 'bad-schema', 'bad-identity', 'no-pin'),
    'install': ('normal', 'nonzero', 'json', 'malformed', 'missing', 'one-token'),
    'check': ('normal', 'uninstalled', 'missing-binary', 'not-executable', 'bad-receipt'),
    'path': ('normal',),
    'help': ('normal',), 'invalid': ('normal',), 'empty': ('normal',),
}.items() for mode in modes})
CASES.update({f'capability.{cmd}': capability_case(cmd) for cmd in
              ('status', 'check', 'sync', 'update', 'finalize', 'attest', 'bad-evidence',
               'error', 'help', 'invalid', 'empty', 'pretty')})
CASES['changes.snapshot_and_diff'] = change_case


def receipt_failure(tmp):
    target = tmp / 'project-hooks.json'
    with mock.patch.object(Path, 'replace', side_effect=OSError('synthetic replace failure')):
        try:
            hooks._write_receipt(target, {'path': 'x', 'sha256': '0' * 64})
            outcome = 'written'
        except OSError as exc:
            outcome = ['OSError', str(exc)]
    return [outcome, sorted(p.name for p in tmp.iterdir())]


CASES['hooks.receipt_failure'] = receipt_failure


def observe(case, tmp):
    try:
        result = {'value': case(tmp)}
    except Exception as exc:  # noqa: BLE001 - freeze reference exception class and text
        result = {'error': [type(exc).__name__, str(exc)]}
    return json.loads(json.dumps(result, default=str).replace(str(tmp), '<tmp>'))


RECORDS = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize('name', sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
