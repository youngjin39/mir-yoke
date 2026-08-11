# Bluebrick: Agent-Guided Adoption

## Purpose

Provide a preservation-first Minimal Starter flow and a separate empty-target Project Agent Kit
recipe without provider-side target mutation.

## Public Interface

`starter/`, `BOOTSTRAP.md`, `recipes/project-agent-kit/`, and the short prompt in `README.md`.

## Rules and Hazards

One explicit invocation owns one target root. Existing repositories use Starter comparison and
preserve local contracts. The Project Agent Kit requires an empty target outside every existing Git
worktree, validates identity and toolchain before mutation, generates project-owned Claude and Codex
surfaces, installs a tracked local Git hook, verifies real checks, creates one initial commit, and
stops before planning or implementation.

Mir Yoke remains read-only. Never discover targets, copy provider history, create provider state,
write receipts, configure remotes, push, or reconstruct repository policy. Missing toolchain,
identity, signing compatibility, or consequential intent is a blocker rather than permission to
write a partial kit or weaken a gate.

## Dependencies and Validation

Depends on Contract and portable plugin non-authority. Validate prompt routing, four-file Starter
scope, target confinement, generated parity, read-only reviewer enforcement, real lint/build/test
commands, Git-hook activation, initial commit, and planning stop.
