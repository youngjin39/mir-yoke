# Bluebrick: Contract

## Purpose

Define Mir Yoke as a public template and reference repository with no provider runtime or standing
consumer authority.

## Public Interface

`README.md`, `CLAUDE.md`, `ARCHITECTURE.md`, ADR-78, and the public decision index.

## Rules and Hazards

Consumer repositories remain authoritative. Do not reintroduce target discovery, rollout,
cross-repository writes, or hash conformance. Edit `CLAUDE.md` before generated `AGENTS.md`.

## Dependencies and Validation

Contract is the stable dependency of every other bluebrick. Validate with
`tests/test_public_template_identity.py` and `tests/test_decision_authority.py`.
