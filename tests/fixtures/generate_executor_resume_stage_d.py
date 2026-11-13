"""Offline resume oracle at the dispatch reference pin; synthetic providers only.

Regenerate: python tests/fixtures/generate_executor_resume_stage_d.py --scratch NEW
Compare: add --compare native/handoff-packet/target/release/executor-query
"""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import shutil
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = runpy.run_path(str(HERE / "generate_executor_dispatch_stage_d.py"))
PIN = D["PIN"]
OUTPUT = HERE / "executor_resume_stage_d.json"


def cases():
    # Dispatch faults exercise the exact reused provider/finalization boundaries.
    values = [
        {"name": "dispatch-" + c["name"], "dispatch": c}
        for c in D["CASES"]
        if not c["name"].startswith(("argv-", "selector-", "pin-", "db-"))
    ]
    values += [
        {"name": n}
        for n in (
            "v2",
            "legacy",
            "missing-job",
            "missing-brief-path",
            "empty-brief-path",
            "state-running",
            "state-completed",
            "state-failed",
            "state-cancelled",
            "cancel-requested",
            "stale-lease",
            "saved-worktree-present",
            "saved-worktree-gone",
            "saved-branch-gone",
            "saved-root-gone",
            "saved-root-file",
            "saved-backend-invalid",
            "options-malformed",
            "options-array",
            "options-null",
            "options-empty",
            "options-digest-missing",
            "options-digest-invalid",
            "options-brief-number",
            "options-path-number",
            "options-timeout-invalid",
            "options-unknown-extension",
            "options-allow-null",
            "options-verify-null",
            "options-backend-invalid",
            "timeout-override",
            "timeout-saved",
            "timeout-range",
            "brief-changed",
            "brief-relative",
            "ledger-valid",
            "ledger-missing",
            "ledger-malformed",
            "ledger-array",
            "ledger-entry-missing",
            "ledger-category-missing",
            "ledger-readonly",
            "ledger-revalidation",
            "crossroot-saved",
            "crossroot-explicit",
            "crossroot-denied",
            "config-malformed",
            "config-array",
            "local-source-directory",
            "native-policy-invalid",
            "native-policy-base",
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
        "update-abort",
        "symlink",
        "parent-file",
    ):
        values.append({"name": "db-" + kind, "db": kind})
    for key in (
        "MIR_EXECUTOR_IMPL",
        "MIR_EXECUTOR_RESUME_IMPL",
        "MIR_EXECUTOR_EXECUTE_IMPL",
        "MIR_EXECUTOR_DISPATCH_IMPL",
        "MIR_EXECUTOR_QUERY_IMPL",
        "MIR_NATIVE_HOOKS",
    ):
        for value in ("python", "native", "0", "invalid"):
            values.append({"name": f"selector-{key}-{value}", "env": {key: value}})
    for kind in ("missing", "malformed", "shape", "digest", "path", "symlink", "not-executable"):
        values.append({"name": "pin-" + kind, "pin": kind})
    for name, argv in (
        ("help", ["resume", "--help"]),
        ("missing-id", ["resume"]),
        ("missing-value", ["resume", "--job-id"]),
        ("unknown", ["resume", "--job-id=x", "--unknown"]),
        ("end-options", ["resume", "--job-id=x", "--"]),
        ("negative-id", ["resume", "--job-id", "-1"]),
        ("empty-id", ["resume", "--job-id="]),
        ("nonutf8-id", ["resume", "--job-id=bad-\udcff"]),
        ("unicode-id", ["resume", "--job-id=\ud55c\uae00"]),
        ("duplicate-id", ["resume", "--job-id=absent", "--job-id=resume-fixture"]),
        ("abbreviation", ["resume", "--job-i=resume-fixture"]),
        ("bad-timeout", ["resume", "--job-id=resume-fixture", "--timeout=bad"]),
        ("negative-timeout", ["resume", "--job-id=resume-fixture", "--timeout=-1"]),
        ("async", ["resume", "--job-id=resume-fixture", "--async"]),
        ("root-missing", ["resume", "--job-id=resume-fixture", "--repo-root=<ROOT>/gone"]),
        ("root-file", ["resume", "--job-id=resume-fixture", "--repo-root=<ROOT>/code.txt"]),
        ("leading-db", ["--jobs-db=<ROOT>/tasks/jobs.db", "resume", "--job-id=resume-fixture"]),
        ("trailing-db", ["resume", "--job-id=resume-fixture", "--jobs-db=tasks/jobs.db"]),
        (
            "db-dot-path",
            ["--jobs-db=<ROOT>/tasks/../tasks/jobs.db", "resume", "--job-id=resume-fixture"],
        ),
    ):
        values.append({"name": "argv-" + name, "argv": argv})
    return values


CASES = cases()


def capture(home, case, setup, route="reference", binary=None):
    # Resume's facade can wait for native admission and Python registry locks
    # sequentially. Keep both observable instead of timing out the harness.
    return D["capture"](home, case, setup, route, binary, timeout=90)


@D["isolated_git_environment"]()
def seed(home, case, reference, database, binary=None):
    dispatch = case.get("dispatch", {"name": "success"})
    setup = D["seed"](home, dispatch, reference, database)
    launcher, env, execute = setup
    env.update(case.get("env", {}))
    brief = home / "brief.json"
    # Dispatch argv values become persisted v2 options, rather than resume flags.
    options = {
        "dispatch_brief": str(brief),
        "brief_sha256": hashlib.sha256(
            brief.read_bytes() if brief.is_file() else b"missing"
        ).hexdigest(),
        "allow_paths": [],
        "verify_cmds": [],
        "expect_changes": "--no-expect-changes" not in execute,
    }
    mapping = {
        "--model": "model",
        "--reasoning-effort": "reasoning_effort",
        "--execution-backend": "execution_backend",
        "--artifacts-dir": "artifacts_dir",
        "--timeout": "timeout",
        "--max-codex-attempts": "max_codex_attempts",
        "--finalize-lock-timeout": "finalize_lock_timeout",
        "--stall-timeout": "stall_timeout",
    }
    for i, arg in enumerate(execute):
        flag, sep, inline = arg.partition("=")
        if flag in mapping or flag in ("--allow-path", "--verify-cmd"):
            value = inline if sep else execute[i + 1]
            if flag == "--allow-path":
                options["allow_paths"].append(value)
            elif flag == "--verify-cmd":
                options["verify_cmds"].append(value)
            else:
                options[mapping[flag]] = (
                    float(value)
                    if flag in ("--finalize-lock-timeout", "--stall-timeout")
                    else int(value)
                    if flag in ("--timeout", "--max-codex-attempts")
                    else value
                )
    db = home / "tasks/jobs.db"
    shutil.copyfile(database, db)
    row = dict(
        job_id="resume-fixture",
        change_id="old-dispatch",
        category="unit",
        family=None,
        repo_root=str(home),
        codex_args='["offline fixture"]',
        timeout_seconds=60,
        status="failed",
        started_at="2000-01-01T00:00:00Z",
        cancel_requested=0,
        dispatch_brief_path=str(brief),
        execution_backend="codex",
        resolved_model="offline-fixture",
        resolved_reasoning_effort="medium",
        allow_harness_self_modify=0,
        resume_count=0,
    )
    argv = ["resume", "--job-id=resume-fixture"]
    name = case["name"]
    config = home / "config/mir-executor.local.json"
    if name in ("config-malformed", "config-array"):
        config.write_text("{" if name == "config-malformed" else "[]")
    if name in ("native-policy-invalid", "native-policy-base"):
        value = json.loads(config.read_text())
        value["native_policy"] = (
            {"version": 2}
            if name == "native-policy-invalid"
            else {"version": 1, "brief_profile": {"name": "base_v1"}}
        )
        value["python_local_hooks"] = False
        config.write_text(json.dumps(value))
    if name == "local-source-directory":
        local = home / "tools/mir_executor/local.py"
        local.unlink()
        local.mkdir()
    if name.startswith("state-"):
        row["status"] = name.removeprefix("state-")
    if name == "cancel-requested":
        row["cancel_requested"] = 1
    if name in (
        "stale-lease",
        "saved-worktree-present",
        "saved-worktree-gone",
        "saved-branch-gone",
    ):
        path = home / "saved-worktree"
        D["git"](home, "worktree", "add", "-qb", "mir-dispatch/saved", str(path))
        row["ai_run_metadata"] = json.dumps(
            {
                "worktree_path": str(path),
                "branch": "mir-dispatch/saved",
                "lease_expires_at": "2000-01-01T00:00:00Z",
            }
        )
        row["status"] = "running"
        if name in ("saved-worktree-gone", "saved-branch-gone"):
            D["git"](home, "worktree", "remove", str(path))
        if name == "saved-branch-gone":
            D["git"](home, "branch", "-D", "mir-dispatch/saved")
    if name in ("saved-root-gone", "saved-root-file"):
        row["repo_root"] = str(home / ("gone" if name.endswith("gone") else "code.txt"))
    if name == "saved-backend-invalid":
        row["execution_backend"] = "invalid"
    if name in ("missing-brief-path", "empty-brief-path"):
        row["dispatch_brief_path"] = None if name.startswith("missing") else ""
    if name == "brief-changed":
        brief.write_text('{"expanded_goal":"changed"}')
    if name == "brief-relative":
        options["dispatch_brief"] = "brief.json"
    if name == "timeout-override":
        options["timeout"] = 0
        argv += ["--timeout=60"]
    if name == "timeout-saved":
        options["timeout"] = 61
    if name in ("timeout-range", "options-timeout-invalid"):
        config = home / "config/mir-executor.local.json"
        value = json.loads(config.read_text())
        value["timeout_seconds_range"] = [1, 120]
        config.write_text(json.dumps(value))
        options["timeout"] = -1 if name == "timeout-range" else "bad"
    option_faults = {
        "options-digest-missing": ("brief_sha256", None),
        "options-digest-invalid": ("brief_sha256", "0" * 64),
        "options-brief-number": ("dispatch_brief", 7),
        "options-path-number": ("artifacts_dir", 7),
        "options-unknown-extension": ("extension", {"keep": True}),
        "options-allow-null": ("allow_paths", None),
        "options-verify-null": ("verify_cmds", None),
        "options-backend-invalid": ("execution_backend", "invalid"),
    }
    if name in option_faults:
        key, value = option_faults[name]
        options[key] = value
    if name.startswith("ledger-"):
        options.update(change_id="fixture", category="unit")
        ledger = home / "tasks/tdd.json"
        if name == "ledger-missing":
            ledger.unlink()
        elif name in (
            "ledger-malformed",
            "ledger-array",
            "ledger-entry-missing",
            "ledger-category-missing",
        ):
            ledger.write_text(
                {
                    "ledger-malformed": "{",
                    "ledger-array": "[]",
                    "ledger-entry-missing": '{"changes":[]}',
                    "ledger-category-missing": '{"changes":[{"id":"fixture","categories":{}}]}',
                }[name]
            )
        elif name == "ledger-readonly":
            ledger.chmod(0o400)
        elif name == "ledger-revalidation":
            with (home / "tools/mir_executor/local.py").open("a") as stream:
                stream.write(
                    "\ndef after_provider_call(result, metadata):\n"
                    '    path = ROOT / "tasks/tdd.json"\n'
                    "    data = json.loads(path.read_text())\n"
                    '    data["changes"][0]["categories"]["unit"]["status"] = "not_applicable"\n'
                    "    path.write_text(json.dumps(data))\n"
                )
    if name.startswith("crossroot-"):
        target = home / "target"
        D["seed"](target, {"name": "success"}, reference, database)
        row["repo_root"] = str(target)
        options["dispatch_brief"] = str(target / "brief.json")
        options["brief_sha256"] = hashlib.sha256((target / "brief.json").read_bytes()).hexdigest()
        options["artifacts_dir"] = str(target / "artifacts")
        if name == "crossroot-explicit":
            argv = ["--jobs-db=" + str(db), *argv, "--repo-root", str(target)]
        if name == "crossroot-denied":
            with (home / "tools/mir_executor/local.py").open("a") as stream:
                stream.write(
                    "\ndef authorize_target(*args):\n"
                    '    raise ValueError("offline target denied")\n'
                )
    if dispatch["name"].startswith("crossroot"):
        row["repo_root"] = str(home / "target")
    raw_options = {
        "legacy": None,
        "options-malformed": "{",
        "options-array": "[]",
        "options-null": "null",
        "options-empty": "{}",
    }
    row["dispatch_options_json"] = raw_options.get(name, json.dumps(options))
    with sqlite3.connect(db) as connection:
        if name != "missing-job" and case.get("db") != "wrong-schema":
            columns = ",".join(row)
            connection.execute(
                f"INSERT INTO jobs ({columns}) VALUES ({','.join('?' for _ in row)})",
                list(row.values()),
            )
        if case.get("db") == "wrong-schema":
            connection.execute("DROP TABLE jobs")
            connection.execute("CREATE TABLE jobs(unexpected TEXT)")
        if case.get("db") == "update-abort":
            connection.execute(
                "CREATE TRIGGER fixture BEFORE UPDATE ON jobs "
                "BEGIN SELECT RAISE(ABORT,'offline fault'); END"
            )
    kind = case.get("db")
    if kind == "missing":
        db.unlink()
    elif kind == "corrupt":
        db.write_bytes(b"offline corrupt database\n")
    elif kind == "directory":
        db.unlink()
        db.mkdir()
    elif kind == "readonly":
        db.chmod(0o400)
    elif kind == "readonly-directory":
        db.parent.chmod(0o500)
    elif kind == "symlink":
        db.rename(db.with_name("linked.db"))
        db.symlink_to(db.with_name("linked.db"))
    elif kind == "parent-file":
        (home / "blocker").write_text("blocker")
        argv = ["--jobs-db=" + str(home / "blocker/jobs.db"), *argv]
    argv = [arg.replace("<ROOT>", str(home)) for arg in case.get("argv", argv)]
    if binary:
        D["install"](home, binary, case.get("pin"))
    return launcher, env, argv


@D["isolated_git_environment"]()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--only")
    parser.add_argument("--routes", default="binary,module")
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    reference = scratch / "reference"
    digest = D["DIRECT"]["STATUS"].archive_reference(reference)
    database = scratch / "template.db"
    D["DIRECT"]["STATUS"].template(reference, database)
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM jobs")
    golden = json.loads(OUTPUT.read_text()) if args.compare else None
    records, results = [], []
    for case in CASES:
        if args.only and case["name"] not in args.only.split(","):
            continue
        if args.compare:
            record = next(c for c in golden["cases"] if c["name"] == case["name"])
            for route in args.routes.split(","):
                home = scratch / route / case["name"]
                setup = seed(home, case, reference, database, args.compare.resolve())
                actual, routing = capture(home, case, setup, route, args.compare.resolve())
                expected = record.get("expected_by_route", {}).get(route, record["expected"])
                difference = D["first_difference"](expected, actual)
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
                    dict(
                        name=case["name"],
                        route=route,
                        status=status,
                        difference=difference,
                        actual=actual,
                        **routing,
                    )
                )
                print(case["name"], route, status, json.dumps(difference), flush=True)
        else:
            home = scratch / "cases" / case["name"]
            expected, _ = capture(home, case, seed(home, case, reference, database))
            record = dict(case, expected=expected)
            if any(b"usage:" in bytes.fromhex(expected[k]) for k in ("stdout_hex", "stderr_hex")):
                home = scratch / "module-cases" / case["name"]
                record["expected_by_route"] = {
                    "module": capture(home, case, seed(home, case, reference, database), "module")[
                        0
                    ]
                }
            records.append(record)
            print(case["name"], expected["exit"], flush=True)
    destination = (
        scratch / "results.json"
        if args.compare
        else scratch / "probe.json"
        if args.only
        else OUTPUT
    )
    payload = (
        results
        if args.compare
        else dict(
            reference=PIN,
            archive_sha256=digest,
            exception_protocol="exit 1; preserve raw stdout; traceback final stderr line",
            cases=records,
        )
    )
    destination.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    (scratch / "provenance.json").write_text(
        json.dumps(
            dict(
                reference=PIN,
                archive_sha256=digest,
                fixture_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                sqlite=sqlite3.sqlite_version,
                python=sys.version,
            ),
            indent=2,
        )
        + "\n"
    )
    return int(bool(args.compare) and any(row["difference"] for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
