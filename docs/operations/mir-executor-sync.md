# Mir Executor common source and explicit sync

Mir Yoke owns the common runtime in `tools/mir_executor/`. Generate its SHA-256
file list with `python -m tools.executor_sync --generate`. The source manifest at
`config/mir-executor-common.json` and Yoke's consumer manifest use the literal
`SOURCE_COMMIT` placeholder to avoid a self-referential commit hash. Consumer sync
resolves `source_commit` to Yoke's current Git HEAD. Sync from a tested, committed
Yoke checkout so that this revision identifies the delivered source.

The generated list includes runtime Python modules and the tiny portable
`tests/test_common_manifest.py` contract. Other tests are repository-owned and never
replaced by sync. Put application-specific tests in `tests/local/` or the repository's
own test tree. The common manifest is independent of `config/adopter-payload.json`;
this optional tool is not an adopter payload or a grant of consumer authority.

## Common, local and policy boundaries

- Common: CLI/parser/job handlers, policy loader, dispatch, executor, jobs, sweep,
  worktree, app-server client, redactor and the small local-hook adapter.
- Local code: optional `tools/mir_executor/local.py`. Absent hooks use defaults.
- Local data: optional `config/mir-executor.local.json`. Keys are `verifiers` (ID
  to argv list), `codex_sandbox_default`, `require_review`, `max_codex_attempts_cap`,
  `artifact_retention_days`, `child_env_filter`, `child_env_extra_keys` and
  `input_limit_bytes`. Verifiers execute registered argv, never arbitrary shell
  command strings supplied by a brief.
- Policy: Harness-deployed `config/model-routing.lock.json` and repository-owned
  `config/sub-agent-policy.json`. Sync writes neither. The lock is read first;
  missing local policy is valid. Local delegation keys, per-project and monitoring
  values merge beneath the lock. `policy.model_routing_lock_path` is a standalone
  seam; policy remains self-contained for partial wheel consumers.

The canonical mode is `user_command_priority`. `obey_user` is an input alias only.
`delegation.mode` wins over top-level `mode`. Unknown modes retain `unresolved_mode`
and emit a warning. Codex dispatch defaults to `workspace-write` in its isolated
worktree. Optional reviewers use `read-only`, are off by default, and must approve
when local `require_review` is true. Local configuration can override the dispatch
sandbox default.

## Change and deliver common code

1. Edit in Yoke and demonstrate regressions failing before fixing.
2. Run affected tests, full tests, Ruff, Python 3.11 compilation and Codex parity.
3. Regenerate common manifests with `python -m tools.executor_sync --generate`.
   Re-run the portable manifest test and commit the tested Yoke source.
4. Inspect each explicitly authorized target with
   `python -m tools.executor_sync --target /path/to/repo`.
5. Apply under target-owner authority with
   `python -m tools.executor_sync --target /path/to/repo --apply`.
   Run target checks and commit there.

Dry-run lists every file as added/changed/unchanged with line counts. Apply writes
selected files and `tools/mir_executor/COMMON_MANIFEST.json` only. Local code/data,
local tests, policy and other files stay untouched. Dirty common files, untracked
files at selected paths and symlink destinations are refused. The tool does not
discover consumers, commit, push or tag.

## Add a local hook

Define only needed hooks in `local.py`. The adapter loads it from the explicit
target root so another repository's hooks cannot leak into that target.

- `register_execute_options(parser)` adds execute flags.
- `pre_execute(args, repo_root)` validates or fills parsed options, including
  `args.repo_root`. It is loaded from the initial root (the bootstrap adapter).
  Execute resolves the selected root and checks that Git recognizes it as a working
  repository after this hook, before reading target-local input limits or dispatching.
- `writer_scope(repo_root)` returns a context manager; default is a no-op.
- `resolve_agent_route(repo_root, name)` returns an `AgentRoute` override.
- `resolve_route_key(repo_root, key)` returns `(model, effort)`.
- `validate_brief(brief, repo_root)` accepts a JSON file Path or plain prompt text.
  A file hook may return a typed object/dict containing `expanded_goal`.
- `render_brief(validated, repo_root)` receives that validation result and returns
  a string for dispatch `brief_text`, or `None` to retain the original prompt.
  Plain-text validation is performed before rendering when this hook is present.
  Without it, the existing validation calls and prompt behavior are preserved.
- `job_identity(args, repo_root, prompt, model)` returns a JSON string or `None`.
  Its result fills `JobRecord.identity_json` at both dispatch and background inserts;
  `model` is the resolved model and `prompt` is the execution prompt.
- `on_job_event(event, payload)` observes the lifecycle described below.
- `state_callback(state, evidence)` receives dispatch state and evidence.
- `before_run(worktree, attempt)` and `after_run(worktree, attempt, result)` wrap
  each attempt.

For an application-specific `--route`, add the flag in `register_execute_options`.
Have `pre_execute` reject conflicting explicit route/model flags and use
`resolve_route_key` for the application's model/effort pair. Its route table stays
in the deployed policy lock; application imports stay in `local.py`. Yoke's local
hook preserves its Pydantic `DispatchBrief` schema. Common code needs no application
imports and accepts a JSON object with a nonempty `expanded_goal`.

## Lifecycle events and resume integrity

`on_job_event` is optional and called through the local-hook adapter. Payloads use
Python objects: `args` is the parsed Namespace, and repository/database paths are
Paths. A local hook owns any serialization or durable application event log.

| Event | Minimum payload |
| --- | --- |
| `job_inserted` | `job_id`, `path` (`dispatch` or `background`), `args`, `repo_root`, `jobs_db` |
| `dispatch_state` | `job_id`, `dispatch_id`, `state`, `evidence` |
| `dispatch_finalized` | `job_id`, `dispatch_id`, `status` (dispatch outcome), `finalize_action`, `merged_files`, `reason`, `review_evidence` |
| `dispatch_failed` | `job_id`, `dispatch_id` (possibly `None`), `error_type`, `message` |

Insertion events fire after each new row is inserted and before dispatch/background
execution. A resume reuses the original row and does not emit `job_inserted`.
Dispatch state events accompany every existing `state_callback(state, evidence)`
call, retaining its two-argument signature. The job context associates resumed
attempts with the original job ID and the new dispatch ID. Direct dispatch calls
without a registered job use `job_id=None`. The new observer also receives
`started` after worktree creation and `running` before each attempt; these extra
events do not add calls to the legacy state callback. Finalized events fire after
`finalize_dispatch`; durable reviewer JSON is included when available, otherwise
`review_evidence=None`. Dispatch exceptions, including worktree-creation failures,
emit `dispatch_failed`.

An exception in `job_inserted` aborts before execution and marks the inserted job
failed. Exceptions in subsequent `on_job_event` calls are printed on stderr and
appended to the job's reason (`JobRecord.stderr`). They do not change an already
successful merge or its completed job status. An exception in the failure observer
is also recorded alongside the original dispatch error. Other existing local-hook
error behavior is unchanged.

New dispatch rows persist one nullable `dispatch_options_json` column. Opening an
existing database for writes adds it without rewriting old rows; read-only legacy
reads remain supported. The JSON stores the absolute brief path and SHA256, allow
paths, verifier IDs, expect-changes, the original change ID (including `None`),
category, resolved model/effort/backend, and retry, artifact, finalize-lock and
stall-timeout options. Existing row fields retain timeout and harness permissions.

Resume checks the stored brief digest before hooks or execution and refuses a
changed or missing file without incrementing the resume counter or changing job
status. It restores saved options, including verifier IDs, before re-dispatching.
The default resume timeout remains the saved timeout, with an explicit resume
`--timeout` override. A legacy row with no stored options retains the previous
resume behavior. Resume does not turn a synthetic dispatch change ID into a ledger ID.

## Drift checks

`python -m tools.executor_sync --check --target /path/to/repo` compares the target
to its manifest and the available Yoke source, including file-list changes.
Inside a consumer, `pytest tools/mir_executor/tests/test_common_manifest.py`
checks committed hashes without Yoke present. A hand edit fails this test. Fix
common code in Yoke and sync again; keep repository behavior in local hooks/data.

Consumer formatters must exclude the common runtime and tiny test, for example:

```toml
[tool.ruff.format]
exclude = ["tools/mir_executor/*.py", "tools/mir_executor/tests/test_common_manifest.py"]
```

Keep local code formatted separately. Run lint explicitly on common files using the
provider's 100-character width; a local formatter must not silently change hashes.
Terminal-artifact retention manages `tasks/dispatch`, including recorded resume
attempt UUIDs. An explicit external `--artifacts-dir` is owner-managed storage.
