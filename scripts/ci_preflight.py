"""Check Yoke's checkout and the Python environment before running CI tests."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP_PROBE = "tests/test_memory_doctor.py::test_doctor_reports_ready_fts_baseline"


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    ).strip()


def revision(source: str, pattern: str) -> str:
    match = re.search(pattern, (ROOT / source).read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise ValueError(f"{source}: test revision could not be read")
    return match[1]


def check_checkout() -> None:
    if git("rev-parse", "--is-shallow-repository") != "false":
        raise ValueError("shallow Git checkout (use fetch-depth: 0)")

    print(f"  HEAD {git('rev-parse', 'HEAD')}", flush=True)
    # These tests read Git objects. Frozen fixture provenance and content hashes
    # that tests compare as strings do not require a Git object.
    pins = {
        source: revision(source, r'^\s*(?:PIN|SOURCE_REVISION) = "([0-9a-f]{40})"')
        for source in (
            "tests/test_retained_package_contract.py",
            "tests/test_run_python_native_parity.py",
            "tests/test_runtime_manifest_args_e02a.py",
            "tests/test_stage_e01_core_adoption.py",
            "tests/test_stage_e02b_native_install.py",
        )
    }
    legacy = "tests/test_capability_legacy_080.py"
    pins[legacy] = revision(legacy, r'"git", "archive", "([0-9a-f]{7,40})"')
    fixture = "native/handoff-packet/tests/fixtures/executor_hook_numeric_responses_reference.json"
    pins[fixture] = json.loads((ROOT / fixture).read_text(encoding="utf-8"))["reference"]
    lock = ".mir/capability-lock.json"
    pins[lock] = json.loads((ROOT / lock).read_text(encoding="utf-8"))["source"]["commit"]

    for source, pin in pins.items():
        try:
            commit = git(
                "rev-parse", "--verify", "--quiet", "--end-of-options", f"{pin}^{{commit}}",
            )
            git("merge-base", "--is-ancestor", commit, "HEAD")
        except subprocess.CalledProcessError as error:
            raise ValueError(f"{source}: {pin} is unreachable from HEAD") from error
        print(f"  {commit} {source}", flush=True)


def check_sqlite(vector: bool) -> None:
    import sqlite3

    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
            connection.execute("INSERT INTO probe VALUES ('preflight')")
            connection.execute("SELECT body FROM probe WHERE probe MATCH 'preflight'").fetchone()
            connection.execute("CREATE TABLE metadata (value TEXT)")
            connection.execute(
                """INSERT INTO metadata VALUES ('{"ready":1}')
                   RETURNING json_extract(value, '$.ready')"""
            ).fetchone()
            if vector:
                import sqlite_vec

                connection.enable_load_extension(True)
                sqlite_vec.load(connection)
                connection.execute("SELECT vec_version()").fetchone()
    except sqlite3.Error as error:
        raise ValueError(f"SQLite {sqlite3.sqlite_version}: {error}") from error
    print(f"  SQLite version {sqlite3.sqlite_version}", flush=True)


def run_temp_probe(environment: dict[str, str]) -> None:
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEMP_PROBE],
        cwd=ROOT, env=environment, check=True,
    )


def check_tmpdir() -> None:
    environment = os.environ.copy()
    configured = environment.get("TMPDIR")
    if not configured:
        environment.pop("TMPDIR", None)
        try:
            run_temp_probe(environment)
        except subprocess.CalledProcessError as error:
            raise ValueError("representative test failed with TMPDIR unset") from error
        print("  TMPDIR unset: representative test passed", flush=True)

    # Explicit dir avoids silently falling back when a configured TMPDIR is unusable.
    with tempfile.TemporaryDirectory(prefix="yoke ci ", dir=configured) as space:
        try:
            run_temp_probe({**environment, "TMPDIR": space, "TEMP": space, "TMP": space})
        except subprocess.CalledProcessError as error:
            raise ValueError("representative test failed with a space in TMPDIR") from error
    print("  TMPDIR with spaces: representative test passed", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--checkout-only", action="store_true")
    modes.add_argument("--runtime-only", action="store_true")
    parser.add_argument("--sqlite-vector", action="store_true")
    args = parser.parse_args()

    def check(name, probe):
        try:
            probe()
        except (AttributeError, ImportError, OSError, ValueError, KeyError,
                subprocess.CalledProcessError) as error:
            raise SystemExit(f"FAIL {name}: {error}") from error
        print(f"PASS {name}", flush=True)

    if not args.runtime_only:
        check("git-checkout", check_checkout)
    if not args.checkout_only:
        check("SQLite", lambda: check_sqlite(args.sqlite_vector))
        check("TMPDIR", check_tmpdir)


if __name__ == "__main__":
    main()
