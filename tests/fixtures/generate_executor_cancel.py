"""Freeze cancel from the pinned Python console reference, using shared oracles.

Regenerate with --scratch pointing to a new disposable synthetic directory.
Cancel is flag-only: clocks, process signalling, leases and receipts are untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def load(name):
    spec = importlib.util.spec_from_file_location(
        "cancel_" + name, Path(__file__).with_name("generate_executor_" + name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = load("status")
CROSS = load("crossroot")
PIN = "01de3ba9dfa0f1a4ff4017fc8164d8cc71878bf6"
SUPPORT.PIN = PIN
SUPPORT.BASE_ARGV = ["cancel", "--job-id", "fixture"]
SUPPORT.SELECTORS = (*SUPPORT.SELECTORS, "MIR_EXECUTOR_CANCEL_IMPL")
CASES = SUPPORT.cases()
for case in CASES:
    if "argv" in case:
        case["argv"] = ["cancel" if arg == "status" else arg for arg in case["argv"]]
CASES.extend([
    {"name": "locked-db", "locked": True},
    {"name": "readonly-mode", "readonly": True},
    {"name": "readonly-directory", "readonly_directory": True},
    {"name": "other-root-row", "update": ["repo_root", "/synthetic-other-root"]},
    {"name": "cancel-flag-zero", "update": ["cancel_requested", 0]},
    {"name": "cancel-flag-null", "nullable_cancel": True},
    {"name": "cancel-no-column", "drop_cancel": True},
    {"name": "cancel-update-failure", "trigger": "abort"},
    {"name": "cancel-after-fail", "trigger": "after_fail",
     "update": ["cancel_requested", 0]},
    {"name": "cancel-before-fail", "trigger": "before_fail",
     "update": ["cancel_requested", 0]},
    {"name": "cancel-before-rollback", "trigger": "rollback",
     "update": ["cancel_requested", 0]},
    {"name": "cancel-ignore-side-effect", "trigger": "ignore_side_effect",
     "update": ["cancel_requested", 0]},
    {"name": "cancel-trigger-ignore", "trigger": "ignore"},
    {"name": "cancel-trigger-timestamp", "trigger": "timestamp"},
    {"name": "cancel-duplicate-rows", "duplicate": True},
    {"name": "cancel-invalid-utf8-row", "invalid_text": True},
    {"name": "unicode-existing-id", "update": ["job_id", "job-\u754c"],
     "argv": ["cancel", "--job-id=job-\u754c"]},
    {"name": "ascii-existing-id", "update": ["job_id", "job-\u754c"],
     "argv": ["cancel", "--job-id=job-\u754c"],
     "env": {"PYTHONIOENCODING": "ascii:strict"}},
])
for state in ("queued", "running", "completed", "finished", "failed", "cancelled"):
    CASES.append({"name": "state-" + state, "update": ["status", state]})
for name, argv in (
    ("unsupported-format", ["cancel", "--job-id=fixture", "--format=json"]),
    ("unsupported-json", ["cancel", "--job-id=fixture", "--json"]),
    ("parent-db", ["--jobs-db=missing/../tasks/jobs.db", "cancel", "--job-id=fixture"]),
    ("trailing-db-slash", ["--jobs-db=tasks/jobs.db/", "cancel", "--job-id=fixture"]),
    ("unicode-id", ["cancel", "--job-id=job-\u754c"]),
    ("ascii-unicode-id", ["cancel", "--job-id=job-\u754c"]),
):
    CASES.append({"name": name, "argv": argv})
CASES[-1]["env"] = {"PYTHONIOENCODING": "ascii:strict"}
for pid in ("live", "dead", "reused"):
    for delivery in ("success", "ESRCH", "EPERM"):
        CASES.append({"name": f"pid-{pid}-{delivery}", "process": pid, "delivery": delivery})
for receipt in ("absent", "existing", "invalid-parent"):
    CASES.append({"name": "receipt-" + receipt, "receipt": receipt,
                  "env": {"MIR_EXECUTOR_OWNED_RECEIPT": "tasks/cancel-receipt"}})
for original in CROSS.CASES:
    if original["command"] == "status":
        case = {**original, "name": original["name"].replace("status", "crossroot"),
                "command": "cancel", "crossroot": True,
                "argv": ["cancel" if arg == "status" else arg for arg in original["argv"]]}
        CASES.append(case)
OUTPUT = Path(__file__).with_name("executor_cancel.json")


def seed(home, case, database):
    if case.get("crossroot"):
        CROSS.seed(home, case, database)
        return home / "tasks/jobs.db"
    path = SUPPORT.seed(home, case, database)
    if case.get("name", "").startswith("state-"):
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE jobs SET cancel_requested=0")
    if any(case.get(key) for key in (
            "nullable_cancel", "drop_cancel", "trigger", "duplicate", "invalid_text")):
        with sqlite3.connect(path) as connection:
            if case.get("nullable_cancel") or case.get("duplicate"):
                # CTAS deliberately removes affinities/constraints like a foreign schema.
                connection.execute("ALTER TABLE jobs RENAME TO previous")
                connection.execute("CREATE TABLE jobs AS SELECT * FROM previous")
                connection.execute("DROP TABLE previous")
                connection.execute("CREATE INDEX idx_jobs_status ON jobs(status)")
                if case.get("duplicate"):
                    connection.execute("INSERT INTO jobs SELECT * FROM jobs")
                else:
                    connection.execute("UPDATE jobs SET cancel_requested=NULL")
            if case.get("drop_cancel"):
                connection.execute("ALTER TABLE jobs DROP COLUMN cancel_requested")
            if case.get("invalid_text"):
                connection.execute("UPDATE jobs SET codex_args=CAST(X'ff00' AS TEXT)")
            if case.get("trigger"):
                body = {"abort": "SELECT RAISE(ABORT, 'cancel fixture refused');",
                        "ignore": "SELECT RAISE(IGNORE);",
                        "after_fail": "SELECT RAISE(FAIL, 'review after failure');",
                        "before_fail": "UPDATE jobs SET resume_count=77; "
                                       "SELECT RAISE(FAIL, 'review before failure');",
                        "rollback": "UPDATE jobs SET resume_count=77; "
                                    "SELECT RAISE(ROLLBACK, 'review rollback');",
                        "ignore_side_effect": "UPDATE jobs SET resume_count=77; "
                                              "SELECT RAISE(IGNORE);",
                        "timestamp": "UPDATE jobs SET completed_at='clock-seam' "
                                     "WHERE job_id=NEW.job_id;"}
                timing = "AFTER" if case["trigger"] == "after_fail" else "BEFORE"
                connection.execute(f"CREATE TRIGGER cancel_fixture {timing} "
                                   "UPDATE OF cancel_requested ON jobs BEGIN "
                                   + body[case["trigger"]] + " END")
    if case.get("readonly"):
        path.chmod(0o400)
    if case.get("readonly_directory"):
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE jobs SET cancel_requested=0")
        path.parent.chmod(0o500)
    if case.get("process"):
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE jobs SET status='running', cancel_requested=0")
        (home / "tasks/worker.lease").write_text("synthetic lease\n", encoding="ascii")
        (home / "tasks/worker.lock").write_text("synthetic lock\n", encoding="ascii")
    if case.get("receipt") == "existing":
        (home / "tasks/cancel-receipt").write_bytes(b"existing receipt\n")
    if case.get("receipt") == "invalid-parent":
        (home / "tasks/cancel-receipt").mkdir()
    return path


def capture(home, case, command):
    if case.get("crossroot"):
        return CROSS.capture(home, case, command)
    connection = None
    child = None
    try:
        if case.get("process"):
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                     cwd=home, env=SUPPORT.environment(home, case))
            if case["process"] == "dead":
                child.terminate()
                child.wait(timeout=5)
            # Store only synthetic identity; cancel must neither inspect nor signal it.
            (home / "tasks/worker.pid").write_text(str(child.pid), encoding="ascii")
            with sqlite3.connect(home / "tasks/jobs.db") as db:
                db.execute("UPDATE jobs SET dispatch_options_json=?", (json.dumps({
                    "pid": child.pid, "identity": case["process"],
                    "signal_result": case["delivery"]}),))
        if case.get("locked"):
            connection = sqlite3.connect(home / "tasks/jobs.db")
            connection.execute("BEGIN EXCLUSIVE")
        # A reference-only seam proves cancel does not consult clock or signal APIs.
        if "-c" in command:
            command = [*command[:-1], "import os; from tools.mir_executor import cli; "
                       "def_forbidden = lambda *a, **k: (_ for _ in ()).throw("
                       "AssertionError('cancel called clock or signal')); "
                       "cli._utc_now = def_forbidden; os.kill = def_forbidden; cli.main()"]
        # The shared snapshot runs after the lock is released.
        original = SUPPORT.snapshot
        def unlocked_snapshot(path):
            if connection is not None:
                connection.rollback()
            return original(path)
        SUPPORT.snapshot = unlocked_snapshot
        try:
            actual = SUPPORT.capture(home, case, command)
        finally:
            SUPPORT.snapshot = original
        if child is not None:
            actual["child_alive"] = child.poll() is None
            storage = actual["storage"]
            storage["tasks/worker.pid"]["bytes"] = b"<CHILD_PID>".hex()
            for row in storage["tasks/jobs.db"]["tables"]["jobs"]["rows"]:
                for index, value in enumerate(row):
                    if isinstance(value, str) and '"pid":' in value:
                        row[index] = value.replace(str(child.pid), "<CHILD_PID>")
        return actual
    finally:
        if connection is not None:
            connection.close()
        if child is not None:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)


install_local_hook = SUPPORT.install_local_hook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    if scratch.exists():
        parser.error("scratch must be new")
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
        install_local_hook(home, case)
        command = [sys.executable, "-c", "from tools.mir_executor.cli import main; main()"]
        record = {**case, "expected": capture(home, case, command)}
        if case.get("root_program"):
            record["expected_by_route"] = {
                "binary": record["expected"],
                "module": capture(home, case, [sys.executable, "-m", "tools.mir_executor"]),
            }
        records.append(record)
    OUTPUT.write_text(json.dumps({
        "reference": PIN, "archive_sha256": digest,
        "entrypoint": "tools.mir_executor.cli.main (direct console call)",
        "exception_protocol": "exit 1; empty stdout; traceback final stderr line",
        "cases": records,
    }, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="ascii")
    (scratch / "provenance.json").write_text(json.dumps({
        "reference": PIN, "archive_sha256": digest, "python": sys.version,
        "fixture_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
    }, indent=2) + "\n", encoding="ascii")
    print(f"Captured {len(records)} cases from {PIN}")


if __name__ == "__main__":
    main()
