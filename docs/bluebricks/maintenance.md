# Bluebrick: Maintenance

## Purpose

Classify, validate, sanitize, and prepare the Starter, Project Agent Kit recipe, portable plugins,
and reference corpus for release.

## Public Interface

`config/template-assets.json`, harness consistency, generated-surface checks, CI, and
`scripts/verify_release_readiness.py`.

## Rules and Hazards

Every candidate file receives exactly one classification. `starter/` is the only consumer payload.
Only plugin packages and marketplace metadata may be optional consumer tools. The recipe is
reference guidance and never a copied payload. Source, CLI, hook, bootstrap, spec, and executor code
remain maintainer or reference material.

A missing check is a release failure. Static tests prove the contract; one-prompt reproducibility
requires separate clean-room Claude and Codex runs against empty targets. Release validation changes
no consumer, remote, fleet, notification, provider activation, or protected capability lock.

## Dependencies and Validation

Depends on all current bluebricks. Validate with recipe and Starter contracts, exhaustive asset
classification, plugin isolation, public identity, sanitization, generated parity, full tests, Ruff,
and clean candidate-tree readiness.
