# Bluebrick: Worker

## Purpose
Provide runtime-specific execution adapters for Claude Code, Codex, and future CLIs while keeping the Engine-facing contract stable.

## Public Interface
- `src/mir/core/worker/mir_provider_adapter.py::MirProviderAdapter`
- `src/mir/core/worker/provider_base.py`
- `src/mir/core/worker/providers/claude_code.py`
- `src/mir/core/worker/providers/codex.py`

## Internal Rules
- Engine talks to Worker through synchronous `dispatch(CompiledJob) -> ProviderResult`.
- Provider-specific argv/env assembly stays inside the provider.
- Prompt payloads travel over stdin for Codex worker and reviewer paths unless a provider contract explicitly requires otherwise.
- Environment exposure is allowlist-based and must preserve real-user HOME injection through the loader sanitizer.

## Non-Obvious Hazards
- Do not make `dispatch` async; the async boundary is intentionally one layer higher.
- Do not leak secrets by widening the provider env allowlist casually.
- Do not move prompt text into argv; it increases shell history and process-list exposure.
- Do not assume Codex and Claude providers share identical flag contracts.

## Dependencies
- `mir.core.contracts.compiled_job.CompiledJob`
- `mir.core.contracts.provider_result.ProviderResult`
- `mir.core.config.loader.sanitize_env`
- provider-specific CLI binaries on PATH

## Downstream Users
- Engine workflow spawn/collect
- Provider sync-contract and live reviewer/provider tests
- Registry-backed provider selection

## Composition
- `src/mir/core/worker/**`
- provider adapters and shared base contracts

## Orchestration
Engine compiles a job -> selected provider builds argv/env -> subprocess executes under sandbox/policy controls -> normalized `ProviderResult` returns to Engine.

## Validation
- `uv run pytest -q tests/test_codex_provider.py tests/test_provider_sync_contract.py tests/test_live_codex_reviewer.py`
- `uv run pytest -q tests/test_interface_registry_matrix.py`
- Typical TDD emphasis: `unit`, `integration`, `edge`, `availability`, `security`, `load`, `soak`