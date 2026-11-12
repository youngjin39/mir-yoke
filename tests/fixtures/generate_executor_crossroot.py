"""Freeze cross-root query admission from the pinned Python console entry.

Regenerate with --scratch pointing to a new disposable synthetic directory.
Git wrappers record the complete child environment, argv and cwd in call order.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shlex
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "crossroot_status_support", Path(__file__).with_name("generate_executor_status.py"))
SUPPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUPPORT)
PIN = "3cd0588da4fbfc894bfd5c9a969ece58a60972da"
SUPPORT.PIN = PIN
OUTPUT = Path(__file__).with_name("executor_crossroot.json")
CASES = [
    {"name": command + "-" + mode, "command": command, "mode": mode,
     "argv": [command, "--repo-root=<HOME>/target", *suffix]}
    for command, suffix in (
        ("status", ["--job-id=fixture"]),
        ("result", ["--job-id=fixture"]),
        ("list-jobs", []),
        ("list-jobs", ["--status=completed"]),
    )
    for mode in ("empty-path", "path-only-git", "failing-git", "normal-git")
]
for case in CASES[12:]:
    case["name"] = case["name"].replace("list-jobs-", "list-jobs-filtered-", 1)

for command in ("status", "result", "list-jobs"):
    for mode in ("nonexecutable-git", "invalid-stdout", "invalid-stderr", "second-call-missing"):
        CASES.append({"name": command + "-" + mode, "command": command, "mode": mode,
                      "argv": [command, "--repo-root=<HOME>/target",
                               *([] if command == "list-jobs" else ["--job-id=fixture"])]})


for command in ("status", "result"):
    for mode, suffix in (
        ("parser-help", ["--help"]),
        ("parser-explicit-help", ["--help=second-review"]),
        ("parser-unknown", ["--second-review-unknown"]),
    ):
        CASES.append({"name": command + "-" + mode, "command": command, "mode": mode,
                      "argv": [command, "--repo-root=<HOME>/target",
                               "--job-id=fixture", *suffix]})


for command in ("status", "result", "list-jobs"):
    CASES.append({"name": command + "-trailing-control", "command": command,
                  "mode": "trailing-control", "argv": [
                      command, "--repo-root=<HOME>/target",
                      *([] if command == "list-jobs" else ["--job-id=fixture"]),
                  ]})

for command in ("status", "result", "list-jobs", "cancel", "resume", "sweep"):
    CASES.append({"name": command + "-native-home-empty-path", "command": command,
                  "mode": "empty-path", "native_home": True, "argv": [
                      command, "--repo-root=<HOME>/target",
                      *([] if command in {"list-jobs", "sweep"} else ["--job-id=fixture"]),
                  ]})


def environment(home, case):
    # Start empty so every child environment entry is frozen and independently checked.
    return dict(HOME=str(home), USERPROFILE=str(home), PYTHONPATH=str(home),
                PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", LC_ALL="C",
                PYTHONIOENCODING="utf-8:strict", COLUMNS="80",
                MIR_EXECUTOR_ARGPARSE_PROG="__main__.py", MIR_EXECUTOR_PYTHON=sys.executable,
                MIR_EXECUTOR_STDOUT_ENCODING="utf-8", MIR_EXECUTOR_STDOUT_ERRORS="strict",
                MIR_EXECUTOR_STDERR_ENCODING="utf-8", MIR_EXECUTOR_STDERR_ERRORS="backslashreplace",
                CROSSROOT_ENV_SENTINEL="unchanged value", __CF_USER_TEXT_ENCODING="0x0:0:0", PATH=(
                    "" if case["mode"] == "empty-path" else str(home / "git-path")))


def seed(home, case, database):
    SUPPORT.seed(home, {}, database)
    target = home / "target"
    (target / "tasks").mkdir(parents=True)
    shutil.copyfile(database, target / "tasks/jobs.db")
    with sqlite3.connect(target / "tasks/jobs.db") as connection:
        connection.execute("UPDATE jobs SET repo_root=?", (str(target),))
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git required to seed the synthetic invoking repository")
    subprocess.run([git, "init", "-q", str(home)], check=True, capture_output=True)
    if case.get("native_home"):
        (home / "config").mkdir()
        (home / "config/mir-executor.local.json").write_text(json.dumps({
            "native_policy": {"version": 1, "target_admission": {
                "authorize_target": True, "family": {"mode": "reject", "failure": {
                    "kind": "ValueError", "message": "review family refusal",
                }},
            }},
        }), encoding="ascii")
    if case["mode"] != "empty-path":
        directory = home / "git-path"
        directory.mkdir()
        script = directory / "git"
        if case["mode"] == "invalid-stdout":
            ending = "os.write(1, b'\\xff'); sys.exit(7)\n"
        elif case["mode"] == "invalid-stderr":
            ending = "os.write(2, b'\\xff'); sys.exit(7)\n"
        elif case["mode"] == "second-call-missing":
            ending = "Path(sys.argv[1]).unlink(); print(home)\n"
        elif case["mode"] == "trailing-control":
            ending = "print(str(home) + '\\x1c\\x1f')\n"
        elif case["mode"] == "normal-git":
            ending = "os.execv(" + repr(git) + ", ['git', *sys.argv[2:]])\n"
        elif case["mode"] == "failing-git":
            ending = "sys.exit(7)\n"
        else:
            ending = "print(home)\n"
        body = (
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "home = Path(os.environ['HOME'])\n"
            "with (home / 'git-trace.jsonl').open('a') as trace:\n"
            "    trace.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), "
            "'env': dict(os.environ)}, sort_keys=True) + '\\n')\n"
            + ending)
        # A shell trampoline also supports interpreter paths containing spaces.
        script.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -c "
                          + shlex.quote(body) + ' "$0" "$@"\n', encoding="ascii")
        script.chmod(0o644 if case["mode"] == "nonexecutable-git" else 0o755)


def normalize(value, home):
    if isinstance(value, dict):
        # macOS injects this per-user CoreFoundation value after process startup.
        # Preserve its presence while replacing host identity with a generic token.
        return {key: "<MACOS_TEXT_ENCODING>" if key == "__CF_USER_TEXT_ENCODING"
                else normalize(item, home) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item, home) for item in value]
    if isinstance(value, str):
        return value.replace(str(home), "<HOME>").replace(sys.executable, "<PYTHON>")
    return value


def capture(home, case, command):
    argv = [arg.replace("<HOME>", str(home)) for arg in case["argv"]]
    completed = subprocess.run([*command, *argv], cwd=home, env=environment(home, case),
                               capture_output=True, check=False, timeout=30)
    stdout, stderr, code = completed.stdout, completed.stderr, completed.returncode
    if b"Traceback (most recent call last):" in stderr:
        stdout, stderr, code = b"", stderr.splitlines(keepends=True)[-1], 1
    trace = home / "git-trace.jsonl"
    return {
        "exit": code,
        "stdout_hex": stdout.replace(str(home).encode(), b"<HOME>").hex(),
        "stderr_hex": stderr.replace(str(home).encode(), b"<HOME>").hex(),
        "storage": SUPPORT.snapshot(home),
        "git_trace": normalize([json.loads(line) for line in trace.read_text().splitlines()]
                               if trace.exists() else [], home),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    if scratch.exists():
        parser.error("scratch must be a new disposable directory")
    scratch.mkdir(parents=True)
    reference = scratch / "reference"
    digest = SUPPORT.archive_reference(reference)
    database = scratch / "template.db"
    SUPPORT.template(reference, database)
    records = []
    for case in CASES:
        home = scratch / "cases" / case["name"]
        seed(home, case, database)
        shutil.copytree(reference / "tools", home / "tools")
        command = [sys.executable, "-c", "from tools.mir_executor.cli import main; main()"]
        before = SUPPORT.snapshot(home)
        records.append({**case, "before_storage": before,
                        "expected": capture(home, case, command)})
    payload = {"reference": PIN, "archive_sha256": digest,
               "entrypoint": "tools.mir_executor.cli.main (direct console call)",
               "exception_protocol": "exit 1; empty stdout; traceback final stderr line",
               "cases": records}
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                      encoding="ascii")
    (scratch / "provenance.json").write_text(json.dumps({
        "reference": PIN, "archive_sha256": digest,
        "fixture_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        "python": sys.version,
    }, indent=2) + "\n", encoding="ascii")
    print(f"Captured {len(records)} cases from {PIN}")


if __name__ == "__main__":
    main()
