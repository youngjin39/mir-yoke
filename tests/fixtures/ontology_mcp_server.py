"""Fake newline-delimited MCP peer; no service, database or external dependencies."""

import json
import os
import sys
import time
from pathlib import Path

mode = sys.argv[1]
Path("pid").write_text(str(os.getpid()))
for line in sys.stdin:
    message = json.loads(line)
    with Path("messages.jsonl").open("a") as log:
        log.write(json.dumps(message) + "\n")
    if message["method"] == "initialize":
        if mode == "init_timeout":
            time.sleep(60)
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "fake", "version": "1"},
        }
    elif message["method"] == "notifications/initialized":
        continue
    else:
        if mode == "timeout":
            time.sleep(60)
        if mode == "malformed":
            print("{", flush=True)
            continue
        if mode == "error":
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "error": {"code": -32603, "message": "fixture error"},
                    }
                ),
                flush=True,
            )
            continue
        if message["params"]["name"] == "feedback":
            pack = message["params"]["arguments"]
        elif mode in ("refusal", "refusal_empty"):
            pack = {
                "status": "refused",
                "reason": "personal namespace is unavailable",
                "namespace": "ns:personal",
            }
        else:
            pack = {
                "schema_version": "mir-context-pack-v1",
                "nodes": [] if mode == "empty" else [{"title": "Fixture"}],
                "citations": [],
            }
        if mode == "refusal_empty":
            pack["nodes"] = []
        if mode == "empty_object":
            pack = {}
        result = {"content": [{"type": "text", "text": json.dumps(pack)}]}
        if mode == "empty_content":
            result["content"] = []
        if mode not in ("text", "empty_content"):
            result["structuredContent"] = pack
        if mode == "tool_error":
            result["isError"] = True
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
