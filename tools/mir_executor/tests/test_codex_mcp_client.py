"""App-server transport tests for the compatible CodexMcpClient interface."""

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
    CodexMcpProtocolError,
    CodexMcpStallError,
    CodexMcpTimeoutError,
)


def test_default_codex_command_is_portable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEX_BIN", raising=False)
    client = CodexMcpClient()

    assert DEFAULT_CODEX_BIN == "codex"
    assert client._codex_bin == DEFAULT_CODEX_BIN
    assert "/Users" not in client._codex_bin


def _write_fake_app_server(tmp_path: pathlib.Path, *, mode: str) -> pathlib.Path:
    record_path = tmp_path / "messages.jsonl"
    server_py = tmp_path / "fake_codex_server.py"
    server_py.write_text(
        textwrap.dedent(
            f"""\
            import json
            import signal
            import sys
            import time

            assert sys.argv[1:] == ["app-server"]
            MODE = {mode!r}
            if MODE == "stubborn_timeout":
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
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
                        "id": message["id"],
                        "result": {{"userAgent": "fake-codex/0.156.0"}}
                    }})
                elif method == "initialized":
                    continue
                elif method == "thread/start":
                    if MODE == "thread_timeout":
                        time.sleep(30)
                    if MODE == "rpc_error":
                        send({{"id": message["id"], "error": {{
                            "code": -32602, "message": "bad model"
                        }}}})
                        continue
                    send({{"id": message["id"], "result": {{"thread": {{"id": "thread-123"}}}}}})
                elif method == "turn/start":
                    turn = {{"id": "turn-123", "status": "inProgress", "items": []}}
                    if MODE != "early_completion":
                        send({{"id": message["id"], "result": {{"turn": turn}}}})
                    if MODE == "exit":
                        sys.exit(7)
                    if MODE == "approval":
                        send({{"id": "approval-1",
                              "method": "item/commandExecution/requestApproval",
                              "params": {{}}}})
                        continue
                    if MODE in ("timeout", "stubborn_timeout"):
                        time.sleep(30)
                    elif MODE == "delayed":
                        time.sleep(0.05)
                    elif MODE in ("notification", "pending_notification", "heartbeat"):
                        for _ in range(5 if MODE == "heartbeat" else 1):
                            send({{
                                "method": "item/agentMessage/delta",
                                "params": {{"threadId": "thread-123", "turnId": "turn-123",
                                           "itemId": "item-1", "delta": "working"}}
                            }})
                            if MODE == "heartbeat":
                                time.sleep(0.25)
                    if MODE == "pending_notification":
                        time.sleep(30)
                    item = {{"type": "agentMessage", "id": "item-1", "text": "codex completed"}}
                    if MODE.startswith("malformed_notification_"):
                        item = {{"none": None, "list": [], "string": "bad"}}[
                            MODE.removeprefix("malformed_notification_")
                        ]
                    if MODE == "malformed_agent_id":
                        item["id"] = []
                    if MODE == "malformed_agent_text":
                        item["text"] = None
                    if MODE == "malformed_completion_agent_id":
                        item["id"] = []
                    if MODE == "malformed_completion_agent_text":
                        item["text"] = None
                    if MODE == "commentary":
                        send({{
                            "method": "item/completed",
                            "params": {{"threadId": "thread-123", "turnId": "turn-123", "item": {{
                                "type": "agentMessage", "id": "commentary-1",
                                "phase": "commentary", "text": "still working"
                            }}}}
                        }})
                    if MODE not in ("completion_items", "malformed_completion_agent_id",
                                    "malformed_completion_agent_text"):
                        item_params = {{"threadId": "thread-123", "turnId": "turn-123",
                                       "item": item}}
                        if MODE == "bad_item_params_list":
                            item_params = []
                        elif MODE == "bad_item_thread_id_list":
                            item_params["threadId"] = []
                        elif MODE == "bad_item_thread_id_dict":
                            item_params["threadId"] = {{}}
                        elif MODE == "bad_item_thread_id_missing":
                            del item_params["threadId"]
                        send({{
                            "method": "item/completed",
                            "params": item_params
                        }})
                    turn["status"] = MODE if MODE in ("failed", "interrupted") else "completed"
                    if MODE == "failed":
                        turn["error"] = {{"message": "model unavailable"}}
                    if MODE in ("completion_items", "duplicate_items"):
                        turn["items"] = [item]
                    if MODE == "malformed_completion_items":
                        turn["items"] = None
                    if MODE == "malformed_completion_item":
                        turn["items"] = [None]
                    if MODE in ("malformed_completion_agent_id",
                                "malformed_completion_agent_text"):
                        turn["items"] = [item]
                    turn_params = {{"threadId": "thread-123", "turn": turn}}
                    if MODE == "bad_turn_params_list":
                        turn_params = []
                    elif MODE == "bad_turn_thread_id_list":
                        turn_params["threadId"] = []
                    elif MODE == "bad_turn_thread_id_dict":
                        turn_params["threadId"] = {{}}
                    elif MODE == "bad_turn_thread_id_missing":
                        del turn_params["threadId"]
                    send({{
                        "method": "turn/completed",
                        "params": turn_params
                    }})
                    if MODE == "early_completion":
                        send({{"id": message["id"], "result": {{"turn": turn}}}})
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
    fake_bin = _write_fake_app_server(tmp_path, mode="success")
    record_path = tmp_path / "messages.jsonl"

    client = CodexMcpClient(codex_bin=str(fake_bin))
    try:
        client.start()
        result = client.call_codex(prompt="hello", cwd=tmp_path, timeout=1.0)
    finally:
        client.close()

    messages = _wait_for_messages(record_path, 3)
    assert messages[0]["method"] == "initialize"
    assert messages[0]["params"]["clientInfo"]["name"] == "mir_executor"
    assert "protocolVersion" not in messages[0]["params"]
    assert "jsonrpc" not in messages[0]
    assert messages[1]["method"] == "initialized"
    assert result.content_text == "codex completed"


def test_call_codex_maps_content_and_thread_id(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="success")
    record_path = tmp_path / "messages.jsonl"

    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        result = client.call_codex(prompt="implement s1", cwd=tmp_path, timeout=1.0)

    assert result.content_text == "codex completed"
    assert result.thread_id == "thread-123"

    tool_call = _wait_for_messages(record_path, 3)[2]
    assert tool_call["method"] == "thread/start"
    assert tool_call["params"] == {
        "cwd": str(tmp_path),
        "sandbox": "danger-full-access",
        "approvalPolicy": "never",
    }
    turn_call = _wait_for_messages(record_path, 4)[3]
    assert turn_call["method"] == "turn/start"
    assert turn_call["params"] == {
        "threadId": "thread-123",
        "input": [{"type": "text", "text": "implement s1"}],
    }


def test_call_codex_includes_base_instructions_and_config(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="success")
    record_path = tmp_path / "messages.jsonl"

    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        client.call_codex(
            prompt="implement s1",
            cwd=tmp_path,
            base_instructions="SLIM",
            config={"project_doc_max_bytes": 0},
            timeout=1.0,
        )

    tool_call = _wait_for_messages(record_path, 3)[2]
    assert tool_call["params"] == {
        "cwd": str(tmp_path),
        "sandbox": "danger-full-access",
        "approvalPolicy": "never",
        "baseInstructions": "SLIM",
        "config": {"project_doc_max_bytes": 0},
    }
    assert "model" not in tool_call["params"]


def test_call_codex_includes_model_with_base_instructions_and_config(
    tmp_path: pathlib.Path,
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="success")
    record_path = tmp_path / "messages.jsonl"

    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        client.call_codex(
            prompt="implement routing",
            cwd=tmp_path,
            model="high",
            base_instructions="SLIM",
            config={"project_doc_max_bytes": 0},
            timeout=1.0,
        )

    tool_call = _wait_for_messages(record_path, 3)[2]
    assert tool_call["params"] == {
        "cwd": str(tmp_path),
        "sandbox": "danger-full-access",
        "approvalPolicy": "never",
        "model": "high",
        "baseInstructions": "SLIM",
        "config": {"project_doc_max_bytes": 0},
    }


def test_call_codex_base_instructions_without_config_omits_config(
    tmp_path: pathlib.Path,
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="success")
    record_path = tmp_path / "messages.jsonl"

    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        client.call_codex(
            prompt="implement s1",
            cwd=tmp_path,
            base_instructions="SLIM",
            timeout=1.0,
        )

    arguments = _wait_for_messages(record_path, 3)[2]["params"]
    assert arguments["baseInstructions"] == "SLIM"
    assert "config" not in arguments


def test_client_uses_codex_bin_environment_default(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="success")
    monkeypatch.setenv("CODEX_BIN", str(fake_bin))

    with CodexMcpClient() as client:
        result = client.call_codex(prompt="env bin", cwd=tmp_path, timeout=1.0)

    assert result.thread_id == "thread-123"


def test_call_timeout_kills_server_and_rejects_pending(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="timeout")
    client = CodexMcpClient(codex_bin=str(fake_bin), kill_timeout=1.0)
    client.start()

    with pytest.raises(CodexMcpTimeoutError):
        client.call_codex(prompt="hang", cwd=tmp_path, timeout=0.05, stall_timeout=None)

    assert client.pending_count == 0
    assert client.is_running is False


def test_call_timeout_none_waits_for_completion(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="delayed")

    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
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
        if method == "thread/start":
            return {"thread": {"id": "thread-test"}}
        turn = {
            "id": "turn-test",
            "status": "completed",
            "items": [{"type": "agentMessage", "id": "item-test", "text": "done"}],
        }
        client._handle_stdout_line(
            json.dumps(
                {"method": "turn/completed", "params": {"threadId": "thread-test", "turn": turn}}
            )
        )
        return {"turn": turn}

    monkeypatch.setattr(client, "_request", fake_request)

    result = client.call_codex(prompt="wait", cwd=tmp_path, timeout=None)

    assert result.content_text == "done"
    assert observed_timeouts == [None, None]


def test_stall_watchdog_kills_silent_server_and_rejects_pending(
    tmp_path: pathlib.Path,
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="timeout")
    client = CodexMcpClient(codex_bin=str(fake_bin), kill_timeout=1.0)
    client.start()

    with pytest.raises(CodexMcpStallError):
        client.call_codex(prompt="silent", cwd=tmp_path, timeout=5.0, stall_timeout=0.05)

    assert client.pending_count == 0
    assert client.is_running is False


def test_progress_callback_is_invoked_for_notifications(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="notification")
    progress: list[tuple[str, object]] = []

    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        result = client.call_codex(
            prompt="notify",
            cwd=tmp_path,
            timeout=1.0,
            progress_callback=lambda method, params: progress.append((method, params)),
        )

    assert result.content_text == "codex completed"
    assert [method for method, _ in progress] == [
        "item/agentMessage/delta",
        "item/completed",
        "turn/completed",
    ]


def test_close_during_pending_call_tears_down_reader_threads_cleanly(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="pending_notification")
    # This test checks teardown; keep the normal startup budget for process scheduling.
    client = CodexMcpClient(codex_bin=str(fake_bin), kill_timeout=0.1)
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
            if "item/agentMessage/delta" in line:
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
    fake_bin = _write_fake_app_server(tmp_path, mode="malformed")

    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        result = client.call_codex(prompt="after malformed", cwd=os.fspath(tmp_path), timeout=1.0)

    assert result.content_text == "codex completed"
    assert client.malformed_messages == ["{not-json"]


@pytest.mark.parametrize("kind", ["none", "list", "string"])
def test_malformed_item_notification_rejects_pending_turn(
    tmp_path: pathlib.Path, kind: str
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode=f"malformed_notification_{kind}")

    with CodexMcpClient(codex_bin=str(fake_bin), call_timeout=None) as client:
        with pytest.raises(CodexMcpProtocolError, match="item/completed.*item"):
            client.call_codex(prompt="malformed item", cwd=tmp_path, timeout=1.0)
        assert client.pending_count == 0
        assert not client.is_running


@pytest.mark.parametrize("mode", ["malformed_completion_items", "malformed_completion_item"])
def test_malformed_completion_items_raise_protocol_error(
    tmp_path: pathlib.Path, mode: str
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode=mode)

    with CodexMcpClient(codex_bin=str(fake_bin), call_timeout=None) as client:
        with pytest.raises(CodexMcpProtocolError, match="turn/completed.*items"):
            client.call_codex(prompt="malformed items", cwd=tmp_path, timeout=1.0)
        assert client.pending_count == 0
        assert not client.is_running


@pytest.mark.parametrize(
    "mode, method",
    [
        ("bad_item_params_list", "item/completed"),
        ("bad_item_thread_id_list", "item/completed"),
        ("bad_item_thread_id_dict", "item/completed"),
        ("bad_item_thread_id_missing", "item/completed"),
        ("bad_turn_params_list", "turn/completed"),
        ("bad_turn_thread_id_list", "turn/completed"),
        ("bad_turn_thread_id_dict", "turn/completed"),
        ("bad_turn_thread_id_missing", "turn/completed"),
    ],
)
def test_malformed_completion_notification_rejects_pending_turn(
    tmp_path: pathlib.Path, mode: str, method: str
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode=mode)

    with CodexMcpClient(codex_bin=str(fake_bin), call_timeout=None) as client:
        with pytest.raises(CodexMcpProtocolError, match=method):
            client.call_codex(prompt="malformed notification", cwd=tmp_path, timeout=1.0)
        assert client.pending_count == 0
        assert not client.is_running


@pytest.mark.parametrize(
    "mode, method",
    [
        ("malformed_agent_id", "item/completed"),
        ("malformed_agent_text", "item/completed"),
        ("malformed_completion_agent_id", "turn/completed"),
        ("malformed_completion_agent_text", "turn/completed"),
    ],
)
def test_malformed_agent_message_fields_raise_protocol_error(
    tmp_path: pathlib.Path, mode: str, method: str
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode=mode)

    with CodexMcpClient(codex_bin=str(fake_bin), call_timeout=None) as client:
        with pytest.raises(CodexMcpProtocolError, match=f"{method}.*agent message fields"):
            client.call_codex(prompt="malformed agent message", cwd=tmp_path, timeout=1.0)
        assert client.pending_count == 0
        assert not client.is_running


@pytest.mark.parametrize(
    "mode", ["early_completion", "completion_items", "duplicate_items", "commentary"]
)
def test_should_return_text_once_when_completion_order_varies(
    tmp_path: pathlib.Path, mode: str
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode=mode)
    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        result = client.call_codex(prompt="hello", cwd=tmp_path, timeout=1.0)
        assert client.pending_count == 0
    assert result.content_text == "codex completed"
    assert result.thread_id == "thread-123"
    assert result.raw_result["turn"]["status"] == "completed"


@pytest.mark.parametrize(
    "mode, message",
    [
        ("failed", "model unavailable"),
        ("interrupted", "interrupted"),
        ("rpc_error", "bad model"),
        ("approval", "Unsupported app-server request"),
    ],
)
def test_should_raise_protocol_error_when_turn_cannot_complete(
    tmp_path: pathlib.Path,
    mode: str,
    message: str,
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode=mode)
    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        with pytest.raises(CodexMcpProtocolError, match=message):
            client.call_codex(prompt="fail", cwd=tmp_path, timeout=1.0)
        assert client.pending_count == 0
        assert not client.is_running


def test_should_raise_process_error_when_server_exits_during_turn(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="exit")
    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        with pytest.raises(CodexMcpProcessError, match="exited with code 7"):
            client.call_codex(prompt="exit", cwd=tmp_path, timeout=1.0)
        assert client.pending_count == 0


@pytest.mark.parametrize("mode", ["thread_timeout", "stubborn_timeout"])
def test_should_kill_process_when_thread_or_turn_times_out(
    tmp_path: pathlib.Path, mode: str
) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode=mode)
    with CodexMcpClient(codex_bin=str(fake_bin), kill_timeout=0.05) as client:
        proc = client._proc
        with pytest.raises(CodexMcpTimeoutError):
            client.call_codex(prompt="timeout", cwd=tmp_path, timeout=0.05)
        assert proc is not None and proc.poll() is not None
        assert client.pending_count == 0
        assert not client.is_running


def test_should_keep_waiting_when_turn_emits_activity(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="heartbeat")
    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        result = client.call_codex(prompt="wait", cwd=tmp_path, timeout=5, stall_timeout=1)
    assert result.content_text == "codex completed"


def test_should_pass_thread_settings_to_app_server(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="success")
    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        client.call_codex(
            prompt="read only",
            cwd=tmp_path,
            sandbox="read-only",
            approval_policy="on-request",
            model="gpt-6-luna",
            config={"model_reasoning_effort": "low"},
            timeout=1,
        )
    params = _read_messages(tmp_path / "messages.jsonl")[2]["params"]
    assert params == {
        "cwd": str(tmp_path),
        "sandbox": "read-only",
        "approvalPolicy": "on-request",
        "model": "gpt-6-luna",
        "config": {"model_reasoning_effort": "low"},
    }
