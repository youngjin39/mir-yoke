"""Private object RPC for the capability-manager Python exemption."""

import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

METHODS = frozenset({"status", "check", "sync", "update", "finalize", "attest"})


@contextlib.contextmanager
def capture(mode=None):
    if mode is not None:
        events, output = [], io.StringIO()
        try:
            with contextlib.ExitStack() as stack:
                if mode in {"activate", "finalize"}:
                    stack.enter_context(contextlib.redirect_stdout(output))
                if mode == "activate":
                    stack.enter_context(contextlib.redirect_stderr(output))
                yield events
        finally:
            if output.getvalue():
                events.append({"stream": "stdout", "data": list(output.getvalue().encode())})
        return
    events, saved, files = [], [], []
    try:
        for fd, stream in [(1, sys.stdout), (2, sys.stderr)]:
            stream.flush()
            saved.append(os.dup(fd))
            files.append(tempfile.TemporaryFile())
            os.dup2(files[-1].fileno(), fd)
        yield events
    finally:
        for fd, prior, file, stream, name in zip(
                (1, 2), saved, files, (sys.stdout, sys.stderr), ("stdout", "stderr"), strict=True):
            stream.flush()
            os.dup2(prior, fd)
            os.close(prior)
            file.seek(0)
            data = file.read(os.fstat(file.fileno()).st_size)
            file.close()
            if data:
                events.append({"stream": name, "data": list(data)})


def main():
    # Private RPC descriptors are never the provider's stdin/stdout/stderr.
    mode = sys.argv[1] if len(sys.argv) == 2 else None
    requests = os.fdopen(os.dup(0), encoding="utf-8")
    replies = os.fdopen(os.dup(0 if mode else 1), "w", encoding="utf-8")
    with open(os.devnull) as null:
        os.dup2(null.fileno(), 0)
        if mode is None:
            os.dup2(null.fileno(), 1)
    cls = manager = None
    terminal_stdout, terminal_stderr = sys.stdout, sys.stderr
    for line in requests:
        with capture(mode) as events:
            try:
                request = json.loads(line)
                if cls is None:
                    # Import precedes the bootstrap caller's text redirects.
                    with contextlib.redirect_stdout(terminal_stdout if mode else sys.stdout), \
                            contextlib.redirect_stderr(terminal_stderr if mode else sys.stderr):
                        module = importlib.import_module("mir.core.capabilities.manager")
                        cls = module.CapabilityManager
                op = request["op"]
                args, kwargs = request.get("args", []), request.get("kwargs", {})
                for key in request.get("path_args", []):
                    args[key] = Path(args[key])
                for key in request.get("path_kwargs", []):
                    kwargs[key] = Path(kwargs[key])
                value = None
                if op == "initialize":
                    if manager is not None:
                        raise RuntimeError("manager already initialized")
                    manager = cls(*args, **kwargs)
                elif op == "call":
                    method = request["method"]
                    if method not in METHODS:
                        raise ValueError("manager method is not public: " + method)
                    value = getattr(manager, method)(*args, **kwargs)
                elif op != "import":
                    raise ValueError("unknown manager operation: " + op)
                response = {"value": value, "error": None}
            except BaseException as exc:
                error = {"class": type(exc).__name__, "message": str(exc)}
                response = {"value": None, "error": error}
        if mode and (response["error"] is not None or request["op"] == "call"):
            sys.stdout.flush()
            sys.stderr.flush()
        replies.write(json.dumps(dict(response, events=events)) + "\n")
        replies.flush()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)  # Replies are flushed; provider threads cannot hold shutdown open.


if __name__ == "__main__":
    main()
