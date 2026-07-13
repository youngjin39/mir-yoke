"""JSON-RPC stdio client for ``codex mcp-server``.

ADR-66 S1 keeps this as a standalone client. Dispatch runner wiring is a later
slice.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

DEFAULT_CODEX_BIN = "codex"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"


class CodexMcpError(RuntimeError):
    """Base class for Codex MCP client failures."""


class CodexMcpProcessError(CodexMcpError):
    """The MCP server process exited or became unavailable."""


class CodexMcpProtocolError(CodexMcpError):
    """The MCP server returned a JSON-RPC error or invalid response."""


class CodexMcpTimeoutError(CodexMcpError, TimeoutError):
    """A JSON-RPC request timed out and the MCP server was killed."""


class CodexMcpStallError(CodexMcpError):
    """A JSON-RPC request had no stdout activity before the stall watchdog fired."""


@dataclass(frozen=True)
class CodexMcpResult:
    """Structured result returned by the Codex MCP ``codex`` tool."""

    content_text: str
    thread_id: str | None
    raw_result: Mapping[str, Any]


@dataclass
class _PendingRequest:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


class CodexMcpClient:
    """Small JSON-RPC client for a single ``codex mcp-server`` subprocess."""

    def __init__(
        self,
        *,
        codex_bin: str | None = None,
        env: Mapping[str, str] | None = None,
        initialize_timeout: float = 10.0,
        call_timeout: float = 600.0,
        kill_timeout: float = 2.0,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
    ) -> None:
        self._codex_bin = codex_bin or os.environ.get("CODEX_BIN", DEFAULT_CODEX_BIN)
        self._env = dict(env) if env is not None else os.environ.copy()
        self._initialize_timeout = initialize_timeout
        self._call_timeout = call_timeout
        self._kill_timeout = kill_timeout
        self._protocol_version = protocol_version

        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[str, _PendingRequest] = {}
        self._closing = False
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._wait_thread: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        self._malformed_messages: list[str] = []
        self._notifications: list[dict[str, Any]] = []
        self._last_activity_ts = time.monotonic()
        self._progress_lock = threading.Lock()
        self._progress_callback: Callable[[str, object], None] | None = None

    @property
    def is_running(self) -> bool:
        """Return True while the MCP server subprocess is alive."""
        return self._proc is not None and self._proc.poll() is None

    @property
    def pending_count(self) -> int:
        """Return the number of currently pending JSON-RPC requests."""
        with self._pending_lock:
            return len(self._pending)

    @property
    def malformed_messages(self) -> list[str]:
        """Return malformed newline-delimited messages observed from stdout."""
        return list(self._malformed_messages)

    @property
    def stderr_lines(self) -> list[str]:
        """Return stderr lines observed from the MCP server."""
        return list(self._stderr_lines)

    def __enter__(self) -> CodexMcpClient:
        self.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def start(self) -> None:
        """Spawn ``codex mcp-server`` and perform the MCP initialize handshake."""
        if self._proc is not None and self._proc.poll() is None:
            raise CodexMcpProcessError("Codex MCP client already started")

        self._closing = False
        try:
            self._proc = subprocess.Popen(
                [self._codex_bin, "mcp-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=self._env,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Codex binary not found: {self._codex_bin!r}. "
                "Set CODEX_BIN to the full path of the codex executable."
            ) from exc

        self._stdout_thread = threading.Thread(
            target=self._read_stdout,
            name="codex-mcp-stdout",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="codex-mcp-stderr",
            daemon=True,
        )
        self._wait_thread = threading.Thread(
            target=self._wait_for_exit,
            name="codex-mcp-wait",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        self._wait_thread.start()

        try:
            self._request(
                "initialize",
                {
                    "protocolVersion": self._protocol_version,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "mir_executor",
                        "version": "0.1.0",
                    },
                },
                timeout=self._initialize_timeout,
            )
            self._notify("notifications/initialized", {})
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Reject pending requests and stop the MCP server subprocess."""
        self._closing = True
        self._reject_all_pending(CodexMcpProcessError("Codex MCP client closed"))
        self._terminate_server()

    def call_codex(
        self,
        *,
        prompt: str,
        cwd: str | os.PathLike[str],
        sandbox: str = "danger-full-access",
        approval_policy: str = "never",
        model: str | None = None,
        base_instructions: str | None = None,
        config: Mapping[str, Any] | None = None,
        timeout: float | None = None,
        stall_timeout: float | None = None,
        progress_callback: Callable[[str, object], None] | None = None,
    ) -> CodexMcpResult:
        """Call the MCP ``codex`` tool and return content text plus thread id."""
        arguments: dict[str, Any] = {
            "prompt": prompt,
            "cwd": os.fspath(cwd),
            "sandbox": sandbox,
            "approval-policy": approval_policy,
        }
        if model is not None:
            arguments["model"] = model
        if base_instructions is not None:
            arguments["base-instructions"] = base_instructions
        if config is not None:
            arguments["config"] = dict(config)

        with self._progress_lock:
            previous_progress_callback = self._progress_callback
            self._progress_callback = progress_callback
        try:
            result = self._request(
                "tools/call",
                {
                    "name": "codex",
                    "arguments": arguments,
                },
                timeout=self._call_timeout if timeout is None else timeout,
                stall_timeout=stall_timeout,
            )
        finally:
            with self._progress_lock:
                self._progress_callback = previous_progress_callback
        if not isinstance(result, Mapping):
            raise CodexMcpProtocolError("Codex tool returned a non-object result")

        content_text = _extract_content_text(result)
        thread_id = _find_thread_id(result) or _find_thread_id_in_text(content_text)
        return CodexMcpResult(
            content_text=content_text,
            thread_id=thread_id,
            raw_result=result,
        )

    def _next_request_id(self) -> int:
        with self._id_lock:
            request_id = self._next_id
            self._next_id += 1
            return request_id

    def _request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout: float,
        stall_timeout: float | None = None,
    ) -> Any:
        request_id = self._next_request_id()
        key = str(request_id)
        pending = _PendingRequest()
        with self._pending_lock:
            self._pending[key] = pending

        watchdog_thread: threading.Thread | None = None
        try:
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": dict(params),
                }
            )
        except Exception:
            with self._pending_lock:
                self._pending.pop(key, None)
            raise

        if stall_timeout is not None:
            self._last_activity_ts = time.monotonic()
            watchdog_thread = threading.Thread(
                target=self._watch_request_stall,
                args=(key, method, pending, stall_timeout),
                name=f"codex-mcp-stall-{key}",
                daemon=True,
            )
            watchdog_thread.start()

        if not pending.event.wait(timeout):
            error = CodexMcpTimeoutError(
                f"Codex MCP request {method!r} timed out after {timeout:g}s"
            )
            self._reject_all_pending(error)
            self._terminate_server()
            raise error

        if watchdog_thread is not None:
            watchdog_thread.join(timeout=self._kill_timeout)

        if pending.error is not None:
            raise pending.error
        return pending.result

    def _watch_request_stall(
        self,
        key: str,
        method: str,
        pending: _PendingRequest,
        stall_timeout: float,
    ) -> None:
        interval = min(max(stall_timeout / 4.0, 0.01), 0.25)
        while not pending.event.wait(interval):
            with self._pending_lock:
                if key not in self._pending:
                    return
            inactive_for = time.monotonic() - self._last_activity_ts
            if inactive_for <= stall_timeout:
                continue

            error = CodexMcpStallError(
                f"Codex MCP request {method!r} stalled after "
                f"{inactive_for:g}s without stdout activity"
            )
            pending_requests = self._drain_pending(error)
            try:
                self._terminate_server()
            finally:
                for pending_request in pending_requests:
                    pending_request.event.set()
            return

    def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    def _send(self, message: Mapping[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None or proc.stdin is None:
            raise CodexMcpProcessError("Codex MCP server stdin is unavailable")
        payload = json.dumps(message, ensure_ascii=False)
        with self._send_lock:
            try:
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()
            except OSError as exc:
                raise CodexMcpProcessError("Codex MCP server stdin write failed") from exc

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                self._handle_stdout_line(line)
        except (OSError, ValueError) as exc:
            if not self._closing:
                self._reject_all_pending(
                    CodexMcpProcessError(f"Codex MCP stdout read failed: {exc}")
                )

    def _read_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                self._stderr_lines.append(line.rstrip("\n"))
        except (OSError, ValueError):
            return

    def _wait_for_exit(self) -> None:
        proc = self._proc
        if proc is None:
            return
        code = proc.wait()
        if not self._closing:
            self._reject_all_pending(
                CodexMcpProcessError(f"Codex MCP server exited with code {code}")
            )

    def _handle_stdout_line(self, line: str) -> None:
        self._last_activity_ts = time.monotonic()
        text = line.strip()
        if not text:
            return

        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            self._malformed_messages.append(text)
            return

        if not isinstance(message, dict):
            self._malformed_messages.append(text)
            return

        has_id = "id" in message
        has_result = "result" in message
        has_error = "error" in message
        has_method = isinstance(message.get("method"), str)

        if has_id and (has_result or has_error):
            pending = self._pop_pending(message["id"])
            if pending is None:
                return
            if has_error:
                pending.error = CodexMcpProtocolError(_json_rpc_error_message(message["error"]))
            else:
                pending.result = message.get("result")
            pending.event.set()
            return

        if has_method and not has_id:
            params = message.get("params", {})
            self._notifications.append({"method": message["method"], "params": params})
            with self._progress_lock:
                progress_callback = self._progress_callback
            if progress_callback is not None:
                try:
                    progress_callback(message["method"], params)
                except Exception as exc:  # noqa: BLE001
                    self._reject_all_pending(
                        CodexMcpError(f"Codex MCP progress callback failed: {exc}")
                    )
            return

        self._malformed_messages.append(text)

    def _pop_pending(self, request_id: object) -> _PendingRequest | None:
        with self._pending_lock:
            return self._pending.pop(str(request_id), None)

    def _drain_pending(self, error: BaseException) -> list[_PendingRequest]:
        with self._pending_lock:
            pending_requests = list(self._pending.values())
            self._pending.clear()
        for pending in pending_requests:
            pending.error = error
        return pending_requests

    def _reject_all_pending(self, error: BaseException) -> None:
        for pending in self._drain_pending(error):
            pending.event.set()

    def _terminate_server(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=self._kill_timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=self._kill_timeout)
        finally:
            current_thread = threading.current_thread()
            for reader_thread in (self._stdout_thread, self._stderr_thread):
                if reader_thread is not None and reader_thread is not current_thread:
                    reader_thread.join(timeout=self._kill_timeout)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass
            self._proc = None


def _json_rpc_error_message(error: object) -> str:
    if isinstance(error, Mapping):
        message = error.get("message")
        if isinstance(message, str):
            return message
    return "Codex MCP JSON-RPC request failed"


def _extract_content_text(result: Mapping[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, Mapping):
                text = item.get("text")
                if isinstance(text, str):
                    texts.append(text)
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)

    text = result.get("text")
    if isinstance(text, str):
        return text
    return json.dumps(result, ensure_ascii=False, sort_keys=True)


def _find_thread_id(value: object) -> str | None:
    if isinstance(value, Mapping):
        for key in ("threadId", "thread_id"):
            found = value.get(key)
            if isinstance(found, str):
                return found
        for nested in value.values():
            found = _find_thread_id(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_thread_id(item)
            if found is not None:
                return found
    return None


def _find_thread_id_in_text(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        found = _find_thread_id(parsed)
        if found is not None:
            return found
    return None
