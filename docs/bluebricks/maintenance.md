# Bluebrick: Maintenance

## Purpose

Classify, validate, sanitize, and prepare the public template for release.

## Public Interface

`config/template-assets.json`, harness consistency, generated-surface checks, CI, and
`scripts/verify_release_readiness.py`.

## Rules and Hazards

Every candidate file receives exactly one asset classification. A missing check is a release
failure. Release validation operates on Mir Yoke only and sends no fleet notification. The
`adopter_payload_boundary` rule permits the exact Mir Yoke provider owner and rejects configured
provider/maintainer markers under a product Profile. The generated adopter payload binds every
release candidate file to one disposition and SHA-256 digest; Phase 2 slim may move only unchanged
entries classified for removal. Modified references are preserved as adopter-owned adaptations,
while provider markers fail closed. Provider-only validators are maintainer assets and cannot enter
an adopter pack. The tracked CLI constraints must equal a frozen production export of `uv.lock`.
The normal CI lane validates the core, planes, packs, deterministic distribution, composition,
derivatives, classification, and release metadata. The complete portable-bootstrap regression is
preserved as an explicit workflow-dispatch job. Its macOS and Linux Bash lanes separately prove
WSL follows Linux and that native-Windows CLI, PowerShell, and Bash entrypoints stop before
mutation; Mir Yoke does not claim a native-Windows ready-state CI lane.

## Dependencies and Validation

Depends on all bluebricks. Validate with asset classification, public surface, full tests, lint,
and clean candidate-tree readiness.
