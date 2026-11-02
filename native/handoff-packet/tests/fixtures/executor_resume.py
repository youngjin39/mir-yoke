"""Capture resume arguments from the Python reference using offline hooks only."""

import contextlib
import dataclasses
import hashlib
import io
import json
import pathlib
import sys
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from tools.mir_executor import cli  # noqa: E402
from tools.mir_executor.jobs import JobRecord, JobRegistry  # noqa: E402

root = pathlib.Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
brief = root / "brief.json"
brief.write_text(json.dumps({"expanded_goal": "fixture task"}), encoding="utf-8")
options = dict(
    allow_paths=["src/"],
    verify_cmds=["unit", "lint"],
    expect_changes=False,
    change_id=None,
    category="unit",
    max_codex_attempts=1,
    finalize_lock_timeout=17.0,
    timeout=123,
    dispatch_brief=str(brief),
    brief_sha256=hashlib.sha256(brief.read_bytes()).hexdigest(),
    model="saved-model",
    reasoning_effort="high",
    execution_backend="codex",
    stall_timeout=45.0,
    artifacts_dir=str(root / "artifacts"),
)
rows = []
for legacy in (False, True):
    job = JobRecord(
        job_id="legacy" if legacy else "current",
        change_id="dispatch-fixture",
        category="unit",
        family="fixture",
        repo_root=str(root),
        codex_args=["task"],
        dispatch_brief_path=str(brief),
        timeout_seconds=600,
        status="failed",
        stdout="old",
        stderr="old",
        exit_code=1,
        duration_seconds=2,
        completed_at="old",
        cancel_requested=True,
        execution_backend="codex",
        resolved_model="old-model",
        resolved_reasoning_effort="medium",
        target_agent="fixture-agent",
        agent_definition_path="agent.md",
        ai_run_metadata={"dispatch_id": "old-attempt", "dispatch_ids": ["older", "old-attempt"]},
        dispatch_options_json=None if legacy else json.dumps(options),
    )
    registry = JobRegistry(root / "jobs.db")
    registry.insert(job)
    registry.close()
    args = cli._build_parser(root).parse_args(
        [
            "--jobs-db",
            str(root / "jobs.db"),
            "resume",
            "--job-id",
            job.job_id,
            "--repo-root",
            str(root),
        ]
    )
    captured = []
    with (
        contextlib.redirect_stdout(io.StringIO()),
        patch.object(cli, "authorize_target"),
        patch.object(cli, "writer_scope", return_value=contextlib.nullcontext()),
        patch.object(cli, "invoke_hook"),
        patch.object(cli, "_prepare_execute_root", side_effect=lambda a: a.repo_root),
        patch.object(
            cli,
            "_handle_dispatch",
            side_effect=lambda a, *rest, captured=captured: captured.append(vars(a)) or 0,
        ),
    ):
        assert cli._handle_resume(args) == 0
    defaults = vars(cli._build_parser(root).parse_args(["execute", "--dispatch"]))
    defaults["jobs_db"] = str(root / "jobs.db")
    rows.append(dict(row=dataclasses.asdict(job), expected=captured[0], defaults=defaults))
print(json.dumps(rows, default=str, ensure_ascii=True))

hooks = root / "tools/mir_executor"
hooks.mkdir(parents=True)
(hooks / "local.py").write_text(
    """
import json
from pathlib import Path

def authorize_target(owner, target, args):
    if (owner / 'deny').exists():
        raise ValueError('authorization refused')

def pre_execute(args, root):
    if (root / 'redirect').exists():
        args.repo_root = root / 'other'

def validate_brief(brief, root):
    data = json.loads(brief.read_text())
    if data.get('repo_root', str(root)) != str(root):
        raise ValueError('brief root changed')
    return data

def on_job_event(name, payload):
    root = Path(__file__).resolve().parents[2]
    with (root / 'events.jsonl').open('a') as out:
        def encode(value):
            return vars(value) if hasattr(value, "__dict__") else str(value)
        out.write(json.dumps([name, payload], default=encode) + '\\n')
""",
    encoding="utf-8",
)
