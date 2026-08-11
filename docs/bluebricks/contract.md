# Bluebrick: Contract

## Purpose

Define Mir Yoke's three layers: four-file Starter compatibility, the standard Project Agent Kit,
and the optional installed v0.8-compatible `mir` CLI, all with no provider runtime or standing
consumer authority.

## Public Interface

`README.md`, `CLAUDE.md`, `ARCHITECTURE.md`, ADR-83, ADR-81, ADR-74, and the public decision index.

## Rules and Hazards

Consumer repositories remain authoritative. Installing the CLI or preserving reference files does
not authorize target discovery, rollout, cross-repository writes, or hash conformance. The standard
Kit creates project-owned harness and memory files but copies no Mir runtime source. Edit
`CLAUDE.md` before generated `AGENTS.md`.

## Dependencies and Validation

Contract is the stable dependency of every other bluebrick. Validate with
`tests/test_public_template_identity.py` and `tests/test_decision_authority.py`.
