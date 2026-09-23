"""JSON-RPC stdio client for ``codex app-server``.

The CodexMcp* public names remain compatible with existing dispatch callers.
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
    """Base class for Codex app-server client failures."""


class CodexMcpProcessError(CodexMcpError):
    """The app-server process exited or became unavailable."""


class CodexMcpProtocolError(CodexMcpError):
    """The app-server returned a JSON-RPC error or invalid response."""


class CodexMcpTimeoutError(CodexMcpError, TimeoutError):
    """A JSON-RPC request timed out and the app-server was killed."""


class CodexMcpStallError(CodexMcpError):
    """A JSON-RPC request had no stdout activity before the stall watchdog fired."""


@dataclass(frozen=True)
class CodexMcpResult:
    """Structured result returned by a completed app-server turn."""

    content_text: str
    thread_id: str | None
    raw_result: Mapping[str, Any]


@dataclass
class _PendingRequest:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


@dataclass
class _PendingTurn:
    pending: _PendingRequest = field(default_factory=_PendingRequest)
    texts: dict[str, str] = field(default_factory=dict)


class CodexMcpClient:
    """Small JSON-RPC client for a single ``codex app-server`` subprocess."""

    def __init__(
        self,
        *,
        codex_bin: str | None = None,
        env: Mapping[str, str] | None = None,
        initialize_timeout: float = 10.0,
        call_timeout: float | None = None,
        kill_timeout: float = 2.0,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
    ) -> None:
        self._codex_bin = codex_bin or os.environ.get("CODEX_BIN", DEFAULT_CODEX_BIN)
        self._env = dict(env) if env is not None else os.environ.copy()
        self._initialize_timeout = initialize_timeout
        self._call_timeout = call_timeout
        self._kill_timeout = kill_timeout
        # Retained as a constructor compatibility argument; app-server has no MCP version.
        _ = protocol_version

        self._proc: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[str, _PendingRequest] = {}
        self._turns: dict[str, _PendingTurn] = {}
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
        """Return True while the app-server subprocess is alive."""
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
        """Return stderr lines observed from the app-server."""
        return list(self._stderr_lines)

    def __enter__(self) -> CodexMcpClient:
        self.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def start(self) -> None:
        """Spawn ``codex app-server`` and perform its initialize handshake."""
        if self._proc is not None and self._proc.poll() is None:
            raise CodexMcpProcessError("Codex app-server client already started")

        self._closing = False
        try:
            self._proc = subprocess.Popen(
                [self._codex_bin, "app-server"],
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
                    "capabilities": {},
                    "clientInfo": {
                        "name": "mir_executor",
                        "version": "0.1.0",
                    },
                },
                timeout=self._initialize_timeout,
            )
            self._notify("initialized", {})
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Reject pending requests and stop the app-server subprocess."""
        self._closing = True
        self._reject_all_pending(CodexMcpProcessError("Codex app-server client closed"))
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
        """Start a thread and wait for its turn to complete, including streamed items."""
        arguments: dict[str, Any] = {
            "cwd": os.fspath(cwd),
            "sandbox": sandbox,
            "approvalPolicy": approval_policy,
        }
        if model is not None:
            arguments["model"] = model
        if base_instructions is not None:
            arguments["baseInstructions"] = base_instructions
        if config is not None:
            arguments["config"] = dict(config)

        effective_timeout = self._call_timeout if timeout is None else timeout
        deadline = None if effective_timeout is None else time.monotonic() + effective_timeout

        def remaining() -> float | None:
            return None if deadline is None else max(0.0, deadline - time.monotonic())

        thread_id: str | None = None
        with self._progress_lock:
            previous_progress_callback = self._progress_callback
            self._progress_callback = progress_callback
        try:
            started = self._request(
                "thread/start", arguments, timeout=remaining(), stall_timeout=stall_timeout
            )
            thread = started.get("thread") if isinstance(started, Mapping) else None
            candidate_id = thread.get("id") if isinstance(thread, Mapping) else None
            if not isinstance(candidate_id, str) or not candidate_id:
                raise CodexMcpProtocolError("thread/start returned no thread id")
            thread_id = candidate_id

            # Register before turn/start: completion notifications may precede its response.
            turn = _PendingTurn()
            key = f"turn:{thread_id}"
            with self._pending_lock:
                self._turns[thread_id] = turn
                self._pending[key] = turn.pending
            started = self._request(
                "turn/start",
                {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]},
                timeout=remaining(),
                stall_timeout=stall_timeout,
            )
            started_turn = started.get("turn") if isinstance(started, Mapping) else None
            if not isinstance(started_turn, Mapping) or not isinstance(started_turn.get("id"), str):
                raise CodexMcpProtocolError("turn/start returned no turn id")
            result = self._wait_pending(
                key,
                "turn/completed",
                turn.pending,
                timeout=remaining(),
                stall_timeout=stall_timeout,
            )
            completed = result.get("turn")
            if not isinstance(completed, Mapping):
                raise CodexMcpProtocolError("turn/completed returned no turn")
            if completed.get("id") != started_turn["id"]:
                raise CodexMcpProtocolError("turn/completed returned an unexpected turn id")
            if completed.get("status") != "completed":
                error = completed.get("error")
                detail = _json_rpc_error_message(error) if error else completed.get("status")
                raise CodexMcpProtocolError(f"Codex turn failed: {detail}")
            for item in completed.get("items", []):
                if item.get("type") == "agentMessage" and item.get("phase") != "commentary":
                    turn.texts[item["id"]] = item["text"]
            return CodexMcpResult(
                content_text="\n".join(turn.texts.values()),
                thread_id=thread_id,
                raw_result=result,
            )
        except Exception:
            self.close()
            raise
        finally:
            with self._pending_lock:
                self._turns.pop(thread_id, None)
                self._pending.pop(f"turn:{thread_id}", None)
            with self._progress_lock:
                self._progress_callback = previous_progress_callback

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
        timeout: float | None,
        stall_timeout: float | None = None,
    ) -> Any:
        request_id = self._next_request_id()
        key = str(request_id)
        pending = _PendingRequest()
        with self._pending_lock:
            self._pending[key] = pending

        self._last_activity_ts = time.monotonic()
        try:
            self._send(
                {
                    "id": request_id,
                    "method": method,
                    "params": dict(params),
                }
            )
        except Exception:
            with self._pending_lock:
                self._pending.pop(key, None)
            raise

        return self._wait_pending(
            key, method, pending, timeout=timeout, stall_timeout=stall_timeout
        )

    def _wait_pending(
        self,
        key: str,
        method: str,
        pending: _PendingRequest,
        *,
        timeout: float | None,
        stall_timeout: float | None,
    ) -> Any:
        watchdog_thread: threading.Thread | None = None
        if stall_timeout is not None:
            watchdog_thread = threading.Thread(
                target=self._watch_request_stall,
                args=(key, method, pending, stall_timeout),
                name=f"codex-mcp-stall-{key}",
                daemon=True,
            )
            watchdog_thread.start()

        if timeout is None:
            pending.event.wait()
        elif not pending.event.wait(timeout):
            error = CodexMcpTimeoutError(
                f"Codex app-server request {method!r} timed out after {timeout:g}s"
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
                f"Codex app-server request {method!r} stalled after "
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
        self._send({"method": method, "params": dict(params)})

    def _send(self, message: Mapping[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None or proc.stdin is None:
            raise CodexMcpProcessError("Codex app-server stdin is unavailable")
        payload = json.dumps(message, ensure_ascii=False)
        with self._send_lock:
            try:
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()
            except OSError as exc:
                raise CodexMcpProcessError("Codex app-server stdin write failed") from exc

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
                    CodexMcpProcessError(f"Codex app-server stdout read failed: {exc}")
                )
        except CodexMcpError as exc:
            self._reject_all_pending(exc)

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
                CodexMcpProcessError(f"Codex app-server exited with code {code}")
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
                        CodexMcpError(f"Codex app-server progress callback failed: {exc}")
                    )
            if isinstance(params, Mapping):
                with self._pending_lock:
                    turn = self._turns.get(params.get("threadId"))
                if turn is not None and not turn.pending.event.is_set():
                    if message["method"] == "item/completed":
                        item = params.get("item", {})
                        if item.get("type") == "agentMessage" and item.get("phase") != "commentary":
                            turn.texts[item["id"]] = item["text"]
                    elif message["method"] == "turn/completed":
                        turn.pending.result = params
                        turn.pending.event.set()
            return

        if has_method and has_id:
            # This unattended client cannot grant approvals or answer interactive requests.
            error = f"Unsupported app-server request: {message['method']}"
            self._send({"id": message["id"], "error": {"code": -32601, "message": error}})
            self._reject_all_pending(CodexMcpProtocolError(error))
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
    return "Codex app-server JSON-RPC request failed"
