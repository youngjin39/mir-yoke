"""Try the pinned native executor before importing the Python executor.

Queries retain their buffered byte protocol. Mutations inherit the caller's
stdin/stdout/stderr, preserving live output and descriptor ordering. Exit 64 is
a decline only without an exact owned receipt in a private temporary directory.
The binary claims ownership before importing hooks, output, registry writes, or
provider launch; if the receipt cannot be written it exits 64 before any effect.
With an owned receipt every exit code, including 64, is final. Older binaries
that decline with 64 without a receipt fall back to Python. Signals reach the
native process group on POSIX; Windows forwards console interrupts and always
terminates/reaps the direct child.
Like Python, interruption does not finalize a running background job's row.
"""
from __future__ import annotations

import codecs
import hashlib
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile

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
    if (os.environ.get('MIR_EXECUTOR_IMPL') == 'python'
            or os.environ.get('MIR_EXECUTOR_QUERY_IMPL') == 'python'
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


class _NativeSignal(BaseException):
    def __init__(self, number: int):
        self.number = number


def _interrupt_native(number, _frame):
    raise _NativeSignal(number)


def _stop_native(child, number: int) -> None:
    try:
        if os.name == 'posix':
            os.killpg(child.pid, number)
        elif number == signal.SIGINT:
            child.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            child.terminate()
    except (OSError, ValueError):
        # Console signal delivery can fail on Windows without an attached console.
        try:
            child.terminate()
        except OSError:
            pass
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            child.kill()
        except OSError:
            pass
        child.wait()
    finally:
        if os.name == 'posix':
            # The native process may have exited before its bridge/provider.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _native_command(argv: list[str]) -> int | None:
    remaining = list(argv)
    if remaining and remaining[0] == '--jobs-db':
        del remaining[:2]
    elif remaining and remaining[0].startswith('--jobs-db='):
        del remaining[0]
    if not remaining or remaining[0] not in {'execute', 'cancel', 'resume', 'sweep'}:
        return None
    command = remaining[0]
    if (os.environ.get('MIR_EXECUTOR_IMPL') == 'python'
            or os.environ.get(f'MIR_EXECUTOR_{command.upper()}_IMPL') == 'python'
            or (command == 'execute' and '--dispatch' in remaining[1:]
                and os.environ.get('MIR_EXECUTOR_DISPATCH_IMPL') == 'python')
            or os.environ.get('MIR_NATIVE_HOOKS') == '0'):
        return None
    try:
        if any(codecs.lookup(stream.encoding or '').name != 'utf-8'
               for stream in (sys.stdout, sys.stderr)):
            return None
        pin = json.loads(_safe_path(_HOME_ROOT, QUERY_PIN).read_bytes())
        executable = _pinned_query(_HOME_ROOT, pin)
        if executable is None:
            return None
        directory = tempfile.TemporaryDirectory(prefix='mir-executor-')
    except (OSError, ValueError, TypeError, AttributeError, LookupError):
        return None
    with directory:
        receipt = pathlib.Path(directory.name) / 'owned'
        environment = dict(os.environ, MIR_EXECUTOR_OWNED_RECEIPT=str(receipt))
        previous = {}
        child = None
        try:
            for number in (signal.SIGINT, signal.SIGTERM):
                previous[number] = signal.signal(number, _interrupt_native)
            # Flush parent buffers before sharing the descriptors with the child.
            sys.stdout.flush()
            sys.stderr.flush()
            try:
                child = subprocess.Popen(
                    [str(executable), '--home-root', str(_HOME_ROOT), *argv],
                    env=environment, start_new_session=os.name == 'posix',
                    creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0),
                )
            except OSError:
                return None  # Spawn failed before the binary could own anything.
            code = child.wait()
            if code == 64 and not (receipt.is_file() and receipt.read_bytes() == b'owned'):
                return None
            return code if code >= 0 else 128 - code
        except (KeyboardInterrupt, _NativeSignal) as error:
            number = error.number if isinstance(error, _NativeSignal) else signal.SIGINT
            # Ignore repeated interrupts while forwarding and reaping.
            for handled in previous:
                signal.signal(handled, signal.SIG_IGN)
            if child is not None:
                _stop_native(child, number)
            return 128 + number
        except BaseException:
            if child is not None:
                _stop_native(child, signal.SIGTERM)
            raise
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)


def _write_output(stream, data: bytes) -> None:
    stream.flush()
    if hasattr(stream, 'buffer'):
        stream.buffer.write(data)
    else:
        stream.write(data.decode('utf-8', errors='surrogateescape'))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    result = _native_query(argv)
    if result is None:
        result = _native_command(argv)
    if result is not None:
        return result
    from tools.mir_executor.cli import main as python_main

    return python_main(argv)
