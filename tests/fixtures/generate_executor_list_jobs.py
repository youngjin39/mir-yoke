"""Freeze list-jobs using only the archived, pinned Python console reference.

Regenerate: set MIR_EXECUTOR_LIST_JOBS_SCRATCH to a new directory, then run
python tests/fixtures/generate_executor_list_jobs.py.
"""
import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "list_jobs_oracle_support", Path(__file__).with_name("generate_executor_status.py"))
SUPPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUPPORT)
SUPPORT.PIN = "9ce2c2efcf10862b907f7c801b8ff40a9dbfb04f"
SUPPORT.OUTPUT = Path(__file__).with_name("executor_list_jobs.json")
SUPPORT.BASE_ARGV = ["list-jobs"]
SUPPORT.SELECTORS = (*SUPPORT.SELECTORS, "MIR_EXECUTOR_LIST_JOBS_IMPL")
# Preserve shared parser, codec, storage, JSON and admission probes. Identifier
# syntax belongs to status/result; list-jobs has no job identifier argument.
CASES = []
for original in SUPPORT.cases():
    case = dict(original)
    if any("id" in item for item in case.get("argv", []) if item.startswith("--job")):
        if case["name"] not in {"help", "short-help", "unknown", "end-options",
                                "unknown-global-flag", "global-help", "leading-repo-root",
                                "leading-end-options", "help-explicit-value",
                                "help-abbreviation-value", "help-short-cluster",
                                "global-db-abbreviation", "duplicate-db", "trailing-db"} and not (
                case["name"].startswith(("legacy-", "repo-root-", "root-positional-",
                                         "leading-inline-", "leading-unknown-"))):
            continue
    if "argv" in case:
        argv = case["argv"]
        translated = []
        skip = False
        for item in argv:
            if skip:
                skip = False
                continue
            if item == "--job-id":
                skip = True
            elif item.startswith("--job-id="):
                continue
            else:
                translated.append("list-jobs" if item == "status" else item)
        case["argv"] = translated
    if case["name"] in {"missing", "missing-id", "help-missing-id", "global-help-missing-id"}:
        continue
    CASES.append(case)
for status in ("running", "completed", "cancelled", "failed"):
    CASES.extend([
        {"name": "filter-" + status, "rows": "many", "argv": ["list-jobs", "--status", status]},
        {"name": "empty-filter-" + status, "rows": "empty",
         "argv": ["list-jobs", "--status=" + status]},
    ])
CASES.extend([
    {"name": "empty", "rows": "empty"},
    {"name": "ordering-and-all-states", "rows": "many"},
    {"name": "locked-db", "locked": True},
])
for name, argv in (
    ("invalid-filter", ["--status=queued"]), ("empty-filter", ["--status="]),
    ("missing-filter", ["--status"]), ("filter-option-value", ["--status", "--unknown"]),
    ("filter-negative", ["--status", "-1"]), ("filter-nonutf8", ["--status=bad-\udcff"]),
    ("filter-abbreviation", ["--sta=failed"]),
    ("duplicate-filter", ["--status=running", "--status=completed"]),
    ("unsupported-limit", ["--limit", "1"]), ("unsupported-zero-limit", ["--limit=0"]),
    ("unsupported-negative-limit", ["--limit=-1"]),
    ("unsupported-format", ["--format=json"]), ("unsupported-json", ["--json"]),
    ("unexpected-job-id", ["--job-id=fixture"]), ("unexpected-positional", ["fixture"]),
):
    CASES.append({"name": name, "argv": ["list-jobs", *argv]})
for column in ("job_id", "status", "change_id", "category", "dispatch_brief_path", "resume_count",
               "started_at", "stdout", "stderr"):
    for name, value in (("blob", {"bytes": "61ff00"}), ("integer", 7)):
        CASES.append({"name": f"field-{column}-{name}", "update": [column, value]})
for name, value in (("none", None), ("empty", ""), ("blank", "blocked_reason= \t\n"),
                    ("separators", "blocked_reason=\x1c\x1dword\x1etail")):
    CASES.append({"name": "stdout-" + name, "update": ["stdout", value]})
for column in ("job_id", "status", "change_id", "category", "started_at", "resume_count"):
    CASES.append({"name": "invalid-utf8-text-" + column, "invalid_text": column})
for name, column, value in (
    ("eager-json", "codex_args", "{"),
    ("blocked", "stdout", "blocked_reason= "),
    ("encoding", "status", "\u754c"),
):
    case = {"name": "later-row-" + name, "rows": "many", "later_update": [column, value]}
    if name == "encoding":
        case["env"] = {"PYTHONIOENCODING": "ascii:strict"}
    CASES.append(case)
for column in ("job_id", "codex_args", "started_at"):
    CASES.append({"name": "uppercase-column-" + column, "rename_column": column})
for name, argv in (
    ("help-before-malformed-help", ["list-jobs", "--help", "--help=x"]),
    ("cluster-help-before-malformed-help", ["list-jobs", "-hfoo", "--help=x"]),
    ("global-help-before-malformed-help", ["--help", "list-jobs", "--help=x"]),
):
    CASES.append({"name": name, "argv": argv})
SUPPORT.CASES = CASES
PIN = SUPPORT.PIN
BASE_SEED = SUPPORT.seed
BASE_CAPTURE = SUPPORT.capture


def seed(home, case, database):
    path = BASE_SEED(home, case, database)
    if case.get("rows"):
        with sqlite3.connect(path) as connection:
            if case["rows"] == "empty":
                connection.execute("DELETE FROM jobs")
            else:
                columns = [row[1] for row in connection.execute("PRAGMA table_info(jobs)")]
                original = list(connection.execute("SELECT * FROM jobs").fetchone())
                connection.execute("DELETE FROM jobs")
                # Intentionally unsorted and with equal timestamps: DESC retains
                # insertion order for ties.
                for index, (state, started) in enumerate([
                    ("queued", "2000"), ("completed", "9000"), ("running", "5000"),
                    ("failed", "9000"), ("cancelled", "1000"), ("", "8000"),
                    ("custom-state", "5000"),
                ]):
                    row = list(original)
                    for key, value in (("job_id", f"job-{index}"), ("status", state),
                                       ("started_at", started), ("stdout", ""),
                                       ("stderr", "")):
                        row[columns.index(key)] = value
                    connection.execute("INSERT INTO jobs VALUES (" +
                                       ",".join("?" for _ in row) + ")", row)
    if "later_update" in case:
        column, value = case["later_update"]
        with sqlite3.connect(path) as connection:
            connection.execute(f"UPDATE jobs SET {column}=? WHERE job_id='job-3'", (value,))
    if "invalid_text" in case:
        with sqlite3.connect(path) as connection:
            connection.execute(f"UPDATE jobs SET {case['invalid_text']}=CAST(X'61ff00' AS TEXT)")
    if "rename_column" in case:
        column = case["rename_column"]
        with sqlite3.connect(path) as connection:
            connection.execute(f'ALTER TABLE jobs RENAME COLUMN "{column}" TO "{column.upper()}"')
    return path


def capture(home, case, command):
    if not case.get("locked"):
        return BASE_CAPTURE(home, case, command)
    connection = sqlite3.connect(home / "tasks/jobs.db")
    connection.execute("BEGIN EXCLUSIVE")
    try:
        return BASE_CAPTURE(home, case, command)
    finally:
        connection.rollback()
        connection.close()


SUPPORT.seed = seed
SUPPORT.capture = capture
install_local_hook = SUPPORT.install_local_hook

if __name__ == "__main__":
    if len(sys.argv) == 1 and "MIR_EXECUTOR_LIST_JOBS_SCRATCH" in os.environ:
        sys.argv.extend(["--scratch", os.environ["MIR_EXECUTOR_LIST_JOBS_SCRATCH"]])
    SUPPORT.main()
