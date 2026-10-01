"""Job operations with the CLI facade passed as the runtime dependency."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys


async def _run_background(
    api,
    job_id: str,
    executor: object,
    change_id: str,
    category: str,
    codex_args: list[str],
    timeout_seconds: int | None,
    jobs_db_path: pathlib.Path,
    model: str | None = None,
    reasoning_effort: str | None = None,
    stall_timeout: float | None = None,
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
                completed_at=api._utc_now(),
            )
            return

        run_kwargs: dict[str, object] = {"timeout_seconds": timeout_seconds}
        if model is not None:
            run_kwargs["model"] = model
        if reasoning_effort is not None:
            run_kwargs["reasoning_effort"] = reasoning_effort
        if stall_timeout is not None:
            run_kwargs["stall_timeout"] = stall_timeout
        result = await executor.run_codex_async(codex_args, **run_kwargs)

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
            completed_at=api._utc_now(),
        )
    except Exception as exc:  # noqa: BLE001
        registry.update_status(
            job_id,
            "failed",
            stderr=str(exc),
            completed_at=api._utc_now(),
        )
    finally:
        registry.close()


def _blocked_reason(payload: str | None) -> str | None:
    """Extract the additive blocked-reason marker from a stored result payload."""
    if not payload:
        return None
    marker = "blocked_reason="
    if marker not in payload:
        return None
    return payload.split(marker, 1)[1].split()[0] or None


def _handle_status(api, args: argparse.Namespace) -> int:
    """Handle the 'status' subcommand."""
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    repo_root = args.repo_root.resolve() if args.repo_root else pathlib.Path.cwd()
    jobs_db_path = api._resolve_jobs_db(args.jobs_db, repo_root)

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
    print(f"[STATUS] allow_harness_self_modify={job.allow_harness_self_modify}")
    print(
        f"[STATUS] resume_count={job.resume_count} last_resumed_at={job.last_resumed_at!r}"
    )
    print(f"[STATUS] started_at={job.started_at} completed_at={job.completed_at}")
    print(f"[STATUS] cancel_requested={job.cancel_requested}")
    blocked_reason = _blocked_reason(job.stdout) or _blocked_reason(job.stderr)
    if blocked_reason is not None:
        print(f"[STATUS] blocked_reason={blocked_reason}")
    return 0


def _handle_result(api, args: argparse.Namespace) -> int:
    """Handle the 'result' subcommand."""
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    repo_root = args.repo_root.resolve() if args.repo_root else pathlib.Path.cwd()
    jobs_db_path = api._resolve_jobs_db(args.jobs_db, repo_root)

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
    print(f"[RESULT] allow_harness_self_modify={job.allow_harness_self_modify}")
    print(
        f"[RESULT] resume_count={job.resume_count} last_resumed_at={job.last_resumed_at!r}"
    )
    print(f"[RESULT] duration_seconds={job.duration_seconds}")
    if job.stdout:
        print(f"[STDOUT] {job.stdout[:500]!r}")
    if job.stderr:
        print(f"[STDERR] {job.stderr[:500]!r}")
    return 0


def _handle_cancel(api, args: argparse.Namespace) -> int:
    """Handle the 'cancel' subcommand."""
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    repo_root = args.repo_root.resolve() if args.repo_root else pathlib.Path.cwd()
    jobs_db_path = api._resolve_jobs_db(args.jobs_db, repo_root)

    registry = JobRegistry(jobs_db_path)
    found = registry.cancel(args.job_id)
    registry.close()

    if not found:
        print(f"[mir_executor] job_id not found: {args.job_id!r}", file=sys.stderr)
        return 1

    print(f"[CANCEL] cancel_requested=True for job_id={args.job_id}")
    return 0


def _handle_resume(api, args: argparse.Namespace) -> int:
    """Resume the original job through the isolated dispatch path."""
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    root = args.repo_root.resolve() if args.repo_root else pathlib.Path.cwd()
    db = api._resolve_jobs_db(args.jobs_db, root)
    registry = JobRegistry(db)
    job = registry.get(args.job_id)
    registry.close()
    if job is None or not job.dispatch_brief_path:
        print(
            "[mir_executor] resume requires an existing job with a dispatch_brief_path",
            file=sys.stderr,
        )
        return 1
    options = None
    if job.dispatch_options_json is not None:
        try:
            options = json.loads(job.dispatch_options_json)
            if not isinstance(options, dict):
                raise ValueError("stored dispatch options must be a JSON object")
            brief = options.get("dispatch_brief") or job.dispatch_brief_path
            digest = options.get("brief_sha256")
            if brief is not None:
                if not isinstance(brief, str) or not isinstance(digest, str):
                    raise ValueError("stored dispatch brief requires a sha256 digest")
                current = hashlib.sha256(pathlib.Path(brief).read_bytes()).hexdigest()
                if current != digest:
                    raise ValueError("dispatch brief sha256 changed; refusing resume")
        except (OSError, TypeError, ValueError) as exc:
            print(f"[mir_executor] resume integrity error: {exc}", file=sys.stderr)
            return 1
    execute_args = api._build_parser(pathlib.Path(job.repo_root)).parse_args(
        ["execute", "--dispatch"]
    )
    execute_args.repo_root = pathlib.Path(job.repo_root)
    execute_args.jobs_db = str(db)
    execute_args.resume_job_id = job.job_id
    execute_args.dispatch_brief = pathlib.Path(job.dispatch_brief_path)
    execute_args.execution_backend = job.execution_backend
    execute_args.model = job.resolved_model
    execute_args.reasoning_effort = job.resolved_reasoning_effort
    execute_args.target_agent = job.target_agent
    execute_args.agent_definition_path = job.agent_definition_path
    execute_args.family = job.family
    execute_args.category = job.category
    execute_args.timeout = (
        args.timeout if args.timeout is not None else job.timeout_seconds
    )
    execute_args.allow_harness_self_modify = job.allow_harness_self_modify
    if options is not None:
        for name in (
            "allow_paths", "verify_cmds", "expect_changes", "change_id", "category",
            "model", "reasoning_effort", "max_codex_attempts", "execution_backend",
            "finalize_lock_timeout", "stall_timeout",
        ):
            if name in options:
                setattr(execute_args, name, options[name])
        for name in ("dispatch_brief", "artifacts_dir"):
            if name in options:
                value = options[name]
                setattr(execute_args, name, pathlib.Path(value) if value is not None else None)
    from tools.mir_executor.local_hooks import local_config, validate_timeout

    try:
        if "timeout_seconds_range" in local_config(execute_args.repo_root):
            for value in (execute_args.timeout, execute_args.stall_timeout,
                          execute_args.finalize_lock_timeout):
                validate_timeout(execute_args.repo_root, value)
    except (OSError, TypeError, ValueError) as exc:
        print(f"[mir_executor] resume timeout error: {exc}", file=sys.stderr)
        return 1
    # Legacy resume does not assume a synthetic change ID is a ledger ID.
    print(
        f"[RESUME] job_id={job.job_id} "
        f"allow_harness_self_modify={job.allow_harness_self_modify}"
    )
    with api.writer_scope(execute_args.repo_root):
        if options is None:
            api.invoke_hook(
                execute_args.repo_root, "pre_execute", execute_args, execute_args.repo_root
            )
        else:
            try:
                execute_args.repo_root = api._prepare_execute_root(execute_args)
            except (OSError, TypeError, ValueError) as exc:
                print(f"[mir_executor] resume root error: {exc}", file=sys.stderr)
                return 1
        return api._handle_dispatch(
            execute_args, execute_args.repo_root, job.codex_args
        )


def _handle_list_jobs(api, args: argparse.Namespace) -> int:
    """Handle the 'list-jobs' subcommand."""
    from tools.mir_executor.jobs import JobRegistry  # noqa: PLC0415

    repo_root = args.repo_root.resolve() if args.repo_root else pathlib.Path.cwd()
    jobs_db_path = api._resolve_jobs_db(args.jobs_db, repo_root)

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
            f" blocked_reason={(_blocked_reason(job.stdout) or _blocked_reason(job.stderr))!r}"
        )
    return 0


def _handle_sweep(api, args: argparse.Namespace) -> int:
    """Handle the dry-run-by-default run-state sweep."""
    from tools.mir_executor.sweep import (  # noqa: PLC0415
        sweep_run_state,
        sweep_terminal_artifacts,
    )

    repo_root = args.repo_root.resolve()
    jobs_db_path = api._resolve_jobs_db(args.jobs_db, repo_root)
    result = sweep_run_state(
        repo_root,
        jobs_db_path,
        grace_seconds=args.grace_seconds,
        apply=args.apply,
    )
    result["terminal_artifacts"] = sweep_terminal_artifacts(
        repo_root, jobs_db_path, apply=args.apply
    )
    print(json.dumps(result, separators=(",", ":")))
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
