"""V3 item validation and provider metadata contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.mir_executor.codex_mcp_client import (
    CodexMcpClient,
    CodexMcpProtocolError,
    CodexMcpResult,
)
from tools.mir_executor.tests.test_codex_mcp_client import _write_fake_app_server


@pytest.mark.parametrize("delivery", ["item/completed", "turn/completed"])
@pytest.mark.parametrize(
    "item", [None, [], {}, {"type": None}, {"type": 5}, {"type": "agentMessage"}]
)
def test_should_reject_malformed_items_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delivery: str, item: object
) -> None:
    client = CodexMcpClient()

    def request(method: str, params: object, **kwargs: object) -> object:
        if method == "thread/start":
            return {"thread": {"id": "thread-test"}}
        turn = {"id": "turn-test", "status": "completed", "items": [item]}
        payload = {"threadId": "thread-test", "turn": turn, "item": item}
        client._handle_stdout_line(json.dumps({"method": delivery, "params": payload}))
        return {"turn": turn}

    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(CodexMcpProtocolError):
        client.call_codex(prompt="test", cwd=tmp_path, timeout=0.01)
    assert not client._pending


@pytest.mark.parametrize("delivery", ["item/completed", "turn/completed"])
def test_should_ignore_unknown_string_item_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, delivery: str
) -> None:
    client = CodexMcpClient()

    def request(method: str, params: object, **kwargs: object) -> object:
        if method == "thread/start":
            return {"thread": {"id": "thread-test"}}
        item = {"type": "futureItem"}
        turn = {"id": "turn-test", "status": "completed", "items": [item]}
        if delivery == "item/completed":
            client._handle_stdout_line(json.dumps({"method": delivery, "params": {
                "threadId": "thread-test", "item": item,
            }}))
        client._handle_stdout_line(json.dumps({"method": "turn/completed", "params": {
            "threadId": "thread-test", "turn": turn,
        }}))
        return {"turn": turn}

    monkeypatch.setattr(client, "_request", request)
    assert client.call_codex(prompt="test", cwd=tmp_path).content_text == ""


def test_should_keep_result_constructor_backward_compatible() -> None:
    result = CodexMcpResult("done", "thread", {})
    assert result.model_id is None
    assert result.token_usage is None
    assert result.tool_version is None


def test_should_collect_tool_version_from_initialize(tmp_path: Path) -> None:
    fake_bin = _write_fake_app_server(tmp_path, mode="success")
    with CodexMcpClient(codex_bin=str(fake_bin)) as client:
        result = client.call_codex(prompt="test", cwd=tmp_path, timeout=1)
    assert result.tool_version == "fake-codex/0.156.0"


@pytest.mark.parametrize("usage_delivery", ["notification", "completion"])
def test_should_collect_provider_model_and_token_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, usage_delivery: str
) -> None:
    client = CodexMcpClient()
    usage = {"total": {"totalTokens": 21, "inputTokens": 13, "outputTokens": 8}}

    def request(method: str, params: object, **kwargs: object) -> object:
        if method == "thread/start":
            return {"thread": {"id": "thread-test"}, "model": "started-model"}
        # Another thread's update must not contaminate this call.
        client._handle_stdout_line(json.dumps({"method": "thread/tokenUsage/updated", "params": {
            "threadId": "other", "tokenUsage": {"total": {"totalTokens": 999}},
        }}))
        turn = {"id": "turn-test", "status": "completed", "items": [
            {"type": "agentMessage", "id": "a", "text": "done", "model": "untrusted"},
        ]}
        payload = {"threadId": "thread-test", "turn": turn,
                   "metadata": {"provider": {"modelId": "actual-model"}}}
        if usage_delivery == "notification":
            client._handle_stdout_line(json.dumps({
                "method": "thread/tokenUsage/updated", "params": {
                    "threadId": "thread-test", "tokenUsage": usage,
                },
            }))
        else:
            turn["tokenUsage"] = usage
        client._handle_stdout_line(json.dumps({"method": "turn/completed", "params": payload}))
        return {"turn": turn}

    monkeypatch.setattr(client, "_request", request)
    result = client.call_codex(prompt="test", cwd=tmp_path, model="requested-model")
    assert result.model_id == "actual-model"
    assert result.token_usage == usage
