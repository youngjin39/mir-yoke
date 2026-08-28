<!-- GENERATED FILE: edit config/project-hooks.json or scripts/generate_codex_derivatives.sh and regenerate. -->

# Codex runtime

`.codex/hooks.json` is generated from `config/project-hooks.json`. The same definition renders
Claude and Codex registrations, while runtime-specific events and timeout limits remain explicit.

## Trust boundary

Project-local Codex configuration loads only after the project is trusted. Non-managed hooks also
require review of their current hash before they run. Use `/hooks` to inspect sources and trust or
disable each hook. Until both trust steps are complete, hook-based safety and continuity behavior is
inactive; repository instructions and explicit verification remain authoritative.

## Permission boundary

The generated root configuration does not select `sandbox_mode`, `sandbox_workspace_write`, or
`default_permissions`. Legacy sandbox settings and permission profiles do not compose, so the
operator's user-level or managed configuration remains authoritative. Write-capable generated
agents inherit that selection; mechanically read-only reviewers retain `sandbox_mode = "read-only"`.

## Maintained events

`PreToolUse`, `PermissionRequest`, `PostToolUse`, `SessionStart`, `PreCompact`,
`PostCompact`, `Stop`, and `SessionEnd` are generated for Codex. Maintainer `SessionEnd`
uses Codex's three-second limit. `UserPromptSubmit` and `StopFailure` remain Claude-only by
repository policy; the compact-only Project Agent Kit template intentionally ships only its compact
lifecycle.

## Wire format

Shared adapters parse `tool_name` and `tool_input`. Current Codex `apply_patch` sends the
unified patch in `tool_input.command`; maintained adapters accept that field first and retain older
`input`, `patch`, and `content` fallbacks for compatible runtimes.

Regenerate with `scripts/generate_codex_derivatives.sh`. Do not edit generated Codex files directly.
