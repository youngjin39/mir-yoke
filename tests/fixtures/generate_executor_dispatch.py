"""Capture E8 dispatch outcomes from the unchanged Python implementation.

Run with E8_SCRATCH pointing to disposable external-volume storage. Only injected
provider results are used; no model process or external service is invoked.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.mir_executor.dispatch import (  # noqa: E402
    CodexAttempt,
    count_consecutive_codex_failures,
    run_dispatch,
)
from tools.mir_executor.jobs import JobRecord, JobRegistry  # noqa: E402
from tools.mir_executor.local_hooks import emit_job_event, job_event_scope  # noqa: E402

HOOK_SOURCE = """from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def record(name, **data):
    with (ROOT / 'hooks.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(name=name, **data), sort_keys=True) + '\\n')
    config = json.loads((ROOT / 'hook-config.json').read_text())
    if config.get('fail') == name:
        raise ValueError('fixture-' + name)
    return config
def validate_brief(brief, root):
    record('validate_brief', brief=brief, root_ok=root == ROOT)
@contextmanager
def writer_scope(root):
    record('writer_enter', root_ok=root == ROOT)
    try:
        yield
    finally:
        record('writer_exit')
def on_job_event(event, payload):
    record('on_job_event', event=event, payload=payload)
def before_run(worktree, attempt):
    record('before_run', attempt=attempt, dispatch_id=worktree.dispatch_id)
def after_provider_call(result, metadata):
    observed = {key: value for key, value in metadata.items() if key != 'elapsed_seconds'}
    record('after_provider_call', result_exit=result.exit_code, metadata=observed)
    config = json.loads((ROOT / 'hook-config.json').read_text())
    if config.get('replace'):
        return replace(result, exit_code=9, retryable=False, blocked_reason='hook-budget')
def after_run(worktree, attempt, result):
    record('after_run', attempt=attempt, result_exit=result.exit_code,
           dispatch_id=worktree.dispatch_id)
"""


def git(root, *args):
    return (
        subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)
        .decode()
        .strip()
    )


def capture(case, scratch):
    root = scratch / case["name"]
    root.mkdir(parents=True)
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / ".gitignore").write_text(".mir/\n.mir-dispatch/\n", encoding="utf-8")
    (repo / "code.txt").write_text("initial\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fixture")
    config = repo / "config/mir-executor.local.json"
    config.parent.mkdir()
    config.write_text(json.dumps(case.get("config", {})), encoding="utf-8")
    if case.get("hooks"):
        hook = repo / "tools/mir_executor/local.py"
        hook.parent.mkdir(parents=True)
        hook.write_text(HOOK_SOURCE, encoding="utf-8")
        (repo / "hook-config.json").write_text(json.dumps(case["hooks"]), encoding="utf-8")
    calls = []
    errors = []

    def runner(wt, attempt):
        calls.append(dict(attempt=attempt, worktree_exists=wt.path.is_dir()))
        if case.get("runner_error"):
            raise RuntimeError("fixture-runner")
        raw = case["results"][min(attempt - 1, len(case["results"]) - 1)]
        return CodexAttempt(**{**raw, "tokens_used": tuple(map(tuple, raw.get("tokens_used", [])))})

    if case.get("provider_hook_applied"):
        runner._mir_provider_hook = True
    kwargs = {
        key: case[key]
        for key in ("max_codex_attempts", "outage_threshold", "prior_consecutive_codex_failures")
        if key in case
    }
    expected = {}
    registry = JobRegistry(root / "jobs.db")
    registry.insert(
        JobRecord(
            job_id="fixture-job",
            change_id="fixture",
            category="unit",
            family=None,
            repo_root=str(repo),
            codex_args=[],
            timeout_seconds=60,
            status="running",
            ai_run_metadata=case.get("previous_metadata"),
        )
    )
    try:
        with job_event_scope(repo, "fixture-job", errors):
            outcome = run_dispatch(
                repo,
                "fixture",
                brief_text="Fixture brief",
                codex_runner=runner,
                worktrees_root=root / "trees",
                **kwargs,
            )
        projected = asdict(outcome)
        del projected["worktree"]
        expected["outcome"] = projected
        metadata = dict(case.get("previous_metadata") or {})
        dispatch_ids = metadata.get("dispatch_ids", [])
        if not isinstance(dispatch_ids, list):
            dispatch_ids = []
        dispatch_ids = list(
            dict.fromkeys(
                value
                for value in [*dispatch_ids, metadata.get("dispatch_id"), "fixture"]
                if isinstance(value, str)
            )
        )
        # The CLI persists these fields after dispatch; finalization is out of E8 scope.
        registry.update_ai_run_metadata(
            "fixture-job",
            {
                "model_id": outcome.model_id,
                "tokens_used": dict(outcome.tokens_used),
                "mcp_protocol": outcome.mcp_protocol,
                "dispatch_id": "fixture",
                "dispatch_ids": dispatch_ids,
            },
        )
    except Exception as error:  # noqa: BLE001
        expected["error"] = type(error).__name__
        expected["message"] = str(error)
        # Mirror the real CLI exception persistence using its actual event/registry APIs.
        emit_job_event(
            repo,
            "dispatch_failed",
            {
                "job_id": "fixture-job",
                "dispatch_id": "fixture",
                "error_type": type(error).__name__,
                "message": str(error),
            },
            errors=errors,
        )
        registry.update_status(
            "fixture-job", "failed", exit_code=1, stderr="; ".join([str(error), *errors])
        )
    record = registry.get("fixture-job")
    expected["registry"] = {
        key: getattr(record, key) for key in ("status", "exit_code", "stderr", "ai_run_metadata")
    }
    registry.close()
    trees = list((root / "trees").glob("*")) if (root / "trees").exists() else []
    wt = next((path for path in trees if path.is_dir()), None)
    expected["calls"] = calls
    expected["events"] = []
    if wt is not None:
        status = json.loads((wt / ".mir-dispatch/status.json").read_text())
        expected["state"] = {
            key: value
            for key, value in status.items()
            if key in {"state", "attempt", "attempts", "reason"}
        }
        events = wt / ".mir-dispatch/dispatch-events.jsonl"
        if events.exists():
            expected["events"] = [json.loads(line) for line in events.read_text().splitlines()]
    else:
        expected["state"] = None
    hooks = repo / "hooks.jsonl"
    expected["hooks"] = (
        [json.loads(line) for line in hooks.read_text().splitlines()] if hooks.exists() else []
    )
    expected["event_errors"] = errors
    return dict(case, expected=expected)


SUCCESS = dict(
    exit_code=0,
    stdout="finished",
    stderr="diagnostic",
    tokens_used=[["input_tokens", 11], ["output_tokens", 3]],
    model_id="fixture-model",
    mcp_protocol="fixture-protocol",
    tool_version="fixture-v1",
)
FAILURE = dict(exit_code=2, error_sig="fixture-error", stdout="partial", stderr="failed")
CASES = [
    dict(name="default-success", results=[SUCCESS]),
    dict(name="default-single-failure", results=[FAILURE, SUCCESS]),
    dict(name="explicit-retry-success", results=[FAILURE, SUCCESS], max_codex_attempts=3),
    dict(name="explicit-exhaustion", results=[FAILURE], max_codex_attempts=2),
    dict(name="outage", results=[FAILURE], prior_consecutive_codex_failures=2),
    dict(name="outage-threshold-one", results=[FAILURE], outage_threshold=1),
    dict(
        name="lane-unavailable",
        results=[dict(FAILURE, lane_unavailable=True)],
        max_codex_attempts=3,
    ),
    dict(name="non-retryable", results=[dict(FAILURE, retryable=False)], max_codex_attempts=3),
    dict(
        name="specific-blocker",
        results=[dict(FAILURE, retryable=False, blocked_reason="budget")],
        max_codex_attempts=3,
    ),
    dict(
        name="cap-accepted",
        results=[FAILURE, SUCCESS],
        max_codex_attempts=2,
        config={"max_codex_attempts_cap": 2},
    ),
    dict(
        name="cap-rejected",
        results=[SUCCESS],
        max_codex_attempts=3,
        config={"max_codex_attempts_cap": 2},
    ),
    dict(name="zero-budget", results=[SUCCESS], max_codex_attempts=0),
    dict(name="negative-budget", results=[SUCCESS], max_codex_attempts=-1),
    dict(name="hooks-success", results=[SUCCESS], hooks={"enabled": True}),
    dict(
        name="hooks-retry",
        results=[FAILURE, SUCCESS],
        max_codex_attempts=2,
        hooks={"enabled": True},
    ),
    dict(
        name="hooks-provider-already-applied",
        results=[SUCCESS],
        hooks={"enabled": True},
        provider_hook_applied=True,
    ),
    dict(
        name="hooks-provider-replacement",
        results=[SUCCESS],
        max_codex_attempts=3,
        hooks={"replace": True},
    ),
    dict(name="hooks-events-fail-nonfatal", results=[SUCCESS], hooks={"fail": "on_job_event"}),
    dict(name="hooks-validate-failure", results=[SUCCESS], hooks={"fail": "validate_brief"}),
    dict(name="hooks-before-failure", results=[SUCCESS], hooks={"fail": "before_run"}),
    dict(name="hooks-after-failure", results=[SUCCESS], hooks={"fail": "after_run"}),
    dict(name="hooks-provider-failure", results=[SUCCESS], hooks={"fail": "after_provider_call"}),
    dict(name="runner-error", results=[SUCCESS], hooks={"enabled": True}, runner_error=True),
    dict(
        name="runner-error-with-event-errors",
        results=[SUCCESS],
        hooks={"fail": "on_job_event"},
        runner_error=True,
    ),
    dict(
        name="resumed-dispatch-history",
        results=[SUCCESS],
        previous_metadata={
            "dispatch_id": "previous",
            "dispatch_ids": ["first", "first", 7, "previous"],
            "old_field": "superseded",
        },
    ),
    dict(
        name="resumed-malformed-history",
        results=[SUCCESS],
        previous_metadata={
            "dispatch_id": "previous",
            "dispatch_ids": "invalid",
        },
    ),
]


def count_cases(scratch):
    cases = []
    for name, rows, prefix in [
        ("empty", [], ""),
        ("all-failed", [("failed", None, "a"), ("failed", "dispatch_status=blocked", "a")], ""),
        (
            "stop-completed",
            [("failed", None, "a"), ("completed", None, "a"), ("failed", None, "a")],
            "",
        ),
        (
            "stop-provider-completed",
            [
                ("failed", None, "a"),
                ("failed", "x dispatch_status=completed y", "a"),
                ("failed", None, "a"),
            ],
            "",
        ),
        (
            "prefix",
            [
                ("failed", None, "scope-a"),
                ("completed", None, "other"),
                ("failed", None, "scope-b"),
            ],
            "scope-",
        ),
        (
            "literal-prefix",
            [("failed", None, "a%one"), ("completed", None, "another"), ("failed", None, "a%two")],
            "a%",
        ),
        ("empty-prefix-result", [("failed", None, "a")], "missing"),
        ("token-substring", [("failed", "notdispatch_status=completed", "a")], ""),
        (
            "first-token-wins",
            [("failed", "dispatch_status=blocked dispatch_status=completed", "a")],
            "",
        ),
    ]:
        db = scratch / f"count-{name}.db"
        registry = JobRegistry(db)
        records = []
        for index, (status, stderr, change_id) in enumerate(rows):
            record = JobRecord(
                job_id=f"job-{index}",
                change_id=change_id,
                category="unit",
                family=None,
                repo_root="<REPO>",
                codex_args=[],
                timeout_seconds=60,
                status=status,
                stderr=stderr,
                started_at=f"2026-01-01T00:00:{59 - index:02d}",
            )
            registry.insert(record)
            records.append(asdict(record))
        registry.close()
        cases.append(
            dict(
                name=name,
                records=records,
                prefix=prefix,
                expected=count_consecutive_codex_failures(db, change_id_prefix=prefix),
            )
        )
    return cases


if __name__ == "__main__":
    scratch = Path(os.environ["E8_SCRATCH"])
    scratch.mkdir(parents=True, exist_ok=True)
    output = dict(
        source="tools.mir_executor.dispatch.run_dispatch",
        hook_source=HOOK_SOURCE,
        cases=[capture(case, scratch) for case in CASES],
        counts=count_cases(scratch),
    )
    destination = Path(__file__).with_name("executor_dispatch.json")
    destination.write_text(json.dumps(output, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    shutil.rmtree(scratch)
