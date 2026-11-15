"""Private object RPC for the capability-manager Python exemption."""

import contextlib
import importlib
import io
import json
import os
import threading
from pathlib import Path

METHODS = frozenset({"status", "check", "sync", "update", "finalize", "attest"})


@contextlib.contextmanager
def capture():
    events, threads, saved = [], [], []

    class Stream(io.FileIO):
        def write(self, data):
            if data:
                events.append({"stream": ("stdout", "stderr")[self.name - 1], "data": list(data)})
            return len(data)

    def drain(fd, stream):
        with os.fdopen(fd, "rb") as pipe:
            while data := pipe.read1(65536):
                events.append({"stream": stream, "data": list(data)})

    try:
        for fd, name in [(1, "stdout"), (2, "stderr")]:
            saved.append(os.dup(fd))
            read, write = os.pipe()
            os.dup2(write, fd)
            os.close(write)
            thread = threading.Thread(target=drain, args=(read, name))
            thread.start()
            threads.append(thread)
        out, err = (io.TextIOWrapper(Stream(fd, "wb", closefd=False), encoding="utf-8",
                                    write_through=True) for fd in (1, 2))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            yield events
    finally:
        for fd, prior in zip((1, 2), saved, strict=True):
            os.dup2(prior, fd)
            os.close(prior)
        for thread in threads:
            thread.join()


def main():
    # Private RPC descriptors are never the provider's stdin/stdout/stderr.
    requests = os.fdopen(os.dup(0), encoding="utf-8")
    replies = os.fdopen(os.dup(1), "w", encoding="utf-8")
    with open(os.devnull) as null:
        os.dup2(null.fileno(), 0)
        os.dup2(null.fileno(), 1)
    cls = manager = None
    for line in requests:
        with capture() as events:
            try:
                request = json.loads(line)
                if cls is None:
                    cls = importlib.import_module("mir.core.capabilities.manager").CapabilityManager
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
        replies.write(json.dumps(dict(response, events=events)) + "\n")
        replies.flush()


if __name__ == "__main__":
    main()
