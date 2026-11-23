"""Freeze direct execute from an archived Python reference, never today's handler.

Only synthetic Git repositories, fake Codex children and scratch databases are used.
Regenerate with --scratch pointing to a new disposable directory.
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path


def load(name):
    spec = importlib.util.spec_from_file_location(
        "direct_" + name, Path(__file__).with_name(name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = load("executor_execute_support")
STATUS = load("generate_executor_status")
PIN = "99a8c865d6977b97d32c42beb330206f6b3f10a3"
STATUS.PIN = PIN
OUTPUT = Path(__file__).with_name("executor_direct.json")
BASE = SUPPORT.argv("success")
SELECTORS = (*STATUS.SELECTORS, "MIR_EXECUTOR_EXECUTE_IMPL", "MIR_EXECUTOR_DISPATCH_IMPL")
DRAIN_CASES = frozenset(
    {
        "negative-timeout",
        "timeout-i64-overflow",
        "timeout-float-overflow",
        "async-timeout-zero",
        "background-timeout-zero",
        "nonutf8-argv",
    }
)


def cases():
    result = [
        {"name": name, "base": name}
        for name in (
            "success",
            "error",
            "timeout",
            "async_success",
            "background_success",
            "missing_identity",
            "partial_identity",
            "unknown_change",
            "input_limit",
            "timeout_range",
            "codex_args_file",
            "input_file_limit",
        )
    ]
    for name in (
        "hook_order",
        "pre_execute_refusal",
        "provider_replacement",
        "cancel_before_start",
        "ledger_revalidation",
        "validate_brief_raises",
    ):
        result.append({"name": name, "base": name, "compatibility": True})
    for name, flag in (
        ("async-timeout-zero", "--async"),
        ("background-timeout-zero", "--background"),
    ):
        result.append(
            {
                "name": name,
                "base": "timeout",
                "argv": [*BASE, "--timeout=0", flag],
                "platform": "posix",
            }
        )
    for key in SELECTORS:
        for value in ("python", "native", "0", "invalid"):
            result.append({"name": f"selector-{key}-{value}", "env": {key: value}})
    for name, argv in (
        ("no-options", ["execute"]),
        ("help", ["execute", "--help"]),
        ("help-missing-value", ["execute", "--timeout", "--help"]),
        ("unknown", [*BASE, "--unknown"]),
        ("end-options", [*BASE, "--"]),
        ("unknown-global", ["--unknown", *BASE]),
        ("global-help", ["--help", *BASE]),
        ("leading-end", ["--", *BASE]),
        ("help-value", [*BASE, "--help=ignored"]),
        ("missing-value", [*BASE, "--timeout"]),
        ("option-value", [*BASE, "--category", "--unknown"]),
        ("negative-timeout", [*BASE, "--timeout", "-1"]),
        ("invalid-timeout", [*BASE, "--timeout", "bad"]),
        ("float-timeout", [*BASE, "--timeout", "0.5"]),
        (
            "abbreviation",
            ["execute", "--change-i=fixture", "--cat=unit", "--codex-a=exec 'offline fixture'"],
        ),
        ("duplicate-change", [*BASE, "--change-id", "missing"]),
        ("duplicate-last", ["execute", "--change-id=missing", *BASE[1:]]),
        ("empty-change", [*BASE, "--change-id="]),
        ("bad-category", [*BASE, "--category=unknown"]),
        ("backend-claude", [*BASE, "--backend=claude"]),
        ("ignored-execution-backend", [*BASE, "--execution-backend=claude"]),
        ("backend-invalid", [*BASE, "--backend=invalid"]),
        ("invalid-effort", [*BASE, "--reasoning-effort=invalid"]),
        ("no-codex-args", BASE[:-2]),
        ("both-codex-args", [*BASE, "--codex-args-file=prompt.txt"]),
        ("missing-args-file", [*BASE[:-2], "--codex-args-file=missing"]),
        ("directory-args-file", [*BASE[:-2], "--codex-args-file=tasks"]),
        ("malformed-shell", [*BASE[:-1], "exec 'unterminated"]),
        ("empty-codex-args", [*BASE[:-1], ""]),
        ("nonutf8-argv", [*BASE, "--model=bad-\udcff"]),
        ("global-db", ["--jobs-db=tasks/other.db", *BASE, "--background"]),
        ("global-db-pair", ["--jobs-db", "tasks/other.db", *BASE, "--background"]),
        ("leading-repo-root", ["--repo-root=<HOME>", *BASE]),
        ("missing-root", [*BASE, "--repo-root=<HOME>/missing"]),
        ("root-file", [*BASE, "--repo-root=<HOME>/prompt.txt"]),
        ("ignored-dispatch-brief", [*BASE, "--dispatch-brief=missing.json"]),
        ("ignored-artifacts-dir", [*BASE, "--artifacts-dir=artifacts"]),
        ("ignored-allow-path", [*BASE, "--allow-path=code.py"]),
        ("ignored-verify-cmd", [*BASE, "--verify-cmd=fixture-must-not-run"]),
        ("ignored-expect-changes", [*BASE, "--no-expect-changes"]),
        ("ignored-max-attempts", [*BASE, "--max-codex-attempts=2"]),
        ("ignored-finalize-timeout", [*BASE, "--finalize-lock-timeout=0"]),
        ("timeout-i64-overflow", [*BASE, "--timeout=" + str(2**63)]),
        ("timeout-float-overflow", [*BASE, "--timeout=" + str(10**400)]),
        ("background-timeout-i64-overflow", [*BASE, "--background", "--timeout=" + str(2**63)]),
    ):
        item = {"name": name, "argv": argv}
        if name in DRAIN_CASES:
            item["platform"] = "posix"
        result.append(item)
    for kind in (
        "missing",
        "directory",
        "malformed",
        "utf16",
        "invalid-utf8",
        "null",
        "array",
        "integer",
        "string",
        "changes-null",
        "changes-object",
        "entry-null",
        "category-null",
        "NaN",
        "Infinity",
        "-Infinity",
        "1e400",
        "surrogate",
        "deep",
        "large-int",
        "negative-zero",
        "permission-denied",
    ):
        result.append({"name": "ledger-" + kind, "ledger": kind})
    for kind in (
        "array", "null", "category-null", "permission-denied", "integer", "string", "entry-null"
    ):
        result.append(
            {"name": "background-ledger-" + kind, "ledger": kind, "argv": [*BASE, "--background"]}
        )
    for kind in (
        "missing",
        "corrupt",
        "directory",
        "parent-file",
        "readonly",
        "readonly-directory",
        "locked",
        "wrong-schema",
        "insert-abort",
        "insert-fail",
        "insert-rollback",
        "insert-ignore",
        "not-null",
        "unique",
        "update-ignore",
        "update-fail",
        "update-abort",
        "update-rollback",
        "update-completed-fail",
        "update-completed-abort",
        "update-completed-rollback",
    ):
        result.append({"name": "db-" + kind, "db": kind, "argv": [*BASE, "--background"]})
    for name in (
        "crossroot",
        "crossroot-nongit",
        "crossroot-help",
        "crossroot-unknown",
        "missing-interpreter",
        "missing-codex",
        "permission-denied-codex",
        "directory-codex",
        "nonutf8-codex",
        "killed-child",
        "sigkill-child",
        "local-disabled",
        "main-worktree-refusal",
        "linked-worktree",
        "linked-worktree-reuse",
    ):
        record = {"name": name}
        if name in {"sigkill-child", "crossroot-help", "crossroot-unknown"}:
            record["platform"] = "posix"
        result.append(record)
    for encoding in (
        "ascii:strict",
        "ascii:backslashreplace",
        "latin1:strict",
        "utf-8:strict",
        "utf-16:strict",
        "utf-32:strict",
        "cp1252:strict",
        "cp932:strict",
        "ascii:namereplace",
    ):
        result.append(
            {
                "name": "codec-" + encoding.replace(":", "-"),
                "env": {"PYTHONIOENCODING": encoding},
                "compatibility": encoding in {"cp932:strict", "ascii:namereplace"},
            }
        )
    return result


CASES = cases()


def seed(home, case, reference=None, database=None):
    base = case.get("base", "success")
    launcher = SUPPORT.seed(home, base)
    if reference is not None:
        shutil.copytree(
            reference / "tools",
            home / "tools",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("local.py", "__pycache__"),
        )
    local = home / "tools/mir_executor/local.py"
    if not local.exists():
        local.write_text("# Synthetic project hook, disabled by local config.\n", encoding="ascii")
    config = home / "config/mir-executor.local.json"
    config.parent.mkdir(exist_ok=True)
    options = json.loads(config.read_text()) if config.exists() else {}
    options["python_local_hooks"] = bool(
        case.get("compatibility") and not case["name"].startswith("codec-")
    )
    config.write_text(json.dumps(options) + "\n", encoding="ascii")
    kind = case.get("ledger")
    ledger = home / "tasks/tdd.json"
    if kind == "missing":
        ledger.unlink()
    elif kind == "directory":
        ledger.unlink()
        ledger.mkdir()
    elif kind:
        text = {
            "malformed": "{broken",
            "null": "null",
            "array": "[]",
            "integer": "17",
            "string": '"abc"',
            "changes-null": '{"changes":null}',
            "changes-object": '{"changes":{}}',
            "entry-null": '{"changes":[null]}',
            "category-null": '{"changes":[{"id":"fixture","categories":null}]}',
        }
        if kind == "utf16":
            ledger.write_bytes(ledger.read_text().encode("utf-16"))
        elif kind == "invalid-utf8":
            ledger.write_bytes(b"\xff\x00")
        elif kind == "permission-denied":
            ledger.chmod(0o000)
        elif kind in {"surrogate", "deep", "large-int", "negative-zero"}:
            value = {
                "surrogate": '"\\ud800"',
                "deep": "[" * 5000 + "0" + "]" * 5000,
                "large-int": "12345678901234567890123456789012345678901234567890",
                "negative-zero": "-0.0",
            }[kind]
            ledger.write_text(
                ledger.read_text().rstrip()[:-1] + ', "extension": ' + value + "}", encoding="ascii"
            )
        else:
            ledger.write_text(
                text.get(kind, ledger.read_text().rstrip()[:-1] + ', "extension": ' + kind + "}"),
                encoding="utf-8",
            )
    kind = case.get("db")
    path = home / "tasks/jobs.db"
    if kind not in (None, "missing"):
        if kind == "corrupt":
            path.write_bytes(b"fixture is not sqlite\n")
        elif kind == "directory":
            path.mkdir()
        elif kind == "parent-file":
            (home / "blocked").write_bytes(b"blocker")
        else:
            if database is not None:
                shutil.copyfile(database, path)
            else:
                script = (
                    "from pathlib import Path; from tools.mir_executor.jobs import JobRegistry; "
                    "JobRegistry(Path('tasks/jobs.db')).close()"
                )
                subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=home,
                    env=environment(home, case, launcher),
                    check=True,
                    capture_output=True,
                )
            with sqlite3.connect(path) as db:
                if kind == "wrong-schema":
                    db.execute("PRAGMA secure_delete=OFF")
                    db.execute("DROP TABLE jobs")
                    db.execute("CREATE TABLE jobs(unexpected TEXT)")
                elif kind.startswith("insert-"):
                    action = kind.removeprefix("insert-").upper()
                    suffix = "" if action == "IGNORE" else ", 'direct fixture refused'"
                    db.execute(
                        "CREATE TRIGGER direct_fixture BEFORE INSERT ON jobs BEGIN "
                        f"SELECT RAISE({action}{suffix}); END"
                    )
                elif kind == "not-null":
                    db.execute(
                        "ALTER TABLE jobs ADD COLUMN fixture_required TEXT NOT NULL DEFAULT ''"
                    )
                    db.execute(
                        "CREATE TRIGGER direct_fixture BEFORE INSERT ON jobs BEGIN "
                        "SELECT RAISE(ABORT, 'NOT NULL constraint failed: "
                        "jobs.fixture_required'); END"
                    )
                elif kind == "unique":
                    db.execute("CREATE UNIQUE INDEX direct_unique ON jobs(category)")
                    db.execute(
                        "INSERT INTO jobs(job_id,change_id,category,repo_root,codex_args,"
                        "timeout_seconds,status,started_at) "
                        "VALUES('existing','fixture','unit','root','[]',1,'completed','started')"
                    )
                elif kind.startswith("update-"):
                    conditional = kind.startswith("update-completed-")
                    action = kind.rsplit("-", 1)[-1].upper()
                    suffix = "" if action == "IGNORE" else ", 'direct late status fault'"
                    condition = "WHEN NEW.status='completed' " if conditional else ""
                    db.execute(
                        "CREATE TRIGGER direct_fixture BEFORE UPDATE OF status ON jobs "
                        f"{condition}BEGIN "
                        f"SELECT RAISE({action}{suffix}); END"
                    )
            if kind == "readonly":
                path.chmod(0o400)
            if kind == "readonly-directory":
                path.parent.chmod(0o500)
    if case["name"].startswith("crossroot"):
        target = home / "target"
        SUPPORT.seed(target, "success")
        (target / "tools/mir_executor/local.py").write_text("# Synthetic disabled hook.\n")
        (target / "config").mkdir()
        shutil.copyfile(config, target / "config/mir-executor.local.json")
        if case["name"].endswith("nongit"):
            shutil.rmtree(target / ".git")
        if case["name"] in {"crossroot-help", "crossroot-unknown"}:
            git = shutil.which("git")
            if git is None:
                raise RuntimeError("Git required for synthetic cross-root admission")
            directory = home / "git-path"
            directory.mkdir()
            wrapper = directory / "git"
            wrapper.write_text(
                "#!/usr/bin/env python3\nimport json, os, sys\nfrom pathlib import Path\n"
                "home = Path(os.environ['HOME'])\n"
                "with (home / 'git-trace.jsonl').open('a') as stream:\n"
                "    stream.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')\n"
                "os.execv(" + repr(git) + ", ['git', *sys.argv[1:]])\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
    if case["name"] == "local-disabled":
        (home / "tools/mir_executor/local.py").write_text(
            "raise AssertionError('disabled local hook imported')\n", encoding="ascii"
        )
    if case["name"] == "permission-denied-codex":
        launcher.chmod(0o600)
    if case["name"] == "killed-child":
        source = launcher.read_text()
        launcher.write_text(
            source.replace(
                "if mode == 'timeout':",
                "if mode == 'killed':\n            os._exit(17)\n        if mode == 'timeout':",
            )
        )
    if case["name"] == "sigkill-child":
        source = launcher.read_text()
        launcher.write_text(
            source.replace(
                "if mode == 'timeout':",
                "if mode == 'sigkill':\n"
                "            os.kill(os.getpid(), __import__('signal').SIGKILL)\n"
                "        if mode == 'timeout':",
            )
        )
    if case["name"] in DRAIN_CASES:
        # These boundary cases fail immediately after a flushed notification or
        # request. Ignoring SIGTERM lets the synthetic observer drain those
        # frames before each client's existing bounded forced-stop path.
        source = launcher.read_text()
        launcher.write_text(
            source.replace(
                "from pathlib import Path\n",
                "from pathlib import Path\nimport signal\n"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n",
            )
        )
    if case["name"].startswith("linked-worktree"):
        origin = home.with_name(home.name + "-origin")
        staged = home.with_name(home.name + "-seed")
        git_environment = dict(environment(home, case, launcher), GIT_CONFIG_NOSYSTEM="1")
        shutil.move(home, staged)
        subprocess.run(
            ["git", "init", "--quiet", str(origin)],
            check=True,
            capture_output=True,
            env=git_environment,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(origin),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=" + str(origin / "no-hooks"),
                "commit",
                "--allow-empty",
                "--quiet",
                "-m",
                "Synthetic worktree fixture",
            ],
            check=True,
            capture_output=True,
            env=git_environment,
        )
        subprocess.run(
            ["git", "-C", str(origin), "worktree", "add", "--quiet", "--detach", str(home)],
            check=True,
            capture_output=True,
            env=git_environment,
        )
        shutil.copytree(staged, home, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
        shutil.rmtree(staged)
        if case["name"].endswith("reuse"):
            (home / "existing-worktree-file").write_bytes(b"preserved\n")
    return launcher


def environment(home, case, launcher):
    env = SUPPORT.environment(home, case.get("base", "success"), launcher)
    for name in SELECTORS:
        env.pop(name, None)
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        PYTHONPATH=str(home),
        MIR_EXECUTOR_PYTHON=sys.executable,
        PYTHONIOENCODING="utf-8:strict",
        MIR_EXECUTOR_ARGPARSE_PROG="-c",
        COLUMNS="80",
    )
    env.update(case.get("env", {}))
    if case["name"] == "missing-interpreter":
        env["MIR_EXECUTOR_PYTHON"] = str(home / "missing-python")
    if case["name"] in {"missing-codex", "nonutf8-codex"}:
        env["CODEX_BIN"] = str(
            home / ("missing-codex" if case["name"] == "missing-codex" else "bad-\udcff")
        )
    if case["name"] == "directory-codex":
        env["CODEX_BIN"] = str(home / "tasks")
    if case["name"] in {"crossroot-help", "crossroot-unknown"}:
        env["PATH"] = str(home / "git-path") + os.pathsep + env.get("PATH", "")
    if case["name"] == "killed-child":
        env["EXECUTE_FIXTURE_MODE"] = "killed"
    if case["name"] == "sigkill-child":
        env["EXECUTE_FIXTURE_MODE"] = "sigkill"
    if case["name"] in {"main-worktree-refusal", "linked-worktree", "linked-worktree-reuse"}:
        env.pop("MIR_CODEX_MAIN", None)
    return env


def arguments(home, case):
    argv = case.get("argv", SUPPORT.argv(case.get("base", "success")))
    argv = [arg.replace("<HOME>", str(home)) for arg in argv]
    if case["name"].startswith("crossroot"):
        argv += ["--repo-root", str(home / "target")]
    if case["name"] == "crossroot-help":
        argv.append("--help")
    if case["name"] == "crossroot-unknown":
        argv.append("--unknown")
    if case.get("db") == "parent-file":
        argv += ["--jobs-db=blocked/jobs.db"]
    return argv


def normalize(text, home, launcher):
    text = SUPPORT.normalize(text, home, launcher)
    text = text.replace(str(home), "<root>").replace(str(Path(sys.executable)), "<python>")
    return re.sub(r"\b[0-9a-f]{32}\b", "<job-id>", text)


def snapshot(home, launcher):
    storage = {}
    for path in sorted(home.rglob("*")):
        relative = path.relative_to(home)
        if any(
            part in {".git", "tools", ".mir", "__pycache__", "config", "git-path"}
            for part in relative.parts
        ):
            continue
        if relative.parts[0] in {
            "offline-policy.json",
            "fake-codex",
            "fake-codex.cmd",
            "server.py",
            "prompt.txt",
        }:
            continue
        if path.is_dir():
            storage[relative.as_posix()] = {
                "kind": "directory",
                "mode": oct(stat.S_IMODE(path.stat().st_mode)),
            }
            continue
        try:
            raw = path.read_bytes()
        except PermissionError:
            # The harness reads a synthetic denied file only after execution,
            # restoring its observed mode before comparing durable effects.
            original_mode = stat.S_IMODE(path.stat().st_mode)
            path.chmod(original_mode | 0o400)
            try:
                raw = path.read_bytes()
            finally:
                path.chmod(original_mode)
        item = {"kind": "file", "mode": oct(stat.S_IMODE(path.stat().st_mode))}
        if path.suffix == ".db" and raw.startswith(b"SQLite format 3\x00"):
            with sqlite3.connect(path) as db:
                tables = [
                    row[0]
                    for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                ]
                item["tables"] = {}
                volatile = False
                for name in tables:
                    cursor = db.execute(f'SELECT * FROM "{name}" ORDER BY rowid')
                    columns = [entry[0] for entry in cursor.description]
                    rows = []
                    for row in cursor:
                        values = dict(zip(columns, row, strict=True))
                        for key in ("job_id", "started_at", "completed_at", "duration_seconds"):
                            if values.get(key) is not None and values.get("job_id") != "existing":
                                values[key] = "<" + key + ">"
                                volatile = True
                        rows.append(values)
                    item["tables"][name] = rows
            # Empty/error databases are compared physically. Successful rows have
            # random IDs and clocks, so retain every column with explicit volatility.
            if not volatile:
                item["bytes"] = (raw[:96] + b"\x00" * 4 + raw[100:]).hex()
        else:
            try:
                item["bytes"] = normalize(raw.decode("utf-8"), home, launcher).encode().hex()
            except UnicodeDecodeError:
                item["bytes"] = raw.hex()
        storage[relative.as_posix()] = item
    return json.loads(normalize(json.dumps(storage, ensure_ascii=True), home, launcher))


def capture(home, case, launcher, command):
    lock = None
    try:
        if case.get("db") == "locked":
            lock = sqlite3.connect(home / "tasks/jobs.db")
            lock.execute("BEGIN EXCLUSIVE")
        result = subprocess.run(
            [*command, *arguments(home, case)],
            cwd=home,
            env=environment(home, case, launcher),
            capture_output=True,
            timeout=45,
            check=False,
        )
    finally:
        if lock is not None:
            lock.rollback()
            lock.close()
    codec = codecs.lookup(case.get("env", {}).get("PYTHONIOENCODING", "utf-8").split(":")[0]).name
    try:
        stdout = result.stdout.decode(codec, "surrogateescape")
        stderr = result.stderr.decode(codec, "surrogateescape")
    except UnicodeError:
        # A native encoding regression must remain a byte mismatch, not crash
        # the capture wrapper before it can report the process and effects.
        return {
            "exit": result.returncode,
            "stdout_hex": result.stdout.hex(),
            "stderr_hex": result.stderr.hex(),
            "storage": snapshot(home, launcher),
        }
    code = result.returncode
    if "Traceback (most recent call last):" in stderr:
        stderr, code = stderr.splitlines()[-1] + "\n", 1
    return {
        "exit": code,
        "stdout_hex": normalize(stdout, home, launcher).encode(codec, "surrogateescape").hex(),
        "stderr_hex": normalize(stderr, home, launcher).encode(codec, "surrogateescape").hex(),
        "storage": snapshot(home, launcher),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    if scratch.exists():
        parser.error("scratch must be new")
    scratch.mkdir(parents=True)
    reference = scratch / "reference"
    digest = STATUS.archive_reference(reference)
    records = []
    database = scratch / "template.db"
    STATUS.empty_template(reference, database)
    for case in CASES:
        home = scratch / "cases" / case["name"]
        launcher = seed(home, case, reference, database)
        command = [sys.executable, "-c", "from tools.mir_executor.cli import main; main()"]
        expected = capture(home, case, launcher, command)
        record = {**case, "expected": expected}
        if case["name"] in {"ledger-surrogate", "nonutf8-argv"}:
            kind = "codex" if case["name"] == "ledger-surrogate" else "root"
            prefix = str(launcher if kind == "codex" else home)
            # Error offsets count the serialized source, which contains one
            # absolute path before the failing surrogate. Keep the raw oracle
            # index and its coordinate width so callers can relocate that path.
            record["encoding_error_path"] = {
                "kind": kind,
                "width": len(json.dumps(prefix, ensure_ascii=False)[1:-1]),
            }
        if any(
            b"usage: -c" in bytes.fromhex(expected[key]) for key in ("stdout_hex", "stderr_hex")
        ):
            module_home = scratch / "module-cases" / case["name"]
            module_launcher = seed(module_home, case, reference, database)
            record["expected_by_route"] = {
                "module": capture(
                    module_home, case, module_launcher, [sys.executable, "-m", "tools.mir_executor"]
                )
            }
        records.append(record)
    OUTPUT.write_text(
        json.dumps(
            {
                "reference": PIN,
                "archive_sha256": digest,
                "template_hex": database.read_bytes().hex(),
                "exception_protocol": "exit 1; preserve raw stdout; traceback final stderr line",
                "cases": records,
            },
            indent=2,
            ensure_ascii=True,
            sort_keys=True,
        )
        + "\n",
        encoding="ascii",
    )
    (scratch / "provenance.json").write_text(
        json.dumps(
            {
                "reference": PIN,
                "archive_sha256": digest,
                "python": sys.version,
                "fixture_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Captured {len(records)} direct cases from {PIN}")


if __name__ == "__main__":
    main()
