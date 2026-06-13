"""
cli.py
------
Argparse CLI entry point for the your-harness Executor.

Usage:
    python -m tools.mir_executor execute \\
        --change-id <id> \\
        --category <name> \\
        --codex-args "<quoted string>" \\
        [--timeout <seconds>] \\
        --repo-root <path>
        [--background | -b]
        [--jobs-db <path>]

    python -m tools.mir_executor status --job-id <id> [--jobs-db <path>]
    python -m tools.mir_executor result --job-id <id> [--jobs-db <path>]
    python -m tools.mir_executor cancel --job-id <id> [--jobs-db <path>]
    python -m tools.mir_executor resume --job-id <id> [--jobs-db <path>]
    python -m tools.mir_executor list-jobs [--status <status>] [--jobs-db <path>]

Exit codes:
    0 — execution and ledger update both succeeded (Codex exit code is in stdout).
    1 — meta-execution error (FileNotFoundError, KeyError, etc.).

Background mode (--background / -b):
    MVP: prints job_id immediately, then runs Codex synchronously within the same
    CLI invocation (asyncio.run), updating job status on completion.
    True process detachment is Out-of-Scope per ADR §8 O1.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import pathlib
import shlex
import subprocess
import sys
import uuid

from tools.mir_executor.executor import MirExecutor

_STANDARD_CATEGORIES = [
    "unit",
    "integration",
    "e2e",
    "browser",
    "edge",
    "architecture",
    "availability",
    "load",
    "soak",
    "security",
    "compatibility",
    "transaction_locking",
]

_DEFAULT_JOBS_DB_RELPATH = pathlib.Path("tasks") / "jobs.db"


def _utc_now() -> str:
    """Return current UTC time as ISO8601 string."""
    return datetime.datetime.now(datetime.UTC).isoformat()


def _resolve_jobs_db(args_jobs_db: str | None, repo_root: pathlib.Path) -> pathlib.Path:
    """Resolve the jobs.db path: --jobs-db override or default <repo_root>/tasks/jobs.db."""
    if args_jobs_db is not None:
        return pathlib.Path(args_jobs_db).resolve()
    return (repo_root / _DEFAULT_JOBS_DB_RELPATH).resolve()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.mir_executor",
        description="your-harness Executor — Codex CLI subprocess wrapper + tdd.json ledger update.",
    )
    # Global --jobs-db option available for all subcommands
    parser.add_argument(
        "--jobs-db",
        metavar="PATH",
        default=None,
        help="Override path to jobs.db (default: <repo_root>/tasks/jobs.db).",
    )
    sub = parser.add_subparsers(dest="subcommand")

    # ------------------------------------------------------------------
    # execute subcommand
    # ------------------------------------------------------------------
    exec_p = sub.add_parser(
        "execute",
        help="Run a Codex command and record the result in tdd.json.",
    )
    exec_p.add_argument(
        "--change-id",
        required=True,
        metavar="ID",
        help="The tdd.json change entry id to update.",
    )
    exec_p.add_argument(
        "--category",
        required=True,
        choices=_STANDARD_CATEGORIES,
        metavar="NAME",
        help=(
            "The category to update. One of: "
            + ", ".join(_STANDARD_CATEGORIES)
            + "."
        ),
    )
    exec_p.add_argument(
        "--codex-args",
        required=True,
        metavar="QUOTED_STRING",
        help=(
            "Arguments to pass to the Codex binary "
            "(shell-quoted string; shlex.split applied internally)."
        ),
    )
    exec_p.add_argument(
        "--timeout",
        type=int,
        default=600,
        metavar="SECONDS",
        help="Subprocess timeout in seconds (default: 600).",
    )
    exec_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        required=True,
        metavar="PATH",
        help="Repository root path. Used to locate tasks/tdd.json.",
    )
    exec_p.add_argument(
        "--async",
        "-a",
        action="store_true",
        default=False,
        dest="use_async",
        help="Use asyncio-based async subprocess (asyncio.TimeoutError on timeout).",
    )
    exec_p.add_argument(
        "--background",
        "-b",
        action="store_true",
        default=False,
        dest="background",
        help=(
            "Background mode: print job_id immediately, then run Codex and update "
            "job status on completion. MVP: runs in same process (true daemon is OOS)."
        ),
    )

    # ------------------------------------------------------------------
    # status subcommand
    # ------------------------------------------------------------------
    status_p = sub.add_parser(
        "status",
        help="Print job status from the JobRegistry.",
    )
    status_p.add_argument(
        "--job-id",
        required=True,
        metavar="JOB_ID",
        help="UUID job_id returned by execute --background.",
    )
    status_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=None,
        help="Repository root path (for default jobs.db location).",
    )

    # ------------------------------------------------------------------
    # result subcommand
    # ------------------------------------------------------------------
    result_p = sub.add_parser(
        "result",
        help="Print job result (exit_code, stdout, stderr, duration) from the JobRegistry.",
    )
    result_p.add_argument(
        "--job-id",
        required=True,
        metavar="JOB_ID",
        help="UUID job_id returned by execute --background.",
    )
    result_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=None,
        help="Repository root path (for default jobs.db location).",
    )

    # ------------------------------------------------------------------
    # cancel subcommand
    # ------------------------------------------------------------------
    cancel_p = sub.add_parser(
        "cancel",
        help="Request cancellation of a background job.",
    )
    cancel_p.add_argument(
        "--job-id",
        required=True,
        metavar="JOB_ID",
        help="UUID job_id returned by execute --background.",
    )
    cancel_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=None,
        help="Repository root path (for default jobs.db location).",
    )

    # ------------------------------------------------------------------
    # resume subcommand
    # ------------------------------------------------------------------
    resume_p = sub.add_parser(
        "resume",
        help="Resume a job from its persisted DispatchBrief and stored registry state.",
    )
    resume_p.add_argument(
        "--job-id",
        required=True,
        metavar="JOB_ID",
        help="UUID job_id returned by execute --background or conductor bridge dispatch.",
    )
    resume_p.add_argument(
        "--timeout",
        type=int,
        default=600,
        metavar="SECONDS",
        help="Subprocess timeout in seconds (default: 600).",
    )
    resume_p.add_argument(
        "--async",
        "-a",
        action="store_true",
        default=False,
        dest="use_async",
        help="Use asyncio-based async subprocess for resume.",
    )
    resume_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=None,
        help="Repository root path (for default jobs.db location).",
    )

    # ------------------------------------------------------------------
    # list-jobs subcommand
    # ------------------------------------------------------------------
    list_p = sub.add_parser(
        "list-jobs",
        help="List background jobs, optionally filtered by status.",
    )
    list_p.add_argument(
        "--status",
        metavar="STATUS",
        default=None,
        choices=["running", "completed", "cancelled", "failed"],
        help="Filter by status: running / completed / cancelled / failed.",
    )
    list_p.add_argument(
        "--repo-root",
        type=pathlib.Path,
        metavar="PATH",
        default=None,
        help="Repository root path (for default jobs.db location).",
    )

    return parser


# ---------------------------------------------------------------------------
# Background job runner (async)
# ---------------------------------------------------------------------------

async def _run_background(
    job_id: str,
    executor: MirExecutor,
    change_id: str,
    category: str,
    codex_args: list[str],
    timeout_seconds: int,
    jobs_db_path: pathlib.Path,
) -> None:
    """Async background runner: invoke run_codex_async + update JobRegistry.

    Cancel polling: checks cancel_requested flag before running (MVP flag-only;
    real SIGTERM is Out-of-Scope per ADR §8 O1).
    """
    # Lazy import to avoid module-load overhead
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    registry = JobRegistry(jobs_db_path)
    try:
        # Check for pre-flight cancel request
        job = registry.get(job_id)
        if job is not None and job.cancel_requested:
            registry.update_status(
                job_id,
                "cancelled",
                completed_at=_utc_now(),
            )
            return

        result = await executor.run_codex_async(codex_args, timeout_seconds=timeout_seconds)

        # Update ledger
        executor.update_ledger(change_id, category, result)

        new_status = "completed" if result.exit_code == 0 else "failed"
        registry.update_status(
            job_id,
            new_status,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            completed_at=_utc_now(),
        )
    except Exception as exc:  # noqa: BLE001
        registry.update_status(
            job_id,
            "failed",
            stderr=str(exc),
            completed_at=_utc_now(),
        )
    finally:
        registry.close()


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _handle_execute(args: argparse.Namespace) -> int:
    """Handle the 'execute' subcommand."""
    try:
        codex_args = shlex.split(args.codex_args)
    except ValueError as exc:
        print(f"[mir_executor] argument parse error: {exc}", file=sys.stderr)
        return 1

    repo_root = args.repo_root.resolve()

    executor = MirExecutor(repo_root=repo_root)

    if args.background:
        # Background mode: insert job record, print job_id, then run async and update.
        # MVP: runs in same CLI process (true daemon detachment is ADR §8 O1 future work).
        from tools.mir_executor.jobs import JobRecord, JobRegistry  # noqa: PLC0415

        job_id = uuid.uuid4().hex
        jobs_db_path = _resolve_jobs_db(args.jobs_db, repo_root)
        registry = JobRegistry(jobs_db_path)

        job = JobRecord(
            job_id=job_id,
            change_id=args.change_id,
            category=args.category,
            family=None,
            repo_root=str(repo_root),
            codex_args=codex_args,
            timeout_seconds=args.timeout,
            status="running",
            started_at=_utc_now(),
        )
        registry.insert(job)
        # Print job_id immediately — caller can record it before Codex runs.
        print(f"[BACKGROUND] job_id={job_id}")
        sys.stdout.flush()

        # Validate ledger entry before starting the async runner.
        try:
            executor._validate_ledger_entry(args.change_id, args.category)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            registry.update_status(job_id, "failed", stderr=str(exc), completed_at=_utc_now())
            registry.close()
            print(f"[mir_executor] {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

        asyncio.run(
            _run_background(
                job_id=job_id,
                executor=executor,
                change_id=args.change_id,
                category=args.category,
                codex_args=codex_args,
                timeout_seconds=args.timeout,
                jobs_db_path=jobs_db_path,
            )
        )
        registry.close()
        return 0

    # Non-background (sync or async) path — BC unchanged.
    try:
        if args.use_async:
            result, update = asyncio.run(
                executor.execute_async(
                    change_id=args.change_id,
                    category=args.category,
                    codex_args=codex_args,
                    timeout_seconds=args.timeout,
                )
            )
        else:
            result, update = executor.execute(
                change_id=args.change_id,
                category=args.category,
                codex_args=codex_args,
                timeout_seconds=args.timeout,
            )
    except (FileNotFoundError, KeyError, PermissionError) as exc:
        print(f"[mir_executor] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(f"[mir_executor] Codex timeout after {exc.timeout}s: {exc}", file=sys.stderr)
        return 1
    except TimeoutError:
        print(f"[mir_executor] async timeout after {args.timeout}s", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[mir_executor] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"[RESULT] change_id={update.change_id!r} category={update.category!r}")
    print(f"[RESULT] codex exit_code={result.exit_code} duration={result.duration_seconds:.2f}s")
    print(f"[RESULT] command={result.command!r}")
    print(
        f"[LEDGER] previous_status={update.previous_status!r} -> new_status={update.new_status!r}"
    )
    print(f"[LEDGER] notes={update.notes!r}")
    if result.stdout:
        print(f"[STDOUT] {result.stdout[:500]!r}")
    if result.stderr:
        print(f"[STDERR] {result.stderr[:500]!r}")
    return 0


def _handle_status(args: argparse.Namespace) -> int:
    """Handle the 'status' subcommand."""
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    repo_root = args.repo_root.resolve() if args.repo_root else pathlib.Path.cwd()
    jobs_db_path = _resolve_jobs_db(args.jobs_db, repo_root)

    registry = JobRegistry(jobs_db_path)
    job = registry.get(args.job_id)
    registry.close()

    if job is None:
        print(f"[mir_executor] job_id not found: {args.job_id!r}", file=sys.stderr)
        return 1

    print(f"[STATUS] job_id={job.job_id}")
    print(f"[STATUS] status={job.status}")
    print(f"[STATUS] change_id={job.change_id!r} category={job.category!r}")
    print(f"[STATUS] family={job.family!r} repo_root={job.repo_root!r}")
    print(f"[STATUS] dispatch_brief_path={job.dispatch_brief_path!r}")
    print(f"[STATUS] resume_count={job.resume_count} last_resumed_at={job.last_resumed_at!r}")
    print(f"[STATUS] started_at={job.started_at} completed_at={job.completed_at}")
    print(f"[STATUS] cancel_requested={job.cancel_requested}")
    return 0


def _handle_result(args: argparse.Namespace) -> int:
    """Handle the 'result' subcommand."""
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    repo_root = args.repo_root.resolve() if args.repo_root else pathlib.Path.cwd()
    jobs_db_path = _resolve_jobs_db(args.jobs_db, repo_root)

    registry = JobRegistry(jobs_db_path)
    job = registry.get(args.job_id)
    registry.close()

    if job is None:
        print(f"[mir_executor] job_id not found: {args.job_id!r}", file=sys.stderr)
        return 1

    if job.status == "running":
        print(f"[RESULT] job_id={job.job_id} status=running (not yet completed)")
        return 0

    print(f"[RESULT] job_id={job.job_id}")
    print(f"[RESULT] status={job.status}")
    print(f"[RESULT] exit_code={job.exit_code}")
    print(f"[RESULT] dispatch_brief_path={job.dispatch_brief_path!r}")
    print(f"[RESULT] resume_count={job.resume_count} last_resumed_at={job.last_resumed_at!r}")
    print(f"[RESULT] duration_seconds={job.duration_seconds}")
    if job.stdout:
        print(f"[STDOUT] {job.stdout[:500]!r}")
    if job.stderr:
        print(f"[STDERR] {job.stderr[:500]!r}")
    return 0


def _handle_cancel(args: argparse.Namespace) -> int:
    """Handle the 'cancel' subcommand."""
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    repo_root = args.repo_root.resolve() if args.repo_root else pathlib.Path.cwd()
    jobs_db_path = _resolve_jobs_db(args.jobs_db, repo_root)

    registry = JobRegistry(jobs_db_path)
    found = registry.cancel(args.job_id)
    registry.close()

    if not found:
        print(f"[mir_executor] job_id not found: {args.job_id!r}", file=sys.stderr)
        return 1

    print(f"[CANCEL] cancel_requested=True for job_id={args.job_id}")
    return 0


def _handle_resume(args: argparse.Namespace) -> int:
    """Handle the 'resume' subcommand."""
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    repo_root = args.repo_root.resolve() if args.repo_root else pathlib.Path.cwd()
    jobs_db_path = _resolve_jobs_db(args.jobs_db, repo_root)
    registry = JobRegistry(jobs_db_path)
    job = registry.get(args.job_id)

    if job is None:
        registry.close()
        print(f"[mir_executor] job_id not found: {args.job_id!r}", file=sys.stderr)
        return 1
    if not job.dispatch_brief_path:
        registry.close()
        print(
            f"[mir_executor] job_id {args.job_id!r} has no dispatch_brief_path to resume from.",
            file=sys.stderr,
        )
        return 1

    executor = MirExecutor(
        repo_root=pathlib.Path(job.repo_root),
        dispatch_brief_path=pathlib.Path(job.dispatch_brief_path),
    )

    resumed_at = _utc_now()
    registry.mark_resumed(job.job_id, resumed_at=resumed_at)
    try:
        if args.use_async:
            result, update = asyncio.run(
                executor.execute_async(
                    change_id=job.change_id,
                    category=job.category,
                    codex_args=job.codex_args,
                    timeout_seconds=args.timeout,
                )
            )
        else:
            result, update = executor.execute(
                change_id=job.change_id,
                category=job.category,
                codex_args=job.codex_args,
                timeout_seconds=args.timeout,
            )
    except (FileNotFoundError, KeyError, PermissionError) as exc:
        registry.update_status(job.job_id, "failed", stderr=str(exc), completed_at=_utc_now())
        registry.close()
        print(f"[mir_executor] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        registry.update_status(
            job.job_id,
            "timeout",
            stderr=f"Codex timeout after {exc.timeout}s: {exc}",
            completed_at=_utc_now(),
        )
        registry.close()
        print(f"[mir_executor] Codex timeout after {exc.timeout}s: {exc}", file=sys.stderr)
        return 1
    except TimeoutError:
        registry.update_status(
            job.job_id,
            "timeout",
            stderr=f"async timeout after {args.timeout}s",
            completed_at=_utc_now(),
        )
        registry.close()
        print(f"[mir_executor] async timeout after {args.timeout}s", file=sys.stderr)
        return 1
    except ValueError as exc:
        registry.update_status(job.job_id, "failed", stderr=str(exc), completed_at=_utc_now())
        registry.close()
        print(f"[mir_executor] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    registry.update_status(
        job.job_id,
        "completed" if result.exit_code == 0 else "failed",
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_seconds=result.duration_seconds,
        completed_at=_utc_now(),
    )
    registry.close()

    print(
        f"[RESUME] job_id={job.job_id} dispatch_brief={job.dispatch_brief_path!r} "
        f"resumed_at={resumed_at}"
    )
    print(f"[RESULT] change_id={update.change_id!r} category={update.category!r}")
    print(f"[RESULT] codex exit_code={result.exit_code} duration={result.duration_seconds:.2f}s")
    print(f"[RESULT] command={result.command!r}")
    return 0


def _handle_list_jobs(args: argparse.Namespace) -> int:
    """Handle the 'list-jobs' subcommand."""
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    repo_root = args.repo_root.resolve() if args.repo_root else pathlib.Path.cwd()
    jobs_db_path = _resolve_jobs_db(args.jobs_db, repo_root)

    registry = JobRegistry(jobs_db_path)
    jobs = registry.list_jobs(status_filter=args.status)
    registry.close()

    if not jobs:
        filter_info = f" (status={args.status!r})" if args.status else ""
        print(f"[LIST] no jobs found{filter_info}")
        return 0

    for job in jobs:
        print(
            f"[JOB] job_id={job.job_id} status={job.status} "
            f"change_id={job.change_id!r} category={job.category!r} "
            f"dispatch_brief_path={job.dispatch_brief_path!r} "
            f"resume_count={job.resume_count} "
            f"started_at={job.started_at}"
        )
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.subcommand is None:
        parser.print_help()
        sys.exit(0)

    if args.subcommand == "execute":
        rc = _handle_execute(args)
    elif args.subcommand == "status":
        rc = _handle_status(args)
    elif args.subcommand == "result":
        rc = _handle_result(args)
    elif args.subcommand == "cancel":
        rc = _handle_cancel(args)
    elif args.subcommand == "resume":
        rc = _handle_resume(args)
    elif args.subcommand == "list-jobs":
        rc = _handle_list_jobs(args)
    else:
        parser.print_help()
        rc = 0

    if rc != 0:
        sys.exit(rc)
    return rc
