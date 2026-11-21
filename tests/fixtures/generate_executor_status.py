"""Freeze status process and storage outcomes from the pinned Python source only.

Regenerate: python tests/fixtures/generate_executor_status.py --scratch /disposable/path
The scratch tree contains an archived reference, synthetic homes, and provenance.
"""
from __future__ import annotations

import argparse
import codecs
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIN = "84b7b8a33cff26cd782170befa8621a1c65d9744"
OUTPUT = ROOT / "tests/fixtures/executor_status.json"
SELECTORS = ("MIR_EXECUTOR_IMPL", "MIR_EXECUTOR_QUERY_IMPL", "MIR_NATIVE_HOOKS",
             "MIR_EXECUTOR_STATUS_IMPL")
BASE_ARGV = ["status", "--job-id", "fixture"]


def cases():
    values = [{"name": "ordinary"}, {"name": "missing", "argv": ["status", "--job-id", "absent"]}]
    for key in SELECTORS:
        for value in ("python", "native", "0", "invalid"):
            values.append({"name": f"selector-{key}-{value}", "env": {key: value}})
    for name, argv in (
        ("missing-id", ["status"]), ("help-missing-id", ["status", "--help"]),
        ("help", [*BASE_ARGV, "--help"]), ("short-help", [*BASE_ARGV, "-h"]),
        ("unknown", [*BASE_ARGV, "--unknown"]), ("end-options", [*BASE_ARGV, "--"]),
        ("unknown-global-flag", ["--unknown", *BASE_ARGV]),
        ("global-help", ["--help", *BASE_ARGV]),
        ("global-help-missing-id", ["--help", "status"]),
        ("leading-repo-root", ["--repo-root", "<HOME>", *BASE_ARGV]),
        ("leading-end-options", ["--", *BASE_ARGV]),
        ("help-explicit-value", [*BASE_ARGV, "--help=ignored"]),
        ("help-abbreviation-value", [*BASE_ARGV, "--he=x"]),
        ("help-short-cluster", [*BASE_ARGV, "-hfoo"]),
        ("missing-value", ["status", "--job-id"]),
        ("negative-id", ["status", "--job-id", "-1"]),
        ("option-value", ["status", "--job-id", "--unknown"]),
        ("duplicate-id", [*BASE_ARGV, "--job-id", "absent"]),
        ("duplicate-id-last", ["status", "--job-id=absent", "--job-id=fixture"]),
        ("abbreviation", ["status", "--job-i", "fixture", "--repo-r", "<HOME>/./"]),
        ("global-db-abbreviation", ["--jobs-d", "tasks/jobs.db", *BASE_ARGV]),
        ("duplicate-db", ["--jobs-db", "ignored.db", "--jobs-db=tasks/jobs.db", *BASE_ARGV]),
        ("trailing-db", [*BASE_ARGV, "--jobs-db=tasks/jobs.db"]),
        ("empty-id", ["status", "--job-id="]),
        ("nonutf8-id", ["status", "--job-id", "bad-\udcff"]),
        ("unicode-version-missing-id", ["status", "--job-id", "\U0001fae9"]),
    ):
        values.append({"name": name, "argv": argv})
    for codec in ("ascii:backslashreplace", "ascii:strict", "latin1:strict",
                  "latin1:backslashreplace", "utf-8:strict", "utf-16:strict",
                  "utf-32:strict"):
        values.append({"name": "stream-" + codec.replace(":", "-"),
                       "env": {"PYTHONIOENCODING": codec}, "data": "unicode"})
    for codec in ("cp932:strict", "cp437:strict", "iso8859-15:strict", "koi8-r:strict",
                  "utf-7:strict", "unicode_escape:strict", "raw_unicode_escape:strict",
                  "ascii:namereplace"):
        values.append({"name": "compat-" + codec.replace(":", "-"),
                       "env": {"PYTHONIOENCODING": codec}, "data": "unicode",
                       "compatibility": True})
    for mode in ("missing-db", "nested-db", "parent-file", "database-directory", "bad-db",
                 "empty-schema", "wrong-schema", "migration", "symlink", "wal", "chmod"):
        values.append({"name": mode, "storage": mode})
    values.append({"name": "nonutf8-db-path", "storage": "nonutf8-path", "platform": "darwin"})
    for codec in ("utf-16", "utf-32"):
        values.append({"name": codec + "-exception",
                       "env": {"PYTHONIOENCODING": codec + ":strict"},
                       "update": ["stdout", "blocked_reason="]})
    for name, column, value in (
        ("bad-codex-json", "codex_args", "{"),
        ("null-codex-json", "codex_args", "null"),
        ("number-codex-json", "codex_args", "17"),
        ("string-codex-json", "codex_args", '"abc"'),
        ("blob-codex-json", "codex_args", {"bytes": "5b2258225d"}),
        ("utf16-codex-json", "codex_args", {"bytes": "fffe5b002200580022005d00"}),
        ("invalid-utf32-codex-json", "codex_args", {"bytes": "fffe000000001100"}),
        ("integer-codex-json", "codex_args", 5),
        ("bad-ai-json", "ai_run_metadata", "{"),
        ("infinite-ai-json", "ai_run_metadata", "1e400"),
        ("bytes-ai-json", "ai_run_metadata", {"bytes": "7b7d"}),
        ("integer-ai-json", "ai_run_metadata", 5),
        ("bytes-status", "status", {"bytes": "61ff00"}),
        ("number-family", "family", 3.5),
        ("unicode-version-family", "family", "\U0001fae9"),
        ("nonprintable-family", "family",
         "\x1c\x1d\x1e\x1f\x85\u2028\u2029\x7f\xa0\u200b\ufeff"),
        ("bytes-family", "family", {"bytes": "61ff00"}),
        ("noncanonical-bool", "cancel_requested", -1),
        ("text-bool", "allow_harness_self_modify", "false"),
        ("empty-blocked", "stdout", "blocked_reason="),
        ("blank-blocked", "stdout", "blocked_reason= \t\n"),
        ("separator-blocked", "stdout", "prefix blocked_reason=first\x1csecond"),
        ("leading-separators-blocked", "stdout", "blocked_reason=\x1c\x1d\x1e\x1ffirst"),
        ("stderr-blocked", "stdout", ""),
        ("bytes-blocked", "stdout", {"bytes": "626c6f636b65645f726561736f6e3d78"}),
        ("number-blocked", "stdout", 7),
    ):
        values.append({"name": name, "update": [column, value]})
    for column in ("codex_args", "ai_run_metadata", "stdout"):
        values.append({"name": "numeric-no-affinity-" + column, "raw_type": column,
                       "update": [column, 7]})
    for column in ("status", "started_at", "completed_at"):
        values.append({"name": "ascii-multiline-" + column,
                       "env": {"PYTHONIOENCODING": "ascii:strict"},
                       "update": [column, "prefix\n\u754c"]})
    for storage in ("long-symlink-chain", "symlink-cycle"):
        values.append({"name": "repo-root-" + storage, "storage": storage,
                       "argv": [*BASE_ARGV, "--repo-root", "<HOME>/alias0"]})
    for name, argv in (
        ("root-missing-repo", ["status", "--repo-root"]),
        ("root-repo-option-value", ["status", "--repo-root", "--job-id", "fixture"]),
        ("root-missing-jobs", ["status", "--jobs-db"]),
        ("root-jobs-option-value", ["--jobs-db", "--bad", "status"]),
    ):
        values.append({"name": name, "argv": argv, "root_program": True})
    for name, hook, extra in (
        ("legacy-crossroot-print", "print", []),
        ("legacy-crossroot-print-deny", "print-deny", []),
        ("legacy-crossroot-allow", "allow", []),
        ("legacy-crossroot-deny", "deny", []),
        ("legacy-crossroot-deny-help", "deny", ["--help"]),
        ("legacy-crossroot-deny-unknown", "deny", ["--unknown"]),
    ):
        values.append({"name": name, "legacy_hook": hook,
                       "argv": [*BASE_ARGV, "--repo-root", "<HOME>/target", *extra]})
    for column in ("status", "started_at", "completed_at"):
        values.append({"name": "cp1252-grouped-" + column,
                       "env": {"PYTHONIOENCODING": "cp1252:strict"},
                       "update": [column, "a\u754c\U0001f600b"]})
    for name, text in (("undefined", "\u0081\u008d"),
                       ("mapped-prefix", "\u20ac\u754c\u754c"),
                       ("mapped-separator", "\u754c\u20ac\u754c")):
        values.append({"name": "cp1252-" + name,
                       "env": {"PYTHONIOENCODING": "cp1252:strict"},
                       "update": ["status", text]})
    for name, text in (("pair", "a\udcff\udcfe"), ("triple", "\udcff\udcfe\udcfd"),
                       ("separated", "x\udcffy\udcfe")):
        values.append({"name": "nonutf8-id-" + name,
                       "argv": ["status", "--job-id=" + text]})
    for payload in ("efbbbf80", "efbbbfeda080ff", "efbbbff09080"):
        values.append({"name": "utf8-sig-invalid-" + payload,
                       "update": ["codex_args", {"bytes": payload}]})
    for name, prefix in (
        ("dash", ["-"]), ("end-dash", ["--", "-"]),
        ("double-end", ["--", "--"]), ("negative", ["-1"]),
        ("negative-decimal", ["-0.5"]), ("help-explicit", ["--help=x"]),
        ("help-abbreviation", ["--h=x"]), ("short-help-explicit", ["-h=x"]),
    ):
        values.append({"name": "root-positional-" + name,
                       "argv": [*prefix, *BASE_ARGV]})
    values.extend([
        {"name": "root-negative-newline", "argv": ["-1\n", *BASE_ARGV]},
        {"name": "job-negative-newline", "argv": ["status", "--job-id", "-1\n"]},
    ])
    for name, prefix in (
        ("leading-inline-repo-space", ["--repo-root=<HOME>"]),
        ("leading-inline-repo-space-end", ["--repo-root=<HOME>", "--"]),
        ("leading-inline-repo-abbreviation-space", ["--rep=<HOME>"]),
        ("leading-unknown-inline-space", ["--unknown=two words"]),
    ):
        values.append({"name": name, "argv": [*prefix, *BASE_ARGV]})
    values.append({"name": "ignores-mutation-receipt",
                   "env": {"MIR_EXECUTOR_OWNED_RECEIPT": "tasks/status-receipt"}})
    return values


CASES = cases()


def environment(home, case):
    env = dict(os.environ)
    for key in SELECTORS:
        env.pop(key, None)
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONPATH=str(home),
               PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8:strict",
               MIR_EXECUTOR_ARGPARSE_PROG="-c", MIR_EXECUTOR_PYTHON=sys.executable, COLUMNS="80")
    env.update(case.get("env", {}))
    return env


def archive_reference(destination):
    data = subprocess.check_output(["git", "archive", PIN, "tools/mir_executor"], cwd=ROOT)
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(destination, filter="data")
    return hashlib.sha256(data).hexdigest()


# The frozen physical SQLite snapshots include bytes left on freed pages.
SQLITE_KEEP_DELETED_BYTES = """\
import sqlite3

fixture_connect = sqlite3.connect

def connect(*args, **kwargs):
    connection = fixture_connect(*args, **kwargs)
    connection.execute("PRAGMA secure_delete=OFF")
    return connection

sqlite3.connect = connect
"""


def template(reference, destination):
    script = r"""import sys
from pathlib import Path
from tools.mir_executor.jobs import JobRegistry, JobRecord
registry = JobRegistry(Path(sys.argv[1]))
registry.insert(JobRecord(job_id='fixture', change_id="change 'quoted' \\",
    category='unit', family='family', repo_root='<HOME>', codex_args=['task'],
    timeout_seconds=60, status='completed', stdout='blocked_reason=stdout-reason details',
    stderr='blocked_reason=stderr-reason details', started_at='started',
    completed_at='completed', resume_count=2, cancel_requested=True,
    allow_harness_self_modify=True))
registry.close()
"""
    subprocess.run(
        [sys.executable, "-c", SQLITE_KEEP_DELETED_BYTES + script, str(destination)],
        cwd=reference, env=environment(reference, {}), check=True, capture_output=True,
    )


def empty_template(reference, destination):
    template(reference, destination)
    with sqlite3.connect(destination) as db:
        db.execute("PRAGMA secure_delete=OFF")
        db.execute("DELETE FROM jobs")


def seed(home, case, database):
    home.mkdir(parents=True)
    path = home / "tasks/jobs.db"
    path.parent.mkdir()
    shutil.copyfile(database, path)
    if case.get("legacy_hook"):
        subprocess.run(["git", "init", "-q", str(home)], env=environment(home, case), check=True,
                       capture_output=True)
        target = home / "target"
        (target / "tasks").mkdir(parents=True)
        target_database = target / "tasks/jobs.db"
        shutil.copyfile(database, target_database)
        with sqlite3.connect(target_database) as connection:
            connection.execute("UPDATE jobs SET repo_root=?", (str(target),))
    storage = case.get("storage")
    if storage in {"missing-db", "nested-db", "parent-file", "database-directory"}:
        path.unlink()
        if storage == "parent-file":
            (home / "blocked").write_text("parent blocker", encoding="ascii")
        elif storage == "database-directory":
            path.mkdir()
    elif storage == "bad-db":
        path.write_bytes(b"fixture is not sqlite\n")
    elif storage in {"empty-schema", "wrong-schema", "migration"}:
        path.unlink()
        with sqlite3.connect(path) as connection:
            if storage == "wrong-schema":
                connection.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY)")
            elif storage == "migration":
                connection.execute("""CREATE TABLE jobs (
                    job_id TEXT PRIMARY KEY, change_id TEXT NOT NULL, category TEXT NOT NULL,
                    family TEXT, repo_root TEXT NOT NULL, codex_args TEXT NOT NULL,
                    timeout_seconds INTEGER NOT NULL, status TEXT NOT NULL, exit_code INTEGER,
                    stdout TEXT, stderr TEXT, duration_seconds REAL, started_at TEXT NOT NULL,
                    completed_at TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0)""")
    elif storage == "symlink":
        target = home / "target.db"
        path.rename(target)
        path.symlink_to("../target.db")
    elif storage == "wal":
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
    if storage == "chmod":
        path.chmod(0o644)
    if storage in {"long-symlink-chain", "symlink-cycle"}:
        count = 45 if storage == "long-symlink-chain" else 3
        for index in range(count):
            target = f"alias{index + 1}" if index < count - 1 else (
                "." if storage == "long-symlink-chain" else "alias0")
            (home / f"alias{index}").symlink_to(target, target_is_directory=True)
    if case.get("data") == "unicode":
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE jobs SET family=?, change_id=?",
                               ("caf\u00e9 \u754c", "na\u00efve"))
    if "update" in case:
        column, value = case["update"]
        if isinstance(value, dict):
            value = bytes.fromhex(value["bytes"])
        with sqlite3.connect(path) as connection:
            if "raw_type" in case:
                ddl = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name='jobs'").fetchone()[0]
                ddl = re.sub(rf'(\b{column}"?\s+)TEXT\b', r"\1BLOB", ddl)
                connection.execute("ALTER TABLE jobs RENAME TO previous_jobs")
                connection.execute(ddl)
                connection.execute("INSERT INTO jobs SELECT * FROM previous_jobs")
                connection.execute("DROP TABLE previous_jobs")
                connection.execute("CREATE INDEX idx_jobs_status ON jobs(status)")
            connection.execute(f"UPDATE jobs SET {column}=?", (value,))
    return path


def install_local_hook(home, case):
    if not case.get("legacy_hook"):
        return
    source = "def authorize_target(home_root, target_root, args):\n"
    if case["legacy_hook"].startswith("print"):
        source += '    print("legacy auth notice")\n'
    source += "    raise ValueError('deny')\n" if "deny" in case["legacy_hook"] else (
        "    return None\n")
    (home / "tools/mir_executor/local.py").write_text(source, encoding="ascii")


def arguments(home, case):
    argv = [item.replace("<HOME>", str(home)) for item in case.get("argv", BASE_ARGV)]
    storage = case.get("storage")
    if storage == "nested-db":
        argv = ["--jobs-db=nested/parents/jobs.db", *argv]
    elif storage == "parent-file":
        argv = ["--jobs-db=blocked/jobs.db", *argv]
    elif storage == "nonutf8-path":
        argv = ["--jobs-db=tasks/nonutf8-\udcff.db", *argv]
    return argv


def logical(value, home):
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    if isinstance(value, str):
        return value.replace(str(home), "<HOME>")
    if isinstance(value, list):
        return [logical(item, home) for item in value]
    if isinstance(value, dict):
        return {key: logical(item, home) for key, item in value.items()}
    return value


def snapshot(home):
    result = {}
    for path in sorted(home.rglob("*")):
        relative = path.relative_to(home)
        if (relative.parts[0] not in {"tasks", "nested", "blocked", "target.db", "target"}
                and not relative.parts[0].startswith("alias")):
            continue
        metadata = path.lstat()
        entry = {"mode": oct(stat.S_IMODE(metadata.st_mode))}
        if path.is_symlink():
            entry.update(kind="symlink", target=os.readlink(path))
        elif path.is_dir():
            entry.update(kind="directory")
        elif path.name.endswith(".db"):
            entry.update(kind="database")
            try:
                connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
                try:
                    tables = [row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
                    entry["tables"] = {}
                    for name in tables:
                        entry["tables"][name] = {
                            "columns": [list(row) for row in connection.execute(
                                f'PRAGMA table_info("{name}")')],
                            "rows": [list(row) for row in connection.execute(
                                f'SELECT * FROM "{name}" ORDER BY rowid')],
                        }
                    entry["indexes"] = [list(row) for row in connection.execute(
                        "SELECT name, tbl_name FROM sqlite_master "
                        "WHERE type='index' ORDER BY name")]
                    entry["journal_mode"] = connection.execute("PRAGMA journal_mode").fetchone()[0]
                finally:
                    connection.close()
            except sqlite3.Error as error:
                entry["error"] = str(error)
        else:
            entry.update(kind="file", bytes=path.read_bytes().hex())
        result[relative.as_posix()] = entry
    return logical(result, home)


def capture(home, case, command):
    completed = subprocess.run([*command, *arguments(home, case)], cwd=home,
                               env=environment(home, case), capture_output=True,
                               timeout=30, check=False)
    stdout, stderr, code = completed.stdout, completed.stderr, completed.returncode
    encoding = codecs.lookup(case.get("env", {}).get(
        "PYTHONIOENCODING", "utf-8:strict").split(":", 1)[0]).name
    error_text = stderr.decode(encoding, "surrogateescape") if stderr else ""
    # COMMON's fail-closed exception protocol deliberately discards partial prints.
    if "Traceback (most recent call last):" in error_text:
        stdout, stderr, code = b"", (error_text.splitlines()[-1] + "\n").encode(encoding), 1
    if stdout:
        stdout = stdout.decode(encoding, "surrogateescape").replace(
            str(home), "<HOME>").encode(encoding, "surrogateescape")
    if stderr:
        stderr = stderr.decode(encoding, "surrogateescape").replace(
            str(home), "<HOME>").encode(encoding, "surrogateescape")
    return {"exit": code, "stdout_hex": stdout.hex(), "stderr_hex": stderr.hex(),
            "storage": snapshot(home)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    options = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("the non-UTF-8 filesystem record must be regenerated on macOS")
    scratch = options.scratch.resolve()
    if scratch.exists():
        raise SystemExit("scratch must be a new disposable directory")
    scratch.mkdir(parents=True)
    reference = scratch / "reference"
    digest = archive_reference(reference)
    database = scratch / "template.db"
    template(reference, database)
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
    payload = {"reference": PIN, "archive_sha256": digest,
               "entrypoint": "tools.mir_executor.cli.main (direct console call)",
               "exception_protocol": "exit 1; empty stdout; traceback final stderr line",
               "cases": records}
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                      encoding="ascii")
    (scratch / "provenance.json").write_text(json.dumps({
        "reference": PIN, "archive_sha256": digest, "python": sys.version,
        "fixture_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
    }, indent=2) + "\n", encoding="ascii")
    print(f"Captured {len(records)} cases from {PIN}")


if __name__ == "__main__":
    main()
