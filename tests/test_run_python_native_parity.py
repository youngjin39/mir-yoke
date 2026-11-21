"""Pinned run-python command and hook launcher parity; no consumer is changed."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from e02a_binary import binary

ROOT = Path(__file__).resolve().parents[1]
PIN = "1324a3c"
SOURCE_REVISION = "4343aba88e811f14f6147a9a9b818b6fb346bec8"


@pytest.fixture
def sandbox():
    root = Path(tempfile.mkdtemp(prefix="run-python-", dir=os.environ.get("TMPDIR")))
    (root / "home").mkdir()
    project = root / "project space"
    project.mkdir()
    for name, source in (
        ("reference.py", "src/mir/cli/run_python.py"),
        ("reference.sh", ".claude/hooks/_lib/run-python.sh"),
    ):
        contents = subprocess.check_output(["git", "show", f"{SOURCE_REVISION}:{source}"], cwd=ROOT)
        (root / name).write_bytes(contents)
    yield root, project
    shutil.rmtree(root)


def executable(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -c {shlex.quote(source)} "$@"\n'
    )
    path.chmod(0o755)


def run_pair(
    sandbox, args, *, shell=False, stdin=b"", environment=None, cli_args=None, decline=False
):
    root, project = sandbox
    executable_binary = binary("run-python", "MIR_RUN_PYTHON_BINARY")
    launcher = binary("run-python-launcher", "MIR_RUN_PYTHON_LAUNCHER_BINARY")
    env = dict(
        os.environ,
        HOME=str(root / "home"),
        PYTHONDONTWRITEBYTECODE="1",
        CLAUDE_PROJECT_DIR=str(project),
        MIR_PROJECT_DIR=str(root / "ignored"),
    )
    env.pop("PYTHONPATH", None)
    env.update(environment or {})
    installed = root / ("provider/bin/run-python-launcher" if shell else "provider/bin/run-python")
    installed.parent.mkdir(parents=True, exist_ok=True)
    python = installed.with_name("python")
    python.symlink_to(sys.executable)
    shutil.copy2(root / ("reference.sh" if shell else "reference.py"), installed)
    reference = ["/bin/bash", str(installed)] if shell else [str(python), str(installed)]
    argv = (
        args
        if shell
        else cli_args
        if cli_args is not None
        else ["--project-root", str(project), *args]
    )
    expected = subprocess.run(
        [*reference, *argv],
        cwd=root,
        env=env,
        input=stdin,
        capture_output=True,
        timeout=15,
        check=False,
    )
    effect = root / "tool-effect"
    expected_effect = effect.read_bytes() if effect.exists() else None
    effect.unlink(missing_ok=True)
    # The migration contract collapses uncaught tracebacks to their final line.
    if not shell and b"Traceback (most recent call last):" in expected.stderr:
        expected.stderr = expected.stderr.splitlines()[-1] + b"\n"
    destination = os.environ.get("MIR_RUN_PYTHON_RECORDS")
    if destination:
        cwd_spelling = subprocess.check_output(
            [sys.executable, "-c", "import os; print(os.getcwd())"], cwd=root
        ).rstrip(b"\n")

        def normalize(value):
            return (
                value.replace(str(root).encode(), b"${TMP}")
                .replace(cwd_spelling, b"${TMP}")
                .replace(str(executable_binary).encode(), b"${BINARY}")
            )

        record = {
            "pin": PIN,
            "case": os.environ.get("PYTEST_CURRENT_TEST", "").split(" (")[0],
            "shell": shell,
            "argv": [normalize(arg.encode()).decode() for arg in argv],
            "stdin_hex": stdin.hex(),
            "stdout_hex": normalize(expected.stdout).hex(),
            "stderr_hex": normalize(expected.stderr).hex(),
            "exit": expected.returncode,
        }
        with Path(destination).open("a") as stream:
            stream.write(json.dumps(record) + "\n")
    shutil.copy2(launcher if shell else executable_binary, installed)
    actual = subprocess.run(
        [str(installed), *argv],
        cwd=root,
        env=env,
        input=stdin,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if decline:
        assert (actual.returncode, actual.stdout, actual.stderr) == (64, b"", b"")
        shutil.copy2(root / "reference.sh", installed)
        actual = subprocess.run(
            ["/bin/bash", str(installed), *argv], cwd=root, env=env, input=stdin,
            capture_output=True, timeout=15, check=False,
        )
    assert (actual.stdout, actual.stderr, actual.returncode) == (
        expected.stdout,
        expected.stderr,
        expected.returncode,
    )
    actual_effect = effect.read_bytes() if effect.exists() else None
    assert actual_effect == expected_effect
    return actual


@pytest.mark.parametrize(
    "mode",
    [
        "inline",
        "stdin",
        "script",
        "module",
        "package",
        "symlink",
        "exit0",
        "exit7",
        "exitstr",
        "exitnone",
        "exitbool",
        "exitlarge",
        "exception",
        "exception-vtab",
        "exception-formfeed",
        "exception-cr",
        "exception-unicode-separator",
        "syntax",
        "signal",
        "atexit",
        "unicode",
        "multiline",
        "interpreter",
        "main-file",
        "original-argv",
        "signal-int",
        "pythonpath",
        "pythonpath-safe",
    ],
)
def test_python_execution(sandbox, mode):
    _, project = sandbox
    interpreter = project / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    source = "import json, os, sys; print(json.dumps([os.getcwd(), sys.argv], ensure_ascii=False))"
    args = ["--", "-c", source, "\ud55c\uae00", "space arg", "--flag"]
    stdin = b""
    if mode == "stdin":
        args, stdin = ["--", "-", "arg"], source.encode()
    elif mode in ("script", "module", "package", "symlink"):
        (project / "helper.py").write_text(source)
        args = ["--", "helper.py", "arg"]
        if mode == "module":
            args = ["--", "-m", "helper", "arg"]
        elif mode == "package":
            (project / "pkg").mkdir()
            (project / "pkg/__init__.py").write_text("")
            (project / "pkg/__main__.py").write_text(source)
            args = ["--", "-m", "pkg", "arg"]
        elif mode == "symlink":
            (project / "link.py").symlink_to("helper.py")
            args = ["--", "link.py", "arg"]
    elif mode.startswith("exit"):
        value = {
            "exit0": "0",
            "exit7": "7",
            "exitstr": "'message'",
            "exitnone": "None",
            "exitbool": "True",
            "exitlarge": "2**80",
        }[mode]
        args = ["--", "-c", f"raise SystemExit({value})"]
    elif mode == "exception":
        args = ["--", "-c", "raise ValueError('broken')"]
    elif mode.startswith("exception-"):
        separator = {
            "exception-vtab": "\v",
            "exception-formfeed": "\f",
            "exception-cr": "\r",
            "exception-unicode-separator": "\u2028",
        }[mode]
        args = ["--", "-c", f"raise UnicodeError({'a' + separator + 'b'!r})"]
    elif mode == "syntax":
        args = ["--", "-c", "if :"]
    elif mode == "multiline":
        args = ["--", "-c", "raise ValueError('first\\nlast')"]
    elif mode == "interpreter":
        interpreter.unlink()
        executable(interpreter, "print('WRONG PROJECT INTERPRETER')")
        args = ["--", "-c", "import sys; print(sys.executable)"]
    elif mode in ("pythonpath", "pythonpath-safe"):
        args = [
            "--",
            "-c",
            "import atexit,sys; print(sys.path); atexit.register(lambda: print(sys.path))",
        ]
    elif mode == "main-file":
        args = ["--", "-c", "import __main__; print(__main__.__file__)"]
    elif mode == "original-argv":
        args = ["--", "-c", "import sys; print(sys.orig_argv)"]
    elif mode == "signal-int":
        args = ["--", "-c", "import os, signal; os.kill(os.getpid(), signal.SIGINT)"]
    elif mode == "signal":
        args = ["--", "-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"]
    elif mode == "atexit":
        args = [
            "--",
            "-c",
            "import atexit,os,sys; atexit.register(lambda: print(os.getcwd(), sys.argv[0]))",
        ]
    environment = None
    if mode == "pythonpath-safe":
        marker = project.parent / "pythonpath-marker"
        marker.mkdir()
        environment = {"PYTHONSAFEPATH": "1", "PYTHONPATH": str(marker)}
    result = run_pair(sandbox, args, stdin=stdin, environment=environment)
    if mode == "signal":
        assert result.returncode == -signal.SIGTERM


@pytest.mark.parametrize(
    "form", ["help", "empty", "abbrev", "equals", "tilde", "relative", "missing-root"]
)
def test_provider_parser(sandbox, form):
    _, project = sandbox
    root = {
        "tilde": "~/../project space",
        "relative": "project space",
        "missing-root": "absent",
    }.get(form, str(project))
    option = "--project-r" if form == "abbrev" else "--project-root"
    args = [option, root, "--", "-c", "print('ok')"]
    if form == "equals":
        args = [f"{option}={root}", "--", "-c", "print('ok')"]
    elif form == "help":
        args = ["--help"]
    elif form == "empty":
        args = []
    run_pair(sandbox, [], cli_args=args)


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--"],
        ["--", "-c"],
        ["--", "-m"],
        ["--", "-m", "missing_helper"],
        ["--", "missing.py"],
        ["--", "."],
        ["--", "../outside.py"],
        ["--", "escape.py"],
        ["--bad"],
        ["--help"],
    ],
)
def test_refusals(sandbox, args):
    root, project = sandbox
    (root / "outside.py").write_text("print('outside')")
    (project / "escape.py").symlink_to(root / "outside.py")
    interpreter = project / ".venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    run_pair(sandbox, args)


@pytest.mark.parametrize(
    "route",
    [
        "venv",
        "windows-venv",
        "uv",
        "missing",
        "adoption",
        "receipt",
        "invalid",
        "manifest",
        "manifest-invalid",
        "manifest-alias",
        "manifest-symlink",
        "manifest-refused",
        "manifest-bash-env",
        "receipt-jq-executable-error",
        "receipt-jq-sha-error",
        "manifest-jq-error",
        "manifest-jq-sha-error",
        "manifest-jq-source-stderr",
        "receipt-awk-error",
        "receipt-awk-wrong",
        "manifest-cdpath",
        "manifest-dirname-missing",
        "manifest-dirname-wrong",
        "manifest-dirname-empty-root",
        "receipt-awk-missing",
        "malformed",
        "no-jq",
        "signal",
        "stdin",
        "bad-shebang",
        "directory",
        "binary-format",
    ],
)
def test_hook_selection(sandbox, route):
    root, project = sandbox
    path = root / "path"
    path.mkdir()
    # Use only synthetic programs; the selected extension can still run Python.
    printer = "import json,sys; print(json.dumps(sys.argv[1:], ensure_ascii=False)); sys.exit(7)\n"
    if route == "signal":
        printer = "import os,signal; os.kill(os.getpid(), signal.SIGTERM)"
    elif route == "stdin":
        printer = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"
    if route not in ("missing", "adoption", "uv"):
        executable(
            project
            / (".venv/Scripts/python.exe" if route == "windows-venv" else ".venv/bin/python"),
            printer,
        )
    if route in ("bad-shebang", "directory", "binary-format"):
        python = project / ".venv/bin/python"
        if route == "bad-shebang":
            python.write_text("#!/nonexistent-run-python-interpreter\n")
        elif route == "directory":
            python.unlink()
            python.mkdir()
        else:
            python.write_bytes(b"\x7fELF\x00\x00\x00\x00")
    if route == "uv":
        executable(path / "uv", printer)
    if route == "adoption":
        (project / "config").mkdir()
        (project / "config/bootstrap-adoption.json").write_text("{}")
    if route in ("receipt", "invalid", "malformed", "no-jq") or route.startswith(
        ("manifest", "receipt-")
    ):
        if route != "no-jq":
            jq = shutil.which("jq")
            assert jq, "Pinned launcher parity requires its declared jq dependency"
            (path / "jq").symlink_to(jq)
        executable(
            path / "sha256sum",
            "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())",
        )
        (path / "awk").symlink_to("/usr/bin/awk")
        (path / "dirname").symlink_to("/usr/bin/dirname")
        external = root / "runtime/bin/mir"
        runtime = external.parent.parent
        verify_args = [
            "runtime-manifest",
            "verify",
            "--runtime-root",
            str(runtime),
            "--manifest",
            str(runtime / "runtime-manifest.json"),
            "--source-url",
            "source",
            "--source-commit",
            "commit",
            "--constraints-sha256",
            "constraints",
        ]
        if route == "manifest-dirname-empty-root":
            verify_args[3] = ""
            verify_args[5] = "runtime-manifest.json"
        if route == "manifest-alias":
            verify_args[5] = str(runtime) + "/./runtime-manifest.json"
        executable(
            external,
            "import sys\nif sys.argv[1] == 'runtime-manifest': "
            f"sys.exit(0 if sys.argv[1:] == {verify_args!r} "
            f"and {route != 'manifest-refused'!r} else 1)\n" + printer,
        )
        cli = {
            "executable": str(external),
            "sha256": hashlib.sha256(external.read_bytes()).hexdigest(),
        }
        if route == "invalid":
            cli["sha256"] = "bad"
        if route.startswith("manifest"):
            manifest = external.parent.parent / "runtime-manifest.json"
            manifest.write_text("{}")
            cli.update(
                runtime_manifest=str(manifest),
                runtime_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                source_url="source",
                source_commit="commit",
                constraints_sha256="constraints",
            )
            if route == "manifest-dirname-empty-root":
                (root / "runtime-manifest.json").write_bytes(manifest.read_bytes())
                cli["runtime_manifest"] = "runtime-manifest.json"
            if route == "manifest-invalid":
                cli["runtime_manifest_sha256"] = "bad"
            elif route == "manifest-alias":
                cli["runtime_manifest"] = str(runtime) + "/./runtime-manifest.json"
            elif route == "manifest-symlink":
                target = runtime / "target.json"
                manifest.rename(target)
                manifest.symlink_to(target.name)
        (project / ".mir").mkdir()
        (project / ".mir/bootstrap-receipt.json").write_text(
            "{" if route == "malformed" else json.dumps({"cli": cli})
        )
    if "jq-" in route:
        selected = {
            "receipt-jq-executable-error": ".cli.executable // empty",
            "receipt-jq-sha-error": ".cli.sha256 // empty",
            "manifest-jq-error": ".cli.runtime_manifest // empty",
            "manifest-jq-sha-error": ".cli.runtime_manifest_sha256 // empty",
            "manifest-jq-source-stderr": ".cli.source_url // empty",
        }[route]
        (path / "jq").unlink()
        executable(
            path / "jq",
            "import subprocess,sys; "
            f"p=subprocess.run([{jq!r}, *sys.argv[1:]], capture_output=True); "
            "sys.stdout.buffer.write(p.stdout); sys.stderr.buffer.write(p.stderr); "
            f"selected=sys.argv[2] == {selected!r}; "
            + ("sys.stderr.write('jq diagnostic\\n' if selected else ''); "
               if route.endswith("stderr") else "")
            + ("sys.exit(p.returncode)" if route.endswith("stderr") else
               "sys.exit(7 if selected else p.returncode)"),
        )
    if route in ("receipt-awk-error", "receipt-awk-wrong"):
        (path / "awk").unlink()
        executable(path / "awk", "import sys; sys.stdin.read(); " +
                   ("sys.exit(9)" if route.endswith("error") else "print('wrong')"))
    environment = {"PATH": str(path)}
    if route == "manifest-cdpath":
        receipt = project / ".mir/bootstrap-receipt.json"
        document = json.loads(receipt.read_text())
        document["cli"]["executable"] = "runtime/bin/mir"
        receipt.write_text(json.dumps(document))
        environment["CDPATH"] = "."
    if route == "manifest-dirname-missing":
        (path / "dirname").unlink()
    if route in ("manifest-dirname-wrong", "manifest-dirname-empty-root"):
        (path / "dirname").unlink()
        executable(path / "dirname", "print('absent')")
    if route == "receipt-awk-missing":
        (path / "awk").unlink()
        executable(
            path / "sha256sum",
            "from pathlib import Path; Path('tool-effect').write_bytes(b'hash'); "
            "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())",
        )

    if route == "manifest-bash-env":
        startup = root / "bash-env"
        startup.write_text("printf 'BASH ENV\\n'\n")
        environment["BASH_ENV"] = str(startup)
    run_pair(
        sandbox,
        ["-c", "space arg", "\ud55c\uae00"],
        shell=True,
        stdin=b"\x00stdin\xff\n" if route == "stdin" else b"",
        environment=environment,
        decline=route == "manifest-bash-env",
    )


@pytest.mark.parametrize("spelling", ["supplied", "getcwd"])
def test_runtime_path_spellings(sandbox, spelling):
    root, project = sandbox
    if spelling == "getcwd":
        root = Path(
            subprocess.check_output(
                [sys.executable, "-c", "import os; print(os.getcwd())"], cwd=root
            )
            .decode()
            .strip()
        )
    test_hook_selection((root, root / project.name), "manifest")


def test_hook_environment_precedes_selection(sandbox):
    root, project = sandbox
    alternate = root / "alternate"
    for directory, marker in ((project, "ORIGINAL"), (alternate, "SELECTED_BY_BASH_ENV")):
        executable(directory / ".venv/bin/python", f"print({marker!r})")
    startup = root / "bash-env"
    startup.write_text(f"export CLAUDE_PROJECT_DIR={shlex.quote(str(alternate))}\n")
    run_pair(
        sandbox,
        ["-c", "unused"],
        shell=True,
        environment={"PATH": str(root / "empty-path"), "BASH_ENV": str(startup)},
        decline=True,
    )


def test_console_does_not_apply_shell_startup_guard(sandbox):
    root, _ = sandbox
    startup = root / "bash-env"
    startup.write_text("exit 99\n")
    run_pair(
        sandbox, ["--", "-c", "print('CONSOLE')"],
        environment={"BASH_ENV": str(startup), "SHELLOPTS": "noexec"},
    )
