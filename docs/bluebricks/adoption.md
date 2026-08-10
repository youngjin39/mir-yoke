# Bluebrick: Adoption

## Purpose

Provide manual core adoption, preservation-first optional composition, and retained greenfield and
existing-repository bootstrap paths.

## Public Interface

`BOOTSTRAP.md`, `starter/`, `yoke plan|apply`, `mir bootstrap`, `mir bootstrap-adoption`, and receipt
schemas.

## Rules and Hazards

One explicit invocation owns one local root. The default flow adapts the four-file core manually.
Optional composition plans without mutation and rejects target conflicts. Existing-repository
assessment is read-only by
default; successful apply writes only the atomic machine-local receipt. Never reconstruct local
policy or specifications. Automated greenfield bootstrap supports macOS, Linux, and WSL. Native
Windows must stop before mutation and guide the agent to WSL or a non-ready reference adaptation.
A full Mir Yoke checkout is provider/maintainer source, not a new-project payload. New projects
should use the core archive or explicit composition and therefore do not inherit provider Git
history. The following Phase 1/2 behavior is preserved for existing users and regression evidence;
it is not the default. Before Phase 1, no effective Git push URL may target the provider; the agent owns remote
handoff and Mir Yoke never mutates Git history or remotes. Greenfield Phase 1 installs the exact
commit from the tracked capability lock into a project-specific external CLI runtime, applies the
tracked production dependency constraints, resets only exact release-matched provider
contracts/tasks, and removes nothing. Passing Phase 2 finalize is the only automatic slim
boundary: it journals and moves exact hash-matched provider
files to an ignored recovery quarantine, validates the remaining tree with the external CLI, rolls
back on any verification or receipt-publication failure, and commits only after the ready receipt
is durable. Startup recovery resolves an interrupted journal before any new transaction. R20
blocks product work until that succeeds.

## Dependencies and Validation

Depends on Contract and Composition. Validate core preservation, plan/apply boundaries, external
CLI isolation, native-Windows fail-before-mutation, symlink
and concurrent-change rejection, Git push ownership, crash recovery, receipt-failure rollback,
bootstrap, and the
separate receipt-only existing-repository adoption path.
