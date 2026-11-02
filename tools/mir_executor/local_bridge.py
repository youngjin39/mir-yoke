"""Persistent, stdlib-only transport for explicitly selected local executor hooks.

Writer exit and EOF cleanup perform normal exit (no remote traceback reconstruction).
Calls use the direct local hook signatures. Caller-side policy wrappers (including
provider metadata assembly and job-event failure policy) remain caller-owned.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import pathlib
import sys
from typing import Any

# Isolated script execution has no package search path; use this script's package.
if __package__ in {None, ""}:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tools.mir_executor import local_hooks

VERSION = "mir-executor.local@1"
MAX_FRAME_BYTES = 1024 * 1024
HOOKS = frozenset(
    {
        "authorize_target",
        "pre_execute",
        "validate_brief",
        "render_brief",
        "job_identity",
        "resolve_agent_route",
        "before_run",
        "after_run",
        "writer_scope",
        "after_provider_call",
        "on_job_event",
    }
)


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"$type", "value"}:
            if value["$type"] == "path":
                return pathlib.Path(value["value"])
            if value["$type"] == "namespace":
                return argparse.Namespace(**_decode(value["value"]))
            if value["$type"] == "subprocess_result":
                from tools.mir_executor.executor import SubprocessResult  # noqa: PLC0415

                return SubprocessResult(**_decode(value["value"]))
            raise ValueError("Unknown argument type")
        return {key: _decode(item) for key, item in value.items()}
    return value


def _encode(value: Any) -> Any:
    """Encode post-call arguments without changing the existing result contract."""
    if isinstance(value, pathlib.Path):
        return {"$type": "path", "value": str(value)}
    if isinstance(value, argparse.Namespace):
        return {"$type": "namespace", "value": _encode(vars(value))}
    # Provider results must remain real dataclasses in local hooks (including
    # dataclasses.replace); only their explicit wire representation crosses JSON.
    if type(value).__name__ == "SubprocessResult":
        from tools.mir_executor.executor import SubprocessResult  # noqa: PLC0415

        if isinstance(value, SubprocessResult):
            return {"$type": "subprocess_result", "value": _encode(vars(value))}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


class Bridge:
    """One module snapshot and object table for one child process."""

    def __init__(self, repo_root: pathlib.Path):
        self.module = local_hooks._module(repo_root)
        self.handles: dict[str, Any] = {}
        self.scopes: list[Any] = []

    def hello(self) -> dict[str, Any]:
        return {
            "version": VERSION,
            "hooks": sorted(name for name in HOOKS if getattr(self.module, name, None) is not None),
            "register_execute_options": getattr(self.module, "register_execute_options", None)
            is not None,
        }

    def _retain(self, value: Any) -> str:
        for key, existing in self.handles.items():
            if existing is value:
                return key
        key = f"h{len(self.handles) + 1}"
        self.handles[key] = value
        return key

    def call(self, frame: Any) -> dict[str, Any]:
        identity = frame.get("id") if isinstance(frame, dict) else None
        response = dict(
            version=VERSION,
            id=identity
            if isinstance(identity, (str, int)) and not isinstance(identity, bool)
            else None,
            ok=False,
            result=None,
            handle=None,
            error=None,
        )
        try:
            if not isinstance(frame, dict) or frame.get("version") != VERSION:
                raise ValueError("Invalid protocol version or frame")
            if isinstance(identity, bool) or not isinstance(identity, (str, int)):
                raise ValueError("A scalar request id is required")
            force_handle = frame.get("force_handle", False)
            if not isinstance(force_handle, bool):
                raise TypeError("force_handle must be a boolean")
            hook = frame.get("hook")
            if not isinstance(hook, str):
                raise TypeError("hook must be a string")
            args = _decode(frame.get("args", []))
            kwargs = _decode(frame.get("kwargs", {}))
            handles = frame.get("handles", {})
            if (
                not isinstance(args, list)
                or not isinstance(kwargs, dict)
                or not isinstance(handles, dict)
            ):
                raise TypeError("args, kwargs and handles must be an array and objects")
            for key, handle in handles.items():
                if not isinstance(handle, str) or handle not in self.handles:
                    raise ValueError("Unknown object handle")
                if key.isdecimal():
                    index = int(key)
                    if index >= len(args):
                        raise ValueError("Handle argument index is out of range")
                    args[index] = self.handles[handle]
                else:
                    kwargs[key] = self.handles[handle]
            if hook == "bridge.object":
                if len(args) != 1 or kwargs:
                    raise ValueError("bridge.object requires one argument")
                result = args[0]
            elif hook in {"writer_scope.enter", "writer_scope.exit"}:
                if len(args) != 1 or kwargs:
                    raise ValueError("writer scope operation requires one handle")
                scope = args[0]
                if hook.endswith(".enter"):
                    if any(item is scope for item in self.scopes):
                        raise ValueError("Writer scope is already entered")
                    result = scope.__enter__()
                    self.scopes.append(scope)
                else:
                    if not self.scopes or self.scopes[-1] is not scope:
                        raise ValueError("Writer scopes must exit in reverse entry order")
                    self.scopes.pop()
                    result = scope.__exit__(None, None, None)
            elif hook in HOOKS:
                function = getattr(self.module, hook, None)
                if function is None:
                    result = None
                elif not callable(function):
                    raise TypeError(f"Executor local hook {hook!r} must be callable")
                else:
                    result = function(*args, **kwargs)
            else:
                raise ValueError("Unsupported hook")
            retain = force_handle or hook in {"validate_brief", "writer_scope", "bridge.object"}
            try:
                encoded_result = _encode(result) if hook == "after_provider_call" else result
                json.dumps(encoded_result, allow_nan=False)
            except (ValueError, TypeError, RecursionError):
                retain = True
                result_json = None
            else:
                result_json = None if force_handle else encoded_result
            if hook == "pre_execute":
                response["args"] = _encode(args)
            response.update(ok=True, result=result_json)
            if retain and result is not None:
                response["handle"] = self._retain(result)
        except BaseException as exc:  # noqa: BLE001
            response["error"] = {"type": type(exc).__name__, "message": str(exc)}
            response["error_category"] = (
                "value_error"
                if isinstance(exc, ValueError)
                else "os_error"
                if isinstance(exc, OSError)
                else "uncaught"
            )
        return response

    def close(self) -> None:
        while self.scopes:
            try:
                self.scopes.pop().__exit__(None, None, None)
            except BaseException as exc:  # noqa: BLE001
                print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        self.handles.clear()


def _write(stream, response: dict[str, Any]) -> None:
    encoded = (
        json.dumps(response, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
    )
    if len(encoded) > MAX_FRAME_BYTES:
        response = dict(
            version=VERSION,
            id=response.get("id"),
            ok=False,
            result=None,
            handle=None,
            error={"type": "ValueError", "message": "Response exceeds frame limit"},
        )
        encoded = json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > MAX_FRAME_BYTES:
            response["id"] = None
            encoded = json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
    stream.write(encoded)
    stream.flush()


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON value")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: local_bridge.py TARGET_ROOT", file=sys.stderr)
        return 2
    output = sys.stdout.buffer
    with contextlib.redirect_stdout(sys.stderr):
        bridge = Bridge(pathlib.Path(sys.argv[1]))
        try:
            _write(output, bridge.hello())
            while raw := sys.stdin.buffer.readline(MAX_FRAME_BYTES + 1):
                try:
                    if len(raw) > MAX_FRAME_BYTES:
                        while raw and not raw.endswith(b"\n"):
                            raw = sys.stdin.buffer.readline(MAX_FRAME_BYTES + 1)
                        raise ValueError("Request exceeds frame limit")
                    if not raw.endswith(b"\n"):
                        raise ValueError("Request must end with a newline")
                    frame = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
                    response = bridge.call(frame)
                except (UnicodeError, ValueError, RecursionError) as exc:
                    response = dict(
                        version=VERSION,
                        id=None,
                        ok=False,
                        result=None,
                        handle=None,
                        error={"type": type(exc).__name__, "message": str(exc)},
                    )
                _write(output, response)
        finally:
            bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
