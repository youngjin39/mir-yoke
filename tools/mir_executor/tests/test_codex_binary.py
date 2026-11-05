"""Shared Windows command-resolution fixtures, runnable on every host."""
import json
from pathlib import Path

import pytest

from tools.mir_executor.codex_mcp_client import resolve_codex_binary, windows_codex_binary

CASES = json.loads((Path(__file__).resolve().parents[3] /
                   'native/handoff-packet/tests/fixtures/codex-resolution.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['name'])
def test_windows_resolution(case):
    files = {name.lower() for name in case['files']}
    assert windows_codex_binary(case['path'], case['pathext'],
                                lambda name: name.lower() in files) == case['expected']


@pytest.mark.parametrize('override', [None, '', 'custom codex.cmd'])
@pytest.mark.parametrize('windows', [True, False])
def test_override_and_platform(override, windows):
    env = {'PATH': r'C:\npm', 'PATHEXT': '.CMD'}
    if override is not None:
        env['CODEX_BIN'] = override
    expected = override or (r'C:\npm\codex.CMD' if windows else 'codex')
    assert resolve_codex_binary(env, windows=windows, is_file=lambda _: True) == expected
    assert env.get('CODEX_BIN') == override
