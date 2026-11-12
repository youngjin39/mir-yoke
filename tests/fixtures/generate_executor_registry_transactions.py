"""Freeze shared registry transaction boundaries from the pinned Python reference."""
import argparse
import dataclasses
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "cancel_oracle", Path(__file__).with_name("generate_executor_cancel.py"))
ORACLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ORACLE)
OUTPUT = (Path(__file__).parents[2] /
          "native/handoff-packet/tests/fixtures/executor_registry_transactions.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=False)
    reference = args.scratch / "reference"
    digest = ORACLE.SUPPORT.archive_reference(reference)
    sys.path.insert(0, str(reference))
    from tools.mir_executor.jobs import JobRecord, JobRegistry

    record = JobRecord(job_id="new", change_id="change", category="unit", family=None,
                       repo_root="fixture-root", codex_args=[], timeout_seconds=60,
                       status="running", started_at="then")
    cases = []
    for operation in ("insert", "update_route_metadata", "update_ai_run_metadata",
                      "update_status", "cancel", "mark_resumed", "record_artifact_sweep"):
        for timing in ("BEFORE", "AFTER"):
            for conflict in ("FAIL", "ABORT", "ROLLBACK", "IGNORE"):
                path = args.scratch / f"{operation}-{timing}-{conflict}.db"
                registry = JobRegistry(path)
                registry.insert(dataclasses.replace(record, job_id="job", resume_count=2))
                table = "artifact_sweeps" if operation == "record_artifact_sweep" else "jobs"
                event = "INSERT" if operation in ("insert", "record_artifact_sweep") else "UPDATE"
                trigger = (f"CREATE TRIGGER failure {timing} {event} ON {table} "
                           "BEGIN INSERT INTO audit VALUES (77); "
                           f"SELECT RAISE({conflict}" +
                           (", 'fixture transaction failure'" if conflict != "IGNORE" else "") +
                           "); END")
                registry._conn.executescript("CREATE TABLE audit(value);" + trigger)
                kwargs = {
                    "insert": {"job": record},
                    "update_route_metadata": dict(job_id="job", execution_backend="native",
                                                  resolved_model=None,
                                                  resolved_reasoning_effort=None),
                    "update_ai_run_metadata": dict(job_id="job", metadata={"tokens": 7}),
                    "update_status": dict(job_id="job", status="failed"),
                    "cancel": dict(job_id="job"),
                    "mark_resumed": dict(job_id="job", resumed_at="again"),
                    "record_artifact_sweep": dict(job_id="job", path="artifacts", files=2,
                                                  size_bytes=10, swept_at="now"),
                }[operation]
                before = path.read_bytes()
                error = None
                try:
                    getattr(registry, operation)(**kwargs)
                except sqlite3.Error as exc:
                    error = type(exc).__name__
                def rows(query, connection=registry._conn):
                    return [list(row) for row in connection.execute(query)]
                cases.append(dict(
                    operation=operation, trigger=trigger, error=error,
                    record=dataclasses.asdict(record),
                    rows=rows("SELECT job_id,status,cancel_requested,resume_count,"
                              "execution_backend,ai_run_metadata FROM jobs ORDER BY job_id"),
                    audit=rows("SELECT * FROM audit"),
                    sweeps=rows("SELECT * FROM artifact_sweeps"),
                    unchanged_bytes=path.read_bytes() == before))
                registry.close()
    failure_modes = []
    for mode in ("commit-busy", "write-busy", "readonly", "constraint", "full"):
        path = args.scratch / f"{mode}.db"
        registry = JobRegistry(path)
        registry.insert(dataclasses.replace(record, job_id="job"))
        registry._conn.execute("PRAGMA busy_timeout=0")
        blocker = sqlite3.connect(path)
        if mode == "commit-busy":
            blocker.execute("BEGIN")
            blocker.execute("SELECT * FROM jobs").fetchall()
        elif mode == "write-busy":
            blocker.execute("BEGIN IMMEDIATE")
        elif mode == "readonly":
            registry._conn.execute("PRAGMA query_only=ON")
        elif mode == "full":
            count = registry._conn.execute("PRAGMA page_count").fetchone()[0]
            registry._conn.execute(f"PRAGMA max_page_count={count}")
        before = path.read_bytes()
        try:
            if mode == "constraint":
                registry.insert(dataclasses.replace(record, job_id="job"))
            elif mode == "full":
                registry.update_ai_run_metadata("job", {"data": "x" * 100000})
            else:
                registry.cancel("job")
        except sqlite3.Error as exc:
            error = exc.sqlite_errorcode
        else:
            raise AssertionError(mode)
        failure_modes.append(dict(mode=mode, code=error,
                                  unchanged_bytes=path.read_bytes() == before,
                                  in_transaction=registry._conn.in_transaction))
        blocker.close()
        registry.close()
    # Python DDL is autocommitted: the successful first ALTER survives the second's failure.
    path = args.scratch / "migration.db"
    initial = "CREATE TABLE jobs(job_id TEXT,status TEXT," + ",".join(
        f"f{i} TEXT" for i in range(1997)) + ")"
    with sqlite3.connect(path) as db:
        db.execute(initial)
    try:
        JobRegistry(path)
    except sqlite3.Error as exc:
        migration_error = str(exc)
    with sqlite3.connect(path) as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(jobs)")]
    OUTPUT.write_text(json.dumps(dict(reference=ORACLE.PIN, archive_sha256=digest, cases=cases,
                                     failure_modes=failure_modes,
                                     migration=dict(initial=initial, error=migration_error,
                                                    columns=columns)),
                                 indent=2, ensure_ascii=True) + "\n", encoding="ascii")
    print(f"Captured {len(cases)} writes and partial migration from {ORACLE.PIN}")


if __name__ == "__main__":
    main()
