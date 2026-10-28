"""Closed ADR-91 package contract, shared by admission and package tests."""

from __future__ import annotations

import ast
import json
import re
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath

from jsonschema import Draft202012Validator, ValidationError, validators
from jsonschema.exceptions import SchemaError

from .config import MCP_FILES, MCP_NAME, MCP_TOOLS

_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?")


def sys_platform() -> str:
    """Small seam for host-specific receipt validation tests."""
    import sys

    return sys.platform


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"MCP package rejected: {message}")


def closed_json(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, f"duplicate key: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    _require(isinstance(value, dict), "JSON must be an object")
    return value


def mcp_launcher(script: str) -> dict:
    return {"command": "python3", "args": ["-I", "-B", "-u", script]}


# Codex passes args verbatim and resolves cwd "." to the installed plugin root.
MCP_LAUNCHERS = {
    "claude": mcp_launcher("${CLAUDE_PLUGIN_ROOT}/mir_mcp.py"),
    "codex": {**mcp_launcher("./mir_mcp.py"), "cwd": "."},
}


def mcp_observed_launcher(runtime: str, installed: Path) -> dict:
    """The process an operator observes each client launch from the installed root."""
    if runtime == "claude-code":
        return {**mcp_launcher(str(installed) + "/mir_mcp.py"), "env": {}}
    return {**mcp_launcher("./mir_mcp.py"), "cwd": str(installed), "env": {}}


def _max_utf8_length(validator, maximum, instance, schema):
    # The stdio server bounds strings by UTF-8 bytes, including receipt arguments.
    if isinstance(instance, str) and len(instance.encode("utf-8")) > maximum:
        yield ValidationError("string exceeds the server's UTF-8 byte bound")


_InputValidator = validators.extend(
    Draft202012Validator,
    {"maxLength": _max_utf8_length},
    # The server accepts only exact ints, never integral floats such as 3.0.
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda checker, instance: type(instance) is int
    ),
)


def _input_schemas(package: Path) -> dict:
    """Read the installed server's single schema definition as data, never code."""
    tree = ast.parse((package / "mir_mcp.py").read_text(encoding="utf-8"))
    declarations = [
        node.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "INPUT_SCHEMAS"
                for target in node.targets)
    ]
    _require(len(declarations) == 1, "input schema declaration")
    schemas = ast.literal_eval(declarations[0])
    _require(isinstance(schemas, dict) and set(schemas) == set(MCP_TOOLS), "input schemas")
    for schema in schemas.values():
        _InputValidator.check_schema(schema)
    return schemas


def validate_mcp_package(package: Path) -> None:
    """Inspect data only; never import or execute the candidate package."""
    _require(not package.is_symlink() and package.is_dir(), "root must be a real directory")
    directories = {
        parent.as_posix()
        for file in MCP_FILES
        for parent in Path(file).parents
        if parent != Path(".")
    }
    found = set()
    for path in package.rglob("*"):
        relative = path.relative_to(package).as_posix()
        mode = path.lstat().st_mode
        _require(not stat.S_ISLNK(mode), "symlink")
        if stat.S_ISDIR(mode):
            _require(relative in directories, f"undeclared directory: {relative}")
        else:
            _require(stat.S_ISREG(mode), "special file")
            _require(not mode & 0o111, "executable file")
            found.add(relative)
    _require(found == set(MCP_FILES), "eight-file inventory drift")
    manifests = []
    for runtime in ("claude", "codex"):
        manifest = closed_json(package / f".{runtime}-plugin/plugin.json")
        keys = {"name", "version", "description", "mcpServers"}
        if runtime == "codex":
            keys |= {"author", "interface"}
            author = manifest.get("author")
            interface = manifest.get("interface")
            _require(isinstance(author, dict) and set(author) == {"name"}, "author metadata")
            _require(
                isinstance(interface, dict)
                and set(interface)
                == {
                    "displayName",
                    "shortDescription",
                },
                "interface metadata",
            )
            _require(
                all(
                    isinstance(value, str) and bool(value.strip())
                    for value in [*author.values(), *interface.values()]
                ),
                "metadata strings",
            )
        _require(set(manifest) == keys, "manifest keys")
        _require(manifest["name"] == MCP_NAME, "manifest name")
        version = manifest["version"]
        _require(isinstance(version, str) and _VERSION.fullmatch(version) is not None, "version")
        _require(
            isinstance(manifest["description"], str) and bool(manifest["description"].strip()),
            "description",
        )
        _require(manifest["mcpServers"] == f"./.mcp.{runtime}.json", "declaration reference")
        server = {
            **MCP_LAUNCHERS[runtime],
            **({"type": "stdio"} if runtime == "claude" else {"env_vars": []}),
        }
        _require(
            closed_json(package / f".mcp.{runtime}.json")
            == {
                "mcpServers": {MCP_NAME: server},
            },
            "closed stdio launcher and empty environment",
        )
        manifests.append(manifest)
    _require(manifests[0]["version"] == manifests[1]["version"], "version parity")
    _require(manifests[0]["description"] == manifests[1]["description"], "description parity")


def validate_mcp_observation(
    observation: object,
    *,
    digest: str,
    runtime: str,
    session: str,
    installed: Path,
    provider: Path,
) -> bool:
    """Validate an operator's fresh-session receipt, not a claim of live execution."""
    if not isinstance(observation, dict) or set(observation) != {
        "installed_sha256",
        "client",
        "client_version",
        "session_id",
        "session_cwd",
        "platform",
        "interpreter",
        "server",
        "protocol_version",
        "launcher",
        "tools",
        "safe_calls",
        "tools_list",
    }:
        return False

    def text(value):
        return isinstance(value, str) and 0 < len(value.strip()) <= 4096

    def sha(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    try:
        cwd = Path(observation["session_cwd"])
        cwd = cwd.resolve() if cwd.is_absolute() else None
        interpreter = observation["interpreter"]
        tools = observation["tools"]
        calls = observation["safe_calls"]
        budget = observation["tools_list"]
        version = interpreter["version"]
        windows = sys_platform() == "win32"
        executable = (
            PureWindowsPath(interpreter["executable"]) if windows
            else PurePosixPath(interpreter["executable"])
        )
        if (
            observation["installed_sha256"] != digest
            or observation["client"] != runtime
            or not text(observation["client_version"])
            or observation["session_id"] != session
            or cwd is None
            or not cwd.is_dir()
            or cwd.is_relative_to(provider.resolve())
            or observation["platform"] not in {"macos", "linux", "wsl", "windows"}
            or (observation["platform"] == "windows") != windows
            or not isinstance(interpreter, dict)
            or set(interpreter) != {"executable", "version"}
            or not executable.is_absolute()
            or (windows and re.fullmatch(r"[A-Za-z]:", executable.drive) is None)
            or not isinstance(version, str)
            or re.fullmatch(r"3\.\d+\.\d+", version) is None
            or int(version.split(".")[1]) < 11
            or observation["server"] != MCP_NAME
            or observation["protocol_version"] not in {"2026-07-28", "2025-11-25"}
            or observation["launcher"] != mcp_observed_launcher(runtime, installed)
            or not isinstance(tools, list)
            or len(tools) != len(MCP_TOOLS)
            or [tool["name"] for tool in tools] != list(MCP_TOOLS)
            or any(
                set(tool) != {"name", "raw_name"} or not text(tool["raw_name"]) for tool in tools
            )
            or len({tool["raw_name"] for tool in tools}) != len(MCP_TOOLS)
            or not isinstance(calls, dict)
            or set(calls) != set(MCP_TOOLS)
        ):
            return False
        schemas = _input_schemas(installed)
        for name, call in calls.items():
            if (
                not isinstance(call, dict)
                or set(call) != {"arguments", "result_sha256", "is_error", "ok"}
                or call["is_error"] is not False
                or call["ok"] is not True
                or not sha(call["result_sha256"])
                or not isinstance(call["arguments"], dict)
                or not _InputValidator(schemas[name]).is_valid(call["arguments"])
                or not Path(call["arguments"]["target_root"]).is_absolute()
            ):
                return False
        if (
            not isinstance(budget, dict)
            or set(budget)
            != {
                "sha256",
                "bytes",
                "tokens",
                "tokenizer",
                "initial_tokens",
                "after_call_tokens",
                "deferred_loading",
            }
            or not sha(budget["sha256"])
            or not text(budget["tokenizer"])
            or budget["deferred_loading"] not in {"observed", "eager"}
        ):
            return False
        for key, maximum in (
            ("bytes", 16384),
            ("tokens", 6000),
            ("initial_tokens", None),
            ("after_call_tokens", None),
        ):
            value = budget[key]
            if (
                type(value) is not int
                or value < (1 if key in {"bytes", "tokens"} else 0)
                or (maximum is not None and value > maximum)
            ):
                return False
    except (KeyError, TypeError, ValueError, OSError, SyntaxError, SchemaError):
        return False
    return True
