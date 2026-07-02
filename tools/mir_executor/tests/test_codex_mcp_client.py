"""Unit tests for the Codex MCP JSON-RPC client."""

from __future__ import annotations

import json
import os
import pathlib
import shlex
import stat
import sys
import textwrap
import time

import pytest

from tools.mir_executor.codex_mcp_client import (
    CodexMcpClient,
    CodexMcpTimeoutError,
)


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
    shell_path = os.sep.join(("", "bin", "sh"))
    fake_bin.write_text(
        "\n".join(
            [
                f"#!{shell_path}",
                f"exec {shlex.quote(sys.executable)} {shlex.quote(str(server_py))} \"$@\"",
                "",
            ]
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
        result = client.call_codex(prompt="implement task", cwd=tmp_path, timeout=1.0)

    assert result.content_text == "codex completed"
    assert result.thread_id == "thread-123"

    tool_call = _wait_for_messages(record_path, 3)[2]
    assert tool_call["method"] == "tools/call"
    assert tool_call["params"]["name"] == "codex"
    assert tool_call["params"]["arguments"] == {
        "prompt": "implement task",
        "cwd": str(tmp_path),
        "sandbox": "danger-full-access",
        "approval-policy": "never",
    }


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
        client.call_codex(prompt="hang", cwd=tmp_path, timeout=0.05)

    assert client.pending_count == 0
    assert client.is_running is False


def test_malformed_json_line_is_recorded_and_ignored(tmp_path: pathlib.Path) -> None:
    fake_bin = _write_fake_mcp_server(tmp_path, mode="malformed")

    with CodexMcpClient(codex_bin=str(fake_bin), initialize_timeout=1.0) as client:
        result = client.call_codex(prompt="after malformed", cwd=os.fspath(tmp_path), timeout=1.0)

    assert result.content_text == "codex completed"
    assert client.malformed_messages == ["{not-json"]
