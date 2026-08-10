# Mir Yoke Minimal Template Architecture

## Product boundary

Mir Yoke is a public, agent-guided template and reference repository, not a universal installer.
It has no provider runtime and no standing authority over consumer repositories. `starter/` is the
only supported consumer payload.

The supported payload is four Markdown files. It starts no agent, service, hook, target scan,
scheduler, or background process and does not require a CLI, plugin, memory database, spec system,
sub-agent, receipt, or platform-specific runtime.

## Supported flow

1. The active AI agent inspects the target repository and existing instructions without mutation.
2. It identifies local purpose, paths, authority, safety boundaries, and verification commands.
3. It adapts, merges, renames, or skips each starter file without overwriting repository-owned work.
4. It runs the target repository's own smallest relevant checks and reviews the final diff.

This is contextual composition, not installation. The target repository owns the result.

## Modules

- **Starter contract** — `starter/HARNESS.md` contains the generic operating contract.
- **Runtime bridges** — `starter/CLAUDE.md` and generated `starter/AGENTS.md` route two common agent
  clients to that one contract.
- **Adoption guide** — `starter/README.md` and `BOOTSTRAP.md` explain preservation-first adaptation.
- **Maintenance** — tests and generation checks keep the starter small and the bridges consistent.
- **Reference/history** — all remaining source, tools, examples, decisions, and specifications are
  optional maintainer or reference material outside supported consumer scope.

Dependencies point toward the Starter contract. Reference machinery cannot become a starter
prerequisite without a new explicit support-boundary decision.

## Data and deployment

The supported core stores no runtime data and has no deployment topology. Distribution is an
immutable Git tree; adoption is a later repository-local choice. Template version lag is not drift.

## Verification

`tests/test_minimal_starter.py` pins the four-file boundary, required contract sections, shared
Claude/Codex routing, and public scope wording. Existing maintainer checks continue to validate
classification, sanitization, and generated surfaces for the full repository.
