"""Optional repository-owned extension hooks for the common executor."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import pathlib
import subprocess
import sys
import uuid
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from types import ModuleType
from typing import Any

_MODULES: dict[pathlib.Path, tuple[int, int, ModuleType]] = {}


def _validate_native_hooks(value: Any) -> None:
    """Validate the native-only transport declaration without launching a host."""
    fields = {'executable', 'argv', 'sha256', 'hooks'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('native_policy.hooks requires exactly executable, argv, sha256, hooks')
    executable = value['executable']
    if (not isinstance(executable, str) or not executable or '\0' in executable
            or pathlib.Path(executable).anchor
            or '..' in pathlib.Path(executable).parts
            or any(part in ('.', '..') for part in (
                executable.replace('\\', '/') if sys.platform == 'win32' else executable
            ).split('/'))):
        raise ValueError('native_policy.hooks.executable must be a repository-relative path '
                         'without dot components or NUL')
    argv = value['argv']
    if (not isinstance(argv, list)
            or any(not isinstance(item, str) or '\0' in item for item in argv)):
        raise ValueError('native_policy.hooks.argv must be a string array without NUL')
    digest = value['sha256']
    if (not isinstance(digest, str) or len(digest) != 64
            or any(char not in '0123456789abcdefABCDEF' for char in digest)):
        raise ValueError('native_policy.hooks.sha256 must contain 64 hexadecimal characters')
    hooks = value['hooks']
    if (not isinstance(hooks, list) or not hooks
            or any(name not in ('writer_scope', 'on_job_event') for name in hooks)
            or len(set(hooks)) != len(hooks)):
        raise ValueError('native_policy.hooks.hooks must contain unique writer_scope '
                         'and/or on_job_event names')


def local_config(repo_root: pathlib.Path) -> dict[str, Any]:
    """Read repository data; absence means common defaults, malformed data fails."""
    path = pathlib.Path(repo_root) / 'config/mir-executor.local.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'{path} must contain a JSON object')
    native = data.get('native_policy')
    if isinstance(native, dict) and 'hooks' in native:
        _validate_native_hooks(native['hooks'])
    return data


def _api_policy(repo_root: pathlib.Path, *, ownership: bool = True) -> dict | None:
    config = local_config(repo_root)
    native = config.get('native_policy')
    if 'native_policy' not in config:
        return None
    if (not isinstance(native, dict) or type(native.get('version')) is not int
            or native['version'] != 1 or set(native) - {'version', 'hooks'}):
        raise ValueError('Python executor APIs support only native_policy version 1 hooks; '
                         'use the native executor for other native_policy sections')
    hooks = native.get('hooks')
    if hooks is not None and ownership:
        module = _module(repo_root)
        for name in hooks['hooks']:
            if module is not None and getattr(module, name, None) is not None:
                raise ValueError(f'{name} is also present in local.py')
    return hooks


def guard_python_api(repo_root: pathlib.Path) -> None:
    """Reject unsupported target and invoking-home policy before API effects."""
    root = pathlib.Path(repo_root).resolve()
    _api_policy(root, ownership=False)
    home = pathlib.Path(__file__).resolve().parents[2]
    if home != root:
        result = subprocess.run(['git', '-C', str(home), 'rev-parse', '--show-toplevel'],
                                capture_output=True, text=True, check=False)
        if result.returncode == 0 and pathlib.Path(result.stdout.strip()).resolve() == home:
            _api_policy(home, ownership=False)
    _api_policy(root)


def _module(repo_root: pathlib.Path) -> ModuleType | None:
    path = pathlib.Path(repo_root).resolve() / 'tools/mir_executor/local.py'
    if not path.exists():
        return None
    stat = path.stat()
    cached = _MODULES.get(path)
    if cached is not None and cached[:2] == (stat.st_mtime_ns, stat.st_size):
        return cached[2]
    name = 'tools.mir_executor._local_' + hashlib.sha256(str(path).encode()).hexdigest()
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load executor hooks: {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    _MODULES[path] = (stat.st_mtime_ns, stat.st_size, module)
    return module


def has_hook(repo_root: pathlib.Path, name: str) -> bool:
    module = _module(repo_root)
    return module is not None and getattr(module, name, None) is not None


def invoke_hook(repo_root: pathlib.Path, name: str, *args: Any, **kwargs: Any) -> Any:
    """Call a declared local hook; a missing hook returns None."""
    module = _module(repo_root)
    hook = getattr(module, name, None) if module is not None else None
    if hook is None:
        return None
    if not callable(hook):
        raise TypeError(f'Executor local hook {name!r} must be callable')
    return hook(*args, **kwargs)


def authorize_target(target_root: pathlib.Path, args: Any) -> None:
    """Consult only the invoking package's Git root for cross-repository admission."""
    home_root = pathlib.Path(__file__).resolve().parents[2]
    target_root = pathlib.Path(target_root).resolve()
    if home_root == target_root:
        return
    result = subprocess.run(
        ['git', '-C', str(home_root), 'rev-parse', '--show-toplevel'],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or pathlib.Path(result.stdout.strip()).resolve() != home_root:
        return
    try:
        invoke_hook(home_root, 'authorize_target', home_root, target_root, args)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f'authorize_target refused {target_root}: {type(exc).__name__}: {exc}'
        ) from exc


_WRITER_ROOTS: ContextVar[frozenset[pathlib.Path]] = ContextVar(
    'mir_executor_writer_roots', default=frozenset()
)


# Sessions follow inherited async worker contexts, just like writer ownership.
_NATIVE_SESSIONS: ContextVar[dict[pathlib.Path, Any] | None] = ContextVar(
    'mir_executor_native_sessions', default=None
)


def _native_context(root: pathlib.Path) -> dict:
    return {'repo_root': str(root), 'cwd': str(pathlib.Path.cwd()),
            'invocation_id': uuid.uuid4().hex, 'job_id': None, 'attempt_id': None}


@contextmanager
def writer_scope(repo_root: pathlib.Path):
    """Acquire once per nested execution, including inherited async worker contexts."""
    from .native_hooks import HookSession, NativeHookError, require_success

    root = pathlib.Path(repo_root).resolve()
    guard_python_api(root)
    held = _WRITER_ROOTS.get()
    if root in held:
        yield
        return
    config = _api_policy(root)
    session = None
    native_token = None
    context = _native_context(root)
    session_context = None
    try:
        if config is not None:
            session = HookSession(root, config)
            session_context = _NATIVE_SESSIONS.set(
                {**(_NATIVE_SESSIONS.get() or {}), root: (session, context)})
        if session is not None and 'writer_scope' in config['hooks']:
            result = require_success(session.call('writer_enter', context))
            native_token = result.get('token') if isinstance(result, dict) else None
            if not isinstance(native_token, str) or not native_token:
                native_token = None
                raise NativeHookError('writer_enter requires opaque token')
            scope = None
        else:
            scope = invoke_hook(root, 'writer_scope', root)
        outcome = 'uncertain'
        try:
            with nullcontext() if scope is None else scope:
                token = _WRITER_ROOTS.set(held | {root})
                try:
                    yield
                    outcome = 'clean'
                except Exception:
                    outcome = 'unclean'
                    raise
                finally:
                    _WRITER_ROOTS.reset(token)
        finally:
            if native_token is not None:
                require_success(session.call('writer_exit', {
                    **context, 'token': native_token, 'outcome': outcome}))
    finally:
        if session_context is not None:
            _NATIVE_SESSIONS.reset(session_context)
        if session is not None:
            session.close()


def _json_value(value: Any) -> Any:
    if isinstance(value, pathlib.Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if hasattr(value, '__dict__'):
        return _json_value(vars(value))
    return value


def _native_event(root: pathlib.Path, event: str, payload: dict) -> bool:
    from .native_hooks import HookSession, require_success

    config = _api_policy(root)
    if config is None or 'on_job_event' not in config['hooks']:
        return False
    current = (_NATIVE_SESSIONS.get() or {}).get(root)
    session, context = current if current else (HookSession(root, config), _native_context(root))
    try:
        require_success(session.call('on_job_event', {
            **context, 'event': event, 'payload': _json_value(payload),
            'job_id': payload.get('job_id'), 'attempt_id': payload.get('dispatch_id')}))
    finally:
        if current is None:
            session.close()
    return True


def validate_timeout(repo_root: pathlib.Path, value: float | None) -> None:
    """Validate optional hard timeouts against target-local inclusive bounds."""
    def positive(number):
        return (not isinstance(number, bool) and isinstance(number, (int, float))
                and math.isfinite(number) and number > 0)

    bounds = local_config(repo_root).get('timeout_seconds_range')
    if bounds is not None and (
        not isinstance(bounds, list) or len(bounds) != 2
        or not all(positive(n) for n in bounds) or bounds[0] > bounds[1]
    ):
        raise ValueError('timeout_seconds_range must be [min, max], finite and positive')
    if value is None:
        return
    if not positive(value):
        raise ValueError('timeout must be finite and positive')
    if bounds is not None and not bounds[0] <= value <= bounds[1]:
        raise ValueError(f'timeout must be within timeout_seconds_range {bounds}')


def after_provider_call(
    repo_root: pathlib.Path,
    result: Any,
    *,
    prompt: str,
    model: str | None,
    reasoning_effort: str | None,
    attempt: int,
    elapsed_seconds: float,
    raw_result: Any = None,
) -> Any:
    """Observe one provider result and allow a target-owned budget replacement."""
    raw = raw_result if isinstance(raw_result, dict) else getattr(raw_result, 'raw_result', {})
    usage = getattr(raw_result, 'token_usage', None) or raw.get('usage', {})
    if isinstance(usage, dict):
        usage = usage.get('last', usage.get('total', usage))
    aliases = {
        'input_tokens': ('input_tokens', 'inputTokens', 'prompt_tokens'),
        'output_tokens': ('output_tokens', 'outputTokens', 'completion_tokens'),
        'total_tokens': ('total_tokens', 'totalTokens'),
    }
    tokens = dict(getattr(result, 'tokens_used', ()))
    if isinstance(usage, dict):
        for name, keys in aliases.items():
            for key in keys:
                value = usage.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    tokens[name] = value
                    break
    metadata = {
        'prompt_sha256': hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
        'model': (getattr(raw_result, 'model_id', None) or raw.get('model')
                  or getattr(result, 'model_id', None) or model),
        'reasoning_effort': reasoning_effort,
        'tool_version': (getattr(raw_result, 'tool_version', None) or raw.get('tool_version')
                         or getattr(result, 'tool_version', None)),
        'attempt': attempt,
        'elapsed_seconds': elapsed_seconds,
        'token_usage': tokens or None,
    }
    replacement = invoke_hook(repo_root, 'after_provider_call', result, metadata)
    return result if replacement is None else replacement


# The context follows nested dispatch calls without adding parameters to their public API.
_JOB_EVENT_CONTEXT: ContextVar[tuple[pathlib.Path, str, list[str]] | None] = ContextVar(
    'mir_executor_job_event_context', default=None
)


@contextmanager
def job_event_scope(repo_root: pathlib.Path, job_id: str, errors: list[str]):
    token = _JOB_EVENT_CONTEXT.set((repo_root.resolve(), job_id, errors))
    try:
        yield
    finally:
        _JOB_EVENT_CONTEXT.reset(token)


def emit_job_event(
    repo_root: pathlib.Path,
    event: str,
    payload: dict[str, Any],
    *,
    errors: list[str] | None = None,
) -> None:
    """Insertion/resume hooks fail closed; later failures cannot undo execution."""
    context = _JOB_EVENT_CONTEXT.get()
    payload = dict(payload)
    if context is not None and context[0] == repo_root.resolve():
        payload.setdefault('job_id', context[1])
        if errors is None:
            errors = context[2]
    payload.setdefault('job_id', None)
    try:
        if not _native_event(repo_root.resolve(), event, payload):
            invoke_hook(repo_root, 'on_job_event', event, payload)
    except Exception as exc:  # noqa: BLE001
        if event in {'job_inserted', 'job_resumed'}:
            raise
        reason = f'on_job_event {event}: {type(exc).__name__}: {exc}'
        print(f'[mir_executor] {reason}', file=sys.stderr)
        if errors is not None:
            errors.append(reason)
