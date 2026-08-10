# Mir Yoke Minimal Starter

This directory is the only supported consumer payload in Mir Yoke. It is intentionally a small,
documentation-only baseline that an AI agent adapts to the repository it has actually opened.

## Use it

1. Ask the agent to inspect the target repository before changing anything.
2. Give the agent this directory as reference material, not as overwrite authority.
3. Let it keep, merge, rename, or skip each file according to existing repository instructions.
4. Replace every `{{...}}` placeholder in `HARNESS.md` with observed project facts or an explicit
   owner decision.
5. Run the target repository's smallest relevant verification and inspect the final diff.

For a new empty repository, the four files may be placed at the repository root. For an existing
repository, do not recursively copy them over local instructions. Merge only the missing rules.

## What the starter contains

- `HARNESS.md` — the repository-owned operating contract and single source of truth.
- `CLAUDE.md` — a thin Claude entrypoint that routes to `HARNESS.md`.
- `AGENTS.md` — the generated Codex entrypoint for the same contract.
- `README.md` — this adoption guide.

Mir Yoke generates `AGENTS.md` while publishing the template. After adoption it is a local,
repository-owned bridge; `HARNESS.md` remains canonical and no Mir Yoke generator is required.

The starter does not install or require a CLI, plugin, hook, memory database, specification system,
sub-agent, daemon, or service. Those may be added later only when the target repository has a
concrete need and its owner accepts the extra maintenance surface.

## Completion check

- Existing repository instructions and local changes are preserved.
- `HARNESS.md` describes the actual project rather than Mir Yoke.
- No `{{...}}` placeholder remains.
- Protected paths and verification commands are accurate.
- The final diff contains only the selected harness files.
