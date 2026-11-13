"""Try the pinned native executor before importing the Python executor.

Queries retain their buffered byte protocol. Mutations inherit the caller's
stdin/stdout/stderr, preserving live output and descriptor ordering. Exit 64 is
a decline only without an exact owned receipt in a private temporary directory.
The binary claims ownership before importing hooks, output, registry writes, or
provider launch; if the receipt cannot be written it exits 64 before any effect.
With an owned receipt every exit code, including 64, is final. Older binaries
that decline with 64 without a receipt fall back to Python, except status, result,
list-jobs, cancel, direct execute and sweep, which require native admission and
refuse without a Python fallback. Status/result/list-jobs/cancel and direct execute
ignore implementation selectors;
only codecs/handlers outside the native family
and configured legacy local hooks use the Python compatibility implementation.
Signals reach the
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
    if argv and argv[0] == 'policy-resolve':
        # Policy targets can differ from the provider holding the trusted pin.
        # Public policy CLI refuses unsupported syntax; it has no Python fallback.
        return _HOME_ROOT
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
    if (_status_requested(argv) or _status_requested(argv, "result")
            or _status_requested(argv, "list-jobs") or _status_requested(argv, "cancel")):
        return _native_status(argv)
    if (os.environ.get('MIR_EXECUTOR_IMPL') == 'python'
            or os.environ.get('MIR_EXECUTOR_QUERY_IMPL') == 'python'
            or os.environ.get('MIR_NATIVE_HOOKS') == '0'):
        return None
    try:
        if any(codecs.lookup(stream.encoding or '').name != 'utf-8'
               for stream in (sys.stdout, sys.stderr)):
            return None
        root = _query_root(argv)
        if root is None:
            return None
        pin = json.loads(_safe_path(_HOME_ROOT, QUERY_PIN).read_bytes())
        executable = _pinned_query(_HOME_ROOT, pin)
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
            except (ProcessLookupError, PermissionError):
                # macOS can report EPERM once the group has only zombie members.
                pass


def _native_command(argv: list[str], *, required: bool = False) -> int | None:
    remaining = list(argv)
    if remaining and remaining[0] == '--jobs-db':
        del remaining[:2]
    elif remaining and remaining[0].startswith('--jobs-db='):
        del remaining[0]
    if required:
        command = 'execute'
    elif not remaining or remaining[0] not in {'execute', 'cancel', 'resume', 'sweep'}:
        return None
    else:
        command = remaining[0]
    if not required and (os.environ.get('MIR_EXECUTOR_IMPL') == 'python'
            or os.environ.get(f'MIR_EXECUTOR_{command.upper()}_IMPL') == 'python'
            or (command == 'execute' and '--dispatch' in remaining[1:]
                and os.environ.get('MIR_EXECUTOR_DISPATCH_IMPL') == 'python')
            or os.environ.get('MIR_NATIVE_HOOKS') == '0'):
        return None
    try:
        if not required and any(codecs.lookup(stream.encoding or '').name != 'utf-8'
                                for stream in (sys.stdout, sys.stderr)):
            return None
        pin = json.loads(_safe_path(_HOME_ROOT, QUERY_PIN).read_bytes())
        executable = _pinned_query(_HOME_ROOT, pin)
        if executable is None:
            return None
        directory = tempfile.TemporaryDirectory(prefix='mir-executor-')
    except RecursionError:
        if not required:
            raise
        return None
    except (OSError, ValueError, TypeError, AttributeError, LookupError):
        return None
    with directory:
        receipt = pathlib.Path(directory.name) / 'owned'
        environment = dict(os.environ, MIR_EXECUTOR_OWNED_RECEIPT=str(receipt))
        environment.setdefault('MIR_EXECUTOR_PYTHON', sys.executable)
        if required:
            environment['MIR_EXECUTOR_ARGPARSE_PROG'] = os.path.basename(sys.argv[0])
            for name, stream in (('STDOUT', sys.stdout), ('STDERR', sys.stderr)):
                for attribute in ('encoding', 'errors'):
                    value = getattr(stream, attribute, None)
                    if value:
                        if attribute == 'encoding':
                            value = codecs.lookup(value).name
                        environment[f'MIR_EXECUTOR_{name}_{attribute.upper()}'] = value
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


def _command_arguments(argv: list[str]) -> list[str]:
    remaining = argv
    while remaining:
        option, separator, _ = remaining[0].partition('=')
        if option != '--' and option.startswith('--') and any(
                name.startswith(option) for name in ('--jobs-db', '--repo-root')):
            remaining = remaining[1 if separator else 2:]
        elif remaining[0].startswith('-'):
            remaining = remaining[1:]
        else:
            break
    return remaining


def _status_requested(argv: list[str], command: str = "status") -> bool:
    remaining = _command_arguments(argv)
    return bool(remaining and remaining[0] == command)


def _dispatch_requested(argv: list[str]) -> bool:
    remaining = _command_arguments(argv)
    if not remaining or remaining[0] != 'execute':
        return False
    options = remaining[1:]
    options = options[:options.index('--')] if '--' in options else options
    return '--dispatch' in options


def _status_codec_decline() -> bool:
    """Decline exactly streams outside the native codec/error-handler family."""
    encodings = {
        'utf-8', 'utf-8-sig', 'ascii', 'iso8859-1', 'cp1252',
        'utf-16', 'utf-16-le', 'utf-16-be', 'utf-32', 'utf-32-le', 'utf-32-be',
    }
    handlers = {
        'strict', 'ignore', 'replace', 'backslashreplace', 'xmlcharrefreplace',
        'surrogateescape', 'surrogatepass',
    }
    return any(codecs.lookup(getattr(stream, 'encoding', None) or 'utf-8').name
               not in encodings or (getattr(stream, 'errors', None) or 'strict')
               not in handlers for stream in (sys.stdout, sys.stderr))


def _python_local_hooks_disabled() -> bool:
    path = _HOME_ROOT / 'config/mir-executor.local.json'
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeError, ValueError, RecursionError):
        # Unparseable legacy data keeps the command's original lazy read point.
        return False
    if not isinstance(data, dict) or 'python_local_hooks' not in data:
        return False
    enabled = data['python_local_hooks']
    if not isinstance(enabled, bool):
        raise ValueError('python_local_hooks must be a boolean')
    if not (_HOME_ROOT / 'tools/mir_executor/local.py').is_file():
        raise ValueError('python_local_hooks requires tools/mir_executor/local.py')
    return not enabled


def _native_status(argv: list[str]) -> int:
    """Native status/result/list-jobs/cancel owns selectors, syntax, pin failures and exit 64."""
    command = next(name for name in ("status", "result", "list-jobs", "cancel")
                   if _status_requested(argv, name))
    try:
        pin = json.loads(_safe_path(_HOME_ROOT, QUERY_PIN).read_bytes())
        executable = _pinned_query(_HOME_ROOT, pin)
        if executable is not None:
            environment = dict(os.environ)
            environment['MIR_EXECUTOR_ARGPARSE_PROG'] = os.path.basename(sys.argv[0])
            environment.setdefault('MIR_EXECUTOR_PYTHON', sys.executable)
            for name, stream in (('STDOUT', sys.stdout), ('STDERR', sys.stderr)):
                for attribute in ('encoding', 'errors'):
                    value = getattr(stream, attribute, None)
                    if value:
                        if attribute == 'encoding':
                            value = codecs.lookup(value).name
                        environment[f'MIR_EXECUTOR_{name}_{attribute.upper()}'] = value
            result = subprocess.run(
                [str(executable), '--home-root', str(_HOME_ROOT), *argv],
                capture_output=True, check=False, env=environment,
            )
            if result.returncode != 64:
                _write_output(sys.stdout, result.stdout)
                _write_output(sys.stderr, result.stderr)
                return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except RecursionError:
        if command not in {'list-jobs', 'cancel'}:
            raise
    except (OSError, ValueError, TypeError, AttributeError, LookupError):
        pass
    print(f'[mir_executor] pinned native {command} unavailable or incompatible; '
          f'Python {command} is retired', file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if (_status_requested(argv) or _status_requested(argv, "result")
            or _status_requested(argv, "list-jobs") or _status_requested(argv, "cancel")):
        try:
            disabled = _python_local_hooks_disabled()
        except ValueError as error:
            sys.stderr.write(f'[mir_executor] native local policy configuration error: {error}\n')
            return 1
        if _status_codec_decline() or (
                (_HOME_ROOT / 'tools/mir_executor/local.py').exists()
                and not disabled):
            # LocalBridge redirects hook stdout to stderr and has no output frames.
            from tools.mir_executor.cli import main as python_main

            return python_main(argv)
        return _native_status(argv)
    if _status_requested(argv, 'execute') and not _dispatch_requested(argv):
        try:
            disabled = _python_local_hooks_disabled()
        except ValueError as error:
            sys.stderr.write(f'[mir_executor] native local policy configuration error: {error}\n')
            return 1
        if _status_codec_decline() or (
                (_HOME_ROOT / 'tools/mir_executor/local.py').exists()
                and not disabled):
            from tools.mir_executor.cli import main as python_main

            return python_main(argv)
        result = _native_command(argv, required=True)
        if result is None:
            print('[mir_executor] pinned native execute unavailable or incompatible; '
                  'Python execute is retired', file=sys.stderr)
            return 2
        return result
    remaining = argv
    if remaining and remaining[0] == '--jobs-db':
        remaining = remaining[2:]
    elif remaining and remaining[0].startswith('--jobs-db='):
        remaining = remaining[1:]
    if remaining and remaining[0] == 'sweep':
        result = _native_command(argv)
        if result is None:
            print('[mir_executor] pinned native sweep unavailable or incompatible; '
                  'Python sweep is retired', file=sys.stderr)
            return 2
        return result
    result = _native_query(argv)
    if result is None:
        result = _native_command(argv)
    if result is not None:
        return result
    from tools.mir_executor.cli import main as python_main

    return python_main(argv)
