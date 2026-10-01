"""
cli.py
------
Argparse CLI entry point for the Mir Executor.

Usage:
    python -m tools.mir_executor execute \\
        [--change-id <id> --category <name>] \\
        (--codex-args "<quoted string>" | --codex-args-file <path>) \\
        [--timeout <seconds>] \\
        [--repo-root <path>]
        [--background | -b]
        [--allow-harness-self-modify]
        [--jobs-db <path>]

    python -m tools.mir_executor status --job-id <id> [--jobs-db <path>]
    python -m tools.mir_executor result --job-id <id> [--jobs-db <path>]
    python -m tools.mir_executor cancel --job-id <id> [--jobs-db <path>]
    python -m tools.mir_executor resume --job-id <id> [--jobs-db <path>]
    python -m tools.mir_executor list-jobs [--status <status>] [--jobs-db <path>]

Exit codes:
    0 — execution succeeded (and a selected ledger update, when requested, succeeded).
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
import hashlib
import json
import pathlib
import re
import shlex
import subprocess
import sys
import tomllib
import uuid

from tools.mir_executor import cli_jobs
from tools.mir_executor.cli_parser import _build_parser
from tools.mir_executor.executor import MirExecutor
from tools.mir_executor.local_hooks import (
    emit_job_event,
    has_hook,
    invoke_hook,
    job_event_scope,
    local_config,
    validate_timeout,
    writer_scope,
)

_DEFAULT_JOBS_DB_RELPATH = pathlib.Path("tasks") / "jobs.db"
_MERGED_FINALIZE_ACTIONS = {
    "merged",
    "merged-but-cleanup-failed",
    "reviewed",
    "reviewed-but-cleanup-failed",
}
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


def _resolve_dispatch_backend(
    sub_agent_policy: object,
    *,
    requested_backend: str | None,
    repo_slug: str | None = None,
    repo_root: pathlib.Path | None = None,
    declared_backend: str | None = None,
) -> str:
    """Resolve backend using the policy's declared sequence and project data."""
    mode_accessor = getattr(sub_agent_policy, "effective_delegation_mode", None)
    mode = (
        mode_accessor()
        if callable(mode_accessor)
        else getattr(sub_agent_policy, "mode", "select")
    )
    if mode == "obey_user":
        mode = "user_command_priority"
    if mode in {"force_codex", "force_claude"}:
        return mode.removeprefix("force_")
    fallback = getattr(sub_agent_policy, "default_backend", "codex")
    if fallback not in _DISPATCH_BACKENDS:
        fallback = "codex"
    per_project = getattr(sub_agent_policy, "per_project", {})
    if isinstance(per_project, dict) and repo_slug:
        project_backend = per_project.get(repo_slug)
        if isinstance(project_backend, dict):
            project_backend = project_backend.get("backend")
        if isinstance(project_backend, str):
            declared_backend = project_backend
    if declared_backend is None and repo_root is not None:
        accessor = getattr(sub_agent_policy, "delegation_project_declaration", None)
        spec = (
            accessor()
            if callable(accessor)
            else getattr(sub_agent_policy, "delegation", {}).get(
                "project_declaration", {}
            )
        )
        if not isinstance(spec, dict):
            spec = {}
        path = spec.get("path", ".mir/repo-profile.toml")
        section = spec.get("section", "execution")
        try:
            with (repo_root / path).open("rb") as handle:
                profile = tomllib.load(handle)
            declaration = profile.get(section, {})
            fields = spec.get("fields", ["backend", "delegated_execution_contract"])
            if not isinstance(fields, list):
                fields = []
            found = set()
            for field in fields:
                value = declaration.get(field) if isinstance(field, str) else None
                if isinstance(value, str):
                    found.update(
                        set(re.findall(r"[a-z0-9]+", value.lower()))
                        & _DISPATCH_BACKENDS
                    )
            declared_backend = next(iter(found)) if len(found) == 1 else None
        except (OSError, TypeError, tomllib.TOMLDecodeError):
            pass
    accessor = getattr(sub_agent_policy, "delegation_resolution_order", None)
    order = (
        accessor()
        if callable(accessor)
        else getattr(sub_agent_policy, "resolution_order", ())
    )
    if callable(order):
        order = order()
    order = order or ("user_command", "project_declaration", "default_backend")
    enabled = {
        "user_command_priority": {
            "user_command",
            "project_declaration",
            "default_backend",
        },
        "per_project": {"project_declaration", "default_backend"},
        "unrestricted": {"user_command", "default_backend"},
        "select": {"user_command", "default_backend"},
    }.get(mode, {"default_backend"})
    candidates = {
        "user_command": requested_backend,
        "project_declaration": declared_backend,
        "default_backend": fallback,
    }
    for step in order:
        backend = candidates.get(step)
        if step in enabled and backend in _DISPATCH_BACKENDS:
            return backend
    return fallback


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


def _resolve_policy_runtime_options(
    sub_agent_policy: object,
    *,
    category: str,
    model: str | None,
    reasoning_effort: str | None,
    stall_timeout: float | None,
) -> tuple[str | None, str | None, float | None]:
    """Resolve policy routing defaults without overriding CLI flags."""
    policy_route: dict[str, object] = {}
    resolve_category = getattr(sub_agent_policy, "resolve_category", None)
    if callable(resolve_category):
        route = resolve_category(category)
        if isinstance(route, dict):
            policy_route = route

    policy_model = policy_route.get("model")
    if not isinstance(policy_model, str):
        policy_model = None
    policy_reasoning_effort = policy_route.get("reasoning_effort")
    if not isinstance(policy_reasoning_effort, str):
        policy_reasoning_effort = None

    return (
        model if model is not None else policy_model,
        reasoning_effort if reasoning_effort is not None else policy_reasoning_effort,
        stall_timeout,
    )


def _build_dispatch_runner(
    dispatch_module: object,
    *,
    backend: str,
    repo_root: pathlib.Path,
    prompt: str,
    timeout_seconds: int | None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    stall_timeout: float | None = None,
    agent_route: object | None = None,
) -> object:
    """Build the runner for the resolved backend."""
    if backend == "claude":
        runner_kwargs = {"timeout_seconds": timeout_seconds}
        if agent_route is not None:
            runner_kwargs["agent_route"] = agent_route
            runner_kwargs["model"] = model
            runner_kwargs["reasoning_effort"] = reasoning_effort
        return dispatch_module.build_claude_runner(
            repo_root,
            **runner_kwargs,
        )
    if (
        not model
        or not model.strip()
        or not reasoning_effort
        or not reasoning_effort.strip()
    ):
        raise ValueError(
            "Codex dispatch requires an explicit model and reasoning effort"
        )
    runner_kwargs: dict[str, object] = {"timeout_seconds": timeout_seconds}
    if model is not None:
        runner_kwargs["model"] = model
    if reasoning_effort is not None:
        runner_kwargs["reasoning_effort"] = reasoning_effort
    if stall_timeout is not None:
        runner_kwargs["stall_timeout"] = stall_timeout
    if agent_route is not None:
        runner_kwargs["agent_route"] = agent_route
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
    brief = json.loads(path.read_text(encoding="utf-8"))
    goal = brief.get("expanded_goal") if isinstance(brief, dict) else None
    if not isinstance(goal, str):
        raise ValueError("DispatchBrief expanded_goal must be a string")
    return goal.strip()


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
    limit = local_config(args.repo_root.resolve()).get("input_limit_bytes")
    if isinstance(limit, int) and limit > 0:
        file = getattr(args, "codex_args_file", None)
        size = (
            file.stat().st_size
            if file
            else len((getattr(args, "codex_args", None) or "").encode("utf-8"))
        )
        if size > limit:
            raise ValueError("Codex input exceeds configured input_limit_bytes")
    codex_args_text = getattr(args, "codex_args", None)
    codex_args_file = getattr(args, "codex_args_file", None)
    has_codex_args = codex_args_text is not None
    has_codex_args_file = codex_args_file is not None
    if not has_codex_args and not has_codex_args_file:
        dispatch_brief = getattr(args, "dispatch_brief", None)
        if args.dispatch and dispatch_brief is not None:
            return []
        raise ValueError(
            "exactly one of --codex-args or --codex-args-file must be provided"
        )
    if has_codex_args and has_codex_args_file:
        raise ValueError(
            "exactly one of --codex-args or --codex-args-file must be provided"
        )
    if has_codex_args_file:
        assert codex_args_file is not None
        return [pathlib.Path(codex_args_file).read_text(encoding="utf-8")]
    assert codex_args_text is not None
    return shlex.split(codex_args_text)


def _prepare_execute_root(args: argparse.Namespace) -> pathlib.Path:
    """Let the bootstrap adapter choose the target before resolving and validating it."""
    initial = pathlib.Path(args.repo_root).resolve()
    invoke_hook(initial, "pre_execute", args, initial)
    root = pathlib.Path(args.repo_root).resolve()
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise ValueError(f"repo root is not a git repository: {root}")
    args.repo_root = root
    return root


def _dispatch_options_json(
    args: argparse.Namespace,
    brief_path: pathlib.Path | None,
    model: str | None,
    effort: str | None,
    backend: str,
    stall_timeout: float | None,
) -> str:
    options = {
        name: getattr(args, name, None)
        for name in (
            "allow_paths", "verify_cmds", "expect_changes", "change_id", "category",
            "max_codex_attempts", "finalize_lock_timeout",
        )
    }
    options.update(
        dispatch_brief=str(brief_path) if brief_path is not None else None,
        brief_sha256=hashlib.sha256(brief_path.read_bytes()).hexdigest()
        if brief_path is not None else None,
        model=model, reasoning_effort=effort,
        execution_backend=backend, stall_timeout=stall_timeout,
        artifacts_dir=str(args.artifacts_dir.resolve()) if args.artifacts_dir else None,
    )
    return json.dumps(options, sort_keys=True)


def _handle_dispatch(
    args: argparse.Namespace,
    repo_root: pathlib.Path,
    codex_args: list[str] | None = None,
) -> int:
    """Route execute --dispatch through the ADR-60 helper."""
    from tools.mir_executor import dispatch  # noqa: PLC0415
    from tools.mir_executor.jobs import JobRecord, JobRegistry  # noqa: PLC0415
    from tools.mir_executor.policy import load_sub_agent_policy  # noqa: PLC0415

    try:
        if "timeout_seconds_range" in local_config(repo_root):
            validate_timeout(repo_root, args.timeout)
            validate_timeout(repo_root, getattr(args, "stall_timeout", None))
            validate_timeout(repo_root, args.finalize_lock_timeout)
    except (OSError, TypeError, ValueError) as exc:
        print(f"[mir_executor] argument parse error: {exc}", file=sys.stderr)
        return 1
    if codex_args is None:
        codex_args = _resolve_execute_codex_args(args)
    dispatch_brief_path = (
        args.dispatch_brief.resolve() if getattr(args, "dispatch_brief", None) else None
    )
    try:
        if dispatch_brief_path is not None:
            validated = invoke_hook(repo_root, "validate_brief", dispatch_brief_path, repo_root)
        if not codex_args:
            prompt = _prompt_from_dispatch_brief(dispatch_brief_path)
            if not prompt:
                raise ValueError("DispatchBrief expanded_goal must be non-empty")
        else:
            prompt = _resolve_dispatch_prompt(codex_args, dispatch_brief_path)
        if dispatch_brief_path is None:
            validated = None
        if dispatch_brief_path is None and has_hook(repo_root, "render_brief"):
            validated = invoke_hook(repo_root, "validate_brief", prompt, repo_root)
        rendered = invoke_hook(repo_root, "render_brief", validated, repo_root)
        brief_text = prompt if rendered is None else rendered
        if not isinstance(brief_text, str):
            raise TypeError("render_brief must return str or None")
        target_agent = (
            validated.get("target_agent")
            if isinstance(validated, dict)
            else getattr(validated, "target_agent", None)
        )
        if target_agent is None and dispatch_brief_path is not None:
            brief_data = json.loads(dispatch_brief_path.read_text(encoding="utf-8"))
            target_agent = (
                brief_data.get("target_agent") if isinstance(brief_data, dict) else None
            )
        if target_agent is not None and (
            not isinstance(target_agent, str) or not target_agent.strip()
        ):
            raise ValueError("DispatchBrief target_agent must be a non-empty string")
        agent_route = (
            dispatch.resolve_agent_route(repo_root, target_agent)
            if target_agent is not None else None
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"[mir_executor] DispatchBrief error: {exc}", file=sys.stderr)
        return 1

    if args.change_id is not None:
        try:
            MirExecutor(repo_root)._validate_ledger_entry(args.change_id, args.category)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            print(f"[mir_executor] {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

    jobs_db_path = _resolve_jobs_db(args.jobs_db, repo_root)
    job_id = getattr(args, "resume_job_id", None) or uuid.uuid4().hex
    dispatch_id = uuid.uuid4().hex if getattr(args, "resume_job_id", None) else job_id
    job_change_id = args.change_id or f"dispatch-{job_id}"
    job_category = args.category or "unclassified"
    prior = dispatch.count_consecutive_codex_failures(
        jobs_db_path,
        change_id_prefix=job_change_id,
    )
    registry = JobRegistry(jobs_db_path)
    previous = registry.get(job_id)
    metadata = dict(previous.ai_run_metadata or {}) if previous else {}
    dispatch_ids = metadata.get("dispatch_ids", [])
    if not isinstance(dispatch_ids, list):
        dispatch_ids = []
    previous_dispatch = metadata.get("dispatch_id")
    dispatch_ids = list(
        dict.fromkeys(
            value
            for value in [*dispatch_ids, previous_dispatch, dispatch_id]
            if isinstance(value, str)
        )
    )
    metadata.update(dispatch_id=dispatch_id, dispatch_ids=dispatch_ids)
    pending_job = JobRecord(
        job_id=job_id,
        change_id=job_change_id,
        category=job_category,
        family=getattr(args, "family", None),
        repo_root=str(repo_root),
        codex_args=codex_args,
        dispatch_brief_path=(
            str(dispatch_brief_path)
            if dispatch_brief_path is not None
            else None
        ),
        allow_harness_self_modify=args.allow_harness_self_modify,
        timeout_seconds=args.timeout if args.timeout is not None else 600,
        status="running",
        started_at=_utc_now(),
    )
    hook_errors: list[str] = []
    try:
        sub_agent_policy = load_sub_agent_policy(repo_root)
        model, reasoning_effort, stall_timeout = _resolve_policy_runtime_options(
            sub_agent_policy,
            category=args.category or "",
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            stall_timeout=getattr(args, "stall_timeout", None),
        )
        repo_slug = _resolve_repo_policy_slug(repo_root)
        backend = _resolve_dispatch_backend(
            sub_agent_policy,
            requested_backend=getattr(args, "execution_backend", None),
            repo_slug=repo_slug,
            repo_root=repo_root,
        )
        if agent_route is not None:
            backend = agent_route.execution_backend
            model = args.model if args.model is not None else agent_route.model or model
            reasoning_effort = (
                args.reasoning_effort
                if args.reasoning_effort is not None else agent_route.reasoning_effort
                or reasoning_effort
            )
        if getattr(args, "resume_job_id", None):
            emit_job_event(repo_root, "job_resumed", {
                "job_id": job_id, "path": "resume", "args": args,
                "repo_root": repo_root, "jobs_db": jobs_db_path,
                "dispatch_options": json.loads(previous.dispatch_options_json)
                if previous and previous.dispatch_options_json is not None else None,
            })
            registry.mark_resumed(job_id, resumed_at=_utc_now())
        else:
            pending_job.identity_json = invoke_hook(
                repo_root, "job_identity", args, repo_root, prompt, model
            )
            pending_job.dispatch_options_json = _dispatch_options_json(
                args, dispatch_brief_path, model, reasoning_effort, backend, stall_timeout
            )
            registry.insert(pending_job)
            emit_job_event(repo_root, "job_inserted", {
                "job_id": job_id, "path": "dispatch", "args": args,
                "repo_root": repo_root, "jobs_db": jobs_db_path,
            })
        registry.update_ai_run_metadata(job_id, metadata)
        registry.update_route_metadata(
            job_id,
            execution_backend=backend,
            resolved_model=model,
            resolved_reasoning_effort=reasoning_effort,
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
            agent_route=agent_route,
        )
        with job_event_scope(repo_root, job_id, hook_errors):
            outcome = dispatch.run_dispatch(
                repo_root,
                dispatch_id=dispatch_id,
                brief_text=brief_text,
                codex_runner=runner,
                max_codex_attempts=args.max_codex_attempts,
                prior_consecutive_codex_failures=prior,
                **(
                    {"artifacts_root": args.artifacts_dir}
                    if getattr(args, "artifacts_dir", None)
                    else {}
                ),
            )

        final = None
        reviewer = (
            dispatch.build_codex_review_runner(repo_root, timeout_seconds=args.timeout)
            if local_config(repo_root).get("require_review", False)
            else None
        )
        if outcome.worktree is not None:
            final = dispatch.finalize_dispatch(
                outcome.worktree,
                repo_root,
                outcome,
                **({"reviewer": reviewer} if reviewer is not None else {}),
                allowlist=getattr(args, "allow_paths", None) or [],
                verification_commands=getattr(args, "verify_cmds", None) or [],
                finalize_lock_timeout=args.finalize_lock_timeout,
                expect_changes=(
                    dispatch.agent_route_expects_changes(agent_route)
                    if agent_route is not None else args.expect_changes
                ),
                allow_harness_self_modify=args.allow_harness_self_modify,
                **(
                    {"artifacts_root": args.artifacts_dir}
                    if getattr(args, "artifacts_dir", None)
                    else {}
                ),
            )
            review_path = (
                getattr(args, "artifacts_dir", None) or repo_root / "tasks/dispatch"
            ) / dispatch_id / "reviewer.json"
            try:
                review_evidence = json.loads(review_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                review_evidence = None
            emit_job_event(repo_root, "dispatch_finalized", {
                "job_id": job_id, "dispatch_id": dispatch_id,
                "status": outcome.status, "finalize_action": final.action,
                "merged_files": final.merged_files, "reason": final.reason,
                "review_evidence": review_evidence,
            }, errors=hook_errors)

        merged = final is not None and final.action in _MERGED_FINALIZE_ACTIONS
        job_status = "completed" if merged else "failed"
        attempt_exit = getattr(outcome, "exit_code", None)
        task_exit = 0 if merged else (attempt_exit or 1)
        registry.update_ai_run_metadata(
            job_id,
            {
                "model_id": getattr(outcome, "model_id", None) or model,
                "tokens_used": dict(getattr(outcome, "tokens_used", ())),
                "mcp_protocol": getattr(outcome, "mcp_protocol", None),
                "dispatch_id": dispatch_id,
                "dispatch_ids": dispatch_ids,
            },
        )
        artifacts = getattr(args, "artifacts_dir", None) or pathlib.Path(
            "tasks/dispatch"
        )
        if outcome.status == "blocked":
            print(
                "[DISPATCH] blocked; inspect the job artifacts under "
                f"{artifacts / dispatch_id} for the failing step",
                file=sys.stderr,
            )
        result_payload = f"artifacts={artifacts / dispatch_id}"
        reason_payload = None
        if final is not None and final.action == "merged-but-cleanup-failed":
            reason_payload = " ".join(
                [
                    f"dispatch_status={outcome.status}",
                    f"finalize_action={final.action}",
                    f"finalize_reason={final.reason}",
                ]
            )
        elif not merged:
            blocked_reason = (
                final.reason
                if final is not None
                else outcome.blocked_reason or "no-finalize-result"
            )
            reason_payload = " ".join(
                [
                    f"dispatch_status={outcome.status}",
                    f"dispatch_reason={outcome.blocked_reason}",
                    f"finalize_action={final.action if final is not None else None}",
                    f"finalize_reason={final.reason if final is not None else None}",
                    f"blocked_reason={blocked_reason}",
                ]
            )
        registry.update_status(
            job_id,
            job_status,
            exit_code=task_exit,
            stdout=result_payload,
            stderr="; ".join(filter(None, [reason_payload, *hook_errors])) or None,
            completed_at=_utc_now(),
        )
    except Exception as exc:  # noqa: BLE001
        if registry.get(job_id) is None:
            registry.insert(pending_job)
        emit_job_event(repo_root, "dispatch_failed", {
            "job_id": job_id, "dispatch_id": dispatch_id,
            "error_type": type(exc).__name__, "message": str(exc),
        }, errors=hook_errors)
        registry.update_status(
            job_id, "failed", exit_code=1,
            stderr="; ".join([str(exc), *hook_errors]), completed_at=_utc_now()
        )
        print(f"[mir_executor] dispatch failed: {exc}", file=sys.stderr)
        return 1
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
    return task_exit


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _handle_execute(args: argparse.Namespace) -> int:
    """Handle the 'execute' subcommand."""
    has_change_id = args.change_id is not None
    has_category = args.category is not None
    if has_change_id != has_category:
        print(
            "[mir_executor] --change-id and --category must be supplied together",
            file=sys.stderr,
        )
        return 1
    if not args.dispatch and not has_change_id:
        print(
            "[mir_executor] --change-id and --category are required outside --dispatch",
            file=sys.stderr,
        )
        return 1

    try:
        repo_root = _prepare_execute_root(args)
        if "timeout_seconds_range" in local_config(repo_root):
            validate_timeout(repo_root, args.timeout)
            validate_timeout(repo_root, getattr(args, "stall_timeout", None))
        codex_args = _resolve_execute_codex_args(args)
    except ValueError as exc:
        print(f"[mir_executor] argument parse error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"[mir_executor] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    executor = MirExecutor(repo_root=repo_root)
    from tools.mir_executor.policy import load_sub_agent_policy  # noqa: PLC0415

    sub_agent_policy = load_sub_agent_policy(repo_root)
    model, reasoning_effort, stall_timeout = _resolve_policy_runtime_options(
        sub_agent_policy,
        category=args.category or "",
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        stall_timeout=getattr(args, "stall_timeout", None),
    )

    if args.dispatch:
        return _handle_dispatch(args, repo_root, codex_args)

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
            family=getattr(args, "family", None),
            repo_root=str(repo_root),
            codex_args=codex_args,
            allow_harness_self_modify=args.allow_harness_self_modify,
            timeout_seconds=args.timeout if args.timeout is not None else 600,
            status="running",
            started_at=_utc_now(),
        )
        try:
            job.identity_json = invoke_hook(
                repo_root, "job_identity", args, repo_root,
                _prompt_from_codex_args(codex_args), model,
            )
            registry.insert(job)
            emit_job_event(repo_root, "job_inserted", {
                "job_id": job_id, "path": "background", "args": args,
                "repo_root": repo_root, "jobs_db": jobs_db_path,
            })
        except Exception as exc:  # noqa: BLE001
            if registry.get(job_id) is None:
                registry.insert(job)
            registry.update_status(
                job_id, "failed", exit_code=1, stderr=str(exc), completed_at=_utc_now()
            )
            registry.close()
            print(f"[mir_executor] background insert failed: {exc}", file=sys.stderr)
            return 1
        # Print job_id immediately — caller can record it before Codex runs.
        print(f"[BACKGROUND] job_id={job_id}")
        sys.stdout.flush()

        # Validate ledger entry before starting the async runner.
        try:
            executor._validate_ledger_entry(args.change_id, args.category)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            registry.update_status(
                job_id, "failed", stderr=str(exc), completed_at=_utc_now()
            )
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
        completed = registry.get(job_id)
        registry.close()
        return (
            completed.exit_code if completed and completed.exit_code is not None else 1
        )

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
        print(
            f"[mir_executor] Codex timeout after {exc.timeout}s: {exc}", file=sys.stderr
        )
        return 1
    except TimeoutError:
        print(f"[mir_executor] async timeout after {args.timeout}s", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[mir_executor] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"[RESULT] change_id={update.change_id!r} category={update.category!r}")
    print(
        f"[RESULT] codex exit_code={result.exit_code} duration={result.duration_seconds:.2f}s"
    )
    print(f"[RESULT] command={result.command!r}")
    print(
        f"[LEDGER] previous_status={update.previous_status!r} -> new_status={update.new_status!r}"
    )
    print(f"[LEDGER] notes={update.notes!r}")
    if result.stdout:
        print(f"[STDOUT] {result.stdout[:500]!r}")
    if result.stderr:
        print(f"[STDERR] {result.stderr[:500]!r}")
    return result.exit_code


async def _run_background(**kwargs):
    return await cli_jobs._run_background(sys.modules[__name__], **kwargs)


def _handle_status(args: argparse.Namespace) -> int:
    return cli_jobs._handle_status(sys.modules[__name__], args)


def _handle_result(args: argparse.Namespace) -> int:
    return cli_jobs._handle_result(sys.modules[__name__], args)


def _handle_cancel(args: argparse.Namespace) -> int:
    return cli_jobs._handle_cancel(sys.modules[__name__], args)


def _handle_resume(args: argparse.Namespace) -> int:
    return cli_jobs._handle_resume(sys.modules[__name__], args)


def _handle_list_jobs(args: argparse.Namespace) -> int:
    return cli_jobs._handle_list_jobs(sys.modules[__name__], args)


def _handle_sweep(args: argparse.Namespace) -> int:
    return cli_jobs._handle_sweep(sys.modules[__name__], args)


def _blocked_reason(payload: str | None) -> str | None:
    return cli_jobs._blocked_reason(payload)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root_parser = argparse.ArgumentParser(add_help=False)
    root_parser.add_argument(
        "--repo-root", type=pathlib.Path, default=pathlib.Path.cwd()
    )
    known, _ = root_parser.parse_known_args(argv)
    parser = _build_parser(known.repo_root.resolve())
    args = parser.parse_args(argv)

    if args.subcommand is None:
        parser.print_help()
        sys.exit(0)

    if args.subcommand == "execute":
        with writer_scope(args.repo_root.resolve()):
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
    elif args.subcommand == "sweep":
        rc = _handle_sweep(args)
    else:
        parser.print_help()
        rc = 0

    if rc != 0:
        sys.exit(rc)
    return rc
