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
- `pre_execute(args, repo_root)` validates or fills parsed options.
- `writer_scope(repo_root)` returns a context manager; default is a no-op.
- `resolve_agent_route(repo_root, name)` returns an `AgentRoute` override.
- `resolve_route_key(repo_root, key)` returns `(model, effort)`.
- `validate_brief(brief, repo_root)` accepts a JSON file Path or plain prompt text.
  A file hook may return a typed object/dict containing `expanded_goal`.
- `state_callback(state, evidence)` receives dispatch state and evidence.
- `before_run(worktree, attempt)` and `after_run(worktree, attempt, result)` wrap
  each attempt.

For an application-specific `--route`, add the flag in `register_execute_options`.
Have `pre_execute` reject conflicting explicit route/model flags and use
`resolve_route_key` for the application's model/effort pair. Its route table stays
in the deployed policy lock; application imports stay in `local.py`. Yoke's local
hook preserves its Pydantic `DispatchBrief` schema. Common code needs no application
imports and accepts a JSON object with a nonempty `expanded_goal`.

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
