"""Capture selected real hooks read-only in a disposable synthetic repository.

Intent authority is the externally supplied Y2b-2 brief. Capture precedes native
resume-fill implementation. Audit and budget callbacks are outside this slice.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import pathlib
import runpy
import sys
import unicodedata

import pydantic

BASE = runpy.run_path(str(pathlib.Path(__file__).with_name('generate_executor_hub_profile.py')))


def capture(owner, scratch):
    paths = {'local': owner / 'tools/mir_executor/local.py',
             'contracts': owner / 'src/mir/core/contracts/dispatch_brief.py',
             'loader': owner / 'src/mir/core/conductor/dispatch_brief.py'}
    sources = {key: path.read_text() for key, path in paths.items()}
    oracle = ('from __future__ import annotations\nimport argparse\nimport json\n'
              'import pathlib\nimport shlex\nimport sys\nimport hashlib\nimport tomllib\n'
              'from contextvars import ContextVar\n'
              'from tools.mir_executor import cli, policy\n'
              'from tools.mir_executor.dispatch import AgentRoute\n'
              'from tools.mir_executor.local_hooks import local_config\n'
              '_REQUESTED_BACKEND = ContextVar("requested_backend", default=None)\n' +
              sources['contracts'].replace('from __future__ import annotations', '') + '\n' +
              'DispatchBrief.__module__ = "mir.core.contracts.dispatch_brief"\n' +
              BASE['functions'](sources['loader'], {'load_dispatch_brief'}).replace(
                  'path: Path', 'path: pathlib.Path') + '\n' +
              BASE['functions'](sources['local'], {'validate_brief', 'resolve_agent_route',
                                                 'pre_execute',
                                                 '_fill_resume_scope', '_resume_allowlist'}) +
              '\nimport types\n_loader = types.ModuleType("mir.core.conductor.dispatch_brief")\n'
              '_loader.load_dispatch_brief = load_dispatch_brief\n'
              'sys.modules[_loader.__name__] = _loader\n')
    namespace = {}
    exec(oracle, namespace)
    namespace['DispatchBrief'].model_rebuild(_types_namespace=namespace)
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / 'config').mkdir(exist_ok=True)
    verifiers = {'offline': ['check'], 'last': ['check'], 'literal': ['other']}
    (scratch / 'config/mir-executor.local.json').write_text(json.dumps({'verifiers': verifiers}))
    cases = []
    variants = [('concrete', ['code.txt']),
                ('convert_order', [' src/** ', 'code.txt', 'src/**', 'src/']),
                *[(f'path_{index}', [value]) for index, value in enumerate([
                    '', ' ', '<unspecified>', '.', '..', '/abs', '../x', 'x/../y',
                    'C:/code', 'C:code', '//host/share/code', '\\\\host\\share\\code',
                    'code\\file', 'code/*', 'code/?', 'code/[ab]', '/**',
                    './', './code', 'x//y', 'é/**', "a'b*", '\x1ccode\x1c',
                    '1:code', 'é:code', '::code', '\u3000code\u3000', '\x85code'])],
                ('empty_scope', []), ('empty_commands', ['code.txt']),
                ('blank_commands', ['code.txt']), ('malformed', ['code.txt']),
                ('missing', ['code.txt']), ('invalid_schema', ['code.txt']),
                ('nonmapping', ['code.txt'])]
    for name, scope in variants:
        for state in ('absent', 'empty', 'supplied', 'paths_only', 'commands_only'):
            for resume in (False, True):
                payload = BASE['brief_payload']()
                payload['owned_scope'] = scope
                payload['verification_commands'] = [
                    'check', 'literal', "'check'", "'open", 'unknown']
                if name == 'empty_commands':
                    payload['verification_commands'] = []
                if name == 'blank_commands':
                    payload['verification_commands'] = [' \t']
                if name == 'invalid_schema':
                    payload.pop('user_intent')
                path = scratch / 'brief.json'
                raw = '{bad' if name == 'malformed' else (
                    '[]' if name == 'nonmapping' else json.dumps(payload))
                path.write_text(raw)
                if name == 'missing':
                    path.unlink()
                args = dict(dispatch=True, dispatch_brief=str(path),
                            execution_backend='claude' if state == 'supplied' else 'codex')
                if resume:
                    args['resume_job_id'] = 'restored-job'
                if state != 'absent':
                    args.update(allow_paths=[] if state == 'empty' else ['supplied/'],
                                verify_cmds=[] if state == 'empty' else ['check'])
                if state == 'paths_only':
                    args.pop('verify_cmds')
                if state == 'commands_only':
                    args.pop('allow_paths')
                argument = argparse.Namespace(**args)
                stderr = io.StringIO()
                outcome = {}
                with contextlib.redirect_stderr(stderr):
                    try:
                        namespace['pre_execute'](argument, scratch)
                    except (Exception, SystemExit) as error:
                        outcome = dict(kind=type(error).__name__, message=str(error))
                def normalized(value):
                    return json.loads(json.dumps(value).replace(str(scratch), '<root>'))
                cases.append(dict(name=f'{name}-{state}-{"resume" if resume else "initial"}',
                                  raw=raw, missing=name == 'missing', args=normalized(args),
                                  patch=normalized(vars(argument)),
                                  stderr=stderr.getvalue().replace(
                                      str(scratch), '<root>'), requested_backend=namespace[
                                          '_REQUESTED_BACKEND'].get(), **outcome))
    return dict(runtime=dict(python=sys.version.split()[0], pydantic=pydantic.__version__,
                             unicode=unicodedata.unidata_version),
                sha256={key: hashlib.sha256(path.read_bytes()).hexdigest()
                        for key, path in paths.items()}, oracle_source=oracle,
                verifiers=verifiers, cases=cases)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner', required=True, type=pathlib.Path)
    parser.add_argument('--scratch', required=True, type=pathlib.Path)
    parser.add_argument('--output', required=True, type=pathlib.Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(capture(args.owner, args.scratch), indent=2) + '\n')


if __name__ == '__main__':
    main()
