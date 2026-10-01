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
  `input_limit_bytes`, `timeout_seconds_range` and `verifier_env`. Verifiers execute registered
  argv, never arbitrary shell command strings supplied by a brief.
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

Define only needed hooks in `local.py`. Execution hooks load from the explicit
target root. The sole admission exception is the optional home-owned guard below.

- `authorize_target(home_root, target_root, args)` belongs to the repository
  containing the running `tools/mir_executor` package. The package's resolved
  location determines home, independently of CWD; its parent must be the Git root.
  A package outside a Git root has no home guard. When home differs from the target,
  the CLI calls this hook before importing target `local.py`, registering target
  options, taking a target writer scope, inserting a job or dispatching. The first
  call receives parsed common CLI options; target-specific options are registered
  only after admission. A hook exception refuses the run with exit 1 and a clear
  stderr message. The target's `authorize_target` is never used for admission.
  Same-home execution and an absent home hook retain existing behavior.
  `pre_execute` root changes and saved resume targets are checked before their
  hooks or dispatch can run.

- `register_execute_options(parser)` adds execute flags.
- `pre_execute(args, repo_root)` validates or fills parsed options, including
  `args.repo_root`. It is loaded from the initial root (the bootstrap adapter).
  Execute resolves the selected root and checks that Git recognizes it as a working
  repository after this hook, before reading target-local input limits or dispatching.
- `writer_scope(repo_root)` returns a context manager; default is a no-op. The
  execution layer holds it for dispatch and finalization, write-capable direct
  provider runners, `MirExecutor.run_codex` / `run_codex_async` / `run_agent_async`,
  and ledger writes. Read-only direct provider routes skip acquisition. Nested
  calls share the lease through a context variable, including worker threads
  inherited from async calls, so an existing CLI lease is acquired only once.
  Independent execution contexts still acquire the local lease separately.
- `resolve_agent_route(repo_root, name)` returns an `AgentRoute` override, or `None`
  to use the common resolver. After the hook returns, common code enforces
  `read-only` when the target Markdown definition denies both `Write` and `Edit`,
  or the target is `codex-final-reviewer`. This also makes expect-changes false;
  a hook cannot widen these agents, but may narrow any other agent.
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
- `before_run(worktree, attempt)` and `after_run(worktree, attempt, result)` wrap
  each attempt.
- `after_provider_call(result, metadata)` observes each returned provider result,
  including mapped provider errors and read-only reviewers. The result is a
  `SubprocessResult` for direct executor calls or `CodexAttempt` for dispatch.
  Return `None` to keep it, or return a replacement of the same type. A local
  budget rule can replace `exit_code` with `2` while preserving `stdout`.
  Metadata keys are `prompt_sha256`, `model`, `reasoning_effort`, `tool_version`,
  `attempt`, `elapsed_seconds` and `token_usage`. The model is provider-confirmed
  when reported, otherwise the requested model. Unknown tool versions and usage
  are `None`; reported token counts use `input_tokens`, `output_tokens` and
  `total_tokens`. App-server token-usage notifications and completion metadata
  are collected, using the last turn's counters when present. Built-in runners
  call this hook once even when invoked through `run_dispatch`; custom runners
  are observed by `run_dispatch`. Raised exceptions retain their existing API.

`timeout_seconds_range: [min, max]` optionally bounds non-null hard timeouts,
including CLI execution, direct executor calls, dispatch/review runners,
verification, finalization locks and restored resume options. Both endpoints must
be finite positive numbers, ordered from minimum to maximum; bounds are inclusive.
`None` remains an optional timeout. Resume validates saved values and explicit
overrides before dispatch, even when its stored options skip `pre_execute`.
Without this key, each entry point retains its previous timeout validation.

A brief's `target_agent` selects the common resolver and its target-local route
hook. A non-null local route wins subject to the common read-only invariant above.
Otherwise, the common resolver reads
`.claude/agents/<target_agent>.md`: frontmatter declares `execution_backend`,
`model` and optional `effort`; the body supplies base instructions. Denying both
`Write` and `Edit` through `disallowedTools` makes the route read-only. Codex
routes use the deployed lock's `agent_criteria[<target_agent>].category`, defaulting
to `implementation`, to resolve model/effort from policy. An optional matching
`.codex/agents/<target_agent>.toml` supplies Codex instructions and sandbox;
it cannot relax the Markdown definition's read-only restriction. Definition path
and SHA256 identify the instructions used. Missing Markdown definitions emit a
warning on stderr and continue without an agent route, preserving pre-v3 dispatch.
CLI dispatch forwards the route to the provider builder, honors its backend,
base instructions and sandbox, and derives `expect_changes` from the route.
A `read-only` route uses the read-only sandbox; Claude receives `--agent`.
Explicit model/effort options override route values; omitted route values retain
the policy selection. `MirExecutor` accepts optional `target_agent` and
`agent_route` constructor arguments, and `run_agent_async(codex_args,
timeout_seconds=None)` selects the declared Codex or Claude backend. Conflicting
agent identities fail before execution. `DispatchOutcome.stderr` preserves the
last attempt's diagnostics for programmatic callers.

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
| `job_resumed` | `job_id`, `path` (`resume`), `args`, `repo_root`, `jobs_db`, `dispatch_options` (stored options object, or `None` for legacy rows) |
| `dispatch_state` | `job_id`, `dispatch_id`, `state`, `evidence` |
| `dispatch_finalized` | `job_id`, `dispatch_id`, `status` (dispatch outcome), `finalize_action`, `merged_files`, `reason`, `review_evidence` |
| `dispatch_failed` | `job_id`, `dispatch_id` (possibly `None`), `error_type`, `message` |

Insertion events fire after each new row is inserted and before dispatch/background
execution. A resume reuses the original row and does not emit `job_inserted`.
It emits `job_resumed` before re-dispatching, after the brief-digest check passes.
A refused resume emits no `job_resumed`.
Dispatch state reaches local code only as `on_job_event("dispatch_state", ...)`; the
unused `state_callback` hook was removed in v3.4. The job context associates resumed
attempts with the original job ID and the new dispatch ID. Direct dispatch calls
without a registered job use `job_id=None`. The new observer also receives
`started` after worktree creation and `running` before each attempt; these extra
events do not add calls to the legacy state callback. Finalized events fire after
`finalize_dispatch`; durable reviewer JSON is included when available, otherwise
`review_evidence=None`. Dispatch exceptions, including worktree-creation failures,
emit `dispatch_failed`.

An exception in `job_inserted` or `job_resumed` aborts before execution and marks the job
failed. Exceptions in subsequent `on_job_event` calls are printed on stderr and
appended to the job's reason (`JobRecord.stderr`). They do not change an already
successful merge or its completed job status. An exception in the failure observer
is also recorded alongside the original dispatch error. Other existing local-hook
error behavior is unchanged.

New dispatch rows persist one nullable `dispatch_options_json` column. Opening an
existing database for writes adds it without rewriting old rows; read-only legacy
reads remain supported. The JSON stores the absolute brief path and SHA256, allow
paths, verifier IDs, expect-changes, the original change ID (including `None`),
category, resolved model/effort/backend, requested timeout (including `None`), and
retry, artifact, finalize-lock and stall-timeout options. Existing row fields retain
the advisory monitoring threshold and harness permissions.

Resume checks the stored brief digest before hooks or execution and refuses a
changed or missing file without incrementing the resume counter or changing job
status. It restores saved options, including verifier IDs, before re-dispatching.
Resume restores the saved requested timeout exactly: omitting `--timeout` at the
original dispatch keeps no hard limit on resume. An explicit resume `--timeout`
overrides that value. A legacy row with no stored timeout retains the previous
resume behavior. Resume does not turn a synthetic dispatch change ID into a ledger ID.

Job persistence redacts and bounds each Codex argument as well as stdout/stderr,
including entire PEM private-key blocks. Writable registry opens restrict the
database and existing SQLite `-wal`, `-shm` and `-journal` files to mode `0600`;
new databases are created with that mode. Read-only opens do not change permissions.
Ledger updates preserve verifier IDs in `command` and store the actual executed
argument list separately as `executed_argv`, alongside result status and notes.
Background provider exceptions and ledger-validation failures persist status
`failed`, `exit_code=1`, redacted stderr and `completed_at` before the CLI exits.

## Verifier environment

Local JSON `verifier_env` defaults to `"inherit"`, retaining the current verifier
environment and credential filtering. Set it to `"isolated"` to give each verifier
invocation a fresh temporary HOME and a temporary `UV_CACHE_DIR` inside that HOME.
Both directories are removed after success, failure, timeout or a process exception.
Other values are refused.

The isolated environment retains only inherited PATH, LANG, all `LC_*` variables,
TMPDIR and names explicitly listed in `child_env_extra_keys`. HOME and UV_CACHE_DIR
always use the temporary paths, even if listed as extra keys. Provider credentials,
Codex configuration and event destinations are absent unless explicitly allowlisted.
This setting applies to merge-gate verifiers only; provider environments are unchanged.

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

## Merge gate and declared secrets (v3.4)

The merge gate refuses any changed file that matches the repository profile's
`[boundaries].secrets` (`.mir/repo-profile.toml`), even inside the allowlist. A
slash-free pattern such as `.env.*` names a file at any depth, like `.gitignore`. The
broader `[paths].protected_paths` stays advisory, because it also lists ordinary working
directories a delegated task may legitimately change. No new
hook or configuration key: the profile already declares the data.
