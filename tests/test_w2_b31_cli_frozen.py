"""Frozen unmodified CLI observations; never recapture from a port.

The reference executes in-process: no interpreter selection, child argv, or env scrub.
Synthetic runpy calls expose execution context; manifest core is reached only via main.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from mir.cli import run_python, runtime_manifest

FIXTURE = Path(__file__).parent / "../native/handoff-packet/tests/fixtures/w2/b31-cli.json"
ENV = {"PYTHONPATH": "synthetic-path", "PYTHONHOME": "synthetic-home",
       "VIRTUAL_ENV": "synthetic-venv"}


def _invoke(module, argv, tmp):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            result = {"return": module.main(argv)}
        except SystemExit as exc:
            result = {"exit": exc.code}
        except Exception as exc:  # noqa: BLE001 - freeze errors with streams
            result = {"error": [type(exc).__name__, str(exc)]}
    result.update(stdout=out.getvalue(), stderr=err.getvalue())
    return json.loads(json.dumps(result).replace(str(tmp), "<tmp>"))


def _manifest(kind):
    def run(tmp):
        if kind in ("help", "empty", "unknown", "create_missing", "verify_missing"):
            args = {"help": ["--help"], "empty": [], "unknown": ["invalid"],
                    "create_missing": ["create"], "verify_missing": ["verify"]}[kind]
            return _invoke(runtime_manifest, args, tmp)
        root = tmp / "runtime"
        root.mkdir()
        payload = root / "helper.py"
        payload.write_text("pass\n", encoding="ascii")
        payload.chmod(0o644)
        target = root / "manifest.json"
        args = ["--runtime-root", str(root), "--manifest", str(target),
                "--source-url", "https://example.invalid/source", "--source-commit", "abc",
                "--constraints-sha256", "def"]
        calls = []
        with mock.patch.object(runtime_manifest, "create_runtime_manifest",
                               wraps=runtime_manifest.create_runtime_manifest) as create, \
                mock.patch.object(runtime_manifest, "verify_runtime_manifest",
                                  wraps=runtime_manifest.verify_runtime_manifest) as verify:
            if kind != "unreadable":
                calls.append(_invoke(runtime_manifest, ["create", *args], tmp))
            if kind == "tampered":
                payload.write_text("changed\n", encoding="ascii")
            if kind == "metadata":
                args[-1] = "other"
            if kind == "invalid_json":
                target.write_text("{", encoding="ascii")
            if kind == "outside":
                args[3] = str(tmp / "outside.json")
                calls.append(_invoke(runtime_manifest, ["create", *args], tmp))
            elif kind != "create":
                calls.append(_invoke(runtime_manifest, ["verify", *args], tmp))
            inputs = [[name, [str(p) for p in call.args], call.kwargs]
                      for name, fn in (("create", create), ("verify", verify))
                      for call in fn.call_args_list]
        return json.loads(json.dumps({"calls": calls, "inputs": inputs,
                                      "bytes": (list(target.read_bytes())
                                                if target.exists() else None)}
                                     ).replace(str(tmp), "<tmp>"))
    return run


def _python(kind, args=(), exit_code=None):
    def run(tmp):
        root = tmp / "project"
        root.mkdir()
        script = root / "helper.py"
        script.write_text("raise AssertionError('must be intercepted')\n", encoding="ascii")
        (root / "folder").mkdir()
        (root / "link.py").symlink_to(script)
        (tmp / "outside.py").write_text("pass\n", encoding="ascii")
        argv = ["--project-root", str(root), "--", *args]
        if kind == "parse":
            argv = list(args)
        elif kind == "unknown":
            argv = ["--project-root", str(root), "--unknown"]
        elif kind == "absolute":
            argv = ["--project-root", str(root / "../project"), str(script), "arg"]
        elif kind == "missing_root":
            argv = ["--project-root", str(tmp / "absent"), "helper.py"]
        seen = []
        prior = (sys.argv, list(sys.path), Path.cwd())

        def execute(*call_args, **kwargs):
            seen.append({"call": list(call_args), "kwargs": kwargs, "argv": list(sys.argv),
                         "cwd": str(Path.cwd()), "path0": sys.path[0],
                         "env_unchanged": dict(os.environ) == ENV})
            if exit_code is not None:
                raise SystemExit(exit_code)

        with mock.patch.dict(os.environ, ENV, clear=True), \
                mock.patch.object(sys, "executable", str(tmp / "absent-python")
                                  if kind == "missing_interpreter" else sys.executable), \
                mock.patch.object(sys, "stdin", io.StringIO(
                    "raise SystemExit(6)" if kind == "stdin_exit" else "print('stdin')\n")), \
                mock.patch.object(run_python.runpy, "run_path", side_effect=execute), \
                mock.patch.object(run_python.runpy, "run_module", side_effect=execute), \
                mock.patch.object(run_python.importlib.util, "find_spec",
                                  return_value=None if kind == "missing_module" else object()), \
                contextlib.ExitStack() as guards:
            for name in ("execv", "execve", "execvp", "execvpe"):
                guards.enter_context(mock.patch.object(os, name, side_effect=AssertionError(name)))
            guards.enter_context(mock.patch("subprocess.Popen",
                                            side_effect=AssertionError("spawn")))
            result = _invoke(run_python, argv, tmp)
        result.update(seen=seen, restored=(sys.argv is prior[0] and sys.path == prior[1]
                                         and Path.cwd() == prior[2]))
        return json.loads(json.dumps(result).replace(str(tmp), "<tmp>"))
    return run


CASES = {f"manifest.{kind}": _manifest(kind) for kind in (
    "help", "empty", "unknown", "create_missing", "verify_missing", "create", "verify",
    "unreadable", "tampered", "metadata", "invalid_json", "outside")}
CASES.update({
    "python.help": _python("parse", ["--help"]),
    "python.required_root": _python("parse"),
    "python.unknown_option": _python("unknown"),
    "python.missing_interpreter_unused": _python("missing_interpreter", ["helper.py"]),
    "python.missing_root": _python("missing_root"),
    "python.no_args": _python("script"),
    "python.script": _python("script", ["helper.py", "arg", "--flag"]),
    "python.absolute": _python("absolute"),
    "python.missing_script": _python("script", ["missing.py"]),
    "python.directory": _python("script", ["folder"]),
    "python.outside": _python("script", ["../outside.py"]),
    "python.symlink": _python("script", ["link.py"]),
    "python.module": _python("module", ["-m", "synthetic_module", "arg"]),
    "python.missing_module": _python("missing_module", ["-m", "synthetic_module"]),
    "python.module_no_name": _python("module", ["-m"]),
    "python.code_no_source": _python("code", ["-c"]),
    "python.code": _python("code", ["-c", "import sys; print(sys.argv)", "arg"]),
    "python.stdin": _python("stdin", ["-", "arg"]),
    "python.code_exit": _python("code", ["-c", "raise SystemExit(7)"]),
    "python.stdin_exit": _python("stdin_exit", ["-"]),
    "python.script_exit": _python("script", ["helper.py"], 7),
    "python.module_exit": _python("module", ["-m", "synthetic_module"], 9),
    "python.script_text_exit": _python("script", ["helper.py"], "message"),
})


def observe(case, tmp: Path) -> dict:
    try:
        return {"value": case(tmp)}
    except Exception as exc:  # noqa: BLE001 - frozen reference errors
        return {"error": [type(exc).__name__, str(exc)]}


RECORDS = json.loads(FIXTURE.read_text(encoding="ascii")) if FIXTURE.exists() else {}


def test_every_case_has_a_frozen_record():
    assert sorted(RECORDS) == sorted(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_reference_matches_frozen_record(name, tmp_path):
    assert observe(CASES[name], tmp_path) == RECORDS[name]
