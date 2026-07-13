"""Unit tests for ADR-66 S1 CodexMcpClient."""

from __future__ import annotations

import json
import os
import pathlib
import stat
import sys
import textwrap
import threading
import time

import pytest

from tools.mir_executor.codex_mcp_client import (
    DEFAULT_CODEX_BIN,
    CodexMcpClient,
    CodexMcpProcessError,
    CodexMcpStallError,
    CodexMcpTimeoutError,
)


def test_default_codex_command_is_portable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEX_BIN", raising=False)
    client = CodexMcpClient()

    assert DEFAULT_CODEX_BIN == "codex"
    assert client._codex_bin == DEFAULT_CODEX_BIN
    assert "/Users" not in client._codex_bin


def _write_fake_mcp_server(tmp_path: pathlib.Path, *, mode: str) -> pathlib.Path:
    record_path = tmp_path / "messages.jsonl"
    server_py = tmp_path / "fake_codex_server.py"
    server_py.write_text(
        textwrap.dedent(
            f"""\
            import json
            import sys
            import time

            MODE = {mode!r}
            RECORD_PATH = {str(record_path)!r}
            malformed_sent = False


            def record(message):
                with open(RECORD_PATH, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(message, sort_keys=True) + "\\n")


            def send(message):
                print(json.dumps(message), flush=True)


            for raw in sys.stdin:
                message = json.loads(raw)
                record(message)
                method = message.get("method")

                if MODE == "malformed" and not malformed_sent:
                    print("{{not-json", flush=True)
                    malformed_sent = True

                if method == "initialize":
                    send({{
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "result": {{
                            "protocolVersion": message["params"]["protocolVersion"],
                            "capabilities": {{}},
                            "serverInfo": {{"name": "fake-codex", "version": "0.0"}}
                        }}
                    }})
                elif method == "notifications/initialized":
                    continue
                elif method == "tools/call":
                    if MODE == "timeout":
                        time.sleep(30)
                    elif MODE == "delayed":
                        time.sleep(0.05)
                    elif MODE == "notification":
                        send({{
                            "jsonrpc": "2.0",
                            "method": "notifications/progress",
                            "params": {{"message": "working"}}
                        }})
                    elif MODE == "pending_notification":
                        send({{
                            "jsonrpc": "2.0",
                            "method": "notifications/progress",
                            "params": {{"message": "working"}}
                        }})
                        time.sleep(30)
                    send({{
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "result": {{
                            "content": [
                                {{"type": "text", "text": "codex completed"}}
                            ],
                            "threadId": "thread-123"
                        }}
                    }})
            """
        ),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "codex"
    fake_bin.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/sh
            exec {sys.executable!r} {str(server_py)!r} "$@"
            """
        ),
        encoding="utf-8",
    )
    fake_bin.chmod(fake_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return fake_bin


def _read_messages(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _wait_for_messages(record_path: pathlib.Path, count: int) -> list[dict]:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        messages = _read_messages(record_path)
        if len(messages) >= count:
            return messages
        time.sleep(0.01)
    return _read_messages(record_path)


def test_initialize_handshake_sends_initialized_notification(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="success")
    record_path = tmp_path / "messages.jsonl"

    client = CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0)
    try:
        client.start()
        result = client.call_codex(prompt="hello", cwd=tmp_path, timeout=1.0)
    finally:
        client.close()

    messages = _wait_for_messages(record_path, 3)
    assert messages[0]["method"] == "initialize"
    assert messages[0]["params"]["clientInfo"]["name"] == "mir_executor"
    assert messages[0]["params"]["protocolVersion"] == "2024-11-05"
    assert messages[1]["method"] == "notifications/initialized"
    assert result.content_text == "codex completed"


def test_call_codex_maps_content_and_thread_id(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="success")
    record_path = tmp_path / "messages.jsonl"

    with CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0) as client:
        result = client.call_codex(prompt="implement s1", cwd=tmp_path, timeout=1.0)

    assert result.content_text == "codex completed"
    assert result.thread_id == "thread-123"

    tool_call = _wait_for_messages(record_path, 3)[2]
    assert tool_call["method"] == "tools/call"
    assert tool_call["params"]["name"] == "codex"
    assert tool_call["params"]["arguments"] == {
        "prompt": "implement s1",
        "cwd": str(tmp_path),
        "sandbox": "danger-full-access",
        "approval-policy": "never",
    }


def test_call_codex_includes_base_instructions_and_config(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="success")
    record_path = tmp_path / "messages.jsonl"

    with CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0) as client:
        client.call_codex(
            prompt="implement s1",
            cwd=tmp_path,
            base_instructions="SLIM",
            config={"project_doc_max_bytes": 0},
            timeout=1.0,
        )

    tool_call = _wait_for_messages(record_path, 3)[2]
    assert tool_call["params"]["arguments"] == {
        "prompt": "implement s1",
        "cwd": str(tmp_path),
        "sandbox": "danger-full-access",
        "approval-policy": "never",
        "base-instructions": "SLIM",
        "config": {"project_doc_max_bytes": 0},
    }
    assert "model" not in tool_call["params"]["arguments"]


def test_call_codex_includes_model_with_base_instructions_and_config(
    tmp_path: pathlib.Path,
) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="success")
    record_path = tmp_path / "messages.jsonl"

    with CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0) as client:
        client.call_codex(
            prompt="implement routing",
            cwd=tmp_path,
            model="high",
            base_instructions="SLIM",
            config={"project_doc_max_bytes": 0},
            timeout=1.0,
        )

    tool_call = _wait_for_messages(record_path, 3)[2]
    assert tool_call["params"]["arguments"] == {
        "prompt": "implement routing",
        "cwd": str(tmp_path),
        "sandbox": "danger-full-access",
        "approval-policy": "never",
        "model": "high",
        "base-instructions": "SLIM",
        "config": {"project_doc_max_bytes": 0},
    }


def test_call_codex_base_instructions_without_config_omits_config(
    tmp_path: pathlib.Path,
) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="success")
    record_path = tmp_path / "messages.jsonl"

    with CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0) as client:
        client.call_codex(
            prompt="implement s1",
            cwd=tmp_path,
            base_instructions="SLIM",
            timeout=1.0,
        )

    arguments = _wait_for_messages(record_path, 3)[2]["params"]["arguments"]
    assert arguments["base-instructions"] == "SLIM"
    assert "config" not in arguments


def test_client_uses_codex_bin_environment_default(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="success")
    monkeypatch.setenv("CODEX_BIN", str(fake_bin))

    with CodexMcpClient(initialize_timeout=1.0) as client:
        result = client.call_codex(prompt="env bin", cwd=tmp_path, timeout=1.0)

    assert result.thread_id == "thread-123"


def test_call_timeout_kills_server_and_rejects_pending(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="timeout")
    client = CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0, kill_timeout=1.0)
    client.start()

    with pytest.raises(CodexMcpTimeoutError):
        client.call_codex(prompt="hang", cwd=tmp_path, timeout=0.05, stall_timeout=None)

    assert client.pending_count == 0
    assert client.is_running is False


def test_call_timeout_none_waits_for_completion(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="delayed")

    with CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0) as client:
        result = client.call_codex(prompt="wait", cwd=tmp_path, timeout=None)

    assert result.content_text == "codex completed"


def test_call_timeout_none_passes_none_to_effective_request(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CodexMcpClient(call_timeout=None)
    observed_timeouts: list[float | None] = []

    def fake_request(
        method: str,
        params: object,
        *,
        timeout: float | None,
        stall_timeout: float | None = None,
    ) -> object:
        _ = method, params, stall_timeout
        observed_timeouts.append(timeout)
        return {"content": [{"type": "text", "text": "done"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    result = client.call_codex(prompt="wait", cwd=tmp_path, timeout=None)

    assert result.content_text == "done"
    assert observed_timeouts == [None]


def test_stall_watchdog_kills_silent_server_and_rejects_pending(
    tmp_path: pathlib.Path,
) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="timeout")
    client = CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0, kill_timeout=1.0)
    client.start()

    with pytest.raises(CodexMcpStallError):
        client.call_codex(prompt="silent", cwd=tmp_path, timeout=5.0, stall_timeout=0.05)

    assert client.pending_count == 0
    assert client.is_running is False


def test_progress_callback_is_invoked_for_notifications(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="notification")
    progress: list[tuple[str, object]] = []

    with CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0) as client:
        result = client.call_codex(
            prompt="notify",
            cwd=tmp_path,
            timeout=1.0,
            progress_callback=lambda method, params: progress.append((method, params)),
        )

    assert result.content_text == "codex completed"
    assert progress == [("notifications/progress", {"message": "working"})]


def test_close_during_pending_call_tears_down_reader_threads_cleanly(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="pending_notification")
    client = CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0, kill_timeout=0.1)
    notification_seen = threading.Event()
    release_notification = threading.Event()
    reader_exceptions: list[tuple[str, str, str]] = []
    call_errors: list[BaseException] = []
    original_excepthook = threading.excepthook

    def record_reader_exception(args: threading.ExceptHookArgs) -> None:
        thread_name = args.thread.name if args.thread is not None else ""
        if thread_name.startswith("codex-mcp-"):
            reader_exceptions.append((thread_name, args.exc_type.__name__, str(args.exc_value)))
            return
        original_excepthook(args)

    def run_call() -> None:
        try:
            client.call_codex(prompt="close while pending", cwd=tmp_path, timeout=5.0)
        except BaseException as exc:
            call_errors.append(exc)

    monkeypatch.setattr(threading, "excepthook", record_reader_exception)

    try:
        client.start()
        original_handle_stdout_line = client._handle_stdout_line

        def hold_progress_notification(line: str) -> None:
            if "notifications/progress" in line:
                notification_seen.set()
                release_notification.wait(timeout=5.0)
            original_handle_stdout_line(line)

        monkeypatch.setattr(client, "_handle_stdout_line", hold_progress_notification)
        call_thread = threading.Thread(target=run_call, name="pending-codex-call")
        call_thread.start()

        assert notification_seen.wait(timeout=2.0)
        client.close()
        release_notification.set()
        call_thread.join(timeout=1.0)

        assert call_thread.is_alive() is False
        assert len(call_errors) == 1
        assert isinstance(call_errors[0], CodexMcpProcessError)
        assert client.pending_count == 0
        assert client.is_running is False

        for reader_thread in (client._stdout_thread, client._stderr_thread):
            if reader_thread is not None:
                reader_thread.join(timeout=1.0)
                assert reader_thread.is_alive() is False

        assert reader_exceptions == []
    finally:
        release_notification.set()
        client.close()


def test_malformed_json_line_is_recorded_and_ignored(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="malformed")

    with CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0) as client:
        result = client.call_codex(prompt="after malformed", cwd=os.fspath(tmp_path), timeout=1.0)

    assert result.content_text == "codex completed"
    assert client.malformed_messages == ["{not-json"]
