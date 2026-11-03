"""Stdlib client for the pinned, repository-owned mir-executor.hooks@1 host."""
from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import queue
import signal
import subprocess
import threading
from typing import Any

PROTOCOL = 'mir-executor.hooks@1'
MAX_FRAME_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 64


class NativeHookError(RuntimeError):
    """A hook protocol or target-owned refusal prevented execution."""


def require_success(reply: dict) -> Any:
    if not reply['ok']:
        error = reply['error']
        # Preserve the target's type name in existing event diagnostics.
        cls = type(error['type'], (NativeHookError,), {})
        raise cls(error['message'])
    return reply['result']


def _validate(value: Any) -> None:
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH or (
            isinstance(item, (dict, list)) and depth >= MAX_JSON_DEPTH
        ):
            raise NativeHookError('native hook JSON depth exceeds limit')
        if isinstance(item, dict):
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            pending.extend((v, depth + 1) for v in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise NativeHookError('nonfinite native hook number')


def _frame(value: Any) -> bytes:
    _validate(value)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(data) >= MAX_FRAME_BYTES:
        raise NativeHookError('native hook frame too large')
    return data + b'\n'


class HookSession:
    """One sequential session; the deadline includes blocked pipe writes."""

    def __init__(self, root: pathlib.Path, config: dict, timeout: float = 10):
        from .local_hooks import _validate_native_hooks

        _validate_native_hooks(config)
        root = pathlib.Path(root).resolve()
        path = root
        for part in pathlib.Path(config['executable']).parts:
            path = path / part
            if path.is_symlink():
                raise NativeHookError('native hook path contains a symlink')
        if (not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()
                != config['sha256'].lower()):
            raise NativeHookError('native hook executable SHA-256 mismatch')
        self.hooks = config['hooks']
        self.timeout = timeout
        self.next_id = 1
        self.closed = False
        self.lock = threading.Lock()
        self.requests: queue.Queue = queue.Queue()
        self.responses: queue.Queue = queue.Queue()
        self.child = subprocess.Popen(
            [str(path), *config['argv']], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None, cwd=pathlib.Path.cwd(), start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
        )
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()
        try:
            hello = self._receive()
            actual = hello.get('hooks')
            if (hello.get('version') != PROTOCOL or not isinstance(actual, list)
                    or any(not isinstance(h, str) for h in actual)
                    or len(actual) != len(self.hooks) or set(actual) != set(self.hooks)):
                raise NativeHookError('invalid native hook hello')
        except BaseException:
            self.close()
            raise

    def _read(self) -> Any:
        data = self.child.stdout.readline(MAX_FRAME_BYTES + 1)
        if len(data) > MAX_FRAME_BYTES or len(data.rstrip(b'\n')) >= MAX_FRAME_BYTES:
            raise NativeHookError('native hook frame too large')
        if not data.endswith(b'\n'):
            raise NativeHookError('unexpected end of native hook frame')
        # Bound nesting before invoking the recursive JSON decoder.
        depth, quoted, escape = 0, False, False
        for byte in data:
            if quoted:
                if escape:
                    escape = False
                elif byte == 92:
                    escape = True
                elif byte == 34:
                    quoted = False
            elif byte == 34:
                quoted = True
            elif byte in (91, 123):
                depth += 1
                if depth > MAX_JSON_DEPTH:
                    raise NativeHookError('native hook JSON depth exceeds limit')
            elif byte in (93, 125):
                depth = max(depth - 1, 0)
        value = json.loads(data.decode('utf-8'))
        _validate(value)
        if not isinstance(value, dict):
            raise NativeHookError('invalid native hook envelope')
        return value

    def _work(self) -> None:
        try:
            self.responses.put(self._read())
            while (frame := self.requests.get()) is not None:
                self.child.stdin.write(frame)
                self.child.stdin.flush()
                self.responses.put(self._read())
        except Exception as exc:  # noqa: BLE001
            self.responses.put(exc)
        finally:
            self.child.stdin.close()
            self.child.stdout.close()

    def _receive(self) -> Any:
        try:
            value = self.responses.get(timeout=self.timeout)
        except queue.Empty:
            raise NativeHookError('native hook timeout') from None
        if isinstance(value, Exception):
            raise NativeHookError(str(value)) from value
        return value

    def call(self, hook: str, params: dict) -> dict:
        with self.lock:
            try:
                if self.closed:
                    raise NativeHookError('native hook session closed')
                if hook not in self.hooks and not (
                    hook in ('writer_enter', 'writer_exit') and 'writer_scope' in self.hooks
                ):
                    raise NativeHookError('unserved native hook')
                _validate(params)
                request_id = self.next_id
                if request_id >= 2**64:
                    raise NativeHookError('request id exhausted')
                self.next_id += 1
                self.requests.put(_frame({'version': PROTOCOL, 'id': request_id,
                                          'hook': hook, 'params': params}))
                reply = self._receive()
                ok = reply.get('ok')
                error = reply.get('error')
                if (reply.get('version') != PROTOCOL or type(reply.get('id')) is not int
                        or reply['id'] != request_id or type(ok) is not bool
                        or (ok and 'result' not in reply)
                        or (not ok and (not isinstance(error, dict)
                            or not isinstance(error.get('type'), str)
                            or not isinstance(error.get('message'), str)))):
                    raise NativeHookError('invalid native hook response')
                return reply
            except BaseException:
                self.close()
                raise

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.requests.put(None)
        if os.name != 'nt':
            try:
                os.killpg(self.child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                if self.child.poll() is None:
                    raise
        else:
            # Best effort system tree cleanup; unlike a Job Object this cannot
            # prevent descendants escaping before cleanup (see protocol docs).
            try:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.child.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=False, timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        try:
            self.child.kill()
        except ProcessLookupError:
            pass
        self.child.wait()
