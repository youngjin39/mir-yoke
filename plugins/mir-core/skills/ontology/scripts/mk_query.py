"""On-demand Memory Keeper MCP stdio client; Python 3.9+, standard library only."""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import signal
import subprocess
import sys
import threading
from pathlib import Path

MAX_MESSAGE = 4 * 1024 * 1024


class Unavailable(Exception):
    """A bounded, non-sensitive reason local work can report and continue past."""


def load_config(repo):
    path = (
        Path(
            os.environ.get("MIR_KNOWLEDGE_SUPPLY_CONFIG")
            or Path.home() / ".mir/knowledge-supply.json"
        )
        .expanduser()
        .resolve()
    )
    if repo == path or repo in path.parents:
        raise Unavailable("configuration must be host-local, outside the repository")
    if any(part.startswith(".env") or part == "secrets" for part in path.parts):
        raise Unavailable("configuration cannot be a secrets file")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Unavailable("host-local configuration is missing") from None
    except (OSError, ValueError, UnicodeError):
        raise Unavailable("host-local configuration cannot be read") from None
    if not isinstance(config, dict) or set(config) != {"memory_keeper"}:
        raise Unavailable("invalid host-local configuration")
    binding = config["memory_keeper"]
    if not isinstance(binding, dict) or set(binding) - {"command", "cwd", "timeout_sec"}:
        raise Unavailable("invalid memory_keeper configuration; do not include secrets")
    command = binding.get("command")
    cwd = binding.get("cwd")
    timeout = binding.get("timeout_sec", 30)
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(arg, str) or not arg.strip() for arg in command)
    ):
        raise Unavailable("command must be a non-empty argument list")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise Unavailable("cwd must be an absolute host-local directory")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (float, int))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise Unavailable("timeout_sec must be finite and positive")
    return command, cwd, timeout


def exchange(child, tool, arguments, client_name):
    """Run in a worker so the caller's deadline also bounds pipe writes and startup."""

    def send(message):
        child.stdin.write((json.dumps({"jsonrpc": "2.0", **message}) + "\n").encode("utf-8"))
        child.stdin.flush()

    def request(request_id, method, params):
        send({"id": request_id, "method": method, "params": params})
        while True:
            line = child.stdout.readline(MAX_MESSAGE + 1)
            if not line:
                raise Unavailable("MCP server closed stdout")
            if len(line) > MAX_MESSAGE:
                raise Unavailable("MCP response exceeds the client message budget")
            message = json.loads(line)
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise Unavailable("invalid MCP response")
            if message.get("id") != request_id:
                continue  # Notifications do not complete a request.
            if "error" in message:
                raise Unavailable("MCP request returned an error")
            result = message.get("result")
            if not isinstance(result, dict):
                raise Unavailable("invalid MCP result")
            return result

    initialized = request(
        1,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": client_name, "version": "1.0"},
        },
    )
    if initialized.get("protocolVersion") not in ("2024-11-05", "2025-03-26", "2025-06-18"):
        raise Unavailable("unsupported MCP protocol version")
    send({"method": "notifications/initialized"})
    result = request(2, "tools/call", {"name": tool, "arguments": arguments})
    if result.get("isError"):
        raise Unavailable("MCP tool returned an error")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    if result.get("content") == []:
        return {}
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            value = json.loads(item.get("text", ""))
            if isinstance(value, dict):
                return value
    raise Unavailable("MCP tool returned no JSON object")


def call(command, cwd, timeout, tool, arguments, client_name):
    try:
        child = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name == "posix"),
        )
    except (OSError, ValueError):
        raise Unavailable("MCP command could not be started") from None
    results = queue.Queue(maxsize=1)

    def work():
        try:
            results.put((exchange(child, tool, arguments, client_name), None))
        except (OSError, ValueError, TypeError, Unavailable):
            results.put((None, "MCP exchange failed"))

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    timed_out = False
    try:
        try:
            result, error = results.get(timeout=timeout)
        except queue.Empty:
            timed_out = True
            raise Unavailable("MCP request timed out") from None
        if error:
            raise Unavailable(error)
        return result
    finally:
        # A launcher can have descendants. Kill the owned process group on POSIX,
        # including when its leader already exited; always wait for the direct child.
        if os.name == "posix":
            try:
                os.killpg(child.pid, signal.SIGKILL if timed_out else signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif child.poll() is None:
            child.kill()
        try:
            child.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        if os.name == "posix":
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        worker.join(timeout=0.2)
        child.stdin.close()
        child.stdout.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--client-name", help="telemetry label only; never authentication")
    parser.add_argument(
        "--soft", action="store_true", help="exit 0 when external knowledge is unavailable"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    query = commands.add_parser("query", help="retrieve a ContextPack")
    query.add_argument("query")
    query.add_argument("--namespaces", nargs="+")
    query.add_argument("--k", type=int, choices=range(1, 101), metavar="1..100")
    feedback = commands.add_parser(
        "feedback", help="record explicit feedback for a received node ref"
    )
    feedback.add_argument("node_ref")
    feedback.add_argument("verdict", choices=("used", "confirmed", "contradicted", "acted_on"))
    args = parser.parse_args(argv)
    try:
        repo = args.repo.resolve()
        command, cwd, timeout = load_config(repo)
        if args.command == "query":
            if not args.query.strip() or len(args.query) > 8192:
                raise Unavailable("query must contain 1..8192 nonblank characters")
            tool = "federation_serve"
            arguments = {"query": args.query}
            if args.namespaces is not None:
                arguments["namespaces"] = args.namespaces
            if args.k is not None:
                arguments["k"] = args.k
        else:
            tool = "feedback"
            arguments = {"node_ref": args.node_ref, "verdict": args.verdict}
        result = call(
            command, cwd, timeout, tool, arguments, args.client_name or repo.name + "-agent"
        )
        if (
            args.command == "query"
            and result.get("status") != "refused"
            and (not result or result.get("nodes") == [])
        ):
            print(json.dumps({"status": "empty", "reason": "ContextPack contains no nodes"}))
            return 0 if args.soft else 2
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (Unavailable, OSError, RuntimeError) as exc:
        reason = (
            str(exc) if isinstance(exc, Unavailable) else "host-local configuration unavailable"
        )
        print(json.dumps({"status": "unavailable", "reason": reason}))
        return 0 if args.soft else 2


if __name__ == "__main__":
    sys.exit(main())
