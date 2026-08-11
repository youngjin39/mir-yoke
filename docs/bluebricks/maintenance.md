# Bluebrick: Maintenance

## Purpose

Classify, validate, sanitize, and prepare the Starter, standard Project Agent Kit, installed CLI,
portable plugins, and inert reference corpus for release.

## Public Interface

`config/template-assets.json`, harness consistency, generated-surface checks, CI, and
`scripts/verify_release_readiness.py`.

## Rules and Hazards

Every candidate file receives exactly one classification. `starter/` is the only fixed payload.
Only plugin packages and marketplace metadata may be optional consumer tools. The recipe is
guidance and never a copied payload. Installed CLI source remains provider code; generated targets
must not vendor it. ADR-82 files remain inert under their reference namespace with no active `yoke`.

A missing repository check is a release failure. Tag validation publishes a GitHub Release only
after repository readiness passes. It does not claim an actual generated-repository runtime run.
Separate Claude and Codex runs are post-release owner acceptance; the observer and verifier remain
available. Release validation changes no consumer, fleet, notification, or provider activation.

## Dependencies and Validation

Depends on all current bluebricks. Validate with recipe, Starter, installed-CLI and inert-reference
contracts, exhaustive classification, plugin isolation, public identity, sanitization, generated
parity, full tests, Ruff, clean candidate readiness, and idempotent GitHub Release publication.
