"""Exercise Windows capture expansion without requiring a Windows host."""
import json

import pytest

from tests import test_policy_resolve_native_parity as policy
from tests.lifecycle_golden import GOLDEN, expand, unpack

WINDOWS_ROOT = r'C:\Users\runner\AppData\Local\Temp\x'


def test_every_json_input_survives_windows_expansion():
    count = 0
    for records in GOLDEN['records'].values():
        for record in records:
            try:
                json.loads(unpack(record['input']))
            except (ValueError, UnicodeDecodeError):
                continue
            expanded = expand(record['input'], WINDOWS_ROOT)
            json.loads(expanded)
            count += 1
    assert count > 1600


def test_nested_json_python_and_plain_paths():
    blob = {'text': json.dumps({'payload': json.dumps({'root': '@TMP@'})})}
    result = json.loads(expand(blob, WINDOWS_ROOT, context='json'))
    assert json.loads(result['payload'])['root'] == WINDOWS_ROOT
    source = {'text': "value = '{\"root\": \"@TMP@\"}'"}
    namespace = {}
    exec(expand(source, WINDOWS_ROOT, context='python'), namespace)
    assert json.loads(namespace['value'])['root'] == WINDOWS_ROOT
    nested = {'text': 'code = "path = \'@TMP@/file\'"'}
    exec(expand(nested, WINDOWS_ROOT, context='python'), namespace)
    exec(namespace['code'], namespace)
    assert namespace['path'] == WINDOWS_ROOT + '/file'
    plain = expand({'text': '@TMP@/file'}, WINDOWS_ROOT, context='plain')
    assert plain == (WINDOWS_ROOT + '/file').encode()
    malformed = expand({'text': '{"root":"@TMP@", bad}'}, WINDOWS_ROOT, context='json')
    assert malformed.endswith(b', bad}')


@pytest.mark.parametrize('platform,expected', [('posix', b'a\nb\n'), ('nt', b'a\r\nb\r\n')])
def test_policy_stream_expectation(platform, expected):
    assert policy.stream_expectation(b'a\nb\n', platform=platform) == expected


@pytest.mark.parametrize('node,suffix', [
    ('test_overlay_path_and_account_home[missing]', r'provider home\absent.json'),
    ('test_replay_adr88_missing_env_policy_file_falls_back_to_the_rendered_policy',
     r'retired\sub-agent-policy.global.json'),
])
def test_policy_frozen_warning_paths_use_platform_separator(node, suffix):
    record = policy.GOLDEN['cases']['tests/test_policy_resolve_native_parity.py::' + node][0]
    frozen = record['expected']['stderr']
    assert policy.frozen_expectation(frozen, WINDOWS_ROOT, WINDOWS_ROOT, platform='nt') == (
        '[mir policy] MIR_SUB_AGENT_POLICY names a missing file: ' + WINDOWS_ROOT + '\\'
        + suffix + '; falling back to the rendered policy\r\n').encode()
    assert policy.frozen_expectation(frozen, '/t', '/r', platform='posix') == (
        frozen.replace('${TMP}', '/t').encode())


@pytest.mark.parametrize('body_failed', [False, True])
def test_policy_call_count_enforced_only_after_passing_body(tmp_path, monkeypatch, body_failed):
    from types import SimpleNamespace
    node = SimpleNamespace(nodeid='synthetic')
    session = SimpleNamespace(testsfailed=0)
    request = SimpleNamespace(node=node, session=session)
    monkeypatch.setitem(policy.GOLDEN['cases'], 'synthetic', [{}])
    fixture = policy.frozen_oracle.__wrapped__(request, tmp_path, monkeypatch)
    next(fixture)
    if body_failed:
        session.testsfailed += 1
        with pytest.raises(StopIteration):
            next(fixture)
    else:
        with pytest.raises(AssertionError, match='calls were removed'):
            next(fixture)


def test_windows_workflow_uses_separate_locked_oracles():
    from pathlib import Path

    import yaml
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / '.github/workflows/validate.yml').read_text())
    steps = workflow['jobs']['windows_native']['steps']
    suite = next(s for s in steps
                 if 'tests/test_executor_query_native_parity.py' in s.get('run', ''))
    assert 'Python 3.12' in suite['name']
    assert suite['env']['UV_PROJECT_ENVIRONMENT'] == '.venv-312'
    assert '3.14' not in suite['run']
    assert suite['env']['PYTHONUTF8'] == '1'
    assert 'handoff-packet/target' in suite['env']['CARGO_TARGET_DIR']
    assert '!cancelled()' in suite['if']
    lock = next(s for s in steps if s.get('name') == 'Preflight uv lock (Python 3.12)')
    assert '--python 3.12' in lock['run'] and '--locked' in lock['run']
    assert lock['env']['UV_PROJECT_ENVIRONMENT'] == '.venv-312'
    current = next(s for s in steps
                   if 'tests/test_handoff_packet_native_parity.py' in s.get('run', ''))
    assert '--python 3.14' in current['run'] and 'Python 3.14' in current['name']
    assert '!cancelled()' in current['if']
    for job in ('native_handoff', 'windows_native'):
        assert any('tests/test_windows_parity_adapters.py' in step.get('run', '')
                   for step in workflow['jobs'][job]['steps'])


def test_windows_snapshot_expansion_preserves_serialization():
    from tests.lifecycle_golden import snapshot_context
    for records in GOLDEN['records'].values():
        for record in records:
            for name, blob in record['setup'].items():
                if 'directory' in blob or 'symlink' in blob:
                    continue
                context = snapshot_context(name)
                before = unpack(blob)
                after = expand(blob, WINDOWS_ROOT, context=context)
                if context == 'python':
                    compile(after, name, 'exec')
                elif context == 'json':
                    lines = zip(before.splitlines(), after.splitlines(), strict=True)
                    for original, expanded in lines:
                        try:
                            json.loads(original)
                        except (ValueError, UnicodeDecodeError):
                            with pytest.raises((ValueError, UnicodeDecodeError)):
                                json.loads(expanded)
                        else:
                            json.loads(expanded)
