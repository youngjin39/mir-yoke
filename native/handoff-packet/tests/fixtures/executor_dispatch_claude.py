"""Portable offline provider fixture; never launches a real provider."""

import json
import os
import sys
import time
from pathlib import Path

mode = sys.argv[1]
if mode == "codex_options_oracle":
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from types import SimpleNamespace
    from unittest.mock import patch

    from tools.mir_executor import dispatch

    data = json.load(sys.stdin)
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call_codex(self, **kwargs):
            captured.update(kwargs)
            captured.pop("progress_callback")
            captured.setdefault("model", None)
            captured.setdefault("stall_timeout", None)
            return SimpleNamespace(
                content_text="",
                thread_id="fixture",
                token_usage=None,
                raw_result={},
                model_id=None,
                tool_version=None,
            )

    with (
        patch.object(dispatch, "dispatch_env", return_value=dict(os.environ)),
        patch.object(
            dispatch, "_provider_runner", side_effect=lambda _root, runner, **kwargs: runner
        ),
    ):
        runner = dispatch.build_codex_mcp_runner(
            Path(data["root"]),
            data["prompt"],
            timeout_seconds=data["timeout"],
            model=data["model"],
            reasoning_effort=data["effort"],
            stall_timeout=data["stall_timeout"],
            client_factory=FakeClient,
            agent_route=SimpleNamespace(**data["agent"]) if data["agent"] else None,
        )
        runner(SimpleNamespace(path=Path(data["cwd"]), dispatch_id="fixture"), 1)
    print(json.dumps(captured))
    sys.exit(0)
if mode == "claude_oracle":
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from dataclasses import asdict
    from types import SimpleNamespace
    from unittest.mock import patch

    from tools.mir_executor import dispatch

    data = json.load(sys.stdin)
    guarded = dispatch._run_guarded

    def run_fake(_command, cwd, env, timeout):
        return guarded(data["command"], cwd, env, timeout)

    with (
        patch.object(dispatch, "dispatch_env", return_value=dict(os.environ)),
        patch.object(dispatch, "_run_guarded", side_effect=run_fake),
    ):
        result = dispatch._run_claude_adapter(
            Path(data["cwd"]),
            SimpleNamespace(path=Path(data["cwd"]), dispatch_id="fixture"),
            timeout_seconds=data["timeout"],
        )
    print(json.dumps(asdict(result)))
    sys.exit(0)
if mode == "oracle":
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from tools.mir_executor.dispatch import _error_sig_from_text, _mcp_tokens

    data = json.load(sys.stdin)
    print(
        json.dumps(
            {"tokens": _mcp_tokens(data["raw"]), "signature": _error_sig_from_text(data["stderr"])}
        )
    )
    sys.exit(0)
if mode == "claude":
    print(
        json.dumps(
            {
                "argv": sys.argv[2:],
                "project": os.environ.get("CLAUDE_PROJECT_DIR"),
                "cwd": os.getcwd(),
                "text": "completed \u2713",
            }
        )
    )
    print("fixture diagnostic", file=sys.stderr)
    sys.exit(7)
if mode == "timeout":
    print("started", flush=True)
    time.sleep(60)
    sys.exit(0)


def send(value):
    print(json.dumps(value), flush=True)


for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialize":
        send({"id": message["id"], "result": {"userAgent": "fixture/1"}})
    elif method == "thread/start":
        assert message["params"]["approvalPolicy"] == "never"
        if mode == "codex_timeout":
            time.sleep(60)
        if mode == "codex_error":
            send({"id": message["id"], "error": {"message": "fixture error"}})
            continue
        send(
            {
                "id": message["id"],
                "result": {"thread": {"id": "thread-fixture"}, "model": "resolved"},
            }
        )
    elif method == "turn/start":
        send({"id": message["id"], "result": {"turn": {"id": "turn-fixture"}}})
        send(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-fixture",
                    "turn": {
                        "id": "turn-fixture",
                        "status": "completed",
                        "items": [
                            {
                                "id": "item-fixture",
                                "type": "agentMessage",
                                "text": "completed \u2713",
                            }
                        ],
                        "usage": {"inputTokens": 12, "outputTokens": 3},
                    },
                },
            }
        )
