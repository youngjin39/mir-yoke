"""Capture Bash startup classes from the pinned launcher, without native output."""

import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = "1324a3c"
SOURCE_REVISION = "4343aba88e811f14f6147a9a9b818b6fb346bec8"
FIXTURE = ROOT / "tests/fixtures/run_python_startup_1324a3c.json"
EXPORTS = (
    "PROJECT_DIR", "_MIR_RECEIPT", "_MIR_EXTERNAL_CLI", "_MIR_EXTERNAL_SHA",
    "_MIR_RUNTIME_ROOT", "_MIR_RUNTIME_MANIFEST", "_MIR_RUNTIME_MANIFEST_SHA",
)
CLASSES = (
    "BASH_ENV", "BASH_FUNC_command%%", "command", "BASH_FUNC_command()",
    "ENV", "SHELLOPTS", "BASHOPTS", "CDPATH", "IFS", "POSIXLY_CORRECT",
    "PS4", "BASH_XTRACEFD", "GLOBIGNORE", "LC_ALL", "LANG", "_", *EXPORTS,
)
CASES = [(name, state) for name in CLASSES for state in ("unset", "set", "empty")]
OPTIONS = (
    "allexport braceexpand emacs errexit errtrace functrace hashall histexpand "
    "history ignoreeof interactive-comments keyword monitor noclobber noexec "
    "noglob nolog notify nounset onecmd physical pipefail posix privileged verbose vi xtrace"
).split()
CASES += [("SHELLOPTS", value) for value in ["defaults", *OPTIONS]]
CASES += [("BASH_FUNC_command%%", "ignored")]


def setup(root, name, state):
    project = root / "project"
    alternate = root / "alternate"
    for directory, marker in ((project, "ORIGINAL"), (alternate, "ALTERNATE")):
        python = directory / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text(
            "#!/bin/sh\nprintf '" + marker + "\\n'\n"
            "printf '%s\\n' \"${PROJECT_DIR-unset}\"\n"
        )
        python.chmod(0o755)
    (root / "home").mkdir()
    startup = root / "startup"
    startup.write_text(
        "printf 'startup\\n' > effect\n"
        f"export CLAUDE_PROJECT_DIR={shlex.quote(str(alternate))}\n"
    )
    env = {
        "HOME": str(root / "home"),
        "PATH": str(root / "empty-path"),
        "CLAUDE_PROJECT_DIR": str(project),
    }
    values = {
        "BASH_ENV": str(startup),
        "BASH_FUNC_command%%": "() { printf 'function\\n' > effect; return 1; }",
        "ENV": str(startup),
        "SHELLOPTS": "xtrace",
        "BASHOPTS": "extdebug",
        "command": "() { printf 'legacy\\n' > effect; return 1; }",
        "BASH_FUNC_command()": "() { printf 'alternate\\n' > effect; return 1; }",
        "CDPATH": ".",
        "IFS": "/",
        "POSIXLY_CORRECT": "1",
        "PS4": "$(printf trace > effect)",
        "BASH_XTRACEFD": "1",
        "GLOBIGNORE": "*",
        "LC_ALL": "C",
        "LANG": "C",
        "_": "OLD",
        **dict.fromkeys(EXPORTS, "OLD"),
    }
    if state != "unset":
        env[name] = (
            "" if state == "empty" else
            "braceexpand:hashall:interactive-comments" if state == "defaults" else
            "ignored" if state == "ignored" else
            state if name == "SHELLOPTS" and state in OPTIONS else values[name]
        )
    if name == "_":
        python = project / ".venv/bin/python"
        source = "import os; print(os.environ.get('_', 'unset'))"
        python.write_text(
            "#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -c " + shlex.quote(source) + "\n"
        )
    if name in EXPORTS:
        setup_exported_receipt(root, project, env, name)
    # Active inputs decline; ENV/BASHOPTS and default/empty shell state do not.
    decline = (
        name in EXPORTS and state != "unset"
        or name in ("BASH_ENV", "BASH_FUNC_command%%") and state == "set"
        or name == "SHELLOPTS"
        and state in ("set", "allexport", "noexec", "onecmd", "verbose", "xtrace")
    )
    return env, decline


def setup_exported_receipt(root, project, env, name):
    tools = root / "tools"
    tools.mkdir()
    jq = shutil.which("jq")
    assert jq, "Pinned receipt parity requires jq"
    for command, target in (
        ("jq", jq), ("shasum", "/usr/bin/shasum"),
        ("awk", "/usr/bin/awk"), ("dirname", "/usr/bin/dirname"),
    ):
        (tools / command).symlink_to(target)
    external = root / "runtime/bin/mir"
    external.parent.mkdir(parents=True)
    external.write_text(
        "#!/bin/sh\nif [ \"$1\" = runtime-manifest ]; then exit 0; fi\n"
        "printf '%s\\n' \"${" + name + "-unset}\"\n"
    )
    external.chmod(0o755)
    physical = subprocess.check_output(
        ["/bin/bash", "-c", 'cd -- "$1" && pwd -P', "capture", str(external.parent / "..")],
        env={"HOME": env["HOME"], "PATH": "/usr/bin:/bin"},
    ).decode().rstrip("\n")
    manifest = Path(physical) / "runtime-manifest.json"
    manifest.write_text("{}")
    cli = {
        "executable": str(external),
        "sha256": hashlib.sha256(external.read_bytes()).hexdigest(),
        "runtime_manifest": str(manifest),
        "runtime_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    }
    (project / ".mir").mkdir()
    (project / ".mir/bootstrap-receipt.json").write_text(json.dumps({"cli": cli}))
    env["PATH"] = str(tools)


def result(process, root):
    physical = subprocess.check_output(
        [sys.executable, "-c", "import os; print(os.getcwd())"], cwd=root,
        env={"HOME": str(root / "home"), "PYTHONDONTWRITEBYTECODE": "1"},
    ).decode().rstrip("\n")

    def norm(raw):
        spellings = {str(root), physical}
        for spelling in sorted(spellings, key=len, reverse=True):
            raw = raw.replace(spelling.encode(), b"${TMP}")
        return raw
    effect = root / "effect"
    return {
        "exit": process.returncode,
        "stdout_hex": norm(process.stdout).hex(),
        "stderr_hex": norm(process.stderr).hex(),
        "effect_hex": effect.read_bytes().hex() if effect.exists() else None,
    }


def reference(root):
    script = root / "launcher"
    script.write_bytes(subprocess.check_output(
        ["git", "show", f"{SOURCE_REVISION}:.claude/hooks/_lib/run-python.sh"], cwd=ROOT
    ))
    return script


def capture():
    records = []
    for name, state in CASES:
        with tempfile.TemporaryDirectory(prefix="startup-") as directory:
            root = Path(directory)
            env, decline = setup(root, name, state)
            script = reference(root)
            process = subprocess.run(
                ["/bin/bash", str(script), "-c", "unused"],
                env=env, cwd=root, capture_output=True, check=False, timeout=10,
            )
            records.append({
                "name": name, "state": state, "decline": decline,
                "reference": result(process, root),
            })
    return {"pin": PIN, "records": records}


if __name__ == "__main__":
    FIXTURE.write_text(json.dumps(capture(), indent=2) + "\n")
