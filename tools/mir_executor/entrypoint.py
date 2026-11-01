"""Try an installed, pinned query reader before importing the Python executor."""
from __future__ import annotations

import codecs
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

_HOME_ROOT = pathlib.Path(__file__).resolve().parents[2]
QUERY_PIN = '.mir/bin/executor-query.json'


def _query_root(argv: list[str]) -> pathlib.Path | None:
    """Recognize only the exact common query options; leave all parsing to Python otherwise."""
    remaining = list(argv)
    if remaining and remaining[0] == '--jobs-db':
        if len(remaining) < 3:
            return None
        del remaining[:2]
    elif remaining and remaining[0].startswith('--jobs-db='):
        del remaining[0]
    if not remaining or remaining.pop(0) not in {'status', 'result', 'list-jobs'}:
        return None
    root = pathlib.Path.cwd()
    seen = set()
    while remaining:
        option, separator, value = remaining.pop(0).partition('=')
        if option not in {'--repo-root', '--job-id', '--status', '--jobs-db'} or option in seen:
            return None
        seen.add(option)
        if not separator:
            if not remaining:
                return None
            value = remaining.pop(0)
        if option == '--repo-root':
            root = pathlib.Path(value)
    return root.resolve()


def _safe_path(root: pathlib.Path, relative: str) -> pathlib.Path:
    path = root
    for part in pathlib.PurePosixPath(relative).parts:
        path /= part
        if path.is_symlink():
            raise ValueError('linked native query path')
    return path


def _pinned_query(root: pathlib.Path, pin: object) -> pathlib.Path | None:
    if not isinstance(pin, dict) or set(pin) != {'path', 'sha256'}:
        return None
    relative, digest = pin['path'], pin['sha256']
    if (relative not in {'.mir/bin/executor-query', '.mir/bin/executor-query.exe'}
            or not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None):
        return None
    executable = _safe_path(root, relative)
    if not executable.is_file() or hashlib.sha256(executable.read_bytes()).hexdigest() != digest:
        return None
    return executable


def _native_query(argv: list[str]) -> int | None:
    if (os.environ.get('MIR_EXECUTOR_QUERY_IMPL') == 'python'
            or os.environ.get('MIR_NATIVE_HOOKS') == '0'):
        return None
    try:
        if any(codecs.lookup(stream.encoding or '').name != 'utf-8'
               for stream in (sys.stdout, sys.stderr)):
            return None
        root = _query_root(argv)
        if root is None or root != _HOME_ROOT:
            return None
        pin = json.loads(_safe_path(root, QUERY_PIN).read_bytes())
        executable = _pinned_query(root, pin)
        if executable is None:
            return None
        result = subprocess.run(
            [str(executable), '--home-root', str(_HOME_ROOT), *argv],
            capture_output=True, check=False,
        )
    except (OSError, ValueError, TypeError, AttributeError, LookupError):
        return None
    if result.returncode == 64:
        return None
    _write_output(sys.stdout, result.stdout)
    _write_output(sys.stderr, result.stderr)
    return result.returncode


def _write_output(stream, data: bytes) -> None:
    stream.flush()
    if hasattr(stream, 'buffer'):
        stream.buffer.write(data)
    else:
        stream.write(data.decode('utf-8', errors='surrogateescape'))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    result = _native_query(argv)
    if result is not None:
        return result
    from tools.mir_executor.cli import main as python_main

    return python_main(argv)
