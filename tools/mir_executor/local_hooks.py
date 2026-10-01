"""One optional target-owned extension seam for the common executor."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from types import ModuleType
from typing import Any

_MODULES: dict[pathlib.Path, tuple[int, int, ModuleType]] = {}


def local_config(repo_root: pathlib.Path) -> dict[str, Any]:
    """Read repository data; absence means common defaults, malformed data fails."""
    path = pathlib.Path(repo_root) / 'config/mir-executor.local.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'{path} must contain a JSON object')
    return data


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


def writer_scope(repo_root: pathlib.Path) -> Any:
    scope = invoke_hook(repo_root, 'writer_scope', repo_root)
    return nullcontext() if scope is None else scope


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
        invoke_hook(repo_root, 'on_job_event', event, payload)
    except Exception as exc:  # noqa: BLE001
        if event in {'job_inserted', 'job_resumed'}:
            raise
        reason = f'on_job_event {event}: {type(exc).__name__}: {exc}'
        print(f'[mir_executor] {reason}', file=sys.stderr)
        if errors is not None:
            errors.append(reason)
