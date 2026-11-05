"""Capture real owner hooks and contracts without writing to the owner checkout."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import runpy
import sys
import types
import unicodedata

import pydantic


def functions(source, names):
    tree = ast.parse(source)
    return '\n\n'.join(ast.get_source_segment(source, node)
                        for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name in names)


def brief_payload(goal='offline fixture'):
    return dict(version=1, task_id='task', slice_id='slice', target_agent='offline-agent',
                user_intent='Update the owned file.', expanded_goal=goal,
                owned_scope=['code.txt'], verification_commands=['offline'],
                stop_conditions=['Stop outside scope.'],
                resume_state_ref='tasks/dispatch/task/slice.json',
                source_refs=dict(task_spec='runtime://task', phase='tasks/phase.json'))


def capture(owner, scratch):
    paths = {
        'local': owner / 'tools/mir_executor/local.py',
        'contracts': owner / 'src/mir/core/contracts/dispatch_brief.py',
        'loader': owner / 'src/mir/core/conductor/dispatch_brief.py',
    }
    sources = {key: path.read_text(encoding='utf-8') for key, path in paths.items()}
    contract = runpy.run_path(str(paths['contracts']))
    loader = types.ModuleType('mir.core.conductor.dispatch_brief')
    loader.__dict__.update(Path=pathlib.Path, Any=object, json=json,
                           DispatchBrief=contract['DispatchBrief'])
    load_source = functions(sources['loader'], {'load_dispatch_brief'})
    exec(load_source, loader.__dict__)
    prior = sys.modules.get(loader.__name__)
    sys.modules[loader.__name__] = loader
    scratch.mkdir(parents=True, exist_ok=True)
    config = scratch / 'config'
    config.mkdir(exist_ok=True)
    hook = runpy.run_path(str(paths['local']))
    cases = []
    try:
        for name, text, limit, file_input in [
            ('file_larger_than_goal', 'éé', 4, True),
            ('goal_below', 'éa', 4, True),
            ('goal_equal', 'éé', 4, True),
            ('goal_above', 'ééa', 4, True),
            ('plain_below', 'éa', 4, False),
            ('plain_equal', 'éé', 4, False),
            ('plain_above', 'ééa', 4, False),
            ('plain_late_above', 'ééa', 4.0, False),
            ('schema_before_bound', 'ééa', 1, True),
            ('limit_zero', 'a', 0, True),
            ('limit_negative', 'a', -1, True),
            ('limit_float_equal', 'éé', 4.0, True),
            ('limit_float_above', 'ééa', 4.0, True),
            ('limit_bool', 'é', True, True),
            ('limit_null', 'a', None, True),
            ('limit_missing', 'a', 'missing', True),
            ('limit_string', 'a', '4', True),
        ]:
            configuration = {} if name == 'limit_missing' else {'input_limit_bytes': limit}
            (config / 'mir-executor.local.json').write_text(json.dumps(configuration))
            payload = brief_payload(text) if file_input else None
            if name == 'schema_before_bound':
                payload.pop('user_intent')
            argument = text
            payload_text = None
            if file_input:
                argument = scratch / 'brief.json'
                payload_text = json.dumps(payload, ensure_ascii=True, indent=2)
                argument.write_text(payload_text)
            try:
                value = hook['validate_brief'](argument, scratch)
                outcome = {'value': value.model_dump(mode='json') if value is not None else None}
            except Exception as error:
                outcome = {'kind': type(error).__name__, 'message': str(error)}
            cases.append(dict(name=name, text=text, limit=limit, payload=payload,
                              payload_text=payload_text, **outcome))
        identity = []
        # Use actual importlib.metadata discovery against synthetic distribution evidence.
        sys.path.insert(0, str(scratch))
        try:
            for version in ['9.8.7+fixture', '한글-é', None]:
                dist = scratch / 'mir_agent_hub-9.8.7.dist-info'
                dist.mkdir(exist_ok=True)
                metadata = dist / 'METADATA'
                if version is None:
                    metadata.unlink()
                    dist.rmdir()
                else:
                    metadata.write_text(
                        f'Metadata-Version: 2.1\nName: mir-agent-hub\nVersion: {version}\n')
                for dispatch in (True, False):
                    for model in (None, '', '모델-é'):
                        prompt = 'exact café 한글 😀\nwith trailing space '
                        value = hook['job_identity'](argparse.Namespace(dispatch=dispatch),
                                                     scratch, prompt, model)
                        identity.append(dict(dispatch=dispatch, model=model, prompt=prompt,
                                             version=version or 'unknown', value=value))
        finally:
            sys.path.remove(str(scratch))
    finally:
        if prior is None:
            sys.modules.pop(loader.__name__)
        else:
            sys.modules[loader.__name__] = prior
    # Ship only the selected owner hooks, retaining their exact Python semantics.
    oracle = ('from __future__ import annotations\nimport argparse\nimport hashlib\n'
              'import importlib.metadata\nimport json\nimport pathlib\n'
              'from tools.mir_executor.local_hooks import local_config\n' +
              sources['contracts'].replace('from __future__ import annotations', '') + '\n' +
              load_source.replace('path: Path', 'path: pathlib.Path') + '\n' +
              functions(sources['local'],
                        {'validate_brief', '_require_input_bound', 'job_identity'}))
    # Bind the captured real loader through its original import name.
    oracle += ('\nimport sys\nimport types\n'
               '_loader = types.ModuleType("mir.core.conductor.dispatch_brief")\n'
               '_loader.load_dispatch_brief = load_dispatch_brief\n'
               'sys.modules[_loader.__name__] = _loader\n')
    return dict(runtime={'python': sys.version.split()[0], 'pydantic': pydantic.__version__,
                         'unicode': unicodedata.unidata_version},
                sha256={key: hashlib.sha256(path.read_bytes()).hexdigest()
                       for key, path in paths.items()}, oracle_source=oracle,
                brief_cases=cases, identity_cases=identity)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner', type=pathlib.Path, required=True)
    parser.add_argument('--scratch', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(capture(args.owner, args.scratch), indent=2,
                                     ensure_ascii=True) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
