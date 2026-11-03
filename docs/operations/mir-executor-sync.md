# Mir Executor common source and explicit sync

Current common base: **v3.8**. v3.8 ignores an agent route's model and reasoning
effort when its declared `execution_backend` differs from the resolved backend;
the category/default route supplies those values instead. Explicit `--model` and
`--reasoning-effort` keep precedence. Forced modes reject recognized opposite-backend
automatic models before creating a runner. Category/default policy routes and
`resolve_category()` declare no backend: the guard recognizes Claude aliases
`sonnet`, `opus`, `fable`, `haiku` and `claude-*` versus Codex `gpt-*`.
Unknown model names are not assigned a backend. An explicit `--model` bypasses
this guard, including under force_codex. A matching-backend agent route retains
its model/effort; a non-forced dispatch with a matching route retains prior behavior.
v3.7 refuses symlinks in private worktree writes
and artifact source files/directories. Agent-route backends win over project/default
backends; explicit `--execution-backend` requests retain policy-permitted precedence.
Forced modes always select their forced backend, including force_codex with a
conflicting Claude agent route.
v3.6 redacts quoted secret assignments, `*_KEY`
names, `Authorization: Basic` values and string values under a secret-named dict key.
v3.5 rejects non-object
`agent_criteria` with a clear `ValueError`, clarifies Mir Harness policy references,
and fixes repository-owned test cleanup of automatic worktree temporary bases.
It also ignores RPC responses without an issued pending request ID, tolerates
excessive JSON nesting, and fails pending calls when the stdout reader ends.
The common manifest format remains schema version 1.

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
- Native admission: optional `native_policy` in the same local JSON. Its closed
  version 1 schema is validated eagerly; keys outside this section retain their
  legacy semantics. Absence preserves the Python bridge path. For example:

  ```json
  {"native_policy":{"version":1,"target_admission":{"family":{"mode":"reject","failure":{"kind":"ValueError","message":"Family selection is unavailable"}}}}}
  ```

  Declaring `native_policy` requires a pinned native executor that supports the
  declared version and sections. The Python command entry points refuse execute
  (including background and dispatch) and resume with exit 1 before local imports,
  hooks, writer leases, worktrees, job writes or provider launch. This applies to
  explicit targets, restored resume targets, and an invoking Git home whose
  cross-repository authorization would otherwise run. Declaration presence is
  sufficient; empty or invalid declarations do not enable Python fallback. A
  missing pin, Python implementation selector, or native decline before ownership
  therefore ends in a clear native-required refusal. Once native execution claims
  ownership, its result is final and is never retried in Python.

  Same-repository status, result and list-jobs remain available, as do cancel,
  sweep (dry-run or apply) and common help: they do not use native-owned command
  hooks. Python skips local option registration for these native-policy targets.
  Cross-repository commands still refuse when their invoking Git home declares
  native policy, because they would consult that home's authorization hook.
  Native policy-resolve remains a common read-only policy query. The guard belongs
  only to Python command entry points; configuration readers, the persistent
  local bridge and native Python helpers remain usable for uncovered hooks.

  Compatibility caveat: the last release before this change, `v0.13.63`, ignores
  `native_policy` entirely. Its Rust `LocalConfig::parse` preserves unknown
  top-level keys, and neither its native admission nor its Python executor
  interprets this section. An older pinned binary can accept a command and run
  it without enforcing the declared policy; the Python fallback guard cannot
  protect a command that binary accepts. Upgrade the pin to a supporting native
  executor before adopting this section. An older binary that declines instead
  reaches the current Python guard and is refused.

  Version 1 also accepts optional `verifier_aliases`:
  `{"configuration_root":"initial"}` reads the original pre_execute root's
  `verifiers`; `{"configuration_root":"target"}` reads the resolved family
  target's configuration. Mapping runs after target admission and before later
  verifier validation. IDs remain unchanged; only exact POSIX Python shlex argv
  matches (comments disabled) map to IDs. Malformed or unknown text is preserved.
  Duplicate argv entries select the last ID in JSON insertion order. An absent
  section does not map commands. Both sections own `pre_execute`; retaining that
  hook in local Python fails closed before import. Other consumer hook behavior
  still needs its own native replacement before adoption.

  Version 1 accepts optional `agent_route` for native local route selection:

  ```json
  {"native_policy":{"version":1,"agent_route":{"source":"codex","criteria":"declared","backend":"policy","sandbox":"read_only","invalid_lock":"empty","requested_backend":true}}}
  ```

  Required fields are `source` (`claude` Markdown or `codex` TOML), `criteria`
  (`defer` to the common resolver when the lock names the agent, `declared` to
  select a category only when declared, or `default` to use `implementation`
  when absent), `backend` (`policy` or `codex`), `sandbox`, and `invalid_lock`
  (`empty` or `error`). Optional `names` is an exact allowlist; optional
  `name_filter: true` accepts `[a-z0-9][a-z0-9-]*`. Optional
  `requested_backend: true` includes the explicit or restored resume backend in
  policy precedence; its default is false. Policy resolution reuses the common
  loader, including project declarations and force modes.

  Claude profiles use the common dispatch instructions, raw definition bytes for
  the hash, and `sandbox: "unset"`. Codex profiles use their developer instructions
  and `sandbox: "read_only"` to preserve raw bytes/instructions and narrow only
  read-only declarations, or `sandbox: "double_opt_in"` to require and trim the
  instructions, hash normalized text, and default to workspace-write. Widening
  requires both the definition and `codex_sandbox_default` to declare
  danger-full-access. Common read-only constraints still apply after selection.
  Unknown fields, invalid values, and incompatible source/sandbox pairs fail
  closed. A retained Python `resolve_agent_route` also fails closed before import.
  Agent-only policies may omit `target_admission`; this preserves existing
  Python `pre_execute`. A present `target_admission` retains its ownership of
  `pre_execute`, including an empty object. Omitting `agent_route` preserves the
  existing route resolver. These options do not register CLI flags or replace
  other local hook state or brief validation.

  Version 1 accepts optional `hooks` for an explicitly pinned native hook host:

  ```json
  {"native_policy":{"version":1,"hooks":{"executable":"tools/hook-host","argv":[],"sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","hooks":["writer_scope","on_job_event"]}}}
  ```

  The section requires exactly `executable`, `argv`, `sha256`, and `hooks`.
  `executable` is a nonempty repository-relative path without NUL or `.`/`..`
  components or platform path anchors. `argv` is an array of strings without
  NUL, including an empty array. `sha256`
  contains exactly 64 hexadecimal characters. `hooks` is a nonempty list of
  unique names drawn from `writer_scope` and `on_job_event`. Unknown fields,
  unsupported hook names, duplicate names, and invalid types fail closed.
  Hooks-only policies may omit `target_admission`, preserving Python
  `pre_execute`. Declared hook names become native-owned; a retained Python
  definition or reference fails closed before import. Omitting `hooks` preserves
  existing behavior. The Python configuration reader validates this declaration
  but does not implement the native host transport.

  After an alias selects another repository, that target's `hooks` declaration
  and `local.py` alone determine writer/event ownership. The initial repository's
  hook host is not started. Target Python hooks remain available when only the
  initial repository declares them native; a target native declaration rejects
  duplicate Python exports, including computed exports revealed by bridge hello,
  before starting its native host or invoking a hook. The initial declarative
  admission, verifier-alias and route-policy coverage retains its cross-root
  duplicate-ownership checks.

  `family` supports `reject`, `alias_map`, and `require_current`. Alias maps are
  explicit slug-to-path objects; relative paths resolve against the configuration
  repository. Normalization is `exact` (default), `strip_lower`, or
  `lower_underscores`. An explicit `unavailable` failure preserves a missing
  resolver without discovering a registry. `unknown` and `unknown_key_error`
  preserve lookup diagnostics. `root_conflict` restricts an alias to the requested
  root or invoking cwd; `require_current` requires the family root to equal the
  configuration root. `repository_local` checks equality with the invoking cwd's
  Git root. `authorize_target: true` applies guards to cross-target admission.
  Failures declare `kind`, `message`, and optional emitted `stderr`; diagnostic
  templates cannot execute code. Successful aliases resolve before writer scope
  and trigger target reauthorization. Covered hook names referenced in `local.py`
  are conservatively rejected before import, including aliases and conditional
  definitions. Remove Python admission hooks when adopting this section;
  unrelated hooks continue through the bridge.
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
the policy selection. Forced modes select their backend unconditionally; the agent
backend overrides project and default backends. An explicit `--execution-backend`
overrides the agent backend only when
the policy permits user selection and its resolution order selects `user_command`;
forced modes and `per_project` ignore this flag. `MirExecutor` accepts optional `target_agent` and
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

## Native query front end

Executor sync may place `executor-query` in the target `.mir/bin/` from the
provider lock, with its path and SHA-256 recorded atomically in the host-local
`.mir/bin/executor-query.json` after the verified binary install. Keep `.mir/bin/`
git-ignored. The tracked `tools/mir_executor/COMMON_MANIFEST.json` carries no host
pin. No host artifact removes any existing local pin so queries use Python; other
files are preserved. Dry-run writes nothing. `check` verifies a local pin only
when its file exists; absence is not drift.
The lightweight entrypoint verifies those bytes before trying `status`, `result`,
`list-jobs`, direct `execute`, or `cancel`, before importing the Python executor. Both module and installed
CLI routes use that entrypoint.

The native reader opens SQLite read-only and never migrates it. It admits only
same-home queries with a fully understood schema, including when
`tools/mir_executor/local.py` or `config/mir-executor.local.json` exists. These
queries do not read local configuration or call execution or authorization hooks.
Python still imports `local.py` and calls `register_execute_options` while building
its parser. Accepted divergence: if that import or registration fails, Python
queries fail while native queries can answer without loading local hooks.
Unsupported arguments, help, legacy schemas, unsupported
sidecars and cross-target requests return 64 without output; the caller then
runs Python with the original arguments. Spawn failure, a missing or mismatched
pin, `MIR_EXECUTOR_QUERY_IMPL=python`, and `MIR_NATIVE_HOOKS=0` also retain Python.
`MIR_EXECUTOR_IMPL=python` disables every native route; execute and cancel also
honor `MIR_EXECUTOR_EXECUTE_IMPL=python` and `MIR_EXECUTOR_CANCEL_IMPL=python`.
Native `execute --dispatch` and `resume` compose explicit brief agents and
target-local `resolve_agent_route` hooks through the bridge, including opaque
validated briefs, repository read-only constraints and Codex definition overrides.
They persist resolved backend/model/effort and restore saved resume options;
resume resolves the agent again from the current integrity-checked brief and
definitions. A missing definition warns and proceeds without an agent route.
No agent-route shape is declined solely because it selects an agent. Invalid
definitions or hook results fail with the reference diagnostic after ownership.
Direct execute retains its existing backend and agent admission boundary.
Cross-target requests, unsupported arguments and explicit dynamic parser
extensions still use Python before ownership.
Execute and cancel inherit the caller's stdin/stdout/stderr without buffering.
Their exit 64 permits retry only without an exact private owned receipt. Native
claims ownership before hook imports, output, registry writes, or provider launch;
if writing the receipt fails, it exits 64 before any effect and Python runs. With
an owned receipt every exit code, including 64, is final. An older pinned binary
that declines with 64 without a receipt therefore falls back to Python.
Query buffering and its existing decline protocol are unchanged.
The entrypoint forwards interrupts and termination to the native process group
on POSIX, and console interrupts or termination to the direct child on Windows,
then waits and escalates to kill when needed. As in Python, interruption leaves
an inserted background row running and leaves its ledger category unchanged.
Windows parity runs in the dedicated native Windows CI lane without enabling
automated Windows bootstrap.
Text containing characters newly assigned after Unicode 15.0 also uses Python,
preserving representation across supported Python Unicode database versions.

## Native command hooks (`mir-executor.hooks@1`)

The optional `native_policy.hooks` host is consumer-owned. Yoke supplies the
transport and owns neither its state nor its lease implementation. The executor
resolves admission configuration, the target and invoking-home authorization
before starting the executable. After an alias resolves, command-hook ownership
comes from the selected target's configuration; initial declarative admission
retains its existing scope. It checks the executable's SHA-256 before spawn,
rejects symlink path components, passes argv directly, and preserves the invoking
cwd and explicit executor environment. No shell or interpreter is selected by
this transport. One host remains alive for the command, including paired writer
operations and ordered job events. Existing ownership receipts are final: a hook
failure after ownership never retries the command through Python.

The child first writes one hello line:

```json
{"version":"mir-executor.hooks@1","hooks":["writer_scope","on_job_event"]}
```

The advertised set must equal the configured set, without duplicates. The parent
then sends sequential requests and waits for exactly one response per request:

```json
{"version":"mir-executor.hooks@1","id":1,"hook":"writer_enter","params":{"repo_root":"/repository","cwd":"/repository","invocation_id":"invocation","job_id":null,"attempt_id":null}}
{"version":"mir-executor.hooks@1","id":1,"ok":true,"result":{"token":"opaque-token"}}
{"version":"mir-executor.hooks@1","id":2,"hook":"writer_exit","params":{"repo_root":"/repository","cwd":"/repository","invocation_id":"invocation","job_id":null,"attempt_id":null,"token":"opaque-token","outcome":"clean"}}
{"version":"mir-executor.hooks@1","id":2,"ok":true,"result":null}
```

Advertising `writer_scope` serves both `writer_enter` and `writer_exit`. Enter
must return a nonempty opaque string token. The child retains the lease until
exit; a token never denotes a Python object. Exit carries `clean` after a zero
command result, `unclean` after a nonzero result or controlled early failure, and
`uncertain` during unwinding or abandonment. Transport loss cannot acknowledge
release: the executor closes the host's process tree and the consumer must retain
its own crash or uncertain-teardown evidence as appropriate.

`on_job_event` uses the same envelope, with `params.event` (a string) and
`params.payload` (a JSON object), plus the roots/cwd/invocation context above.
Its job and attempt identifiers are taken from the payload, or are null when
unavailable. Paths are strings and argument namespaces are plain objects; Python
bridge object tags do not cross this transport. Successful events return null.
Errors use this response shape:

```json
{"version":"mir-executor.hooks@1","id":3,"ok":false,"error":{"type":"RuntimeError","message":"hook refused"}}
```

Errors in `job_inserted` and `job_resumed` abort preparation. Later event errors
produce diagnostics and are recorded by the existing event-error path; they
cannot roll back execution. Hook responses preserve the distinction between an
application error and a broken transport. Other hooks remain on the existing
`mir-executor.local@1` bridge, except hooks already owned by declarative admission
or agent-route policy. No other executable hook names are supported in this slice.

stdin and stdout carry UTF-8 JSON Lines only. stderr is inherited for diagnostics.
Each frame is at most 1,048,576 bytes including its newline. JSON nesting is
bounded to 64 containers and numbers must be finite. Request IDs are increasing
unsigned integers; the response ID and version must match. Unknown envelope
fields are tolerated for diagnostics; required fields and types are validated.
The ten-second exchange deadline includes blocked stdin writes and hello. Invalid
hello, malformed/oversized/deep/nonfinite frames, mismatched versions or IDs,
timeout, EOF and crashes close the session and reap its owned process tree.
Timed-out requests are never retried. Unix uses a dedicated process group;
Windows assigns the suspended child to a kill-on-close Job Object before resuming
it, so descendants cannot escape ownership before the first hook runs.
