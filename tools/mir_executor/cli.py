"""
cli.py
------
Argparse CLI entry point for the your-harness Executor.

Usage:
    python -m tools.mir_executor execute \\
        --change-id <id> \\
        --category <name> \\
        (--codex-args "<quoted string>" | --codex-args-file <path>) \\
        [--timeout <seconds>] \\
        (--family <slug> | --repo-root <path>)
        [--background | -b]
        [--allow-harness-self-modify]
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
import tomllib
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
_MERGED_FINALIZE_ACTIONS = {"merged", "merged-but-cleanup-failed"}
_DISPATCH_BACKENDS = frozenset({"codex", "claude"})
_DEFAULT_DISPATCH_PROMPT = (
    "Read the task brief at .mir-dispatch/brief.md and implement it fully "
    "in this worktree. Do not edit tasks/plan.md."
)
_CODEX_EXEC_FLAGS_WITH_VALUE = frozenset(
    {
        "--approval",
        "--approval-policy",
        "--add-dir",
        "--cd",
        "--color",
        "--config",
        "--config-profile",
        "--cwd",
        "--disable",
        "--enable",
        "--image",
        "--local-provider",
        "--model",
        "--output-last-message",
        "--output-schema",
        "--profile",
        "--reasoning-effort",
        "--sandbox",
        "-C",
        "-c",
        "-i",
        "-m",
        "-o",
        "-p",
        "-s",
    }
)
_CODEX_EXEC_BOOLEAN_FLAGS = frozenset(
    {
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
        "--ephemeral",
        "--full-auto",
        "--help",
        "--ignore-rules",
        "--ignore-user-config",
        "--json",
        "--no-color",
        "--oss",
        "--skip-git-repo-check",
        "--strict-config",
        "--version",
        "-V",
        "-h",
    }
)


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
    codex_args_group = exec_p.add_mutually_exclusive_group(required=True)
    codex_args_group.add_argument(
        "--codex-args",
        metavar="QUOTED_STRING",
        help=(
            "Arguments for legacy Codex invocation. In --dispatch mode, "
            "exec-shaped flags are dropped and the positional prompt is sent "
            "to the MCP Codex backend."
        ),
    )
    codex_args_group.add_argument(
        "--codex-args-file",
        type=pathlib.Path,
        metavar="PATH",
        help=(
            "Read UTF-8 file content and use it as one raw positional prompt "
            "argument, without shlex tokenization."
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
        "--model",
        default=None,
        metavar="MODEL",
        help=(
            "Optional Codex model name (e.g. a codex model id); omit to inherit "
            "Codex defaults."
        ),
    )
    exec_p.add_argument(
        "--reasoning-effort",
        default=None,
        metavar="EFFORT",
        help=(
            "Optional Codex model_reasoning_effort (free string); omit to inherit "
            "Codex defaults."
        ),
    )
    exec_p.add_argument(
        "--stall-timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help=(
            "Optional no-progress MCP stall timeout in seconds; omit to inherit "
            "policy monitoring defaults."
        ),
    )
    exec_p.add_argument(
        "--jobs-db",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="Override path to jobs.db (default: <repo_root>/tasks/jobs.db).",
    )
    root_group = exec_p.add_mutually_exclusive_group(required=True)
    root_group.add_argument(
        "--family",
        metavar="SLUG",
        help=(
            "Family slug to look up in the profile_compiler registry "
            "(e.g. '<example-family>'). Resolves to the registered absolute repo root."
        ),
    )
    root_group.add_argument(
        "--repo-root",
        type=pathlib.Path,
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
    exec_p.add_argument(
        "--dispatch",
        action="store_true",
        default=False,
        dest="dispatch",
        help=(
            "ADR-60 R2/R3: run the codex-exec dispatch helper (worktree + finite "
            "fallback + outage guard) instead of the legacy background runner."
        ),
    )
    exec_p.add_argument(
        "--execution-backend",
        choices=sorted(_DISPATCH_BACKENDS),
        default=None,
        dest="execution_backend",
        metavar="BACKEND",
        help=(
            "ADR-61 dispatch-only backend request. Used only when the sub-agent "
            "policy mode is select; force_codex and unknown values fail closed to codex."
        ),
    )
    exec_p.add_argument(
        "--expect-changes",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="expect_changes",
        help=(
            "Require a dispatch to produce a git diff before merge (default: true). "
            "Use --no-expect-changes for legitimate no-op or verify-only dispatches."
        ),
    )
    exec_p.add_argument(
        "--allow-harness-self-modify",
        action="store_true",
        default=False,
        dest="allow_harness_self_modify",
        help=(
            "Allow dispatch merge-back for liftable harness prefixes "
            "(.claude/, .ai-harness/, config/, docs/) when also allowlisted. "
            "tasks/ remains denied."
        ),
    )
    exec_p.add_argument(
        "--allow-path",
        action="append",
        dest="allow_paths",
        default=argparse.SUPPRESS,
        metavar="PATH",
        help="Repeatable ADR-60 dispatch merge allowlist path.",
    )
    exec_p.add_argument(
        "--verify-cmd",
        action="append",
        dest="verify_cmds",
        default=argparse.SUPPRESS,
        metavar="COMMAND",
        help="Repeatable ADR-60 dispatch verification command to re-run before merge.",
    )
    exec_p.add_argument(
        "--dispatch-brief",
        type=pathlib.Path,
        default=None,
        dest="dispatch_brief",
        metavar="PATH",
        help=(
            "Persisted DispatchBrief JSON. In --dispatch mode, expanded_goal "
            "is used as the MCP prompt when --codex-args contains no prompt positional."
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
                completed_at=_utc_now(),
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


def _resolve_dispatch_backend(
    sub_agent_policy: object,
    *,
    requested_backend: str | None,
    repo_slug: str | None,
) -> str:
    """Resolve the effective dispatch runner backend, fail-closed to codex."""
    mode = getattr(sub_agent_policy, "mode", "force_codex")
    per_project = getattr(sub_agent_policy, "per_project", {})
    if mode == "force_codex":
        return "codex"
    if mode == "force_claude":
        return "claude"
    if mode == "select":
        return requested_backend if requested_backend in _DISPATCH_BACKENDS else "codex"
    if mode == "obey_user":
        return requested_backend if requested_backend in _DISPATCH_BACKENDS else "codex"
    if mode == "unrestricted":
        return requested_backend if requested_backend in _DISPATCH_BACKENDS else "codex"
    if mode == "per_project" and isinstance(per_project, dict):
        if not repo_slug:
            return "codex"
        backend = per_project.get(repo_slug)
        return backend if backend in _DISPATCH_BACKENDS else "codex"
    return "codex"


def _resolve_repo_policy_slug(repo_root: pathlib.Path) -> str | None:
    """Resolve the slug used for per-project policy lookup."""
    profile_path = repo_root / ".mir" / "repo-profile.toml"
    try:
        with profile_path.open("rb") as fh:
            profile = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None

    repo_section = profile.get("repo")
    if not isinstance(repo_section, dict):
        return None
    slug = repo_section.get("slug")
    if isinstance(slug, str) and slug.strip():
        return slug.strip()
    return None


def _string_route_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _resolve_policy_runtime_options(
    sub_agent_policy: object,
    *,
    category: str,
    model: str | None,
    reasoning_effort: str | None,
    stall_timeout: float | None,
) -> tuple[str | None, str | None, float | None]:
    """Resolve policy routing/monitoring defaults without overriding CLI flags."""
    category_route: dict[str, object] = {}
    routing_for_category = getattr(sub_agent_policy, "routing_for_category", None)
    if callable(routing_for_category):
        route = routing_for_category(category)
        if isinstance(route, dict):
            category_route = route

    category_prefer: list[dict[str, object]] = []
    routing_prefer_for_category = getattr(
        sub_agent_policy,
        "routing_prefer_for_category",
        None,
    )
    if callable(routing_prefer_for_category):
        prefer = routing_prefer_for_category(category)
        if isinstance(prefer, list):
            category_prefer = [item for item in prefer if isinstance(item, dict)]

    primary_route = category_prefer[0] if category_prefer else category_route
    policy_model = _string_route_value(primary_route.get("model"))
    policy_reasoning_effort = _string_route_value(primary_route.get("reasoning_effort"))

    routing_default_model = getattr(sub_agent_policy, "routing_default_model", None)
    if policy_model is None and callable(routing_default_model):
        policy_model = routing_default_model()

    routing_default_reasoning_effort = getattr(
        sub_agent_policy,
        "routing_default_reasoning_effort",
        None,
    )
    if policy_reasoning_effort is None and callable(routing_default_reasoning_effort):
        policy_reasoning_effort = routing_default_reasoning_effort()

    monitoring_stall_timeout_seconds = getattr(
        sub_agent_policy,
        "monitoring_stall_timeout_seconds",
        None,
    )
    policy_stall_timeout: float | None = None
    if callable(monitoring_stall_timeout_seconds):
        policy_stall_timeout = monitoring_stall_timeout_seconds()

    return (
        model if model is not None else policy_model,
        reasoning_effort if reasoning_effort is not None else policy_reasoning_effort,
        stall_timeout if stall_timeout is not None else policy_stall_timeout,
    )


def _build_dispatch_runner(
    dispatch_module: object,
    *,
    backend: str,
    repo_root: pathlib.Path,
    prompt: str,
    timeout_seconds: int,
    model: str | None = None,
    reasoning_effort: str | None = None,
    stall_timeout: float | None = None,
) -> object:
    """Build the runner for the resolved backend."""
    if backend == "claude":
        return dispatch_module.build_claude_runner(
            repo_root,
            timeout_seconds=timeout_seconds,
        )
    runner_kwargs: dict[str, object] = {"timeout_seconds": timeout_seconds}
    if model is not None:
        runner_kwargs["model"] = model
    if reasoning_effort is not None:
        runner_kwargs["reasoning_effort"] = reasoning_effort
    if stall_timeout is not None:
        runner_kwargs["stall_timeout"] = stall_timeout
    return dispatch_module.build_codex_mcp_runner(repo_root, prompt, **runner_kwargs)


def _prompt_from_codex_args(codex_args: list[str]) -> str:
    """Extract the prompt positional from an exec-shaped Codex argv."""
    prompt_parts: list[str] = []
    index = 0
    while index < len(codex_args):
        token = codex_args[index]
        if token == "--":
            prompt_parts = codex_args[index + 1 :]
            break
        if token == "exec" and not prompt_parts:
            index += 1
            continue

        flag_name = token.split("=", 1)[0]
        if flag_name in _CODEX_EXEC_FLAGS_WITH_VALUE:
            index += 1 if "=" in token else 2
            continue
        if flag_name in _CODEX_EXEC_BOOLEAN_FLAGS:
            index += 1
            continue
        if token.startswith("-") and not prompt_parts:
            index += 1
            continue

        prompt_parts = codex_args[index:]
        break

    if len(prompt_parts) == 1:
        return prompt_parts[0]
    return " ".join(prompt_parts).strip()


def _prompt_from_dispatch_brief(path: pathlib.Path | None) -> str:
    """Load DispatchBrief.expanded_goal when a persisted brief is supplied."""
    if path is None:
        return ""
    from mir.core.conductor.dispatch_brief import load_dispatch_brief  # noqa: PLC0415

    return load_dispatch_brief(path).expanded_goal.strip()


def _resolve_dispatch_prompt(
    codex_args: list[str],
    dispatch_brief_path: pathlib.Path | None,
) -> str:
    """Resolve the structured prompt sent to the MCP Codex backend."""
    prompt = _prompt_from_codex_args(codex_args)
    if prompt:
        return prompt
    prompt = _prompt_from_dispatch_brief(dispatch_brief_path)
    if prompt:
        return prompt
    return _DEFAULT_DISPATCH_PROMPT


def _resolve_execute_codex_args(args: argparse.Namespace) -> list[str]:
    """Resolve execute prompt source into persisted argv-shaped codex_args."""
    codex_args_text = getattr(args, "codex_args", None)
    codex_args_file = getattr(args, "codex_args_file", None)
    has_codex_args = codex_args_text is not None
    has_codex_args_file = codex_args_file is not None
    if has_codex_args == has_codex_args_file:
        raise ValueError("exactly one of --codex-args or --codex-args-file must be provided")
    if has_codex_args_file:
        return [pathlib.Path(codex_args_file).read_text(encoding="utf-8")]
    return shlex.split(codex_args_text)


def _handle_dispatch(
    args: argparse.Namespace,
    repo_root: pathlib.Path,
    codex_args: list[str] | None = None,
) -> int:
    """Route execute --background --dispatch through the ADR-60 helper."""
    from tools.mir_executor import dispatch  # noqa: PLC0415
    from tools.mir_executor.jobs import JobRecord, JobRegistry  # noqa: PLC0415
    from tools.mir_executor.policy import load_sub_agent_policy  # noqa: PLC0415

    if codex_args is None:
        codex_args = _resolve_execute_codex_args(args)
    dispatch_brief_path = (
        args.dispatch_brief.resolve() if getattr(args, "dispatch_brief", None) else None
    )
    prompt = _resolve_dispatch_prompt(codex_args, dispatch_brief_path)
    jobs_db_path = _resolve_jobs_db(args.jobs_db, repo_root)
    prior = dispatch.count_consecutive_codex_failures(
        jobs_db_path,
        change_id_prefix=args.change_id,
    )
    job_id = uuid.uuid4().hex
    registry = JobRegistry(jobs_db_path)
    registry.insert(
        JobRecord(
            job_id=job_id,
            change_id=args.change_id,
            category=args.category,
            family=args.family,
            repo_root=str(repo_root),
            codex_args=codex_args,
            dispatch_brief_path=(
                str(dispatch_brief_path) if dispatch_brief_path is not None else None
            ),
            allow_harness_self_modify=args.allow_harness_self_modify,
            timeout_seconds=args.timeout,
            status="running",
            started_at=_utc_now(),
        )
    )
    sub_agent_policy = load_sub_agent_policy(repo_root)
    model, reasoning_effort, stall_timeout = _resolve_policy_runtime_options(
        sub_agent_policy,
        category=args.category,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        stall_timeout=getattr(args, "stall_timeout", None),
    )
    repo_slug = args.family or _resolve_repo_policy_slug(repo_root)
    backend = _resolve_dispatch_backend(
        sub_agent_policy,
        requested_backend=getattr(args, "execution_backend", None),
        repo_slug=repo_slug,
    )
    runner = _build_dispatch_runner(
        dispatch,
        backend=backend,
        repo_root=repo_root,
        prompt=prompt,
        timeout_seconds=args.timeout,
        model=model,
        reasoning_effort=reasoning_effort,
        stall_timeout=stall_timeout,
    )
    try:
        outcome = dispatch.run_dispatch(
            repo_root,
            dispatch_id=job_id,
            brief_text=prompt,
            codex_runner=runner,
            claude_fallback=None,
            prior_consecutive_codex_failures=prior,
        )

        final = None
        if outcome.worktree is not None:
            final = dispatch.finalize_dispatch(
                outcome.worktree,
                repo_root,
                outcome,
                allowlist=getattr(args, "allow_paths", None) or [],
                verification_commands=getattr(args, "verify_cmds", None) or [],
                expect_changes=args.expect_changes,
                allow_harness_self_modify=args.allow_harness_self_modify,
            )

        # status is the codex-lane outcome for the outage guard; task success requires merge.
        job_status = "completed" if outcome.status == "completed" else "failed"
        task_exit = (
            0
            if final is not None and final.action in _MERGED_FINALIZE_ACTIONS
            else 1
        )
        if outcome.status == "blocked":
            print(
                "[DISPATCH] blocked with no fallback under sub-agent policy; "
                "see docs/harness-engineering/codex-dispatch-failure-diagnostic.md",
                file=sys.stderr,
            )
        registry.update_status(
            job_id,
            job_status,
            exit_code=task_exit,
            stdout=f"artifacts=tasks/dispatch/{job_id}",
            completed_at=_utc_now(),
        )
    finally:
        registry.close()

    print(
        f"[DISPATCH] status={outcome.status} attempts={outcome.attempts} "
        f"fell_back={outcome.fell_back} reason={outcome.blocked_reason!r}"
    )
    if final is not None:
        print(
            f"[FINALIZE] action={final.action} reason={final.reason!r} "
            f"merged={final.merged_files}"
        )
    return (
        0
        if final is not None and final.action in _MERGED_FINALIZE_ACTIONS
        else 1
    )


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _handle_execute(args: argparse.Namespace) -> int:
    """Handle the 'execute' subcommand."""
    try:
        codex_args = _resolve_execute_codex_args(args)
    except ValueError as exc:
        print(f"[mir_executor] argument parse error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"[mir_executor] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.family is not None:
        # Lazy import avoids circular dependency
        from tools.profile_compiler.cli import resolve_family_path  # noqa: PLC0415
        try:
            repo_root = resolve_family_path(args.family).resolve()
        except KeyError as exc:
            print(f"[mir_executor] Unknown family slug: {args.family!r}. {exc}", file=sys.stderr)
            return 1
    else:
        repo_root = args.repo_root.resolve()

    executor = MirExecutor(repo_root=repo_root)
    from tools.mir_executor.policy import load_sub_agent_policy  # noqa: PLC0415

    sub_agent_policy = load_sub_agent_policy(repo_root)
    model, reasoning_effort, stall_timeout = _resolve_policy_runtime_options(
        sub_agent_policy,
        category=args.category,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        stall_timeout=getattr(args, "stall_timeout", None),
    )

    if args.background:
        if args.dispatch:
            return _handle_dispatch(args, repo_root, codex_args)
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
            family=args.family,
            repo_root=str(repo_root),
            codex_args=codex_args,
            allow_harness_self_modify=args.allow_harness_self_modify,
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
                model=model,
                reasoning_effort=reasoning_effort,
                stall_timeout=stall_timeout,
            )
        )
        registry.close()
        return 0

    # Non-background (sync or async) path — BC unchanged.
    try:
        if args.use_async:
            execute_kwargs: dict[str, object] = {"timeout_seconds": args.timeout}
            if model is not None:
                execute_kwargs["model"] = model
            if reasoning_effort is not None:
                execute_kwargs["reasoning_effort"] = reasoning_effort
            if stall_timeout is not None:
                execute_kwargs["stall_timeout"] = stall_timeout
            result, update = asyncio.run(
                executor.execute_async(
                    change_id=args.change_id,
                    category=args.category,
                    codex_args=codex_args,
                    **execute_kwargs,
                )
            )
        else:
            execute_kwargs = {"timeout_seconds": args.timeout}
            if model is not None:
                execute_kwargs["model"] = model
            if reasoning_effort is not None:
                execute_kwargs["reasoning_effort"] = reasoning_effort
            if stall_timeout is not None:
                execute_kwargs["stall_timeout"] = stall_timeout
            result, update = executor.execute(
                change_id=args.change_id,
                category=args.category,
                codex_args=codex_args,
                **execute_kwargs,
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
    print(f"[STATUS] allow_harness_self_modify={job.allow_harness_self_modify}")
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
    print(f"[RESULT] allow_harness_self_modify={job.allow_harness_self_modify}")
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
        f"allow_harness_self_modify={job.allow_harness_self_modify} resumed_at={resumed_at}"
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
