"""Offline pinned Stage D dispatch capture; fake providers and synthetic Git only.

Run with --scratch NEW; add --compare BINARY to retain native differences.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import runpy
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DIRECT = runpy.run_path(str(HERE / "generate_executor_direct.py"))
DISPATCH = runpy.run_path(str(HERE / "executor_dispatch_cli_support.py"))
SUPPORT = runpy.run_path(str(HERE / "executor_execute_support.py"))
FAULTS = runpy.run_path(str(HERE / "executor_dispatch_stage_d_faults.py"))
PIN = "d7ce42656224c719094358f343317907bf6e46a9"
DIRECT["STATUS"].PIN = PIN
OUTPUT = HERE / "executor_dispatch_stage_d.json"


def cases():
    values = [
        {"name": name}
        for name in (
            "success",
            "relative_artifacts",
            "claude_success",
            "claude_invalid_timeout",
            "gate_block",
            "review_reject",
            "hook_failure",
            "finalize_rollback",
            "provider-failure",
            "provider-timeout",
            "provider-killed",
            "provider-malformed",
            "provider-retry-success",
            "provider-exhaustion",
            "provider-no-change",
            "verify-fail",
            "verify-unknown",
            "no-verifiers",
            "no-allowlist",
            "no-expect-changes",
            "default-artifacts",
            "artifacts-file",
            "artifacts-symlink",
            "brief-missing",
            "brief-malformed",
            "brief-array",
            "brief-empty",
            "brief-target-invalid",
            "brief-directory",
            "brief-symlink",
            "render-invalid",
            "validate-failure",
            "pre-execute-refusal",
            "writer-refusal",
            "event-failure",
            "local-disabled",
            "crossroot",
            "crossroot-deny",
            "crossroot-nongit",
            "tmpdir-linked",
            "dirty-target",
        )
    ]
    for kind in (
        "missing",
        "locked",
        "corrupt",
        "readonly",
        "readonly-directory",
        "directory",
        "wrong-schema",
        "insert-abort",
        "update-abort",
    ):
        values.append({"name": "db-" + kind, "db": kind})
    for key in (
        "MIR_EXECUTOR_IMPL",
        "MIR_EXECUTOR_QUERY_IMPL",
        "MIR_EXECUTOR_EXECUTE_IMPL",
        "MIR_EXECUTOR_DISPATCH_IMPL",
        "MIR_NATIVE_HOOKS",
    ):
        for value in ("python", "native", "0", "invalid"):
            values.append({"name": f"selector-{key}-{value}", "env": {key: value}})
    for kind in ("missing", "malformed", "shape", "digest", "path", "symlink", "not-executable"):
        values.append({"name": "pin-" + kind, "pin": kind})
    for name, extra in (
        ("help", ["--help"]),
        ("unknown", ["--unknown"]),
        ("end-options", ["--"]),
        ("missing-value", ["--timeout"]),
        ("bad-timeout", ["--timeout=bad"]),
        ("negative-timeout", ["--timeout=-1"]),
        ("zero-attempts", ["--max-codex-attempts=0"]),
        ("bad-backend", ["--execution-backend=invalid"]),
        ("bad-effort", ["--reasoning-effort=invalid"]),
        ("bad-lock-timeout", ["--finalize-lock-timeout=-1"]),
        ("unknown-category", ["--change-id=fixture", "--category=unknown"]),
        ("unknown-change", ["--change-id=missing", "--category=unit"]),
        ("identity", ["--change-id=fixture", "--category=unit"]),
        ("async", ["--async"]),
        ("background", ["--background"]),
        ("root-missing", ["--repo-root=<ROOT>/missing"]),
        ("root-file", ["--repo-root=<ROOT>/code.txt"]),
        ("nonutf8", ["--model=bad-\udcff"]),
        ("path-traversal", ["--allow-path=../outside"]),
    ):
        values.append({"name": "argv-" + name, "extra": extra})
    return values + FAULTS["cases"]()


CASES = cases()
SERVER = (
    DISPATCH["SERVER"]
    .replace(
        "if method == 'initialize':",
        """if method == 'initialize':
        if mode in ('provider-failure', 'provider-exhaustion'):
            sys.exit(7)
        if mode == 'provider-killed':
            import signal
            os.kill(os.getpid(), signal.SIGKILL)
        if mode == 'provider-malformed':
            print('not-json', flush=True)
            sys.exit(0)
        if mode == 'provider-retry-success':
            marker = root / 'retry-once'
            if not marker.exists():
                marker.touch()
                sys.exit(7)""",
    )
    .replace(
        "(cwd / 'code.txt').write_text('delegated change\\n')",
        "if mode not in ('provider-no-change', 'no-expect-changes'):\n"
        "                (cwd / 'code.txt').write_text('delegated change\\n')",
    )
    .replace(
        "elif method == 'turn/start':",
        "elif method == 'turn/start':\n        if mode == 'provider-timeout':\n"
        "            import time\n            time.sleep(3)\n            sys.exit(0)",
    )
)


def seed(home, case, reference, database, binary=None):
    launcher, env, argv = DISPATCH["seed"](home, case["name"], SUPPORT)
    shutil.copytree(
        reference / "tools",
        home / "tools",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("local.py", "__pycache__"),
    )
    launcher.write_text("#!/usr/bin/env python3\n" + SERVER, encoding="utf-8")
    launcher.chmod(0o755)
    (home / "server.py").write_text(SERVER, encoding="utf-8")
    bindir = home / "fake-bin"
    bindir.mkdir()
    for name, source in (("codex", launcher), ("claude", home / "fake-claude")):
        destination = bindir / name
        if source.exists():
            destination.symlink_to(source)
        else:
            destination.write_text("#!/bin/sh\nexit 99\n", encoding="ascii")
            destination.chmod(0o755)
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        PYTHONPATH=str(home),
        PATH=str(bindir) + os.pathsep + os.environ["PATH"],
        CODEX_HOME=str(home / "codex-home"),
        MIR_EXECUTOR_PYTHON=sys.executable,
        MIR_EXECUTOR_ARGPARSE_PROG="-c",
        PYTHONIOENCODING="utf-8:strict",
        COLUMNS="80",
        DISPATCH_FIXTURE_MODE=case["name"],
    )
    for key in tuple(env):
        if key.startswith("MIR_EXECUTOR_") and key.endswith("_IMPL"):
            env.pop(key)
    env.pop("MIR_NATIVE_HOOKS", None)
    env.update(case.get("env", {}))
    config_path = home / "config/mir-executor.local.json"
    config = json.loads(config_path.read_text())
    name = case["name"]
    if name == "local-disabled":
        config["python_local_hooks"] = False
    if name == "verify-fail":
        config["verifiers"]["offline"] = [sys.executable, "-c", "raise SystemExit(3)"]
    if name == "verify-unknown":
        argv[argv.index("offline")] = "missing"
    for scenario, flag in (
        ("no-verifiers", "--verify-cmd"),
        ("no-allowlist", "--allow-path"),
        ("default-artifacts", "--artifacts-dir"),
    ):
        if name == scenario:
            index = argv.index(flag)
            del argv[index : index + 2]
    if name == "no-expect-changes":
        argv += ["--no-expect-changes"]
    if name == "artifacts-file":
        (home / "artifacts").write_text("blocker")
    if name == "artifacts-symlink":
        (home / "outside").mkdir()
        (home / "artifacts").symlink_to(home / "outside", target_is_directory=True)
    brief = home / "brief.json"
    if name in ("brief-missing", "brief-directory"):
        brief.unlink()
        if name == "brief-directory":
            brief.mkdir()
    if name == "brief-symlink":
        brief.rename(home / "linked-brief.json")
        brief.symlink_to(home / "linked-brief.json")
    if name in ("brief-malformed", "brief-array", "brief-empty", "brief-target-invalid"):
        brief.write_text(
            {
                "brief-malformed": "{",
                "brief-array": "[]",
                "brief-empty": '{"expanded_goal":""}',
                "brief-target-invalid": '{"expanded_goal":"x","target_agent":3}',
            }[name]
        )
    local = home / "tools/mir_executor/local.py"
    with local.open("a") as stream:
        stream.write("""
def after_provider_call(result, metadata):
    with (ROOT / 'provider-diagnostics').open('a') as stream:
        stream.write(json.dumps({'stderr': result.stderr,
            'error_sig': getattr(result, 'error_sig', '')}) + '\\n')
""")
    additions = {
        "render-invalid": "def render_brief(*args):\n    return 3\n",
        "validate-failure": (
            'def validate_brief(*args):\n    raise ValueError("offline validation")\n'
        ),
        "pre-execute-refusal": 'def pre_execute(*args):\n    raise ValueError("offline refusal")\n',
        "writer-refusal": (
            "@contextmanager\ndef writer_scope(*args):\n"
            '    raise ValueError("offline writer")\n    yield\n'
        ),
        "event-failure": 'def on_job_event(*args):\n    raise ValueError("offline event")\n',
    }
    if name in additions:
        with local.open("a") as stream:
            stream.write("\n" + additions[name])
    if name.startswith("crossroot"):
        target = home / "target"
        target.mkdir()
        git(target, "init", "-q")
        argv += ["--repo-root", str(target)]
        if name == "crossroot-nongit":
            shutil.rmtree(target / ".git")
        if name == "crossroot-deny":
            with local.open("a") as stream:
                stream.write(
                    "\ndef authorize_target(*args):\n"
                    '    raise ValueError("offline target denied")\n'
                )
    if name == "tmpdir-linked":
        (home / "physical-tmp").mkdir()
        (home / "linked-tmp").symlink_to(home / "physical-tmp", target_is_directory=True)
        env["TMPDIR"] = str(home / "linked-tmp")
    if name == "dirty-target":
        (home / "code.txt").write_text("user change\n")
    if name == "provider-timeout":
        argv += ["--timeout=1"]
    if name in ("provider-retry-success", "provider-exhaustion"):
        argv += ["--max-codex-attempts=2"]
    FAULTS["apply"](home, case, env, argv, config, local)
    config_path.write_text(json.dumps(config), encoding="ascii")
    kind = case.get("db")
    db = home / "tasks/jobs.db"
    if kind and kind != "missing":
        if kind == "corrupt":
            db.write_bytes(b"offline corrupt database\n")
        elif kind == "directory":
            db.mkdir()
        else:
            shutil.copyfile(database, db)
            with sqlite3.connect(db) as connection:
                if kind == "wrong-schema":
                    connection.execute("DROP TABLE jobs")
                    connection.execute("CREATE TABLE jobs(unexpected TEXT)")
                elif kind in ("insert-abort", "update-abort"):
                    operation = "INSERT" if kind == "insert-abort" else "UPDATE OF status"
                    connection.execute(
                        f"CREATE TRIGGER fixture BEFORE {operation} ON jobs "
                        "BEGIN SELECT RAISE(ABORT,'offline fault'); END"
                    )
            if kind == "readonly":
                db.chmod(0o400)
            if kind == "readonly-directory":
                db.parent.chmod(0o500)
    argv += [arg.replace("<ROOT>", str(home)) for arg in case.get("extra", [])]
    if binary:
        install(home, binary, case.get("pin"))
    return launcher, env, argv


def install(home, binary, fault=None):
    destination = home / ".mir/bin/executor-query"
    destination.parent.mkdir(parents=True)
    shutil.copy2(binary, destination)
    destination.chmod(0o755)
    pin = destination.parent / "executor-query.json"
    value = {
        "path": ".mir/bin/executor-query",
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }
    if fault == "digest":
        value["sha256"] = "0" * 64
    if fault == "path":
        value["path"] = "../executor-query"
    pin.write_text(json.dumps(value), encoding="ascii")
    if fault == "missing":
        pin.unlink()
    if fault in ("malformed", "shape"):
        pin.write_text("{" if fault == "malformed" else "[]", encoding="ascii")
    if fault == "symlink":
        destination.rename(destination.with_name("linked"))
        destination.symlink_to(destination.with_name("linked"))
    if fault == "not-executable":
        destination.chmod(0o600)
    cli = home / "tools/mir_executor/cli.py"
    text = cli.read_text()
    position = text.index("\n", text.index("from __future__ import annotations"))
    cli.write_text(
        text[:position] + "\nfrom pathlib import Path as _FixturePath\n"
        '_FixturePath(__file__).resolve().parents[2].joinpath("forwarded").touch()\n'
        + text[position:]
    )


def git(home, *args):
    return subprocess.check_output(["git", "-C", str(home), *args], stderr=subprocess.PIPE).decode()


def normalize(text, home):
    diagnostics = home / "provider-diagnostics"
    if diagnostics.exists():
        for line in diagnostics.read_text().splitlines():
            row = json.loads(line)
            raw = row["stderr"]
            signature = row["error_sig"]
            tail = "\n".join(raw.splitlines()[-20:])
            if signature and signature == hashlib.sha256(tail.encode()).hexdigest()[:12]:
                canonical = re.sub(r"timed out after [\d.eE+-]+s", "timed out after <clock>s", tail)
                canonical = canonical.replace(str(home), "<root>")
                text = text.replace(signature, hashlib.sha256(canonical.encode()).hexdigest()[:12])
    text = re.sub(r"timed out after [\d.eE+-]+s", "timed out after <clock>s", text)
    text = text.replace(str(home), "<root>").replace(str(Path(sys.executable)), "<python>")
    text = re.sub(r'mir-wt-[^/\\\s"\']+', "mir-wt-<temp>", text)
    text = re.sub(r"mir-verify-[^/\s\"']+", "mir-verify-<temp>", text)
    text = re.sub(r"\b[0-9a-f]{32}\b", "<id>", text)
    text = re.sub(r"\b[0-9a-f]{40}\b", "<commit>", text)
    text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)", "<timestamp>", text)
    return re.sub(
        r'("(?:duration_s|elapsed_seconds|duration_seconds)":\s*)[\d.eE+-]+',
        r'\1"<duration>"',
        text,
    )


def snapshot(home):
    files = {}
    ignored = {"tools", ".git", "config", "fake-bin", "__pycache__", "codex-home"}
    seeds = {
        "server.py",
        "fake-codex",
        "fake-claude",
        "claude-server.py",
        "offline-policy.json",
        "prompt.txt",
        "forwarded",
        "native-owned",
        "native-imported",
    }
    for path in sorted(home.rglob("*")):
        relative = path.relative_to(home)
        if relative.as_posix() == ".mir" or relative.parts[:2] in {
            (".mir", "bin"),
            (".mir", "owned-receipt"),
        }:
            continue
        if any(part in ignored for part in relative.parts) or relative.parts[0] in seeds:
            continue
        if path.is_symlink():
            files[relative.as_posix()] = {"link": normalize(os.readlink(path), home)}
        elif path.is_dir():
            files[normalize(relative.as_posix(), home)] = {
                "directory_mode": oct(stat.S_IMODE(path.stat().st_mode))
            }
        elif path.is_file():
            mode = stat.S_IMODE(path.stat().st_mode)
            try:
                raw = path.read_bytes()
            except PermissionError:
                path.chmod(mode | 0o400)
                raw = path.read_bytes()
                path.chmod(mode)
            item = {"mode": oct(mode)}
            if raw.startswith(b"SQLite format 3\x00") and path.suffix == ".db":
                with sqlite3.connect(path) as db:
                    tables = [
                        row[0]
                        for row in db.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                        )
                    ]
                    db.row_factory = sqlite3.Row
                    item["tables"] = {
                        table: [
                            dict(row)
                            for row in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
                        ]
                        for table in tables
                    }
                    if not any(item["tables"].values()):
                        item["hex"] = (raw[:96] + b"\x00" * 4 + raw[100:]).hex()
            else:
                try:
                    item["hex"] = normalize(raw.decode("utf-8"), home).encode().hex()
                except UnicodeDecodeError:
                    item["hex"] = raw.hex()
            files[normalize(relative.as_posix(), home)] = item
    commits = [
        line.split("\0")
        for line in git(home, "log", "--all", "--format=%H%x00%P%x00%s").splitlines()
    ]
    subjects = {row[0]: normalize(row[2], home) for row in commits}
    graph = sorted(
        [
            {
                "subject": subjects[row[0]],
                "parents": [subjects.get(parent, "<external>") for parent in row[1].split()],
            }
            for row in commits
        ],
        key=lambda row: json.dumps(row, sort_keys=True),
    )
    refs = {
        normalize(line.split(" ", 1)[0], home): subjects.get(line.split(" ", 1)[1])
        for line in git(
            home, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads"
        ).splitlines()
    }

    def project(value, key=""):
        if isinstance(value, dict):
            return {normalize(k, home): project(v, k) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [project(v) for v in value]
        if isinstance(value, str):
            # File bytes were normalized BEFORE hex encoding. A 16-byte file's
            # 32-digit hex must never be mistaken for a generated UUID.
            return value if key == "hex" else normalize(value, home)
        if key in {"duration_s", "elapsed_seconds", "duration_seconds"} and value is not None:
            return "<duration>"
        return value

    return project(
        {
            "files": files,
            "worktrees": git(home, "worktree", "list", "--porcelain"),
            "branches": git(home, "branch", "--format=%(refname:short)"),
            "diff": git(home, "diff", "HEAD"),
            "status": git(home, "status", "--porcelain"),
            "commit_graph": graph,
            "branch_commits": refs,
        }
    )


def capture(home, case, setup, route="reference", binary=None):
    _, env, argv = setup
    command = [sys.executable, "-c", "from tools.mir_executor.cli import main; main()"]
    if route == "module":
        command = [sys.executable, "-m", "tools.mir_executor"]
    elif route == "binary":
        command = [str(binary), "--home-root", str(home)]
        receipt = home / ".mir" / "owned-receipt"
        receipt.mkdir(parents=True, mode=0o700)
        env = dict(env, MIR_EXECUTOR_OWNED_RECEIPT=str(receipt / "receipt"))
    lock = None
    if case.get("db") == "locked":
        lock = sqlite3.connect(home / "tasks/jobs.db")
        lock.execute("BEGIN EXCLUSIVE")
    try:
        process = subprocess.Popen(
            [*command, *argv],
            cwd=home,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=40)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    finally:
        if lock:
            lock.rollback()
            lock.close()
    code = process.returncode
    (home.parent / (home.name + ".stdout")).write_bytes(stdout)
    (home.parent / (home.name + ".stderr")).write_bytes(stderr)
    if b"Traceback (most recent call last):" in stderr:
        code, stderr = 1, stderr.splitlines()[-1] + b"\n"
    result = {
        "exit": code,
        "stdout_hex": normalize(stdout.decode("utf-8", "surrogateescape"), home)
        .encode("utf-8", "surrogateescape")
        .hex(),
        "stderr_hex": normalize(stderr.decode("utf-8", "surrogateescape"), home)
        .encode("utf-8", "surrogateescape")
        .hex(),
        "effects": snapshot(home),
    }
    receipt = home / ".mir/owned-receipt/receipt"
    routing = {
        "forwarded": (home / "forwarded").exists(),
        "owned": (home / "native-owned").exists()
        or (receipt.exists() and receipt.read_bytes() == b"owned"),
    }
    (home.parent / (home.name + ".capture.json")).write_text(
        json.dumps(
            {"name": case["name"], "route": route, "actual": result, **routing},
            ensure_ascii=True,
            indent=2,
        )
        + "\n"
    )
    return result, routing


def first_difference(expected, actual, prefix=""):
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(expected.keys() | actual.keys()):
            if key not in expected or key not in actual:
                return {
                    "field": prefix + "/" + key,
                    "byte": 0,
                    "expected_size": len(json.dumps(expected.get(key))),
                    "actual_size": len(json.dumps(actual.get(key))),
                }
            found = first_difference(expected[key], actual[key], prefix + "/" + key)
            if found:
                return found
        return None
    if expected == actual:
        return None

    def encode(value):
        if prefix.endswith(("_hex", "/hex")) and isinstance(value, str):
            return bytes.fromhex(value)
        return json.dumps(value, ensure_ascii=True, sort_keys=True).encode()

    left, right = encode(expected), encode(actual)
    offset = next(
        (i for i, pair in enumerate(zip(left, right, strict=False)) if pair[0] != pair[1]),
        min(len(left), len(right)),
    )
    return {
        "field": prefix,
        "byte": offset,
        "expected_size": len(left),
        "actual_size": len(right),
        "expected_byte": left[offset : offset + 1].hex(),
        "actual_byte": right[offset : offset + 1].hex(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--only", help="Comma-separated probe names; never writes frozen output")
    parser.add_argument(
        "--routes",
        default="binary,module",
        help="Comparison routes, including reference for oracle repeatability",
    )
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    reference = scratch / "reference"
    archive_sha256 = DIRECT["STATUS"].archive_reference(reference)
    database = scratch / "template.db"
    DIRECT["STATUS"].template(reference, database)
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM jobs")
    golden = json.loads(OUTPUT.read_text()) if args.compare else None
    records, results = [], []
    selected = [case for case in CASES if not args.only or case["name"] in args.only.split(",")]
    for case in selected:
        if args.compare:
            expected = next(
                row["expected"] for row in golden["cases"] if row["name"] == case["name"]
            )
            record = next(row for row in golden["cases"] if row["name"] == case["name"])
            for route in args.routes.split(","):
                expected = record.get("expected_by_route", {}).get(route, record["expected"])
                home = scratch / route / case["name"]
                setup = seed(home, case, reference, database, args.compare)
                actual, routing = capture(home, case, setup, route, args.compare)
                difference = first_difference(expected, actual)
                status = (
                    "forwarded"
                    if routing["forwarded"]
                    else "declined"
                    if actual["exit"] == 64 and not routing["owned"]
                    else "differs"
                    if difference
                    else "native-equal"
                )
                results.append(
                    {
                        "name": case["name"],
                        "route": route,
                        "status": status,
                        "difference": difference,
                        "actual": actual,
                        **routing,
                    }
                )
                print(case["name"], route, status, json.dumps(difference), flush=True)
        else:
            home = scratch / "cases" / case["name"]
            setup = seed(home, case, reference, database)
            expected, _ = capture(home, case, setup)
            record = {**case, "expected": expected}
            if any(
                b"usage:" in bytes.fromhex(expected[key]) for key in ("stdout_hex", "stderr_hex")
            ):
                module_home = scratch / "module-cases" / case["name"]
                module_setup = seed(module_home, case, reference, database)
                record["expected_by_route"] = {
                    "module": capture(module_home, case, module_setup, "module")[0]
                }
            records.append(record)
            print(case["name"], expected["exit"], flush=True)
    if args.compare:
        (scratch / "results.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=True) + "\n"
        )
        return int(any(row["difference"] for row in results))
    output = {
        "reference": PIN,
        "archive_sha256": archive_sha256,
        "exception_protocol": "exit 1; preserve raw stdout; traceback final stderr line",
        "cases": records,
    }
    destination = scratch / "probe.json" if args.only else OUTPUT
    destination.write_text(
        json.dumps(output, indent=2, ensure_ascii=True, sort_keys=True) + "\n", encoding="ascii"
    )
    (scratch / "provenance.json").write_text(
        json.dumps(
            {
                "reference": PIN,
                "archive_sha256": archive_sha256,
                "python": sys.version,
                "sqlite": sqlite3.sqlite_version,
                "fixture_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
