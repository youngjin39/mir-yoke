# Bluebrick: Engine

## Purpose
Compile drafted intent into an executable job, enforce policy and isolation gates, run the worker/reviewer loop, and own the execution-time control plane.

## Public Interface
- `src/mir/core/engine/compiler.py::compile`
- `src/mir/core/engine/router.py`
- `src/mir/core/engine/workflow/spawn.py`
- `src/mir/core/engine/workflow/intent_verification.py::verify`
- memory, MCP, policy, and audit services consumed by higher layers

## Internal Rules
- Compile is the last refusal gate before a worker spawns.
- `GateBlocked` with `STANDARD_CODES` stays the user-facing failure contract.
- Session minting and isolation checks happen before worker execution.
- Artifact sanitation runs before reviewer judgment.
- Reviewer/provider failures must normalize into explicit typed verdicts, not implicit PASS behavior.

## Non-Obvious Hazards
- Do not skip `target_files` root confinement or SHA pin checks.
- Do not move required tool or provider allowlist validation out of compile.
- Do not let reviewer transport contracts drift; Codex-backed review must use MCP/native routing, not raw `codex exec`.
- Do not weaken sanitizer-first ordering in intent verification.
- Do not turn async/sync provider boundaries into ad hoc mixed call paths.

## Dependencies
- `mir.core.contracts.*`
- `mir.core.config.loader`
- `mir.core.engine.policy_store`
- `mir.core.engine.session_mint`
- `mir.core.registry`
- `mir.core.engine.memory.*`
- `mir.core.engine.mcp.*`

## Downstream Users
- Conductor normal-mode flow
- Worker providers via compiled job dispatch
- Reviewer selection and workflow FSM paths
- Audit/memory-backed runtime checks

## Composition
- `src/mir/core/engine/**`
- registries and workflow helpers
- policy, memory, audit, and MCP integration points

## Orchestration
`TaskSpec` -> compile -> policy/isolation/session plan -> worker dispatch -> artifact sanitize -> reviewer verdict -> workflow FSM decides pass/retry/escalate.

## Validation
- `uv run pytest -q tests/test_phase_gate_completion.py tests/test_spawn.py tests/test_live_codex_reviewer.py`
- `uv run pytest -q tests/test_circuit_breaker.py tests/test_sanitize.py tests/test_predicates.py`
- `uv run mypy src/mir`
- Typical TDD emphasis: `unit`, `integration`, `edge`, `architecture`, `availability`, `compatibility`, `transaction_locking`
