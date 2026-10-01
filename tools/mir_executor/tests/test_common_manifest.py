"""Portable drift check: no provider checkout or executor imports required."""
from __future__ import annotations

import hashlib
import json
import pathlib


def test_should_match_common_manifest():
    root = pathlib.Path(__file__).resolve().parents[3]
    path = root / 'tools/mir_executor/COMMON_MANIFEST.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    assert manifest['version'] == 1
    assert isinstance(manifest['source_commit'], str) and manifest['source_commit']
    assert manifest['files'], 'Common manifest must not be empty'
    assert 'tools/mir_executor/tests/test_common_manifest.py' in manifest['files']
    for name, expected in manifest['files'].items():
        relative = pathlib.PurePosixPath(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        assert relative.is_relative_to(pathlib.PurePosixPath('tools/mir_executor'))
        assert relative.name != 'local.py'
        assert not relative.is_relative_to(pathlib.PurePosixPath('tools/mir_executor/tests/local'))
        current = root
        for part in relative.parts:
            current = current / part
            assert not current.is_symlink(), f'Common symlink: {name}'
        actual = hashlib.sha256(current.read_bytes()).hexdigest()
        assert actual == expected, f'Common executor drift: {name}'
