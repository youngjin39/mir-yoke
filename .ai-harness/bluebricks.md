# Bluebricks

Bluebricks is the development model used in this repository.

A bluebrick is a module-level blueprint unit.
Multiple bluebricks are connected through composition and orchestration.

## Purpose

The purpose of bluebricks is to help AI agents understand the repository as a system of bounded design units, not as a pile of files.

## Bluebrick Template

```md
# Bluebrick: <name>

## Purpose
What this bluebrick is responsible for.

## Public Interface
APIs, functions, classes, events, configs, or files exposed to other bluebricks.

## Internal Rules
Implementation rules that must be preserved.

## Non-Obvious Hazards
Hidden patterns that can break build, runtime behavior, compatibility, or data.

## Dependencies
What this bluebrick depends on.

## Downstream Users
What depends on this bluebrick.

## Composition
How this bluebrick is combined with others.

## Orchestration
Who calls this bluebrick, in what order, and under what conditions.

## Validation
How to test or verify changes.
```

## Current Core Bluebricks

## Composite TDD Validation Rule

For every non-trivial code change, the affected bluebrick must define a composite TDD matrix in
`tasks/tdd.json`.

Each bluebrick validation pass must explicitly classify:

- `unit`
- `integration`
- `e2e`
- `browser`
- `edge`
- `architecture`
- `availability`
- `load`
- `soak`
- `security`
- `compatibility`
- `transaction_locking`

The category may be closed as `not_applicable`, but it may not be omitted.

### Bluebrick: Conductor

#### Purpose
Accept external task requests, classify ingress mode, preserve an audit trail, and hand normal-mode work to Engine without leaking transport-specific concerns into execution code.

#### Public Interface
- `src/mir/core/conductor/ingress.py::handle_discord_event`
- `src/mir/core/conductor/reporter.py::ConductorReporter`
- `src/mir/cli/conductor_dispatch.py::main`
- `mir conductor-dispatch` stdio JSON boundary

#### Internal Rules
- Keep ingress as the top-level recoverable exception boundary.
- Record the inbound fingerprint before branch handling.
- Keep meta-mode and normal-mode dispatch separated.
- Preserve the subprocess IPC contract: stdin one JSON object, stdout one JSON result object.

#### Non-Obvious Hazards
- Do not bypass `ConductorReporter` by returning raw exceptions to the caller.
- Do not turn `KeyboardInterrupt` or `SystemExit` into swallowed recoverable failures.
- Do not collapse the subprocess boundary back into an in-process happy path.
- Meta-mode requests require the extra audit/database wiring; missing wiring must refuse cleanly, not degrade silently.

#### Dependencies
- `mir.core.contracts.discord_event.DiscordEvent`
- `mir.core.engine.audit_log.AuditLog`
- `mir.core.engine.memory.store`
- `mir.core.conductor.normal_mode`
- `mir.core.conductor.meta_mode`

#### Downstream Users
- Discord adapter and future external transport adapters
- Demo and smoke paths that call `mir conductor-dispatch`
- Tests that pin the stdio IPC outcome shape

#### Composition
- `src/mir/core/conductor/**`
- `src/mir/cli/conductor_dispatch.py`
- reporter and ingress outcome serialization

#### Orchestration
External event -> `handle_discord_event` -> normal/meta branch -> `TaskSpec` draft or refusal -> serialized outcome returned to the transport boundary.

#### Validation
- `uv run pytest -q tests/test_cli_conductor_dispatch.py tests/test_demo_m3.py`
- `uv run pytest -q tests/test_interface_registry_matrix.py`
- Typical TDD emphasis: `integration`, `e2e`, `architecture`, `availability`, `security`

### Bluebrick: Engine

#### Purpose
Compile drafted intent into an executable job, enforce policy and isolation gates, run the worker/reviewer loop, and own the execution-time control plane.

#### Public Interface
- `src/mir/core/engine/compiler.py::compile`
- `src/mir/core/engine/router.py`
- `src/mir/core/engine/workflow/spawn.py`
- `src/mir/core/engine/workflow/intent_verification.py::verify`
- memory, MCP, policy, and audit services consumed by higher layers

#### Internal Rules
- Compile is the last refusal gate before a worker spawns.
- `GateBlocked` with `STANDARD_CODES` stays the user-facing failure contract.
- Session minting and isolation checks happen before worker execution.
- Artifact sanitation runs before reviewer judgment.
- Reviewer/provider failures must normalize into explicit typed verdicts, not implicit PASS behavior.

#### Non-Obvious Hazards
- Do not skip `target_files` root confinement or SHA pin checks.
- Do not move required tool or provider allowlist validation out of compile.
- Do not let reviewer CLI contract drift; `codex exec --output-schema` requires a schema file path, not inline JSON.
- Do not weaken sanitizer-first ordering in intent verification.
- Do not turn async/sync provider boundaries into ad hoc mixed call paths.

#### Dependencies
- `mir.core.contracts.*`
- `mir.core.config.loader`
- `mir.core.engine.policy_store`
- `mir.core.engine.session_mint`
- `mir.core.registry`
- `mir.core.engine.memory.*`
- `mir.core.engine.mcp.*`

#### Downstream Users
- Conductor normal-mode flow
- Worker providers via compiled job dispatch
- Reviewer selection and workflow FSM paths
- Audit/memory-backed runtime checks

#### Composition
- `src/mir/core/engine/**`
- registries and workflow helpers
- policy, memory, audit, and MCP integration points

#### Orchestration
`TaskSpec` -> compile -> policy/isolation/session plan -> worker dispatch -> artifact sanitize -> reviewer verdict -> workflow FSM decides pass/retry/escalate.

#### Validation
- `uv run pytest -q tests/test_phase_gate_completion.py tests/test_spawn.py tests/test_live_codex_reviewer.py`
- `uv run pytest -q tests/test_circuit_breaker.py tests/test_sanitize.py tests/test_predicates.py`
- `uv run mypy src/mir`
- Typical TDD emphasis: `unit`, `integration`, `edge`, `architecture`, `availability`, `compatibility`, `transaction_locking`

### Bluebrick: Worker

#### Purpose
Provide runtime-specific execution adapters for Claude Code, Codex, and future CLIs while keeping the Engine-facing contract stable.

#### Public Interface
- `src/mir/core/worker/mir_provider_adapter.py::MirProviderAdapter`
- `src/mir/core/worker/provider_base.py`
- `src/mir/core/worker/providers/claude_code.py`
- `src/mir/core/worker/providers/codex.py`

#### Internal Rules
- Engine talks to Worker through synchronous `dispatch(CompiledJob) -> ProviderResult`.
- Provider-specific argv/env assembly stays inside the provider.
- Prompt payloads travel over stdin for Codex worker and reviewer paths unless a provider contract explicitly requires otherwise.
- Environment exposure is allowlist-based and must preserve real-user HOME injection through the loader sanitizer.

#### Non-Obvious Hazards
- Do not make `dispatch` async; the async boundary is intentionally one layer higher.
- Do not leak secrets by widening the provider env allowlist casually.
- Do not move prompt text into argv; it increases shell history and process-list exposure.
- Do not assume Codex and Claude providers share identical flag contracts.

#### Dependencies
- `mir.core.contracts.compiled_job.CompiledJob`
- `mir.core.contracts.provider_result.ProviderResult`
- `mir.core.config.loader.sanitize_env`
- provider-specific CLI binaries on PATH

#### Downstream Users
- Engine workflow spawn/collect
- Provider sync-contract and live reviewer/provider tests
- Registry-backed provider selection

#### Composition
- `src/mir/core/worker/**`
- provider adapters and shared base contracts

#### Orchestration
Engine compiles a job -> selected provider builds argv/env -> subprocess executes under sandbox/policy controls -> normalized `ProviderResult` returns to Engine.

#### Validation
- `uv run pytest -q tests/test_codex_provider.py tests/test_provider_sync_contract.py tests/test_live_codex_reviewer.py`
- `uv run pytest -q tests/test_interface_registry_matrix.py`
- Typical TDD emphasis: `unit`, `integration`, `edge`, `availability`, `security`, `load`, `soak`

### Bluebrick: Harness Runtime

#### Purpose
Define the durable human/agent operating contract: startup context, skills, hooks, generated Codex mirrors, deny-list enforcement, and session continuity.

#### Public Interface
- `CLAUDE.md`
- `AGENTS.md` generated mirror
- `.claude/hooks/*`
- `.claude/skills/*`
- `.ai-harness/*.md` and `.ai-harness/deny-list.yaml`
- `scripts/generate_codex_derivatives.sh`

#### Internal Rules
- Source of truth lives in `CLAUDE.md`, `.claude/agents/*`, and `.claude/skills/*`.
- Generated Codex mirrors must be regenerated, not hand-edited.
- Startup context, closeout, and guardrail behavior must match the documented harness contract.
- Root guidance stays short; durable detail belongs under `.ai-harness/`.

#### Non-Obvious Hazards
- Do not patch `AGENTS.md`, `.agents/`, or `.codex/` by hand.
- Do not leave deny-list as documentation-only policy; hook enforcement must stay wired.
- Do not let SessionStart/PreCompact/SessionEnd behavior drift from the runtime docs.
- Do not bloat root files with per-module detail that belongs in durable harness docs.

#### Dependencies
- Claude hook runtime
- Codex derivative generator
- `jq`, shell utilities, and repo-local policy docs
- task trackers under `tasks/`

#### Downstream Users
- Claude Code sessions
- Codex sessions through generated mirrors
- review/runner/handoff workflows
- future family generators that reuse this harness pattern

#### Composition
- `CLAUDE.md`, `AGENTS.md`
- `.claude/**`, `.agents/**`, `.codex/**`
- `.ai-harness/**`
- `tasks/**`
- `scripts/generate_codex_derivatives.sh`

#### Orchestration
Session start -> startup context load -> skill-triggered execution -> hook guardrails on tool use/edit -> validation/closeout -> regenerated Codex mirrors when source changes.

#### Validation
- `./scripts/generate_codex_derivatives.sh`
- `uv run pytest -q tests/test_codex_derivation_script.py tests/test_hook_scripts.py`
- `uv run ruff check src tests`

## Agent Rule

Before making non-trivial code changes, identify the affected bluebrick and check:

- hazards
- dependencies
- downstream users
- validation method
