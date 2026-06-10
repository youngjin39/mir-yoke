# Bluebrick: Conductor

## Purpose
Accept external task requests, classify ingress mode, preserve an audit trail, and hand normal-mode work to Engine without leaking transport-specific concerns into execution code.

## Public Interface
- `src/mir/core/conductor/ingress.py::handle_discord_event`
- `src/mir/core/conductor/reporter.py::ConductorReporter`
- `src/mir/cli/conductor_dispatch.py::main`
- `mir conductor-dispatch` stdio JSON boundary

## Internal Rules
- Keep ingress as the top-level recoverable exception boundary.
- Record the inbound fingerprint before branch handling.
- Keep meta-mode and normal-mode dispatch separated.
- Preserve the subprocess IPC contract: stdin one JSON object, stdout one JSON result object.

## Non-Obvious Hazards
- Do not bypass `ConductorReporter` by returning raw exceptions to the caller.
- Do not turn `KeyboardInterrupt` or `SystemExit` into swallowed recoverable failures.
- Do not collapse the subprocess boundary back into an in-process happy path.
- Meta-mode requests require the extra audit/database wiring; missing wiring must refuse cleanly, not degrade silently.

## Dependencies
- `mir.core.contracts.discord_event.DiscordEvent`
- `mir.core.engine.audit_log.AuditLog`
- `mir.core.engine.memory.store`
- `mir.core.conductor.normal_mode`
- `mir.core.conductor.meta_mode`

## Downstream Users
- Discord adapter and future external transport adapters
- Demo and smoke paths that call `mir conductor-dispatch`
- Tests that pin the stdio IPC outcome shape

## Composition
- `src/mir/core/conductor/**`
- `src/mir/cli/conductor_dispatch.py`
- reporter and ingress outcome serialization

## Orchestration
External event -> `handle_discord_event` -> normal/meta branch -> `TaskSpec` draft or refusal -> serialized outcome returned to the transport boundary.

## Validation
- `uv run pytest -q tests/test_cli_conductor_dispatch.py tests/test_demo_m3.py`
- `uv run pytest -q tests/test_interface_registry_matrix.py`
- Typical TDD emphasis: `integration`, `e2e`, `architecture`, `availability`, `security`