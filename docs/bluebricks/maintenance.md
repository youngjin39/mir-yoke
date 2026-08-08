# Bluebrick: Maintenance

## Purpose

Classify, validate, sanitize, and prepare the public template for release.

## Public Interface

`config/template-assets.json`, harness consistency, generated-surface checks, CI, and
`scripts/verify_release_readiness.py`.

## Rules and Hazards

Every candidate file receives exactly one asset classification. A missing check is a release
failure. Release validation operates on Mir Yoke only and sends no fleet notification.

## Dependencies and Validation

Depends on all bluebricks. Validate with asset classification, public surface, full tests, lint,
and clean candidate-tree readiness.
