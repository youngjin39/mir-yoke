"""Run a repository-local hook helper inside the installed Mir tool environment."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import os
import runpy
import sys
from collections.abc import Iterator
from pathlib import Path


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mir run-python")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("python_args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


@contextlib.contextmanager
def _project_execution(root: Path, argv: list[str]) -> Iterator[None]:
    prior_argv = sys.argv
    prior_cwd = Path.cwd()
    prior_path = list(sys.path)
    sys.argv = argv
    sys.path.insert(0, str(root))
    try:
        os.chdir(root)
        yield
    finally:
        sys.argv = prior_argv
        sys.path[:] = prior_path
        os.chdir(prior_cwd)


def _system_exit_code(exc: SystemExit) -> int:
    return exc.code if isinstance(exc.code, int) else 1


def main(argv: list[str]) -> int:
    namespace = _parse(argv)
    root = namespace.project_root.expanduser().resolve(strict=True)
    python_args = list(namespace.python_args)
    if python_args[:1] == ["--"]:
        python_args = python_args[1:]
    if not python_args:
        print("run-python requires a script path or -m module", file=sys.stderr)
        return 2
    if python_args[0] == "-c":
        if len(python_args) < 2:
            print("run-python -c requires source code", file=sys.stderr)
            return 2
        try:
            with _project_execution(root, ["-c", *python_args[2:]]):
                exec(compile(python_args[1], "<mir-run-python>", "exec"), {"__name__": "__main__"})
        except SystemExit as exc:
            return _system_exit_code(exc)
        return 0
    if python_args[0] == "-":
        try:
            source = sys.stdin.read()
            with _project_execution(root, ["-", *python_args[1:]]):
                exec(compile(source, "<stdin>", "exec"), {"__name__": "__main__"})
        except SystemExit as exc:
            return _system_exit_code(exc)
        return 0
    if python_args[0] == "-m":
        if len(python_args) < 2:
            print("run-python -m requires a module name", file=sys.stderr)
            return 2
        module_name = python_args[1]
        try:
            with _project_execution(root, [module_name, *python_args[2:]]):
                if importlib.util.find_spec(module_name) is None:
                    print(f"hook helper module is unavailable: {module_name}", file=sys.stderr)
                    return 2
                runpy.run_module(module_name, run_name="__main__", alter_sys=True)
        except SystemExit as exc:
            return _system_exit_code(exc)
        return 0

    script = Path(python_args[0])
    if not script.is_absolute():
        script = root / script
    try:
        script = script.resolve(strict=True)
        script.relative_to(root)
    except (OSError, ValueError) as exc:
        print(f"hook helper must be a real file inside {root}: {exc}", file=sys.stderr)
        return 2
    if not script.is_file() or script.is_symlink():
        print(f"hook helper must be a non-symlink file: {script}", file=sys.stderr)
        return 2

    try:
        with _project_execution(root, [str(script), *python_args[1:]]):
            runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        return _system_exit_code(exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
