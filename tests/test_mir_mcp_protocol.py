"""Hermetic ADR-91 dual-era stdio contract through both host interpreters."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "plugins/mir-mcp"
VERSIONS = ["2026-07-28", "2025-11-25"]
TOOLS = [
    "ontology_validate",
    "ontology_lookup",
    "ontology_impact",
    "handoff_pins",
    "relations_query",
]
META = {
    "io.modelcontextprotocol/protocolVersion": VERSIONS[0],
    "io.modelcontextprotocol/clientInfo": {"name": "hermetic-test", "version": "1.0.0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}
ERRORS = [
    "E_SCHEMA",
    "E_PATH",
    "E_PROTECTED",
    "E_LIMIT",
    "E_FORMAT",
    "E_VERSION",
    "E_IO",
    "E_GIT",
    "E_TIMEOUT",
    "E_CURSOR",
]
CACHE = {"ttlMs": 3600000, "cacheScope": "public"}


@pytest.fixture(
    params=["/usr/bin/python3", str(ROOT / ".venv/bin/python")],
    ids=["system-python", "venv-python"],
)
def interpreter(request) -> str:
    assert Path(request.param).is_file(), "Both compatibility interpreters must be available"
    return request.param


def _request(method: str, params: dict | None = None, *, modern: bool = True, identity=1) -> dict:
    values = copy.deepcopy(params or {})
    if modern:
        values["_meta"] = copy.deepcopy(META)
    return {"jsonrpc": "2.0", "id": identity, "method": method, "params": values}


def _run(interpreter: str, frames: list, *, package: Path = PACKAGE, cwd: Path) -> list[dict]:
    payload = b"".join(
        (json.dumps(frame, separators=(",", ":")).encode() if isinstance(frame, dict) else frame)
        + b"\n"
        for frame in frames
    )
    completed = subprocess.run(
        [interpreter, "-I", "-B", "-u", str(package / "mir_mcp.py")],
        input=payload,
        capture_output=True,
        cwd=cwd,
        env={},
        timeout=15,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert b"Traceback" not in completed.stderr
    lines = completed.stdout.splitlines()
    assert lines, "Server must produce protocol output"
    results = []
    for line in lines:
        assert len(line) <= 16384
        value = json.loads(line)
        assert value["jsonrpc"] == "2.0"
        assert set(value) in ({"jsonrpc", "id", "result"}, {"jsonrpc", "id", "error"})
        results.append(value)
    return results


def _success(value: dict, *, modern: bool = True) -> dict:
    assert "error" not in value, value
    result = value["result"]
    if modern:
        assert result["resultType"] == "complete"
    else:
        assert "resultType" not in result
    return result


def _tool_result(value: dict, *, modern: bool = True) -> dict:
    result = _success(value, modern=modern)
    structured = result["structuredContent"]
    assert set(structured) == {"ok", "data", "error", "next_cursor", "profile_protections"}
    assert isinstance(structured["ok"], bool)
    assert result["isError"] is not structured["ok"]
    if structured["ok"]:
        assert result["content"] == []
    else:
        [item] = result["content"]
        assert set(item) == {"type", "text"} and item["type"] == "text"
        assert len(json.dumps(item["text"], ensure_ascii=False).encode()) <= 512
        assert json.loads(item["text"])["code"] == structured["error"]["code"]
    assert structured["profile_protections"] in {"available", "unavailable"}
    assert structured["error"] is None or (
        set(structured["error"]) == {"code"} and structured["error"]["code"] in ERRORS
    )
    return structured


def test_modern_discovery_and_direct_calls(interpreter: str, tmp_path: Path) -> None:
    replies = _run(
        interpreter,
        [
            _request("server/discover", identity=1),
            _request("tools/list", identity=2),
            _request(
                "tools/call",
                {
                    "name": "ontology_validate",
                    "arguments": {"target_root": str(tmp_path), "scope": "contract"},
                },
                identity=3,
            ),
        ],
        cwd=tmp_path,
    )
    assert [reply["id"] for reply in replies] == [1, 2, 3]
    discovery = _success(replies[0])
    assert discovery["supportedVersions"] == VERSIONS
    assert discovery["capabilities"] == {"tools": {}}
    assert {key: discovery[key] for key in CACHE} == CACHE
    listed = _success(replies[1])
    assert {key: listed[key] for key in CACHE} == CACHE
    _assert_inventory(listed)
    assert _tool_result(replies[2])["ok"] is True
    assert not set(CACHE) & set(replies[2]["result"])


def _assert_inventory(result: dict) -> None:
    assert "nextCursor" not in result
    assert [tool["name"] for tool in result["tools"]] == TOOLS
    fields = {
        "ontology_validate": {"scope"},
        "ontology_lookup": {"query", "limit"},
        "ontology_impact": {"paths"},
        "handoff_pins": {"paths"},
        "relations_query": {"adapter", "graph", "anchor", "purpose", "depth", "max_edges"},
    }
    required = {
        "ontology_validate": set(),
        "ontology_lookup": {"query"},
        "ontology_impact": {"paths"},
        "handoff_pins": {"paths"},
        "relations_query": {"anchor", "purpose"},
    }
    output_required = {
        "ontology_validate": {
            (): {"valid", "contract_version", "mapping_version", "counts", "findings"},
            ("properties", "counts"): {"errors", "warnings", "refs"},
            ("properties", "findings", "items"): {"code", "pointer"},
        },
        "ontology_lookup": {
            (): {"contract", "matches"},
            ("properties", "contract"): {"id", "version"},
            ("properties", "matches", "items"): {"pointer", "score", "label", "refs"},
        },
        "ontology_impact": {
            (): {"affected_entries", "checks_to_run", "stale_refs",
                 "undeclared_check_links", "revalidate"},
            ("properties", "affected_entries", "items"): {"pointer", "refs"},
            ("properties", "stale_refs", "items"): {"pointer", "ref", "code"},
            ("properties", "undeclared_check_links", "items"): {"pointer", "ref"},
        },
        "handoff_pins": {
            (): {"repository_root", "head", "dirty", "sources", "mapping_path",
                 "mapping_version", "mapping_sha256", "contract_id", "contract_version",
                 "contract_sha256", "observed_at", "unknowns", "pin_inventory"},
            ("properties", "sources", "items"): {
                "path", "revision", "sha256", "modified_vs_head",
            },
            ("properties", "pin_inventory", "items"): {
                "pin", "pointer", "kind", "required", "availability",
            },
        },
        "relations_query": {
            (): {"anchor", "purpose", "scope", "source", "edges", "notices", "truncated",
                 "resolved_anchors"},
            ("properties", "source"): {"graph", "sha256"},
            ("properties", "edges", "items"): {"source", "relation", "target", "source_line"},
        },
    }
    for tool in result["tools"]:
        assert set(tool) == {"name", "description", "inputSchema", "outputSchema", "annotations"}
        assert tool["description"] and "\n" not in tool["description"]
        assert tool["annotations"] == {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        }
        schema = tool["inputSchema"]
        assert schema["type"] == "object" and schema["additionalProperties"] is False
        assert (
            set(schema["properties"])
            == {"target_root", "cursor", "page_size"} | fields[tool["name"]]
        )
        assert set(schema["required"]) == {"target_root"} | required[tool["name"]]
        assert schema["properties"]["target_root"]["type"] == "string"
        assert schema["properties"]["page_size"]["minimum"] == 1
        assert schema["properties"]["page_size"]["maximum"] == 64
        assert schema["properties"]["page_size"]["default"] == 16
        if tool["name"] == "ontology_lookup":
            assert schema["properties"]["limit"]["maximum"] == 16
        output = tool["outputSchema"]
        assert output["type"] == "object" and output["additionalProperties"] is False
        assert set(output["properties"]) == {
            "ok",
            "data",
            "error",
            "next_cursor",
            "profile_protections",
        }
        assert set(output["required"]) == {
            "ok",
            "data",
            "error",
            "next_cursor",
            "profile_protections",
        }
        assert set(output["properties"]["error"]["anyOf"][0]["required"]) == {"code"}
        data = output["properties"]["data"]["anyOf"][0]
        for path, expected in output_required[tool["name"]].items():
            nested = data
            for key in path:
                nested = nested[key]
            assert set(nested["required"]) == expected, (tool["name"], path)
    assert len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()) <= 16384


def test_legacy_initialization_list_and_call(interpreter: str, tmp_path: Path) -> None:
    replies = _run(
        interpreter,
        [
            _request(
                "initialize",
                {
                    "protocolVersion": VERSIONS[1],
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
                modern=False,
            ),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            _request("tools/list", modern=False, identity=2),
            _request(
                "tools/call",
                {
                    "name": "ontology_validate",
                    "arguments": {"target_root": str(tmp_path), "scope": "contract"},
                },
                modern=False,
                identity=3,
            ),
        ],
        cwd=tmp_path,
    )
    assert len(replies) == 3
    initialized = _success(replies[0], modern=False)
    assert initialized["protocolVersion"] == VERSIONS[1]
    assert initialized["capabilities"] == {"tools": {}}
    assert set(_success(replies[1], modern=False)) == {"tools"}
    _assert_inventory(_success(replies[1], modern=False))
    assert _tool_result(replies[2], modern=False)["ok"] is True


CODEX_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 0,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {
            "experimental": {"codex/auth-change": {}},
            "elicitation": {"form": {}, "url": {}},
        },
        "clientInfo": {"name": "codex-mcp-client", "title": "Codex", "version": "0.164.0"},
    },
}


def test_codex_legacy_session_negotiates_and_ignores_request_metadata(
    interpreter: str, tmp_path: Path
) -> None:
    replies = _run(
        interpreter,
        [
            CODEX_INITIALIZE,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": {"progressToken": 0}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "_meta": {"callId": "exec-1", "x-codex-turn-metadata": {"turn": 1}},
                "name": "ontology_validate",
                "arguments": {"target_root": str(tmp_path), "scope": "contract"},
            }},
        ],
        cwd=tmp_path,
    )
    assert [reply["id"] for reply in replies] == [0, 1, 2]
    initialized = _success(replies[0], modern=False)
    assert initialized["protocolVersion"] == VERSIONS[1]
    assert initialized["capabilities"] == {"tools": {}}
    _assert_inventory(_success(replies[1], modern=False))
    assert _tool_result(replies[2], modern=False)["ok"] is True


def test_legacy_request_metadata_without_version_is_ordinary(
    interpreter: str, tmp_path: Path
) -> None:
    initialize = _request("initialize", {
        "protocolVersion": VERSIONS[1], "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    }, modern=False)
    replies = _run(
        interpreter,
        [
            initialize,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
             "params": {"_meta": {"progressToken": 0}}},
        ],
        cwd=tmp_path,
    )
    assert [reply["id"] for reply in replies] == [1, 2]
    _assert_inventory(_success(replies[1], modern=False))


def test_versioned_metadata_after_legacy_initialization_stays_modern(
    interpreter: str, tmp_path: Path
) -> None:
    unsupported = _request("tools/list", identity=2)
    unsupported["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "1900-01-01"
    incomplete = _request("tools/list", identity=3)
    del incomplete["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"]
    replies = _run(
        interpreter,
        [
            CODEX_INITIALIZE,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            unsupported,
            incomplete,
            _request("tools/list", identity=4),
        ],
        cwd=tmp_path,
    )
    assert [reply["id"] for reply in replies] == [0, 2, 3, 4]
    assert _success(replies[0], modern=False)["protocolVersion"] == VERSIONS[1]
    assert replies[1]["error"]["code"] == -32022
    assert replies[1]["error"]["data"] == {
        "code": "E_VERSION", "supported": VERSIONS, "requested": "1900-01-01"
    }
    assert replies[2]["error"]["data"] == {"code": "E_SCHEMA"}
    _assert_inventory(_success(replies[3]))


def test_unversioned_metadata_before_initialization_is_refused(
    interpreter: str, tmp_path: Path
) -> None:
    frame = {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": {"progressToken": 0}}}
    pending = copy.deepcopy(frame)
    pending["id"] = 2
    replies = _run(interpreter, [frame, CODEX_INITIALIZE, pending], cwd=tmp_path)
    assert replies[0]["error"]["code"] == -32602
    assert replies[0]["error"]["data"] == {"code": "E_SCHEMA"}
    assert replies[2]["id"] == 2
    assert replies[2]["error"]["data"] == {"code": "E_SCHEMA"}


@pytest.mark.parametrize(
    "key", ["io.modelcontextprotocol/protocolVersion", "io.modelcontextprotocol/clientCapabilities"]
)
def test_direct_modern_calls_require_version_and_capabilities(
    interpreter: str, tmp_path: Path, key: str
) -> None:
    frame = _request("tools/list")
    del frame["params"]["_meta"][key]
    reply = _run(interpreter, [frame], cwd=tmp_path)[0]
    assert reply["error"]["data"] == {"code": "E_SCHEMA"}


@pytest.mark.parametrize("era", ["legacy", "modern"])
def test_unsupported_version_is_explicit(interpreter: str, tmp_path: Path, era: str) -> None:
    if era == "legacy":
        frame = _request("initialize", {
            "protocolVersion": "1900-01-01", "clientInfo": {"name": "test", "version": "1"},
            "capabilities": {},
        }, modern=False)
        # The MCP lifecycle answers an unsupported request with a supported version.
        result = _success(_run(interpreter, [frame], cwd=tmp_path)[0], modern=False)
        assert result["protocolVersion"] == VERSIONS[1]
        return
    frame = _request("server/discover")
    frame["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "1900-01-01"
    error = _run(interpreter, [frame], cwd=tmp_path)[0]["error"]
    assert error["code"] == -32022
    assert error["data"] == {"code": "E_VERSION", "supported": VERSIONS, "requested": "1900-01-01"}


@pytest.mark.parametrize("limit", [16, 17])
def test_ontology_lookup_limit_boundary(interpreter, tmp_path, limit):
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/ontology-map.json").write_text(json.dumps({
        "contract": {"id": "mir.common-semantics", "version": "1.1.0"},
        "domain": {"concepts": [{"name": "sample", "ref": "source.py"}]},
    }))
    (tmp_path / "source.py").write_text("def sample(): pass\n")
    result = _tool_result(_run(interpreter, [_request("tools/call", {
        "name": "ontology_lookup",
        "arguments": {"target_root": str(tmp_path), "query": "sample", "limit": limit},
    })], cwd=tmp_path)[0])
    if limit == 16:
        assert result["ok"] is True
        assert result["data"]["matches"]
    else:
        assert result["ok"] is False
        assert result["error"] == {"code": "E_SCHEMA"}


@pytest.mark.parametrize("metadata", [None, [], 1])
def test_malformed_legacy_metadata_cannot_crash(interpreter, tmp_path, metadata):
    request = _request("initialize", {"protocolVersion": "1900-01-01", "_meta": metadata},
                       modern=False)
    responses = _run(interpreter, [request, _request("tools/list", identity=2)], cwd=tmp_path)
    assert responses[0]["error"]["data"]["code"] in {"E_VERSION", "E_SCHEMA"}
    _assert_inventory(_success(responses[1]))


@pytest.mark.parametrize("era", ["legacy", "modern"])
@pytest.mark.parametrize("value", [{}, [], 7, None, True], ids=["object", "array", "number",
                                                          "null", "bool"])
def test_nonstring_protocol_version_errors_and_next_request_survives(
    interpreter, tmp_path, era, value
):
    if era == "legacy":
        frame = _request("initialize", {
            "protocolVersion": value, "clientInfo": {"name": "test", "version": "1"},
            "capabilities": {},
        }, modern=False)
    else:
        frame = _request("tools/list")
        frame["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = value
    replies = _run(interpreter, [frame, _request("tools/list", identity=2)], cwd=tmp_path)
    assert len(replies) == 2
    assert replies[0]["error"]["data"] == {"code": "E_SCHEMA"}
    assert replies[1]["id"] == 2
    _assert_inventory(_success(replies[1]))


def _request_field_cases():
    fields = [
        ("modern", (), (dict,)),
        ("modern", ("jsonrpc",), (str,)),
        ("modern", ("id",), (str, int)),
        ("modern", ("method",), (str,)),
        ("modern", ("params",), (dict,)),
        ("modern", ("params", "_meta"), (dict,)),
        ("legacy", ("params",), (dict,)),
        ("legacy", ("params", "protocolVersion"), (str,)),
        ("legacy", ("params", "_meta"), (dict,)),
        ("legacy", ("params", "capabilities"), (dict,)),
        ("legacy", ("params", "clientInfo"), (dict,)),
    ]
    for key, types in [
        ("io.modelcontextprotocol/protocolVersion", (str,)),
        ("io.modelcontextprotocol/clientInfo", (dict,)),
        ("io.modelcontextprotocol/clientCapabilities", (dict,)),
    ]:
        fields.append(("modern", ("params", "_meta", key), types))
    for key in ("name", "version"):
        fields.append(("legacy", ("params", "clientInfo", key), (str,)))
        fields.append(("modern", ("params", "_meta",
                                  "io.modelcontextprotocol/clientInfo", key), (str,)))
    fields.extend([
        ("ontology_validate", ("params", "name"), (str,)),
        ("ontology_validate", ("params", "arguments"), (dict,)),
    ])
    common = {"target_root": str, "cursor": str, "page_size": int}
    additional = {
        "ontology_validate": {"scope": str},
        "ontology_lookup": {"query": str, "limit": int},
        "ontology_impact": {"paths": list},
        "handoff_pins": {"paths": list},
        "relations_query": {"adapter": str, "graph": str, "anchor": str,
                            "purpose": str, "depth": int, "max_edges": int},
    }
    for tool, properties in additional.items():
        for key, kind in {**common, **properties}.items():
            fields.append((tool, ("params", "arguments", key), (kind,)))
        if "paths" in properties:
            fields.append((tool, ("params", "arguments", "paths", 0), (str,)))
    return fields


@pytest.mark.parametrize("context,path,accepted", _request_field_cases(),
                         ids=lambda value: str(value))
def test_every_request_field_rejects_wrong_json_types_and_keeps_serving(
    interpreter, tmp_path, context, path, accepted
):
    if context == "legacy":
        template = _request("initialize", {
            "protocolVersion": VERSIONS[1], "clientInfo": {"name": "test", "version": "1"},
            "capabilities": {}, "_meta": {},
        }, modern=False)
    elif context == "modern":
        template = _request("tools/list")
    else:
        arguments = {"target_root": str(tmp_path)}
        arguments.update({
            "ontology_validate": {"scope": "contract"},
            "ontology_lookup": {"query": "test"},
            "ontology_impact": {"paths": ["source.txt"]},
            "handoff_pins": {"paths": ["source.txt"]},
            "relations_query": {"anchor": "REQ", "purpose": "implementation"},
        }[context])
        template = _request("tools/call", {"name": context, "arguments": arguments})
    frames = []
    for value in ({}, [], 7, 1.5, None, True, "wrong-type"):
        if type(value) in accepted:
            continue
        frame = copy.deepcopy(template)
        if path:
            parent = frame
            for part in path[:-1]:
                parent = parent[part]
            parent[path[-1]] = value
        else:
            frame = value
        frames.extend([json.dumps(frame).encode(), _request("tools/list", identity=2)])
    replies = _run(interpreter, frames, cwd=tmp_path)
    assert len(replies) == len(frames)
    for bad, good in zip(replies[::2], replies[1::2], strict=True):
        if "error" in bad:
            assert bad["error"]["data"] == {"code": "E_SCHEMA"}
        else:
            assert _tool_result(bad)["error"] == {"code": "E_SCHEMA"}
        assert good["id"] == 2
        _assert_inventory(_success(good))


@pytest.mark.parametrize("container", ["object", "array"])
def test_nested_malformed_version_never_escapes_error_envelope(interpreter, tmp_path, container):
    # Accepted request depth 32 would overflow the deeper E_VERSION response envelope.
    value = "bad"
    for _ in range(30):
        value = {"v": value} if container == "object" else [value]
    frame = _request("initialize", {"protocolVersion": value}, modern=False)
    replies = _run(interpreter, [frame, _request("tools/list", identity=2)], cwd=tmp_path)
    assert replies[0]["error"]["data"] == {"code": "E_SCHEMA"}
    _assert_inventory(_success(replies[1]))


@pytest.mark.parametrize(
    "method", ["resources/list", "prompts/list", "tasks/list", "unknown/action"]
)
def test_unadvertised_methods_are_rejected(interpreter: str, tmp_path: Path, method: str) -> None:
    error = _run(interpreter, [_request(method)], cwd=tmp_path)[0]["error"]
    assert error["code"] == -32601
    assert error["data"] == {"code": "E_SCHEMA"}


@pytest.mark.parametrize(
    "raw,code,reason", [(b"{malformed", -32700, "E_FORMAT"), (b"x" * 65537, -32600, "E_LIMIT")]
)
def test_malformed_oversized_frames_preserve_stdout_protocol(
    interpreter: str, tmp_path: Path, raw: bytes, code: int, reason: str
) -> None:
    replies = _run(interpreter, [raw, _request("tools/list", identity=7)], cwd=tmp_path)
    assert len(replies) == 2
    assert replies[0]["id"] is None
    assert replies[0]["error"]["code"] == code
    assert replies[0]["error"]["data"] == {"code": reason}
    assert replies[1]["id"] == 7
    _assert_inventory(_success(replies[1]))


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"target_root": "relative"},
        {"target_root": "/", "extra": True},
        {"target_root": "/", "page_size": True},
    ],
)
def test_invalid_tool_arguments_are_structured_errors(
    interpreter: str, tmp_path: Path, arguments: dict
) -> None:
    result = _tool_result(
        _run(
            interpreter,
            [_request("tools/call", {"name": "ontology_validate", "arguments": arguments})],
            cwd=tmp_path,
        )[0]
    )
    assert result["ok"] is False
    assert result["error"]["code"] in {"E_SCHEMA", "E_PATH"}
    assert result["data"] is None


@pytest.mark.parametrize("modern", [True, False], ids=["modern", "legacy"])
def test_failure_reason_is_visible_text_in_both_eras(
    interpreter: str, tmp_path: Path, modern: bool
) -> None:
    frames = [_request("tools/call", {"name": "ontology_validate", "arguments": {}},
                       modern=modern)]
    if not modern:
        frames[:0] = [
            _request("initialize", {
                "protocolVersion": VERSIONS[1], "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            }, modern=False),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        ]
    reply = _run(interpreter, frames, cwd=tmp_path)[-1]
    assert _tool_result(reply, modern=modern)["ok"] is False
    assert json.loads(reply["result"]["content"][0]["text"]) == {"code": "E_SCHEMA"}


@pytest.mark.parametrize("count", [2, 200])
def test_failure_text_keeps_bounded_prefix_of_unknowns(monkeypatch, count: int) -> None:
    source = PACKAGE / "mir_mcp.py"
    spec = importlib.util.spec_from_file_location("protocol_mir_mcp", source)
    server = importlib.util.module_from_spec(spec)
    # Compile from source so a test never writes __pycache__ into a plugin tree.
    exec(compile(source.read_bytes(), str(source), "exec"), server.__dict__)
    unknowns = [f"source-{index:03}.txt: E_GIT \"quoted\"" for index in range(count)]
    structured = {
        "ok": False,
        "data": {"unknowns": unknowns},
        "error": {"code": "E_GIT"},
        "next_cursor": None,
        "profile_protections": "available",
    }
    monkeypatch.setattr(server, "execute", lambda name, arguments: structured)
    reply = server.Protocol().request(
        _request("tools/call", {"name": "handoff_pins", "arguments": {}}, identity="x" * 256)
    )
    result = _tool_result(reply)
    assert result is structured
    reason = json.loads(reply["result"]["content"][0]["text"])
    assert reason["code"] == "E_GIT"
    assert reason["unknowns"] == unknowns[: len(reason["unknowns"])]
    if count == 2:
        assert set(reason) == {"code", "unknowns"} and reason["unknowns"] == unknowns
    else:
        assert set(reason) == {"code", "unknowns", "omitted"}
        assert 0 < len(reason["unknowns"]) < len(unknowns)
        assert reason["omitted"] == len(unknowns) - len(reason["unknowns"])


def test_isolated_package_works_without_checkout_or_siblings(
    interpreter: str, tmp_path: Path
) -> None:
    package = tmp_path / "isolated plugin with spaces"
    shutil.copytree(PACKAGE, package)
    target = tmp_path / "unrelated target"
    target.mkdir()
    result = _tool_result(
        _run(
            interpreter,
            [
                _request(
                    "tools/call",
                    {
                        "name": "ontology_validate",
                        "arguments": {"target_root": str(target), "scope": "contract"},
                    },
                )
            ],
            package=package,
            cwd=target,
        )[0]
    )
    assert result["ok"] is True
    assert not list(tmp_path.rglob("__pycache__"))
    assert not list(tmp_path.rglob("*.pyc"))


def test_codex_declaration_launches_without_variable_expansion(
    interpreter: str, tmp_path: Path
) -> None:
    # Codex passes declared args verbatim and resolves cwd "." to the installed plugin root;
    # without cwd it starts the server in the session directory.
    package = tmp_path / "installed plugin with spaces"
    shutil.copytree(PACKAGE, package)
    session = tmp_path / "session cwd"
    session.mkdir()
    server = json.loads((package / ".mcp.codex.json").read_text())["mcpServers"]["mir-mcp"]
    command = shutil.which(server["command"], path=str(Path(interpreter).parent))
    assert command is not None
    payload = b"".join(
        json.dumps(frame, separators=(",", ":")).encode() + b"\n"
        for frame in [
            _request(
                "initialize",
                {
                    "protocolVersion": VERSIONS[1],
                    "capabilities": {},
                    "clientInfo": {"name": "codex-launch", "version": "1"},
                },
                modern=False,
            ),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            _request("tools/list", modern=False, identity=2),
            _request(
                "tools/call",
                {
                    "name": "ontology_validate",
                    "arguments": {"target_root": str(session), "scope": "contract"},
                },
                modern=False,
                identity=3,
            ),
        ]
    )
    completed = subprocess.run(
        [command, *server["args"]],
        input=payload,
        capture_output=True,
        cwd=package if server.get("cwd") == "." else session,
        env={},
        timeout=15,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    assert _success(replies[0], modern=False)["protocolVersion"] == VERSIONS[1]
    _assert_inventory(_success(replies[1], modern=False))
    assert _tool_result(replies[2], modern=False)["ok"] is True
    assert not list(tmp_path.rglob("__pycache__"))


def test_modern_client_info_is_optional(interpreter: str, tmp_path: Path) -> None:
    frame = _request("tools/list")
    del frame["params"]["_meta"]["io.modelcontextprotocol/clientInfo"]
    _assert_inventory(_success(_run(interpreter, [frame], cwd=tmp_path)[0]))


@pytest.mark.parametrize("client_info", [None, {}, {"name": "client"}, "client"])
def test_legacy_requires_valid_client_info(interpreter, tmp_path, client_info):
    params = {"protocolVersion": VERSIONS[1], "capabilities": {}}
    if client_info is not None:
        params["clientInfo"] = client_info
    error = _run(interpreter, [_request("initialize", params, modern=False)], cwd=tmp_path)[0]
    assert error["error"]["data"] == {"code": "E_SCHEMA"}


@pytest.mark.parametrize("section,value", [("contract", []), ("domain", 7)])
@pytest.mark.parametrize("tool", ["ontology_validate", "ontology_lookup", "ontology_impact"])
def test_malformed_mapping_returns_short_error_and_process_continues(
    interpreter, tmp_path, section, value, tool
):
    (tmp_path / ".mir").mkdir()
    mapping = {"contract": {"id": "mir.common-semantics", "version": "1.1.0"}}
    mapping[section] = value
    (tmp_path / ".mir/ontology-map.json").write_text(json.dumps(mapping))
    arguments = {"target_root": str(tmp_path)}
    if tool == "ontology_lookup":
        arguments["query"] = "test"
    elif tool == "ontology_impact":
        arguments["paths"] = ["source.py"]
    replies = _run(interpreter, [
        _request("tools/call", {"name": tool, "arguments": arguments}),
        _request("tools/list", identity=2),
    ], cwd=tmp_path)
    assert len(replies) == 2
    structured = _tool_result(replies[0])
    assert structured["error"] == {"code": "E_FORMAT"} or structured["ok"]
    if tool == "ontology_validate" and structured["ok"]:
        assert structured["data"]["valid"] is False
    _assert_inventory(_success(replies[1]))


def test_null_meta_returns_short_error_and_continues(interpreter, tmp_path):
    frame = _request("tools/list")
    frame["params"]["_meta"] = None
    replies = _run(interpreter, [frame, _request("tools/list", identity=2)], cwd=tmp_path)
    assert replies[0]["error"]["data"] == {"code": "E_SCHEMA"}
    _assert_inventory(_success(replies[1]))


def test_null_request_id_is_invalid(interpreter, tmp_path):
    reply = _run(interpreter, [_request("tools/list", identity=None)], cwd=tmp_path)[0]
    assert reply["error"]["data"] == {"code": "E_SCHEMA"}


@pytest.mark.parametrize(
    "client_info",
    [
        None,
        "client",
        [],
        {},
        {"name": "client"},
        {"version": "1"},
        {"name": 7, "version": "1"},
        {"name": "client", "version": 7},
    ],
)
def test_present_client_info_must_have_string_name_and_version(
    interpreter: str, tmp_path: Path, client_info
) -> None:
    frame = _request("tools/list")
    frame["params"]["_meta"]["io.modelcontextprotocol/clientInfo"] = client_info
    error = _run(interpreter, [frame], cwd=tmp_path)[0]["error"]
    assert error["code"] == -32602
    assert error["data"] == {"code": "E_SCHEMA"}


def test_all_tools_share_era_semantics_and_satisfy_declared_output(interpreter, tmp_path):
    (tmp_path / ".mir").mkdir()
    (tmp_path / ".mir/repo-profile.toml").write_text('slug = "test"\n')
    (tmp_path / "source.py").write_text("def sample(): pass\n")
    (tmp_path / ".mir/ontology-map.json").write_text(json.dumps({
        "contract": {"id": "mir.common-semantics", "version": "1.1.0"},
        "domain": {"concepts": [{"name": "sample", "ref": "source.py"}]},
    }))
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec/graph.yaml").write_text("edges:\n  - [REQ, implemented_in, source.py]\n")
    args = [
        {}, {"query": "sample"}, {"paths": ["source.py"]},
        {"paths": ["source.py"]}, {"anchor": "REQ", "purpose": "implementation"},
    ]
    modern = [_request("tools/list")]
    legacy = [
        _request("initialize", {
            "protocolVersion": VERSIONS[1], "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        }, modern=False),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        _request("tools/list", modern=False),
    ]
    for name, extra in zip(TOOLS, args, strict=True):
        params = {"name": name, "arguments": {"target_root": str(tmp_path), **extra}}
        modern.append(_request("tools/call", params))
        legacy.append(_request("tools/call", params, modern=False))
    modern_results = _run(interpreter, modern, cwd=tmp_path)
    legacy_results = _run(interpreter, legacy, cwd=tmp_path)[1:]
    tools = _success(modern_results[0])["tools"]
    assert tools == _success(legacy_results[0], modern=False)["tools"]
    for tool, modern_reply, legacy_reply in zip(
        tools, modern_results[1:], legacy_results[1:], strict=True
    ):
        first = _tool_result(modern_reply)
        second = _tool_result(legacy_reply, modern=False)
        Draft202012Validator.check_schema(tool["outputSchema"])
        Draft202012Validator(tool["outputSchema"]).validate(first)
        Draft202012Validator(tool["outputSchema"]).validate(second)
        if tool["name"] == "handoff_pins":
            first["data"].pop("observed_at")
            second["data"].pop("observed_at")
        assert first == second
