"""Capture pinned schema readers in isolated roots; no network or database."""
import json
import subprocess
from pathlib import Path

scope = {"__file__": __file__}
exec(Path(__file__).with_name("generate_y_e13.py").read_text().split("resources =")[0], scope)
a, root, packages = (scope[k] for k in ("a", "root", "packages"))
wrapper = root / "capture.py"
wrapper.write_text('''import sys, pathlib, sysconfig, socket, json
root = pathlib.Path(__file__).resolve().parent
stdlib = sysconfig.get_path('stdlib')
sys.path[:] = [str(root / 'src'), str(root), stdlib, str(pathlib.Path(stdlib) / 'lib-dynload')]
from mir.core.adoption import boundary, slim
for name, module in list(sys.modules.items()):
    if name.split('.')[0] in PACKAGE_SET:
        paths = [module.__file__] if module.__file__ else module.__path__
        assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), name
def forbidden(*args, **kwargs):
    raise AssertionError('network forbidden')
socket.socket = forbidden
try:
    work = pathlib.Path.cwd()
    if sys.argv[1] == 'boundary':
        value = boundary.load_boundary(work)
    else:
        value = slim._load_payload(work, {'payload_manifest': 'config/p.json'})
    print(json.dumps({'value': value}))
except Exception as exc:
    print(json.dumps({'class': type(exc).__name__, 'message': str(exc)}))
'''.replace('PACKAGE_SET', repr(set(['mir', *packages]))))
records = []
for mode in ['boundary', 'payload']:
    base = dict(schema_version=1)
    base.update(dict(provider_markers=['a'], provider_text_markers=[]) if mode == 'boundary'
                else dict(files=[]))
    for case in ['absent', 'null', 'number', 'true', 'false', 'empty', 'object', 'required-ok',
                 'required-fail', 'type-fail', 'bad-schema', 'bad-json', 'missing',
                 'directory', 'bad-document', 'bad-version', 'unsupported',
                 'wide-error', 'unicode-error', 'invalid-required', 'empty-required']:
        value = dict(base)
        schema = None
        if case not in ['absent', 'null', 'number', 'bad-document', 'bad-version']:
            value['$schema'] = 's'
        if case in ['null', 'number']:
            value['$schema'] = None if case == 'null' else 3
        if case in ['required-fail', 'type-fail', 'wide-error', 'unicode-error']:
            value = {'schema_version': 1, '$schema': 's'}
        schemas = {'true': True, 'false': False, 'empty': {}, 'object': {'type': 'object'},
                   'required-ok': {'required': [
                       'provider_markers' if mode == 'boundary' else 'files']},
                   'required-fail': {'required': ['missing']},
                   'type-fail': {'type': 'array'}, 'bad-schema': {'type': 12},
                   'unsupported': {'properties': {'schema_version': {'const': 1}}},
                   'wide-error': {'required': ['x' * 80]},
                   'unicode-error': {'required': ['한']},
                   'invalid-required': {'required': [1]},
                   'empty-required': {'required': []}}
        if case in schemas:
            schema = json.dumps(schemas[case])
        if case == 'bad-json':
            schema = '{'
        if case == 'bad-version':
            value['schema_version'] = 2
        document = '{' if case == 'bad-document' else json.dumps(value)
        work = root / f'{mode}-{case}'
        (work / 'config').mkdir(parents=True, exist_ok=True)
        path = 'config/adopter-boundary.json' if mode == 'boundary' else 'config/p.json'
        (work / path).write_text(document)
        if schema is not None:
            (work / 'config/s').write_text(schema)
        if case == 'directory':
            (work / 'config/s').mkdir(exist_ok=True)
        out = subprocess.run([str(scope['sys'].executable), '-I', str(wrapper), mode],
                             cwd=work, env={'HOME': str(work), 'PATH': '/usr/bin:/bin'},
                             capture_output=True, check=True)
        result = json.loads(out.stdout.replace(str(work).encode(), b'{ROOT}'))
        assert not out.stderr, out.stderr
        records.append(dict(mode=mode, case=case, document=document, schema=schema,
                            refused=case in ['bad-schema', 'unsupported', 'type-fail', 'false',
                                            'wide-error', 'unicode-error',
                                            'invalid-required', 'empty-required'],
                            result=result))
assert 'value' in records[0]['result']
assert records[8]['result']['class'] == 'BoundaryError'
a.output.write_text('[\n' + ',\n'.join(json.dumps(r, sort_keys=True) for r in records) + '\n]\n')
